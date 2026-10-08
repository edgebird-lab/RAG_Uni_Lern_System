package de.edgebird.lernsystem.ingest

import de.edgebird.lernsystem.core.i18n.tr

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.pdf.PdfRenderer
import android.media.ExifInterface
import android.os.ParcelFileDescriptor
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import de.edgebird.lernsystem.core.ingest.Block
import de.edgebird.lernsystem.core.ingest.LoadedDoc
import de.edgebird.lernsystem.core.ingest.OcrText
import de.edgebird.lernsystem.core.ingest.TextNormalizer
import java.io.File
import java.io.InputStream

/** Texterkennung für ein Bild (blockierend, auf einem IO-Thread aufrufen). */
interface TextRecognizer {
    fun recognize(bitmap: Bitmap): String
}

/** Texterkennung mit ML Kit (lateinische Schrift, Modell ist in der App enthalten, es braucht kein Netz). */
class MlKitTextRecognizer : TextRecognizer, AutoCloseable {
    private val client by lazy { TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS) }

    override fun recognize(bitmap: Bitmap): String {
        val result = Tasks.await(client.process(InputImage.fromBitmap(bitmap, 0)))
        return OcrText.joinBlocks(result.textBlocks.map { b -> b.lines.map { it.text } })
    }

    override fun close() { client.close() }
}

/** Bilder laden: verkleinern (Speicher), nach EXIF-Ausrichtung drehen. */
object ImageDecoder {
    const val MAX_EDGE = 3000

    fun decode(open: () -> InputStream, maxEdge: Int = MAX_EDGE): Bitmap {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        open().use { BitmapFactory.decodeStream(it, null, bounds) }
        require(bounds.outWidth > 0 && bounds.outHeight > 0) { tr("Das Bild konnte nicht gelesen werden", "The image could not be read") }
        var sample = 1
        while (maxOf(bounds.outWidth, bounds.outHeight) / sample > maxEdge * 2) sample *= 2
        val raw = open().use { BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inSampleSize = sample }) } ?: error("Das Bild konnte nicht gelesen werden")
        val rotation = runCatching { open().use { ExifInterface(it).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL) } }.getOrDefault(ExifInterface.ORIENTATION_NORMAL)
        val matrix = Matrix()
        when (rotation) {
            ExifInterface.ORIENTATION_ROTATE_90 -> matrix.postRotate(90f)
            ExifInterface.ORIENTATION_ROTATE_180 -> matrix.postRotate(180f)
            ExifInterface.ORIENTATION_ROTATE_270 -> matrix.postRotate(270f)
            else -> Unit
        }
        val scale = maxEdge.toFloat() / maxOf(raw.width, raw.height)
        if (scale < 1f) matrix.postScale(scale, scale)
        if (matrix.isIdentity) return raw
        return Bitmap.createBitmap(raw, 0, 0, raw.width, raw.height, matrix, true).also { if (it !== raw) raw.recycle() }
    }
}

/** Fotos und Screenshots (jpg, png, webp): Der Text wird erkannt und wie eine einseitige Seite importiert. */
class ImageDocumentLoader(private val recognizer: TextRecognizer) : DocumentLoader {
    override val extensions = setOf("jpg", "jpeg", "png", "webp")

    override fun load(source: DocumentSource): LoadedDoc {
        val bitmap = try { ImageDecoder.decode(source.open) } catch (e: Exception) { throw LoadException(tr("Das Bild konnte nicht gelesen werden: ${e.message}", "The image could not be read: ${e.message}"), e) }
        val text = try { TextNormalizer.normalize(recognizer.recognize(bitmap)) } catch (e: Exception) { throw LoadException(tr("Die Texterkennung ist fehlgeschlagen: ${e.message}", "Text recognition failed: ${e.message}"), e) } finally { bitmap.recycle() }
        if (text.isBlank()) return LoadedDoc(text = "", blocks = emptyList(), emptyPages = 1)
        return LoadedDoc(text = text, blocks = listOf(Block(text, page = 1)))
    }
}

/** Rendert Seiten eines PDFs als Bild (für die Texterkennung gescannter Seiten). */
internal class PdfPageRenderer(context: Context, bytes: ByteArray) : AutoCloseable {
    private val file = File.createTempFile("ocr", ".pdf", context.cacheDir).also { it.writeBytes(bytes) }
    private val renderer = PdfRenderer(ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY))

    fun render(index: Int, targetWidth: Int = 1800): Bitmap = renderer.openPage(index).use { page ->
        val scale = targetWidth.toFloat() / page.width
        val bmp = Bitmap.createBitmap(targetWidth, (page.height * scale).toInt().coerceAtLeast(1), Bitmap.Config.ARGB_8888)
        Canvas(bmp).drawPaint(Paint().apply { color = android.graphics.Color.WHITE })   // PdfRenderer zeichnet nur auf einen weißen Untergrund sauber
        page.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
        bmp
    }

    override fun close() { runCatching { renderer.close() }; file.delete() }
}

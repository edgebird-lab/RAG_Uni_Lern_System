package de.edgebird.lernsystem.ingest

import de.edgebird.lernsystem.core.i18n.tr

import android.content.Context
import de.edgebird.lernsystem.core.ingest.Block
import de.edgebird.lernsystem.core.ingest.LoadedDoc
import de.edgebird.lernsystem.core.ingest.OcrText
import de.edgebird.lernsystem.core.ingest.TextNormalizer
import io.legere.pdfiumandroid.PdfiumCore
import java.io.InputStream

/** Eine einzulesende Quelle. `key` ist der eindeutige Schlüssel (z. B. Content-URI), `displayName` der Dateiname. */
class DocumentSource(val key: String, val displayName: String, val open: () -> InputStream) {
    val extension: String get() = displayName.substringAfterLast('.', "").lowercase()
}

class LoadException(message: String, cause: Throwable? = null) : Exception(message, cause)

interface DocumentLoader {
    val extensions: Set<String>

    /** Blockierend; vom Aufrufer auf einem IO-Dispatcher auszuführen. */
    fun load(source: DocumentSource): LoadedDoc
}

/** .txt, .md, .markdown (UTF-8, mit Fallback auf ISO-8859-1). */
class TextDocumentLoader : DocumentLoader {
    override val extensions = setOf("txt", "md", "markdown")

    override fun load(source: DocumentSource): LoadedDoc {
        val bytes = source.open().use { it.readBytes() }
        val raw = decode(bytes)
        // Foto-Dokumente enthalten Seitenwechsel (Form Feed): daraus werden Seiten mit Nummern
        if (OcrText.PAGE_BREAK in raw) {
            val pages = raw.split(OcrText.PAGE_BREAK)
            val blocks = pages.mapIndexedNotNull { i, p -> TextNormalizer.normalize(p).takeIf { it.isNotBlank() }?.let { Block(it, page = i + 1) } }
            return LoadedDoc(text = blocks.joinToString("\n\n") { it.text }, blocks = blocks, emptyPages = pages.count { it.isBlank() })
        }
        val text = TextNormalizer.normalize(raw)
        return LoadedDoc(text = text, blocks = listOf(Block(text)), isMarkdown = source.extension != "txt")
    }

    private fun decode(bytes: ByteArray): String {
        val utf8 = Charsets.UTF_8.newDecoder()
            .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
            .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT)
        return try {
            utf8.decode(java.nio.ByteBuffer.wrap(bytes)).toString().removePrefix("\uFEFF")
        } catch (e: java.nio.charset.CharacterCodingException) {
            String(bytes, Charsets.ISO_8859_1)
        }
    }
}

/** PDF mit Text-Ebene (PDFium). Seiten ohne Text (Scans) werden, wenn eine Texterkennung vorhanden ist, per OCR gelesen (höchstens [maxOcrPages] je Dokument). */
class PdfDocumentLoader(private val context: Context, private val recognizer: TextRecognizer? = null, private val maxOcrPages: Int = 80) : DocumentLoader {
    override val extensions = setOf("pdf")

    override fun load(source: DocumentSource): LoadedDoc {
        val bytes = source.open().use { it.readBytes() }
        val blocks = mutableListOf<Block>()
        var empty = 0
        var ocrBudget = maxOcrPages
        val ocr = recognizer
        val renderer by lazy { PdfPageRenderer(context, bytes) }
        try {
            PdfiumCore(context).newDocument(bytes).use { doc ->
                for (i in 0 until doc.getPageCount()) {
                    val text = doc.openPage(i)?.use { page ->
                        page.openTextPage()?.use { tp ->
                            val n = tp.textPageCountChars()
                            if (n > 0) tp.textPageGetText(0, n).orEmpty() else ""
                        }
                    }.orEmpty()
                    var normalized = TextNormalizer.normalize(stripPdfiumMarkers(text))
                    if (normalized.isBlank() && ocr != null && ocrBudget > 0) {
                        ocrBudget--
                        normalized = runCatching {
                            val bmp = renderer.render(i)
                            try { TextNormalizer.normalize(ocr.recognize(bmp)) } finally { bmp.recycle() }
                        }.getOrDefault("")
                    }
                    if (normalized.isBlank()) empty++ else blocks += Block(normalized, page = i + 1)
                }
            }
        } catch (e: Exception) {
            throw LoadException(tr("PDF konnte nicht gelesen werden: ${e.message}", "The PDF could not be read: ${e.message}"), e)
        } finally {
            if (ocrBudget < maxOcrPages) runCatching { renderer.close() }
        }
        return LoadedDoc(text = blocks.joinToString("\n\n") { it.text }, blocks = blocks, emptyPages = empty)
    }
}

/**
 * PDFium setzt an Stellen, an denen es eine Silbentrennung am Zeilenende selbst zusammengefügt hat, das Zeichen
 * U+FFFE (bzw. U+0002 in älteren Versionen). Diese Marker entfernen, dann steht das Wort wieder am Stück.
 */
internal fun stripPdfiumMarkers(text: String): String = text.filterNot { it == '\uFFFE' || it == '\uFFFF' || it == '\u0002' }

object Loaders {
    /** Mit Texterkennung für Fotos und gescannte PDFs (Modell ist in der App, kein Netz nötig). */
    fun default(context: Context, recognizer: TextRecognizer? = MlKitTextRecognizer()): List<DocumentLoader> =
        listOfNotNull(TextDocumentLoader(), PdfDocumentLoader(context, recognizer), recognizer?.let { ImageDocumentLoader(it) })
}

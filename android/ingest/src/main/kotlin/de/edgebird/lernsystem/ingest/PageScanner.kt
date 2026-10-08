package de.edgebird.lernsystem.ingest

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Matrix
import android.graphics.Paint
import de.edgebird.lernsystem.core.scan.DocumentCorners
import de.edgebird.lernsystem.core.scan.Pt
import java.io.File

/** Blatt auf einem Foto finden und entzerren (Perspektivkorrektur), alles auf dem Gerät. */
object PageScanner {
    private const val MAX_EDGE = 2400

    /** Bild verkleinert laden (für Anzeige und Erkennung), EXIF-Drehung berücksichtigt. */
    fun load(file: File, maxEdge: Int = 1600): Bitmap? = runCatching {
        val b = ImageDecoder.decode({ file.inputStream() })
        val k = maxEdge.toFloat() / maxOf(b.width, b.height)
        if (k >= 1f) b else Bitmap.createScaledBitmap(b, (b.width * k).toInt(), (b.height * k).toInt(), true).also { b.recycle() }
    }.getOrNull()

    /** Ecken des hellen Blatts oder, wenn nichts erkannt wird, ein Rahmen mit kleinem Rand. */
    fun detect(bmp: Bitmap): List<Pt> {
        val w = 160; val h = (160f * bmp.height / bmp.width).toInt().coerceAtLeast(1)
        val small = Bitmap.createScaledBitmap(bmp, w, h, true)
        val px = IntArray(w * h).also { small.getPixels(it, 0, w, 0, 0, w, h) }
        small.recycle()
        val gray = IntArray(px.size) { val c = px[it]; ((c shr 16 and 255) * 299 + (c shr 8 and 255) * 587 + (c and 255) * 114) / 1000 }
        return DocumentCorners.detect(gray, w, h) ?: listOf(Pt(0.04f, 0.04f), Pt(0.96f, 0.04f), Pt(0.96f, 0.96f), Pt(0.04f, 0.96f))
    }

    /** Schneidet das Viereck aus und entzerrt es zu einem Rechteck. */
    fun warp(src: Bitmap, q: List<Pt>): Bitmap {
        var (w, h) = DocumentCorners.outputSize(q, src.width, src.height)
        val k = MAX_EDGE.toFloat() / maxOf(w, h)
        if (k < 1f) { w = (w * k).toInt().coerceAtLeast(1); h = (h * k).toInt().coerceAtLeast(1) }
        val from = floatArrayOf(q[0].x * src.width, q[0].y * src.height, q[1].x * src.width, q[1].y * src.height, q[2].x * src.width, q[2].y * src.height, q[3].x * src.width, q[3].y * src.height)
        val to = floatArrayOf(0f, 0f, w.toFloat(), 0f, w.toFloat(), h.toFloat(), 0f, h.toFloat())
        val m = Matrix().apply { setPolyToPoly(from, 0, to, 0, 4) }
        val out = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        Canvas(out).drawBitmap(src, m, Paint(Paint.FILTER_BITMAP_FLAG))
        return out
    }

    /** Ersetzt die Bilddatei durch die zugeschnittene Fassung. */
    fun crop(file: File, q: List<Pt>): Boolean = runCatching {
        val src = load(file, MAX_EDGE) ?: return false
        val out = warp(src, q)
        src.recycle()
        file.outputStream().use { out.compress(Bitmap.CompressFormat.JPEG, 92, it) }
        out.recycle()
        true
    }.getOrDefault(false)
}

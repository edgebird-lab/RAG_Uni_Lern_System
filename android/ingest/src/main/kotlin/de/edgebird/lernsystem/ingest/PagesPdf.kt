// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ingest

import android.graphics.Bitmap
import android.graphics.pdf.PdfDocument
import java.io.File

/** Baut aus Fotoseiten ein PDF (Original eines Foto-Dokuments zum Ansehen, Teilen und Drucken). Jede Seite hat die Form ihres Bildes. */
object PagesPdf {
    private const val MAX_EDGE = 1800
    private const val PAGE_WIDTH_PT = 595   // A4-Breite in Punkten

    /** @return Zahl der geschriebenen Seiten; Seiten, die sich nicht lesen lassen, werden übersprungen. */
    fun build(pages: List<File>, out: File): Int {
        val pdf = PdfDocument()
        var n = 0
        try {
            for (f in pages) {
                val bmp = runCatching { ImageDecoder.decode({ f.inputStream() }) }.getOrNull() ?: continue
                try {
                    val k = MAX_EDGE.toFloat() / maxOf(bmp.width, bmp.height)
                    val scaled = if (k < 1f) Bitmap.createScaledBitmap(bmp, (bmp.width * k).toInt().coerceAtLeast(1), (bmp.height * k).toInt().coerceAtLeast(1), true) else bmp
                    val w = PAGE_WIDTH_PT; val h = (PAGE_WIDTH_PT * scaled.height.toFloat() / scaled.width).toInt().coerceAtLeast(1)
                    val page = pdf.startPage(PdfDocument.PageInfo.Builder(w, h, ++n).create())
                    page.canvas.drawBitmap(scaled, null, android.graphics.Rect(0, 0, w, h), null)
                    pdf.finishPage(page)
                    if (scaled !== bmp) scaled.recycle()
                } finally { bmp.recycle() }
            }
            if (n > 0) out.outputStream().use { pdf.writeTo(it) }
        } finally { pdf.close() }
        return n
    }
}

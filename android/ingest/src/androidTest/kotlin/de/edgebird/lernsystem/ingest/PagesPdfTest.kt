// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ingest

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class PagesPdfTest {
    private fun jpg(dir: File, name: String, w: Int, h: Int, color: Int): File {
        val b = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        Canvas(b).apply { drawColor(color); drawText("Seite", 40f, 80f, Paint().apply { textSize = 60f; this.color = Color.BLACK }) }
        return File(dir, name).also { f -> f.outputStream().use { b.compress(Bitmap.CompressFormat.JPEG, 90, it) } }
    }

    @Test fun buildsReadablePdfWithOnePagePerImage() {
        val dir = InstrumentationRegistry.getInstrumentation().targetContext.cacheDir
        val pages = listOf(jpg(dir, "pp1.jpg", 800, 1000, Color.WHITE), File(dir, "kaputt.jpg").also { it.writeText("kein Bild") }, jpg(dir, "pp2.jpg", 1200, 600, Color.LTGRAY))
        val out = File(dir, "pages.pdf")
        assertEquals(2, PagesPdf.build(pages, out))        // das kaputte Bild wird übersprungen
        ParcelFileDescriptor.open(out, ParcelFileDescriptor.MODE_READ_ONLY).use { pfd ->
            PdfRenderer(pfd).use { r ->
                assertEquals(2, r.pageCount)
                r.openPage(0).use { assertTrue(it.height > it.width) }     // Hochformat bleibt Hochformat
                r.openPage(1).use { assertTrue(it.width > it.height) }     // Querformat bleibt Querformat
            }
        }
        assertEquals(0, PagesPdf.build(listOf(File(dir, "kaputt.jpg")), File(dir, "leer.pdf")))
        pages.forEach { it.delete() }; out.delete()
    }
}

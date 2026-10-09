// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ingest

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class PageScannerTest {
    /** Dunkler Tisch, helles schiefes Blatt mit einer schwarzen Linie quer. */
    private fun photo(): Bitmap {
        val b = Bitmap.createBitmap(800, 1000, Bitmap.Config.ARGB_8888)
        val c = Canvas(b)
        c.drawColor(Color.rgb(50, 40, 30))
        val p = Path().apply { moveTo(180f, 120f); lineTo(650f, 170f); lineTo(700f, 880f); lineTo(120f, 900f); close() }
        c.drawPath(p, Paint().apply { color = Color.rgb(240, 240, 235); isAntiAlias = true })
        return b
    }

    @Test fun detectsPageCorners() {
        val q = PageScanner.detect(photo())
        assertEquals(180f / 800, q[0].x, 0.03f); assertEquals(120f / 1000, q[0].y, 0.03f)
        assertEquals(650f / 800, q[1].x, 0.03f)
        assertEquals(700f / 800, q[2].x, 0.03f); assertEquals(880f / 1000, q[2].y, 0.03f)
        assertEquals(120f / 800, q[3].x, 0.03f)
    }

    @Test fun cropReplacesFileWithStraightPage() {
        val f = File(InstrumentationRegistry.getInstrumentation().targetContext.cacheDir, "scan-test.jpg")
        f.outputStream().use { photo().compress(Bitmap.CompressFormat.JPEG, 90, it) }
        val q = PageScanner.detect(photo())
        assertTrue(PageScanner.crop(f, q))
        val out = android.graphics.BitmapFactory.decodeFile(f.absolutePath)
        // Ergebnis ist fast ganz hell (nur das Blatt), also kein dunkler Tisch mehr in der Bildmitte und am Rand
        val px = IntArray(out.width * out.height).also { out.getPixels(it, 0, out.width, 0, 0, out.width, out.height) }
        val dark = px.count { Color.red(it) < 120 }
        assertTrue("dunkler Anteil ${dark.toFloat() / px.size}", dark.toFloat() / px.size < 0.03f)
        assertTrue(out.width in 400..800 && out.height in 700..1000)
        f.delete()
    }
}

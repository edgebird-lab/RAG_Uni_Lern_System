package de.edgebird.lernsystem.core.scan

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class DocumentCornersTest {
    private fun image(w: Int, h: Int, bg: Int, fg: Int, inside: (Int, Int) -> Boolean) = IntArray(w * h) { if (inside(it % w, it / w)) fg else bg }

    @Test fun findsRectangle() {
        val w = 100; val h = 80
        val g = image(w, h, 40, 220) { x, y -> x in 20..79 && y in 10..69 }
        val q = DocumentCorners.detect(g, w, h)!!
        assertEquals(0.20f, q[0].x, 0.02f); assertEquals(0.125f, q[0].y, 0.02f)
        assertEquals(0.80f, q[1].x, 0.02f); assertEquals(0.875f, q[2].y, 0.02f)
        assertEquals(0.20f, q[3].x, 0.02f)
    }

    @Test fun findsSkewedQuad() {
        val w = 120; val h = 120
        // Trapez: oben schmal, unten breit
        val g = image(w, h, 30, 230) { x, y -> y in 15..104 && x >= 40 - (y - 15) / 4 && x <= 80 + (y - 15) / 4 }
        val q = DocumentCorners.detect(g, w, h)!!
        assertTrue(q[0].x > q[3].x, "oben links liegt weiter rechts als unten links")
        assertTrue(q[1].x < q[2].x)
        assertTrue(q[0].y < q[3].y)
    }

    @Test fun noContrastOrWholeImageGivesNull() {
        assertNull(DocumentCorners.detect(IntArray(50 * 50) { 128 }, 50, 50))
        assertNull(DocumentCorners.detect(image(50, 50, 40, 220) { x, y -> x in 1..48 && y in 1..48 }, 50, 50))
    }

    @Test fun tinyObjectGivesNull() {
        assertNull(DocumentCorners.detect(image(100, 100, 30, 230) { x, y -> x in 10..20 && y in 10..20 }, 100, 100))
    }

    @Test fun outputSizeFollowsEdges() {
        val q = listOf(Pt(0.2f, 0.1f), Pt(0.8f, 0.1f), Pt(0.8f, 0.9f), Pt(0.2f, 0.9f))
        val (w, h) = DocumentCorners.outputSize(q, 1000, 2000)
        assertEquals(600, w); assertEquals(1600, h)
        assertNotNull(q)
    }
}

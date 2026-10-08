package de.edgebird.lernsystem.core.summary

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class SummarySectionsTest {
    private fun text(n: Int, seed: String) = (seed + " ").repeat(n / (seed.length + 1) + 1).take(n)

    @Test
    fun `gleiche Fundstelle wird bis zum Budget zusammengefasst, Rest beginnt neu`() {
        val pieces = (1..4).map { SourcePiece("Kosten", text(1200, "Kosten$it")) }
        val s = SummarySections.build(pieces, budget = 3000, overlap = 0)
        assertEquals(2, s.size)
        assertTrue(s.all { it.title == "Kosten" })
        assertTrue(s.all { it.text.length <= 3000 + 10 })
    }

    @Test
    fun `Ueberlappung des Chunkers wird entfernt`() {
        val a = "A".repeat(100) + " " + "ende des ersten Chunks mit genug Text fuer die Ueberlappung hier drin."
        val tail = a.takeLast(60)
        val b = "$tail " + "Anfang des zweiten Chunks."
        val joined = SummarySections.joinWithoutOverlap(listOf(a, b), maxOverlap = 150)
        assertEquals(1, Regex(Regex.escape(tail)).findAll(joined).count(), joined)
        assertTrue(joined.endsWith("Anfang des zweiten Chunks."))
    }

    @Test
    fun `Header-Praefix des Chunkers wird entfernt`() {
        val s = SummarySections.build(listOf(SourcePiece("Teil › Kosten", "[Teil › Kosten]\n" + text(200, "Inhalt"))), budget = 3000)
        assertFalse(s.single().text.startsWith("["))
    }

    @Test
    fun `kurze Nachbarseiten werden zu einem Seitenbereich vereinigt`() {
        val pieces = listOf(SourcePiece("Seite 3", text(300, "a")), SourcePiece("Seite 4", text(300, "b")), SourcePiece("Seite 5", text(300, "c")))
        val s = SummarySections.build(pieces, budget = 3000)
        assertEquals(1, s.size)
        assertEquals("Seite 3–5", s.single().title)
    }

    @Test
    fun `lange Seiten bleiben getrennt`() {
        val pieces = listOf(SourcePiece("Seite 3", text(1500, "a")), SourcePiece("Seite 4", text(1500, "b")))
        assertEquals(listOf("Seite 3", "Seite 4"), SummarySections.build(pieces, budget = 3000).map { it.title })
    }

    @Test
    fun `leere Chunks werden ignoriert`() = assertTrue(SummarySections.build(listOf(SourcePiece("x", "  ")), 3000).isEmpty())

    @Test
    fun `Titel verschiedener Art werden mit Schraegstrich verbunden`() = assertEquals("Kosten / Erlöse", SummarySections.mergeTitles("Kosten", "Erlöse"))
}

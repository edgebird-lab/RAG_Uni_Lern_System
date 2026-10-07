package de.edgebird.lernsystem.core

import de.edgebird.lernsystem.core.rag.Citations
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class CitationsTest {
    @Test
    fun `einzelne und gruppierte Verweise`() {
        assertEquals(setOf(2), Citations.cited("Antwort [2].", 4))
        assertEquals(setOf(1, 3), Citations.cited("Das steht in [1, 3] und [3].", 4))
    }

    @Test
    fun `Nummern ausserhalb der Quellen werden ignoriert`() {
        assertEquals(setOf(1), Citations.cited("[1] [7] [0]", 4))
        assertEquals(emptySet<Int>(), Citations.cited("kein Verweis, aber Array[x]", 4))
    }

    @Test
    fun `Verweigerung wird auch mit Zusatz erkannt`() {
        assertTrue(Citations.isNotFound("Nicht im Material gefunden."))
        assertTrue(Citations.isNotFound("  nicht im   Material gefunden. Leider."))
        assertFalse(Citations.isNotFound("Die Antwort steht in [1]."))
    }

    @Test
    fun `kurze Rueckfrage bekommt die vorige Frage fuer die Suche`() {
        assertEquals("Wer ernennt den Kanzler? Und wer entlässt ihn?", Citations.retrievalQuery("Und wer entlässt ihn?", "Wer ernennt den Kanzler?"))
        val long = "Wie berechnet man die Herstellkosten je Stück bei der zweistufigen Divisionskalkulation?"
        assertEquals(long, Citations.retrievalQuery(long, "Wer ernennt den Kanzler?"))
        assertEquals("Und wer?", Citations.retrievalQuery("Und wer?", null))
    }
}

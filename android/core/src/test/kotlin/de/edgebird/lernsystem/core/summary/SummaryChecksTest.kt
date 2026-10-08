package de.edgebird.lernsystem.core.summary

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class SummaryChecksTest {
    @Test
    fun `abgeschnittene Antworten werden erkannt`() {
        assertTrue(SummaryChecks.looksTruncated("Das ist ein langer Satz, der mitten in einer Aufzählung endet und dann"  + ","))
        assertTrue(SummaryChecks.looksTruncated("Ein langer erster Punkt steht hier, der vollständig ist.\n-"))
        assertFalse(SummaryChecks.looksTruncated("Ein vollständiger Satz, der ordentlich mit einem Punkt endet und lang genug ist."))
        assertFalse(SummaryChecks.looksTruncated("kurz"))
        assertTrue(SummaryChecks.looksTruncated("Die Effizienz von Quicksort liegt darin, dass es Elemente vertauscht und dadurch sehr schnell wird, wobei..."))
        assertTrue(SummaryChecks.looksTruncated("Das Prinzip beinhaltet die Trennung der Liste in linke und rechte Teillisten anhand eines Pivotelements, gefolgt von der rekursiven Sortierung dieser"))
        assertFalse(SummaryChecks.looksTruncated("- Kurzer Punkt ohne Punkt am Ende\n- Noch ein kurzer Punkt ohne Satzzeichen am Ende der Liste hier"))
    }

    @Test
    fun `unvollstaendiger Schluss wird abgeschnitten`() {
        val absatz = "Quicksort ist ein schneller Sortieralgorithmus. Er arbeitet rekursiv und in place. Die Effizienz liegt darin, dass es Elemente..."
        assertEquals("Quicksort ist ein schneller Sortieralgorithmus. Er arbeitet rekursiv und in place.", SummaryChecks.trimIncomplete(absatz))
        val liste = "- Erster vollständiger Punkt steht hier und ist lang genug beschrieben.\n- Zweiter Punkt bricht mitten im Satz ab, weil das Token-Limit erreicht war und dann"
        assertEquals("- Erster vollständiger Punkt steht hier und ist lang genug beschrieben.", SummaryChecks.trimIncomplete(liste))
        val ok = "Ein vollständiger Satz, der ordentlich mit einem Punkt endet und lang genug ist."
        assertEquals(ok, SummaryChecks.trimIncomplete(ok))
    }

    @Test
    fun `Ellipse mitten im Text wird abgeschnitten, der Rest bleibt`() {
        val md = "Quicksort ist ein schneller Algorithmus. Er arbeitet rekursiv. Die Effizienz liegt darin, dass es Elemente...\n\n**Das Wichtigste:**\n- Punkt eins ist vollständig.\n- Punkt zwei auch."
        val expected = "Quicksort ist ein schneller Algorithmus. Er arbeitet rekursiv.\n\n**Das Wichtigste:**\n- Punkt eins ist vollständig.\n- Punkt zwei auch."
        assertEquals(expected, SummaryChecks.trimIncomplete(md))
        assertEquals("Ein vollständiger Text. Ohne Ellipse.", SummaryChecks.trimIncomplete("Ein vollständiger Text. Ohne Ellipse."))
    }

    @Test
    fun `leere Marker`() {
        assertTrue(SummaryChecks.isEmptySection(""))
        assertTrue(SummaryChecks.isEmptySection("(kein prüfungsrelevanter Inhalt)"))
        assertTrue(SummaryChecks.isEmptySection("(kein pruefungsrelevanter inhalt)."))
        assertFalse(SummaryChecks.isEmptySection("Inhalt"))
    }

    @Test
    fun `Zahlen aus dem Quelltext sind erlaubt`() {
        val source = "Die Frist beträgt 14 Tage. Der Betrag liegt bei 1.250,50 Euro und 3,5 Prozent."
        assertEquals(emptyList<String>(), SummaryChecks.unsupportedNumbers("Frist: 14 Tage; Betrag 1.250,50 Euro; Zins 3,5 %", source))
    }

    @Test
    fun `erfundene Zahlen werden gemeldet, Listenmarker und einstellige Zahlen nicht`() {
        val source = "Die Frist beträgt 14 Tage."
        val bad = SummaryChecks.unsupportedNumbers("1. Die Frist beträgt 30 Tage.\n2. Es gibt 3 Fälle und 1999 Beispiele.", source)
        assertEquals(listOf("30", "1999"), bad)
    }

    @Test
    fun `Tausenderpunkt und Dezimalkomma werden vereinheitlicht`() {
        assertEquals(emptyList<String>(), SummaryChecks.unsupportedNumbers("1250 Euro", "Betrag: 1.250 Euro"))
    }
}

package de.edgebird.lernsystem.ingest

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class PdfiumMarkersTest {
    @Test
    fun `Silbentrennungs-Marker werden entfernt`() {
        assertEquals("Divisionskalkulation", stripPdfiumMarkers("Divisions￾kalkulation"))
        assertEquals("Wort", stripPdfiumMarkers("Wo\u0002rt"))
    }
}

// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

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

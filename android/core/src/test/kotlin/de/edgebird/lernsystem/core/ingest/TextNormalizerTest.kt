// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.ingest

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class TextNormalizerTest {
    @Test
    fun `echte Silbentrennung wird zusammengefuegt`() {
        assertEquals("Entscheidung", TextNormalizer.normalize("Ent-\nscheidung"))
    }

    @Test
    fun `Zahlenbereiche und Komposita bleiben erhalten`() {
        assertEquals("2020-\n21", TextNormalizer.normalize("2020-\n21"))
        assertEquals("Nord-\nDeutschland", TextNormalizer.normalize("Nord-\nDeutschland"))
    }

    @Test
    fun `Unicode wird auf NFC gebracht`() {
        val decomposed = "über" // u + kombinierendes Trema
        assertEquals("über", TextNormalizer.normalize(decomposed))
    }

    @Test
    fun `Whitespace und Leerzeilen werden vereinheitlicht`() {
        assertEquals("a b\n\nc", TextNormalizer.normalize("a \t b\r\n\r\n\r\n\r\nc  "))
    }

    @Test
    fun `leere Eingabe`() = assertEquals("", TextNormalizer.normalize(""))
}

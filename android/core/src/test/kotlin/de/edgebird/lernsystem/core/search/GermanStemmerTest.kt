// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.search

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class GermanStemmerTest {
    @Test
    fun `typische Faelle`() {
        assertEquals("aufeinanderfolg", GermanStemmer.stem("aufeinanderfolgenden"))
        assertEquals("ergebnis", GermanStemmer.stem("ergebnisse"))
        assertEquals("bundesprasident", GermanStemmer.stem("bundespräsident"))
        assertEquals("haus", GermanStemmer.stem("häuser"))
        assertEquals("geniess", GermanStemmer.stem("genießen"))
    }

    @Test
    fun `Paritaet mit dem Python-Snowball-Stemmer`() {
        val lines = checkNotNull(javaClass.getResourceAsStream("/search/stems.tsv")).reader(Charsets.UTF_8).readLines()
        assertTrue(lines.size > 5000)
        val diffs = lines.mapNotNull { l ->
            val (w, expected) = l.split("\t")
            val actual = GermanStemmer.stem(w)
            if (actual != expected) "$w: erwartet $expected, war $actual" else null
        }
        assertTrue(diffs.isEmpty(), "${diffs.size} Abweichungen von ${lines.size}, z. B.:\n" + diffs.take(25).joinToString("\n"))
    }
}

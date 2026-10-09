// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.cards

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class AnkiExportTest {
    @Test
    fun `eine Zeile je Karte, Tabs und Zeilenumbrueche werden entschaerft`() {
        val tsv = AnkiExport.toTsv(listOf(AnkiExport.Row("Frage\tmit Tab?", "Zeile 1\nZeile 2", "Mein Skript")))
        assertEquals("Frage mit Tab?\tZeile 1<br>Zeile 2\tMein_Skript\n", tsv)
    }

    @Test
    fun `LaTeX wird fuer Anki ausgezeichnet`() {
        val tsv = AnkiExport.toTsv(listOf(AnkiExport.Row("Was ist \$x^2\$?", "\$\$a+b\$\$", null)))
        assertEquals("Was ist \\(x^2\\)?\t\\[a+b\\]\t\n", tsv)
    }

    @Test
    fun `leere Liste ergibt leeren Text`() = assertEquals("", AnkiExport.toTsv(emptyList()))
}

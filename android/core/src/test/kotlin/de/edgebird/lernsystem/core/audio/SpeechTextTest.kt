// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.audio

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test

class SpeechTextTest {
    @Test fun `Markdown, Quellenmarker und Abkuerzungen werden fuer die Sprache aufbereitet`() {
        val t = SpeechText.prepare("## Titel\n\n- Das ist **wichtig**, z. B. bei 5 % Zinsen [Quelle 2].\n- Siehe ca. 20 Min, d. h. bzw. usw.")
        assertTrue("zum Beispiel" in t && "5 Prozent" in t && "circa" in t && "das heißt" in t && "beziehungsweise" in t && "und so weiter" in t)
        assertFalse("**" in t || "Quelle" in t || "#" in t)
    }

    @Test fun `Saetze werden bis zur Obergrenze zusammengefasst, Absaetze bleiben getrennt mit laengerer Pause`() {
        val text = "Erster Satz. Zweiter Satz. Dritter Satz.\n\nNeuer Absatz hier."
        val c = SpeechText.chunks(text, max = 30)
        assertEquals(listOf("Erster Satz. Zweiter Satz.", "Dritter Satz.", "Neuer Absatz hier."), c.map { it.first })
        assertEquals(listOf(120, 450, 450), c.map { it.second })
    }

    @Test fun `ein sehr langer Satz wird an Kommas geteilt, nie ueber die Obergrenze`() {
        val long = (1..30).joinToString(", ") { "Teil Nummer $it des langen Satzes" } + "."
        val c = SpeechText.chunks(long, max = 100)
        assertTrue(c.size > 5)
        assertTrue(c.all { it.first.length <= 100 })
    }

    @Test fun `PCM-Umwandlung begrenzt und ordnet die Bytes`() {
        val b = SpeechText.toPcm16(floatArrayOf(0f, 1f, -1f, 2f))
        assertEquals(8, b.size)
        assertEquals(0, b[0].toInt()); assertEquals(0xFF, b[2].toInt() and 0xFF); assertEquals(0x7F, b[3].toInt())
        assertEquals(0x01, b[4].toInt() and 0xFF); assertEquals(0x80, b[5].toInt() and 0xFF)   // -32767
        assertEquals(0xFF, b[6].toInt() and 0xFF)                                              // 2f wird auf 1f begrenzt
    }
}

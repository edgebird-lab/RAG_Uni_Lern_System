// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.summary

import de.edgebird.lernsystem.core.i18n.Lang
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue

/** Die Prompts folgen der Sprache der Zusammenfassung, nicht der der Oberfläche (sonst entsteht ein Sprachmischmasch). */
class SummaryLanguageTest {
    private val umlaut = Regex("[äöüß]|Schreibe|Verwende|Abschnitt")

    @Test
    fun `englische Zusammenfassung bei deutscher Oberflaeche hat rein englische Anweisungen`() {
        val before = Lang.current
        Lang.current = Lang.DE
        try {
            for (format in SummaryFormat.entries) {
                val spec = SummarySpec(format = format, language = SummaryLanguage.EN)
                val prompt = SummaryPrompts.section(spec, "Skript", "Heaps", "Ein Heap ist ein Baum.", 60)
                // Der Quelltext selbst bleibt deutsch; geprüft wird der Teil ohne ihn
                val rules = prompt.replace("Ein Heap ist ein Baum.", "")
                assertFalse(umlaut.containsMatchIn(rules), "$format: deutsche Anweisung im Prompt:\n$rules")
                assertTrue("English" in prompt)
            }
            assertTrue(SummaryPrompts.proseFinal(SummarySpec(language = SummaryLanguage.EN), "x", "teil").contains("English"))
            assertTrue(Lang.effective == Lang.DE)
        } finally { Lang.current = before }
    }

    @Test
    fun `deutsche Zusammenfassung bei englischer Oberflaeche hat deutsche Anweisungen`() {
        val before = Lang.current
        Lang.current = Lang.EN
        try {
            val prompt = SummaryPrompts.section(SummarySpec(language = SummaryLanguage.DE), "Script", "Heaps", "text", 60)
            assertTrue("Deutsch" in prompt, prompt)
        } finally { Lang.current = before }
    }
}

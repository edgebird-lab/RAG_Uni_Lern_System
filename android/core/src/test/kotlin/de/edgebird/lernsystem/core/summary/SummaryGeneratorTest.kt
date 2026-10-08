package de.edgebird.lernsystem.core.summary

import de.edgebird.lernsystem.core.ai.GenerationParams
import de.edgebird.lernsystem.core.ai.LlmEngine
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class SummaryGeneratorTest {
    /** Antwortet der Reihe nach mit den vorbereiteten Texten (der letzte wiederholt sich) und merkt sich die Prompts. */
    private class Scripted(vararg replies: String) : LlmEngine {
        private val queue = ArrayDeque(replies.toList())
        val prompts = mutableListOf<String>()
        val maxTokens = mutableListOf<Int>()
        override suspend fun load() = Unit
        override fun generate(prompt: String, params: GenerationParams): Flow<String> = flow {
            prompts += prompt; maxTokens += params.maxTokens
            emit(if (queue.size > 1) queue.removeFirst() else queue.first())
        }
        override fun close() = Unit
    }

    private val section = SummarySection("Kosten", "Kosten sind bewerteter Güterverbrauch. Die Frist beträgt 14 Tage und der Satz 3,5 Prozent. ".repeat(3))

    @Test
    fun `Abschnitt wird zusammengefasst`() = runTest {
        val r = SummaryGenerator(Scripted("- Kosten sind **bewerteter Güterverbrauch**.\n- Frist 14 Tage."), "Skript").summarizeSection(section, PartKind.BULLETS)
        assertNotNull(r.text)
        assertTrue(r.unsupportedNumbers.isEmpty())
    }

    @Test
    fun `zu kurzer Abschnitt wird uebersprungen, ohne das Modell zu fragen`() = runTest {
        val llm = Scripted("x")
        val r = SummaryGenerator(llm, "Skript").summarizeSection(SummarySection("A", "kurz"), PartKind.BULLETS)
        assertEquals(SkipReason.TOO_SHORT, r.reason)
        assertTrue(llm.prompts.isEmpty())
    }

    @Test
    fun `leerer Marker ergibt keine Zusammenfassung`() = runTest {
        val r = SummaryGenerator(Scripted("(kein prüfungsrelevanter Inhalt)"), "S").summarizeSection(section, PartKind.OUTLINE)
        assertEquals(SkipReason.NOT_RELEVANT, r.reason)
        assertNull(r.text)
    }

    @Test
    fun `abgeschnittene Antwort wird mit mehr Tokens neu angefragt`() = runTest {
        val llm = Scripted("- Erster Punkt ist hier ausführlich beschrieben und lang genug,", "- Erster Punkt vollständig.\n- Zweiter Punkt vollständig und lang genug beschrieben.")
        val r = SummaryGenerator(llm, "S").summarizeSection(section, PartKind.BULLETS)
        assertTrue(r.text!!.contains("Zweiter Punkt"))
        assertTrue(llm.maxTokens[1] > llm.maxTokens[0])
    }

    @Test
    fun `erfundene Zahlen loesen einen Neuversuch aus, der bessere Versuch gewinnt`() = runTest {
        val llm = Scripted("- Die Frist beträgt 99 Tage.", "- Die Frist beträgt 14 Tage.")
        val r = SummaryGenerator(llm, "S").summarizeSection(section, PartKind.BULLETS)
        assertEquals("- Die Frist beträgt 14 Tage.", r.text)
        assertTrue(r.unsupportedNumbers.isEmpty())
        assertTrue(llm.prompts[1].contains("Zahlen, die im Quelltext nicht stehen"))
    }

    @Test
    fun `bleiben Zahlen unbelegt, wird der Befund gemeldet`() = runTest {
        val r = SummaryGenerator(Scripted("- Die Frist beträgt 99 Tage."), "S").summarizeSection(section, PartKind.BULLETS)
        assertEquals(listOf("99"), r.unsupportedNumbers)
    }

    @Test
    fun `Fehler im Modell ergibt uebersprungenen Abschnitt`() = runTest {
        val broken = object : LlmEngine {
            override suspend fun load() = Unit
            override fun generate(prompt: String, params: GenerationParams): Flow<String> = flow { error("kaputt") }
            override fun close() = Unit
        }
        assertEquals(SkipReason.FAILED, SummaryGenerator(broken, "S").summarizeSection(section, PartKind.BULLETS).reason)
    }

    @Test
    fun `Kurzfassung in einem Schritt, wenn alles ins Budget passt`() = runTest {
        val llm = Scripted("Absatz mit Kernaussage.\n\n**Das Wichtigste:**\n- Punkt")
        val md = SummaryGenerator(llm, "Skript").shortSummary(listOf("A" to "- a1", "B" to "- b1"))
        assertEquals(1, llm.prompts.size)
        assertTrue(md!!.contains("Das Wichtigste"))
        assertTrue(llm.prompts[0].contains("### A") && llm.prompts[0].contains("### B"))
    }

    @Test
    fun `Kurzfassung verdichtet grosse Mengen stapelweise`() = runTest {
        val llm = Scripted("- verdichtet", "- verdichtet", "- verdichtet", "Absatz.\n\n**Das Wichtigste:**\n- Ende")
        val parts = (1..9).map { "Abschnitt $it" to "- " + "Inhalt ".repeat(100) }
        val md = SummaryGenerator(llm, "Skript", reduceBudget = 2000).shortSummary(parts)
        assertTrue(llm.prompts.size >= 3, "erwartet mehrere Verdichtungsschritte, war ${llm.prompts.size}")
        assertTrue(llm.prompts.dropLast(1).all { "Verdichte sie" in it })
        assertTrue(md!!.contains("Ende"))
    }

    @Test
    fun `ohne Teile keine Kurzfassung`() = runTest { assertNull(SummaryGenerator(Scripted("x"), "S").shortSummary(emptyList())) }

    @Test
    fun `Zusammensetzen der Abschnitte`() {
        val md = SummaryGenerator(Scripted("x"), "S").assemble("Skript", listOf("Seite 1" to "- a", "Seite 2" to "- b"), "Gemma")
        assertTrue(md.startsWith("# Zusammenfassung: Skript"))
        assertTrue("## Seite 1\n\n- a" in md && "## Seite 2\n\n- b" in md)
    }
}

// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.quiz

import de.edgebird.lernsystem.core.ai.GenerationParams
import de.edgebird.lernsystem.core.ai.LlmEngine
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test
import kotlin.random.Random

class MultipleChoiceTest {
    private val chunk = "Bei der Photosynthese wandeln Pflanzen Lichtenergie in chemische Energie um. Dabei entstehen Sauerstoff und Glucose aus Kohlenstoffdioxid und Wasser. Die Lichtreaktion findet in den Thylakoidmembranen statt."

    private fun raw(q: String = "Welche Stoffe entstehen bei der Photosynthese?", c: String = "Sauerstoff und Glucose", w: List<String> = listOf("Stickstoff und Salz", "Methan und Eisen", "Ammoniak und Zucker"), e: String = "Laut Abschnitt entstehen Sauerstoff und Glucose.") =
        MultipleChoice.Raw(q, c, w, e)

    @Test fun `gueltige Frage wird gebaut, gemischt und die richtige Antwort bleibt auffindbar`() {
        val q = MultipleChoice.build(raw(), chunk, Random(1))!!
        assertEquals(4, q.options.size)
        assertEquals("Sauerstoff und Glucose", q.correct)
        assertEquals(4, q.options.toSet().size)
        // andere Startwerte mischen anders, die Zuordnung bleibt richtig
        val orders = (1..8).map { MultipleChoice.build(raw(), chunk, Random(it))!!.options }.toSet()
        assertTrue(orders.size > 1)
    }

    @Test fun `erfundene richtige Antwort wird abgelehnt`() {
        assertNull(MultipleChoice.build(raw(c = "Fotonen verschmelzen zu Plasma im Mitochondrium"), chunk, Random(1)))
    }

    @Test fun `zu wenige oder doppelte falsche Antworten werden abgelehnt`() {
        assertNull(MultipleChoice.build(raw(w = listOf("Stickstoff und Salz", "stickstoff und salz!", "Methan und Eisen")), chunk, Random(1)))
        assertNull(MultipleChoice.build(raw(w = listOf("Stickstoff und Salz", "Methan und Eisen")), chunk, Random(1)))
        assertNull(MultipleChoice.build(raw(w = listOf("Sauerstoff und Glucose", "Methan und Eisen", "Ammoniak und Zucker")), chunk, Random(1)))
    }

    @Test fun `falsche Antwort, die die richtige enthaelt, wird abgelehnt`() {
        assertNull(MultipleChoice.build(raw(w = listOf("Sauerstoff und Glucose und Wasser", "Methan und Eisen", "Ammoniak und Zucker")), chunk, Random(1)))
    }

    @Test fun `Quellenbezug in der Frage und sehr lange Antworten werden abgelehnt`() {
        assertNull(MultipleChoice.build(raw(q = "Was zeigt Abbildung 3 zur Photosynthese?"), chunk, Random(1)))
        assertNull(MultipleChoice.build(raw(c = "Sauerstoff und Glucose ".repeat(12)), chunk, Random(1)))
    }

    @Test fun `die richtige Antwort darf nicht deutlich heraussticheln`() {
        val q = raw(c = "Sauerstoff und Glucose, die aus Kohlenstoffdioxid und Wasser entstehen", w = listOf("Salz", "Eisen", "Zucker"))
        assertNull(MultipleChoice.build(q, chunk, Random(1)))
    }

    @Test fun `JSON mit Text drumherum wird gelesen`() {
        val r = MultipleChoice.parse("Hier: ```json {\"frage\": \"Was?\", \"richtig\": \"A\", \"falsch\": [\"B\", \"C\", \"D\"], \"erklaerung\": \"weil\"} ```")!!
        assertEquals(listOf("B", "C", "D"), r.wrong)
        assertNull(MultipleChoice.parse("kaputt"))
        assertNull(MultipleChoice.parse("{\"frage\": \"\", \"richtig\": \"A\"}"))
    }

    private class Scripted(vararg val replies: String) : LlmEngine {
        var n = 0
        override suspend fun load() {}
        override fun generate(prompt: String, params: GenerationParams): Flow<String> = flowOf(replies[minOf(n++, replies.size - 1)])
        override fun close() {}
    }

    @Test fun `Generator versucht es erneut, wenn der erste Versuch unbrauchbar ist`() = runTest {
        val bad = """{"frage": "Welche Stoffe entstehen bei der Photosynthese?", "richtig": "Methan", "falsch": ["A", "B", "C"], "erklaerung": ""}"""
        val good = """{"frage": "Welche Stoffe entstehen bei der Photosynthese?", "richtig": "Sauerstoff und Glucose", "falsch": ["Stickstoff und Salz", "Methan und Eisen", "Ammoniak und Zucker"], "erklaerung": "steht im Text"}"""
        val llm = Scripted(bad, good)
        val q = MultipleChoice.generate(llm, chunk, Random(3))
        assertNotNull(q); assertEquals(2, llm.n)
        assertNull(MultipleChoice.generate(Scripted("Unsinn"), chunk, Random(3), attempts = 2))
    }
}

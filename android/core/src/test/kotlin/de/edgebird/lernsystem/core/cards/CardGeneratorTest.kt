// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.cards

import de.edgebird.lernsystem.core.ai.Embedder
import de.edgebird.lernsystem.core.ai.GenerationParams
import de.edgebird.lernsystem.core.ai.LlmEngine
import de.edgebird.lernsystem.core.search.SearchTokenizer
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class CardGeneratorTest {
    private val chunk = "# Deckungsbeitrag\n" + "Der Deckungsbeitrag ist die Differenz aus Erlösen und variablen Kosten. Er zeigt, wie viel ein Produkt zur Deckung der Fixkosten beiträgt. ".repeat(2)

    /** Antwortet je nach Prompt: Fragen-Prompt -> JSON, Antwort-Prompt -> Text. Mit Skript für Neuversuche. */
    private class ScriptedLlm(val questionReplies: MutableList<String>, val answerReplies: MutableList<String>) : LlmEngine {
        val prompts = mutableListOf<String>()
        override suspend fun load() = Unit
        override fun generate(prompt: String, params: GenerationParams): Flow<String> = flow {
            prompts += prompt
            val list = if ("Gib NUR gültiges JSON" in prompt) questionReplies else answerReplies
            emit(if (list.size > 1) list.removeAt(0) else list.first())
        }
        override fun close() = Unit
    }

    private class BowEmbedder : Embedder {
        override val dimensions = 32
        override suspend fun load() = Unit
        override suspend fun embed(texts: List<String>) = texts.map { t ->
            val v = FloatArray(dimensions)
            SearchTokenizer.tokenize(t).forEach { v[(it.hashCode() and 0x7fffffff) % dimensions] += 1f }
            de.edgebird.lernsystem.core.ai.VectorCodec.normalize(v)
        }
        override fun close() = Unit
    }

    @Test
    fun `erzeugt Karten aus Frage und Antwort`() = runTest {
        val llm = ScriptedLlm(
            mutableListOf("""{"questions": ["Wie berechnet man den Deckungsbeitrag eines Produkts?", "Wofür dient der Deckungsbeitrag im Unternehmen?"]}"""),
            mutableListOf("Der Deckungsbeitrag ergibt sich aus den Erlösen abzüglich der variablen Kosten."),
        )
        val cards = CardGenerator(llm).generate(chunk, n = 2)
        assertEquals(2, cards.size)
        assertTrue(cards.all { it.answer.startsWith("Der Deckungsbeitrag") })
    }

    @Test
    fun `Fragen mit Quellenbezug werden verworfen und mit Hinweis neu angefragt`() = runTest {
        val llm = ScriptedLlm(
            mutableListOf(
                """{"questions": ["Was zeigt Abbildung 2?", "Was steht laut Skript über Kosten?"]}""",
                """{"questions": ["Wie berechnet man den Deckungsbeitrag eines Produkts?"]}""",
            ),
            mutableListOf("Erlöse minus variable Kosten ergibt den Deckungsbeitrag eines Produkts."),
        )
        val stats = GenerationStats()
        val cards = CardGenerator(llm).generate(chunk, n = 1, stats = stats)
        assertEquals(1, cards.size)
        assertEquals(2, stats.rejectedQuestions)
        assertEquals(1, stats.retries)
        assertTrue(llm.prompts.any { "WICHTIG - der letzte Versuch hatte Mängel" in it })
    }

    @Test
    fun `Dubletten zu vorhandenen Fragen werden erkannt`() = runTest {
        val emb = BowEmbedder()
        val existing = emb.embed(listOf("Wie berechnet man den Deckungsbeitrag eines Produkts?"))
        val llm = ScriptedLlm(
            mutableListOf("""{"questions": ["Wie berechnet man den Deckungsbeitrag eines Produkts?"]}"""),
            mutableListOf("Erlöse minus variable Kosten."),
        )
        val stats = GenerationStats()
        val cards = CardGenerator(llm, emb, retries = 0).generate(chunk, n = 1, existing = existing.map { it to "Wie berechnet man den Deckungsbeitrag eines Produkts?" }, stats = stats)
        assertTrue(cards.isEmpty())
        assertEquals(1, stats.duplicates)
    }

    @Test
    fun `Antwort mit Quellenbezug wird neu erzeugt, bleibt der Mangel, faellt die Karte weg`() = runTest {
        val q = """{"questions": ["Wie berechnet man den Deckungsbeitrag eines Produkts?"]}"""
        val ok = ScriptedLlm(mutableListOf(q), mutableListOf("Siehe Abbildung 2.", "Erlöse minus variable Kosten ergibt den Deckungsbeitrag."))
        assertEquals(1, CardGenerator(ok).generate(chunk, n = 1).size)
        val bad = ScriptedLlm(mutableListOf(q), mutableListOf("Siehe Abbildung 2."))
        val stats = GenerationStats()
        assertTrue(CardGenerator(bad).generate(chunk, n = 1, stats = stats).isEmpty())
        assertEquals(1, stats.rejectedAnswers)
    }

    @Test
    fun `NICHT_IM_TEXT ergibt keine Karte`() = runTest {
        val llm = ScriptedLlm(mutableListOf("""{"questions": ["Wie berechnet man den Deckungsbeitrag eines Produkts?"]}"""), mutableListOf("NICHT_IM_TEXT"))
        assertTrue(CardGenerator(llm).generate(chunk, n = 1).isEmpty())
    }

    @Test
    fun `kaputtes JSON und Text drumherum`() {
        assertEquals(listOf("Frage eins hier?"), CardPrompts.parseQuestions("Hier: ```json\n{\"questions\": [\"Frage eins hier?\", 5, null]}\n``` fertig"))
        assertEquals(emptyList<String>(), CardPrompts.parseQuestions("kein JSON"))
        assertEquals(emptyList<String>(), CardPrompts.parseQuestions("{\"questions\": [\"offen\""))
    }

    @Test
    fun `zu kurze Abschnitte ergeben keine Karten`() = runTest {
        assertTrue(CardGenerator(ScriptedLlm(mutableListOf("x"), mutableListOf("y"))).generate("kurz", n = 2).isEmpty())
    }
}

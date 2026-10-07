package de.edgebird.lernsystem.core.cards

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/** Paritätstest gegen `ragapp/card_quality.py` und `ragapp/ingestion/question_gen.py` (Referenz: `eval/tools/make_cards_fixture.py`). */
class CardQualityParityTest {
    private val fx: JsonObject by lazy {
        JsonParser.parseReader(checkNotNull(javaClass.getResourceAsStream("/cards/quality_fixture.json")).reader(Charsets.UTF_8)).asJsonObject
    }

    private fun codes(o: JsonObject) = o.getAsJsonArray("problems").map { it.asString }
    private fun List<CardProblem>.codes() = map { it.code }

    @Test
    fun `Fragen-Pruefung stimmt mit Python ueberein`() {
        val diffs = fx.getAsJsonArray("questions").map { it.asJsonObject }.mapNotNull { o ->
            val actual = CardQuality.questionProblems(o["text"].asString).codes()
            if (actual != codes(o)) "'${o["text"].asString.take(60)}': erwartet ${codes(o)}, war $actual" else null
        }
        assertTrue(diffs.isEmpty(), diffs.joinToString("\n"))
    }

    @Test
    fun `Antwort-Pruefung stimmt mit Python ueberein`() {
        val diffs = fx.getAsJsonArray("answers").map { it.asJsonObject }.mapNotNull { o ->
            val actual = CardQuality.answerProblems(o["text"].asString, o["question"].asString).codes()
            if (actual != codes(o)) "'${o["text"].asString.take(60)}': erwartet ${codes(o)}, war $actual" else null
        }
        assertTrue(diffs.isEmpty(), diffs.joinToString("\n"))
    }

    @Test
    fun `Antwort-Bereinigung, Fragenerkennung und Ueberschrift-Echo stimmen mit Python ueberein`() {
        fx.getAsJsonArray("clean").map { it.asJsonObject }.forEach { assertEquals(it["clean"].asString, CardPrompts.cleanAnswer(it["raw"].asString), it["raw"].asString) }
        fx.getAsJsonArray("is_frage").map { it.asJsonObject }.forEach { assertEquals(it["value"].asBoolean, CardPrompts.isQuestion(it["text"].asString), it["text"].asString) }
        fx.getAsJsonArray("echo").map { it.asJsonObject }.forEach {
            assertEquals(it["value"].asBoolean, CardPrompts.isHeadingEcho(it["question"].asString, it["chunk"].asString), it["question"].asString)
        }
    }

    @Test
    fun `Fixture enthaelt auffaellige und unauffaellige Faelle`() {
        val q = fx.getAsJsonArray("questions").map { codes(it.asJsonObject) }
        assertTrue(q.any { it.isNotEmpty() } && q.any { it.isEmpty() })
    }
}

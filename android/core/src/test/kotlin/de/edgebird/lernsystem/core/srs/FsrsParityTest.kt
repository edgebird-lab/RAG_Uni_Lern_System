// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.srs

import com.google.gson.JsonParser
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import kotlin.math.abs

/** Paritätstest gegen py-fsrs 6.3 (Referenz aus `eval/tools/make_fsrs_fixture.py`, 300 zufällige Bewertungsfolgen). */
class FsrsParityTest {
    @Test
    fun `Kotlin-Planer liefert dieselben Werte wie das Python-Paket`() {
        val stream = checkNotNull(javaClass.getResourceAsStream("/srs/fsrs_fixture.json"))
        val cases = JsonParser.parseReader(stream.reader(Charsets.UTF_8)).asJsonArray
        val scheduler = FsrsScheduler(FsrsConfig(desiredRetention = 0.9, maximumIntervalDays = 365))
        var reviews = 0
        val problems = mutableListOf<String>()
        cases.forEachIndexed { ci, c ->
            var card = FsrsCard(dueMillis = 0)
            c.asJsonArray.forEachIndexed { ri, r ->
                val o = r.asJsonObject
                card = scheduler.review(card, Rating.entries.first { it.value == o["rating"].asInt }, o["now"].asLong)
                reviews++
                fun near(a: Double?, b: Double) = a != null && abs(a - b) <= 1e-9 * max(1.0, abs(b))
                val ok = card.state.value == o["state"].asInt &&
                    card.step == (if (o["step"].isJsonNull) null else o["step"].asInt) &&
                    near(card.stability, o["stability"].asDouble) && near(card.difficulty, o["difficulty"].asDouble) &&
                    card.dueMillis == o["due"].asLong
                if (!ok && problems.size < 5) problems += "Folge $ci Schritt $ri: $card vs $o"
            }
        }
        assertTrue(problems.isEmpty(), "Abweichungen:\n" + problems.joinToString("\n"))
        assertTrue(reviews > 2000, "zu wenige Bewertungen: $reviews")
    }

    private fun max(a: Double, b: Double) = if (a > b) a else b

    @Test
    fun `neue Karte mit Gut bleibt im Lernen und kommt nach 10 Minuten wieder`() {
        val s = FsrsScheduler()
        val c = s.review(FsrsCard(dueMillis = 0), Rating.GOOD, 1_000_000)
        assertEquals(CardState.LEARNING, c.state)
        assertEquals(1, c.step)
        assertEquals(1_000_000 + 10 * 60_000L, c.dueMillis)
    }

    @Test
    fun `Lernschritte durchlaufen und in Review graduieren`() {
        val s = FsrsScheduler()
        var c = FsrsCard(dueMillis = 0)
        var t = 0L
        repeat(2) { c = s.review(c, Rating.GOOD, t); t = c.dueMillis }
        assertEquals(CardState.REVIEW, c.state)
        assertEquals(null, c.step)
        assertTrue(c.dueMillis - t >= 0)
    }

    @Test
    fun `Vergessen im Review fuehrt ins Wiederlernen`() {
        val s = FsrsScheduler()
        var c = FsrsCard(dueMillis = 0)
        var t = 0L
        repeat(2) { c = s.review(c, Rating.GOOD, t); t = c.dueMillis }
        c = s.review(c, Rating.AGAIN, t + FsrsScheduler.DAY_MS * 3)
        assertEquals(CardState.RELEARNING, c.state)
        assertEquals(0, c.step)
    }

    @Test
    fun `Intervall ist nach oben begrenzt`() {
        val s = FsrsScheduler(FsrsConfig(maximumIntervalDays = 30))
        var c = FsrsCard(dueMillis = 0)
        var t = 0L
        repeat(25) { c = s.review(c, Rating.EASY, t); t = c.dueMillis }
        assertTrue(c.dueMillis - (c.lastReviewMillis ?: 0) <= 30 * FsrsScheduler.DAY_MS)
    }
}

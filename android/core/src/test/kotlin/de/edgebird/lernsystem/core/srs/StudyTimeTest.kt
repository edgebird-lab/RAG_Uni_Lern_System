// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.srs

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.time.ZoneId
import java.time.ZonedDateTime

class StudyTimeTest {
    private val zone = ZoneId.of("Europe/Berlin")
    private fun t(y: Int, m: Int, d: Int, h: Int = 12) = ZonedDateTime.of(y, m, d, h, 0, 0, 0, zone).toInstant().toEpochMilli()

    @Test
    fun `Streak zaehlt aufeinanderfolgende Tage`() {
        val reviews = listOf(t(2026, 3, 1), t(2026, 3, 2, 8), t(2026, 3, 2, 22), t(2026, 3, 3))
        assertEquals(3, StudyTime.streak(reviews, t(2026, 3, 3, 18), zone))
    }

    @Test
    fun `Heute noch ohne Lernen haelt die Serie von gestern`() {
        assertEquals(2, StudyTime.streak(listOf(t(2026, 3, 1), t(2026, 3, 2)), t(2026, 3, 3, 9), zone))
    }

    @Test
    fun `Luecke bricht die Serie`() {
        assertEquals(1, StudyTime.streak(listOf(t(2026, 3, 1), t(2026, 3, 3)), t(2026, 3, 3, 9), zone))
        assertEquals(0, StudyTime.streak(listOf(t(2026, 3, 1)), t(2026, 3, 5), zone))
        assertEquals(0, StudyTime.streak(emptyList(), t(2026, 3, 5), zone))
    }

    @Test
    fun `Tagesgrenze richtet sich nach der Zeitzone`() {
        // 23:30 Berlin am 1.3. ist 22:30 UTC: derselbe lokale Tag wie 00:10 am 1.3.?
        assertEquals(StudyTime.dayStart(t(2026, 3, 1, 0), zone), StudyTime.dayStart(t(2026, 3, 1, 23), zone))
    }

    @Test
    fun `Anzeige der Faelligkeit`() {
        val now = 0L
        assertEquals("in ~1 Minute", StudyTime.humanizeDue(60_000, now))
        assertEquals("in 10 Minuten", StudyTime.humanizeDue(10 * 60_000, now))
        assertEquals("in 5 Stunden", StudyTime.humanizeDue(5 * 3_600_000L, now))
        assertEquals("morgen", StudyTime.humanizeDue(24 * 3_600_000L, now))
        assertEquals("in 3 Tagen", StudyTime.humanizeDue(3 * 86_400_000L, now))
        assertEquals("in 2 Monaten", StudyTime.humanizeDue(60 * 86_400_000L, now))
    }

    @Test
    fun `Lernkarten mit naher Faelligkeit bleiben in der Sitzung`() {
        val soon = FsrsCard(CardState.LEARNING, 1, 1.0, 5.0, dueMillis = 10 * 60_000L)
        assertTrue(StudyTime.shouldRequeueInSession(soon, 0))
        assertFalse(StudyTime.shouldRequeueInSession(soon.copy(state = CardState.REVIEW, step = null), 0))
        assertFalse(StudyTime.shouldRequeueInSession(soon.copy(dueMillis = 3 * 86_400_000L), 0))
    }
}

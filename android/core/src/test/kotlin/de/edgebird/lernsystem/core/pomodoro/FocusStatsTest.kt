package de.edgebird.lernsystem.core.pomodoro

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import java.time.ZoneId
import java.time.ZonedDateTime

class FocusStatsTest {
    private val zone = ZoneId.of("Europe/Berlin")
    private fun t(d: Int, h: Int = 10) = ZonedDateTime.of(2026, 3, d, h, 0, 0, 0, zone).toInstant().toEpochMilli()
    private val min = 60_000L

    @Test
    fun `Minuten je Tag und Sitzungen`() {
        val sessions = listOf(FocusSession(t(10, 9), 25 * min, true), FocusSession(t(10, 14), 25 * min, true), FocusSession(t(8), 10 * min, false))
        val w = FocusStats.perDay(sessions, t(10, 20), zone)
        assertEquals(7, w.size)
        assertEquals(50, w.last().minutes)
        assertEquals(2, w.last().sessions)
        assertEquals(10, w[4].minutes) // 8. März
        assertEquals(0, w[5].minutes)
    }

    @Test
    fun `heute zaehlt nur den heutigen Tag`() {
        val sessions = listOf(FocusSession(t(9, 23), 25 * min, true), FocusSession(t(10, 1), 5 * min, true))
        assertEquals(5, FocusStats.todayMinutes(sessions, t(10, 12), zone))
    }

    @Test
    fun `Fortschritt zum Tagesziel ist begrenzt`() {
        assertEquals(0.5f, FocusStats.goalProgress(60, 120))
        assertEquals(1f, FocusStats.goalProgress(300, 120))
        assertEquals(0f, FocusStats.goalProgress(10, 0))
    }

    @Test
    fun `leere Liste ergibt Nullen`() {
        assertEquals(List(7) { 0 }, FocusStats.perDay(emptyList(), t(10), zone).map { it.minutes })
    }
}

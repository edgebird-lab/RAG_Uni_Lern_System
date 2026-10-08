package de.edgebird.lernsystem.core.pomodoro

import java.time.Instant
import java.time.ZoneId

/** Eine Fokusphase für die Statistik. */
data class FocusSession(val startedAtMillis: Long, val focusedMs: Long, val completed: Boolean)

data class DayMinutes(val dayStartMillis: Long, val minutes: Int, val sessions: Int)

/** Lernzeit-Statistik aus den Fokusphasen. Eine Phase zählt zum Tag ihres Beginns. */
object FocusStats {
    private const val DAY_MS = 86_400_000L

    private fun dayStart(millis: Long, zone: ZoneId) =
        Instant.ofEpochMilli(millis).atZone(zone).toLocalDate().atStartOfDay(zone).toInstant().toEpochMilli()

    /** Die letzten [days] Tage, ältester zuerst; der letzte Eintrag ist heute. Minuten werden pro Tag aus der Summe gerundet. */
    fun perDay(sessions: List<FocusSession>, nowMillis: Long, zone: ZoneId, days: Int = 7): List<DayMinutes> {
        val byDay = sessions.groupBy { dayStart(it.startedAtMillis, zone) }
        return (days - 1 downTo 0).map { back ->
            val start = dayStart(nowMillis - back * DAY_MS, zone)
            val list = byDay[start].orEmpty()
            DayMinutes(start, (list.sumOf { it.focusedMs } / 60_000.0).let { Math.round(it).toInt() }, list.size)
        }
    }

    fun todayMinutes(sessions: List<FocusSession>, nowMillis: Long, zone: ZoneId): Int = perDay(sessions, nowMillis, zone, 1).single().minutes

    /** Fortschritt zum Tagesziel in Minuten, höchstens 1. */
    fun goalProgress(minutes: Int, goalMinutes: Int): Float = if (goalMinutes <= 0) 0f else (minutes.toFloat() / goalMinutes).coerceIn(0f, 1f)
}

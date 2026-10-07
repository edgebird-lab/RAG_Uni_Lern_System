package de.edgebird.lernsystem.core.srs

import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import kotlin.math.roundToLong

/** Zeit-Hilfen für das Lernen: Tagesgrenzen, Streak und die Anzeige „in 3 Tagen“. */
object StudyTime {
    /** Beginn des Tages (lokal) in Millisekunden, in dem [millis] liegt. */
    fun dayStart(millis: Long, zone: ZoneId): Long = Instant.ofEpochMilli(millis).atZone(zone).toLocalDate().atStartOfDay(zone).toInstant().toEpochMilli()

    /**
     * Aktuelle Serie aufeinanderfolgender Lerntage. Heute ohne Wiederholung zählt die Serie von gestern weiter
     * (der Tag ist ja noch nicht vorbei); fehlt auch gestern, ist sie 0.
     */
    fun streak(reviewMillis: Collection<Long>, nowMillis: Long, zone: ZoneId): Int {
        val days: Set<LocalDate> = reviewMillis.map { Instant.ofEpochMilli(it).atZone(zone).toLocalDate() }.toSet()
        var day = Instant.ofEpochMilli(nowMillis).atZone(zone).toLocalDate()
        if (day !in days) day = day.minusDays(1)
        var n = 0
        while (day in days) { n++; day = day.minusDays(1) }
        return n
    }

    /** Menschliche Beschreibung des Abstands bis zur Fälligkeit (wie `humanize_due` der PC-App). */
    fun humanizeDue(dueMillis: Long, nowMillis: Long): String {
        val sec = maxOf(0.0, (dueMillis - nowMillis) / 1000.0)
        return when {
            sec < 90 -> "in ~1 Minute"
            sec < 3600 -> "in ${(sec / 60).roundToLong()} Minuten"
            sec < 2 * 86400 -> {
                val h = sec / 3600
                if (h >= 20) "morgen" else "in ${h.roundToLong()} Stunden"
            }
            else -> {
                val d = sec / 86400
                when {
                    d < 30 -> "in ${d.roundToLong()} Tagen"
                    d < 365 -> "in ${(d / 30).roundToLong()} Monaten"
                    else -> "in ${"%.1f".format(java.util.Locale.GERMANY, d / 365)} Jahren"
                }
            }
        }
    }

    /** Wie Anki: Lern-/Wiederlern-Karten mit naher Fälligkeit bleiben in der Sitzung (Standard 20 Minuten). */
    fun shouldRequeueInSession(card: FsrsCard, nowMillis: Long, windowMs: Long = 20 * 60_000L): Boolean =
        (card.state == CardState.LEARNING || card.state == CardState.RELEARNING) && card.dueMillis <= nowMillis + windowMs
}

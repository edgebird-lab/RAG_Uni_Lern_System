package de.edgebird.lernsystem.core.pomodoro

enum class PomodoroPhase { FOCUS, SHORT_BREAK, LONG_BREAK }

/**
 * IDLE: nichts läuft (Fokus bereit), RUNNING: Zeit läuft, PAUSED: angehalten,
 * WAITING: die nächste Phase ist dran, wartet aber auf den Start (kein Auto-Start).
 */
enum class PomodoroStatus { IDLE, RUNNING, PAUSED, WAITING }

/** Einstellungen; Dauern in Sekunden (Tests und der Debug-Schnelltest nutzen kurze Werte). */
data class PomodoroSettings(
    val focusSeconds: Int = 25 * 60,
    val shortBreakSeconds: Int = 5 * 60,
    val longBreakSeconds: Int = 15 * 60,
    /** Nach so vielen Fokusphasen folgt die lange Pause. */
    val cyclesBeforeLongBreak: Int = 4,
    val autoStartBreaks: Boolean = true,
    val autoStartFocus: Boolean = false,
) {
    fun seconds(phase: PomodoroPhase) = when (phase) {
        PomodoroPhase.FOCUS -> focusSeconds
        PomodoroPhase.SHORT_BREAK -> shortBreakSeconds
        PomodoroPhase.LONG_BREAK -> longBreakSeconds
    }

    fun totalMs(phase: PomodoroPhase) = seconds(phase) * 1000L
}

/**
 * Zustand des Timers. Rein zeitstempelbasiert (kein Zähler pro Sekunde): Die verbleibende Zeit ergibt sich aus
 * [remainingAtAnchorMs] zum Zeitpunkt [anchorMillis], deshalb übersteht der Zustand das Beenden der App.
 */
data class PomodoroState(
    val phase: PomodoroPhase = PomodoroPhase.FOCUS,
    val status: PomodoroStatus = PomodoroStatus.IDLE,
    /** Abgeschlossene Fokusphasen der laufenden Runde (0 bis cyclesBeforeLongBreak - 1). */
    val completedFocus: Int = 0,
    val phaseTotalMs: Long,
    /** Verbleibende Zeit zum Zeitpunkt [anchorMillis] (bei PAUSED/IDLE/WAITING: die aktuell verbleibende Zeit). */
    val remainingAtAnchorMs: Long,
    val anchorMillis: Long = 0,
    /** Beginn der Phase (für die Statistik); 0, solange sie nicht gestartet wurde. */
    val phaseStartedAtMillis: Long = 0,
    /** Bereits gelaufene Zeit der Phase vor dem aktuellen Abschnitt (wegen Pausen). */
    val elapsedBeforeAnchorMs: Long = 0,
    /** Dokument, dem die Fokusphase zugeordnet ist. */
    val documentId: Long? = null,
) {
    fun encode(): String = listOf(
        phase.name, status.name, completedFocus, phaseTotalMs, remainingAtAnchorMs, anchorMillis, phaseStartedAtMillis, elapsedBeforeAnchorMs, documentId ?: "",
    ).joinToString(";")

    companion object {
        fun decode(s: String): PomodoroState? = runCatching {
            val p = s.split(";")
            PomodoroState(
                PomodoroPhase.valueOf(p[0]), PomodoroStatus.valueOf(p[1]), p[2].toInt(), p[3].toLong(), p[4].toLong(),
                p[5].toLong(), p[6].toLong(), p[7].toLong(), p[8].toLongOrNull(),
            )
        }.getOrNull()
    }
}

/** Eine beendete Phase; [PhaseEnded.completed] ist wahr, wenn sie bis zum Ende (oder mindestens zur Hälfte) lief. */
data class PhaseEnded(
    val phase: PomodoroPhase,
    val startedAtMillis: Long,
    val plannedMs: Long,
    val actualMs: Long,
    val completed: Boolean,
    val documentId: Long?,
)

data class Transition(val state: PomodoroState, val events: List<PhaseEnded> = emptyList())

/** Zustandsmaschine für Fokus, Kurzpause und Langpause. Alle Funktionen sind rein; die Zeit wird übergeben. */
object Pomodoro {
    /** Verspätung, bis zu der eine automatisch startende Phase noch rückwirkend zum geplanten Ende beginnt. */
    const val AUTO_START_GRACE_MS = 30_000L

    fun initial(settings: PomodoroSettings = PomodoroSettings()) = PomodoroState(
        phase = PomodoroPhase.FOCUS, status = PomodoroStatus.IDLE, phaseTotalMs = settings.totalMs(PomodoroPhase.FOCUS), remainingAtAnchorMs = settings.totalMs(PomodoroPhase.FOCUS),
    )

    fun remainingMs(s: PomodoroState, now: Long): Long =
        if (s.status == PomodoroStatus.RUNNING) maxOf(0, s.remainingAtAnchorMs - (now - s.anchorMillis)) else s.remainingAtAnchorMs

    fun elapsedMs(s: PomodoroState, now: Long): Long = when (s.status) {
        PomodoroStatus.RUNNING -> s.elapsedBeforeAnchorMs + minOf(now - s.anchorMillis, s.remainingAtAnchorMs).coerceAtLeast(0)
        PomodoroStatus.PAUSED -> s.elapsedBeforeAnchorMs
        else -> 0
    }

    /** Geplantes Ende der laufenden Phase; `null`, wenn die Zeit nicht läuft. */
    fun endMillis(s: PomodoroState): Long? = if (s.status == PomodoroStatus.RUNNING) s.anchorMillis + s.remainingAtAnchorMs else null

    fun start(s: PomodoroState, now: Long, documentId: Long? = s.documentId): PomodoroState =
        if (s.status == PomodoroStatus.IDLE || s.status == PomodoroStatus.WAITING) {
            s.copy(
                status = PomodoroStatus.RUNNING, remainingAtAnchorMs = s.phaseTotalMs, anchorMillis = now, phaseStartedAtMillis = now,
                elapsedBeforeAnchorMs = 0, documentId = if (s.phase == PomodoroPhase.FOCUS) documentId else null,
            )
        } else s

    fun pause(s: PomodoroState, now: Long): PomodoroState {
        if (s.status != PomodoroStatus.RUNNING) return s
        val run = minOf(maxOf(0, now - s.anchorMillis), s.remainingAtAnchorMs)
        return s.copy(status = PomodoroStatus.PAUSED, remainingAtAnchorMs = s.remainingAtAnchorMs - run, elapsedBeforeAnchorMs = s.elapsedBeforeAnchorMs + run, anchorMillis = now)
    }

    fun resume(s: PomodoroState, now: Long): PomodoroState =
        if (s.status == PomodoroStatus.PAUSED) s.copy(status = PomodoroStatus.RUNNING, anchorMillis = now) else s

    /**
     * Verarbeitet das Ende der laufenden Phase, falls [now] das geplante Ende erreicht hat. Bei später Verarbeitung
     * (App war beendet) startet eine automatisch folgende Phase nur dann rückwirkend, wenn die Verspätung klein ist;
     * sonst wartet sie auf den Start, damit nie Zeit als „gelernt“ zählt, in der niemand da war.
     */
    fun advance(s: PomodoroState, now: Long, settings: PomodoroSettings): Transition {
        var state = s
        val events = mutableListOf<PhaseEnded>()
        repeat(3) {
            val end = endMillis(state) ?: return Transition(state, events)
            if (now < end) return Transition(state, events)
            if (state.phase == PomodoroPhase.FOCUS) events += ended(state, actual = state.phaseTotalMs, completed = true) // nur Fokusphasen werden gebucht
            state = next(state, endedAt = end, now = now, settings = settings, completedFocus = state.phase == PomodoroPhase.FOCUS)
        }
        return Transition(state, events)
    }

    /** Beendet die laufende oder pausierte Phase vorzeitig. Eine Fokusphase zählt als abgeschlossen, wenn mindestens die Hälfte lief. */
    fun skip(s: PomodoroState, now: Long, settings: PomodoroSettings): Transition {
        if (s.status != PomodoroStatus.RUNNING && s.status != PomodoroStatus.PAUSED) {
            // nichts läuft: zur nächsten Phase springen, ohne Statistik
            return Transition(next(s, endedAt = now, now = now, settings = settings, completedFocus = false, forceWait = true))
        }
        val actual = elapsedMs(s, now)
        val completed = s.phase != PomodoroPhase.FOCUS || actual * 2 >= s.phaseTotalMs
        val ev = if (s.phase == PomodoroPhase.FOCUS && actual > 0) listOf(ended(s, actual, completed)) else emptyList()
        return Transition(next(s, endedAt = now, now = now, settings = settings, completedFocus = s.phase == PomodoroPhase.FOCUS && completed), ev)
    }

    /** Beendet alles und setzt auf „Fokus bereit“ zurück. Eine angefangene Fokusphase wird als nicht abgeschlossen gebucht. */
    fun stop(s: PomodoroState, now: Long, settings: PomodoroSettings): Transition {
        val actual = elapsedMs(s, now)
        val ev = if (s.phase == PomodoroPhase.FOCUS && (s.status == PomodoroStatus.RUNNING || s.status == PomodoroStatus.PAUSED) && actual > 0) listOf(ended(s, actual, completed = false)) else emptyList()
        return Transition(initial(settings).copy(documentId = s.documentId), ev)
    }

    /** Übernimmt neue Einstellungen; eine noch nicht gestartete Phase bekommt die neue Dauer. */
    fun applySettings(s: PomodoroState, settings: PomodoroSettings): PomodoroState =
        if (s.status == PomodoroStatus.IDLE || s.status == PomodoroStatus.WAITING) {
            val total = settings.totalMs(s.phase)
            s.copy(phaseTotalMs = total, remainingAtAnchorMs = total)
        } else s

    private fun ended(s: PomodoroState, actual: Long, completed: Boolean) =
        PhaseEnded(s.phase, s.phaseStartedAtMillis, s.phaseTotalMs, actual, completed, s.documentId)

    private fun next(s: PomodoroState, endedAt: Long, now: Long, settings: PomodoroSettings, completedFocus: Boolean, forceWait: Boolean = false): PomodoroState {
        val cycles = maxOf(1, settings.cyclesBeforeLongBreak)
        var done = s.completedFocus
        val nextPhase = when (s.phase) {
            PomodoroPhase.FOCUS -> {
                if (completedFocus) done += 1
                if (done >= cycles) { done = 0; PomodoroPhase.LONG_BREAK } else PomodoroPhase.SHORT_BREAK
            }
            else -> PomodoroPhase.FOCUS
        }
        val total = settings.totalMs(nextPhase)
        val auto = if (nextPhase == PomodoroPhase.FOCUS) settings.autoStartFocus else settings.autoStartBreaks
        val base = s.copy(phase = nextPhase, completedFocus = done, phaseTotalMs = total, remainingAtAnchorMs = total, elapsedBeforeAnchorMs = 0, phaseStartedAtMillis = 0, documentId = if (nextPhase == PomodoroPhase.FOCUS) s.documentId else null)
        return if (auto && !forceWait && now - endedAt <= AUTO_START_GRACE_MS) {
            base.copy(status = PomodoroStatus.RUNNING, anchorMillis = endedAt, phaseStartedAtMillis = endedAt)
        } else {
            base.copy(status = PomodoroStatus.WAITING, anchorMillis = now)
        }
    }
}

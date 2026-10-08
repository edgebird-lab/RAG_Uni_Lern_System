package de.edgebird.lernsystem.core.pomodoro

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class PomodoroTest {
    private val s = PomodoroSettings(focusSeconds = 100, shortBreakSeconds = 20, longBreakSeconds = 60, cyclesBeforeLongBreak = 3, autoStartBreaks = true, autoStartFocus = false)
    private val sec = 1000L

    private fun started(now: Long = 0, doc: Long? = null) = Pomodoro.start(Pomodoro.initial(s), now, doc)

    @Test
    fun `Start setzt die Zeit in Gang`() {
        val st = started(5 * sec)
        assertEquals(PomodoroStatus.RUNNING, st.status)
        assertEquals(100 * sec, Pomodoro.remainingMs(st, 5 * sec))
        assertEquals(70 * sec, Pomodoro.remainingMs(st, 35 * sec))
        assertEquals(105 * sec, Pomodoro.endMillis(st))
    }

    @Test
    fun `Pause friert die Restzeit ein, Fortsetzen laeuft weiter`() {
        val paused = Pomodoro.pause(started(0), 30 * sec)
        assertEquals(PomodoroStatus.PAUSED, paused.status)
        assertEquals(70 * sec, Pomodoro.remainingMs(paused, 500 * sec))
        assertEquals(30 * sec, Pomodoro.elapsedMs(paused, 500 * sec))
        val resumed = Pomodoro.resume(paused, 200 * sec)
        assertEquals(50 * sec, Pomodoro.remainingMs(resumed, 220 * sec))
        assertEquals(50 * sec, Pomodoro.elapsedMs(resumed, 220 * sec))
        assertEquals(270 * sec, Pomodoro.endMillis(resumed))
    }

    @Test
    fun `vor dem Ende passiert nichts`() {
        val t = Pomodoro.advance(started(0), 99 * sec, s)
        assertTrue(t.events.isEmpty())
        assertEquals(PomodoroPhase.FOCUS, t.state.phase)
    }

    @Test
    fun `Ende der Fokusphase bucht sie und startet die Pause automatisch zum geplanten Ende`() {
        val t = Pomodoro.advance(started(0, doc = 7), 101 * sec, s)
        val e = t.events.single()
        assertEquals(PomodoroPhase.FOCUS, e.phase)
        assertTrue(e.completed)
        assertEquals(100 * sec, e.actualMs)
        assertEquals(7L, e.documentId)
        assertEquals(PomodoroPhase.SHORT_BREAK, t.state.phase)
        assertEquals(PomodoroStatus.RUNNING, t.state.status)
        assertEquals(1, t.state.completedFocus)
        assertEquals(100 * sec, t.state.anchorMillis) // beginnt zum geplanten Ende, nicht erst jetzt
        assertEquals(120 * sec, Pomodoro.endMillis(t.state))
    }

    @Test
    fun `nach der Pause wartet die Fokusphase auf den Start, weil kein Auto-Start`() {
        val inBreak = Pomodoro.advance(started(0), 100 * sec, s).state
        val t = Pomodoro.advance(inBreak, 120 * sec, s)
        assertTrue(t.events.isEmpty()) // Pausen werden nicht gebucht
        assertEquals(PomodoroPhase.FOCUS, t.state.phase)
        assertEquals(PomodoroStatus.WAITING, t.state.status)
        val again = Pomodoro.start(t.state, 130 * sec, documentId = 3)
        assertEquals(PomodoroStatus.RUNNING, again.status)
        assertEquals(3L, again.documentId)
    }

    @Test
    fun `nach drei Fokusphasen kommt die lange Pause und die Runde beginnt von vorn`() {
        val auto = s.copy(autoStartFocus = true)
        var st = Pomodoro.start(Pomodoro.initial(auto), 0)
        var t = 0L
        val order = mutableListOf<PomodoroPhase>()
        repeat(6) {
            t = Pomodoro.endMillis(st)!!
            st = Pomodoro.advance(st, t, auto).state
            order += st.phase
        }
        assertEquals(
            listOf(PomodoroPhase.SHORT_BREAK, PomodoroPhase.FOCUS, PomodoroPhase.SHORT_BREAK, PomodoroPhase.FOCUS, PomodoroPhase.LONG_BREAK, PomodoroPhase.FOCUS),
            order,
        )
        assertEquals(0, st.completedFocus)
    }

    @Test
    fun `spaete Verarbeitung startet die naechste Phase nicht rueckwirkend`() {
        val t = Pomodoro.advance(started(0), 100 * sec + Pomodoro.AUTO_START_GRACE_MS + 1, s)
        assertEquals(PomodoroPhase.SHORT_BREAK, t.state.phase)
        assertEquals(PomodoroStatus.WAITING, t.state.status)
        assertEquals(1, t.events.size) // die Fokusphase selbst zählt vollständig
    }

    @Test
    fun `Ueberspringen der Fokusphase vor der Haelfte zaehlt nicht als abgeschlossen`() {
        val t = Pomodoro.skip(started(0), 30 * sec, s)
        val e = t.events.single()
        assertEquals(false, e.completed)
        assertEquals(30 * sec, e.actualMs)
        assertEquals(PomodoroPhase.SHORT_BREAK, t.state.phase)
        assertEquals(0, t.state.completedFocus)
    }

    @Test
    fun `Ueberspringen nach der Haelfte zaehlt als abgeschlossen`() {
        val t = Pomodoro.skip(started(0), 60 * sec, s)
        assertTrue(t.events.single().completed)
        assertEquals(1, t.state.completedFocus)
    }

    @Test
    fun `Ueberspringen einer Pause bucht nichts und geht zum Fokus`() {
        val inBreak = Pomodoro.advance(started(0), 100 * sec, s).state
        val t = Pomodoro.skip(inBreak, 105 * sec, s)
        assertTrue(t.events.isEmpty())
        assertEquals(PomodoroPhase.FOCUS, t.state.phase)
    }

    @Test
    fun `Stop bucht den angefangenen Fokus als nicht abgeschlossen und setzt zurueck`() {
        val t = Pomodoro.stop(Pomodoro.pause(started(0, doc = 2), 40 * sec), 90 * sec, s)
        val e = t.events.single()
        assertEquals(false, e.completed)
        assertEquals(40 * sec, e.actualMs) // pausierte Zeit zählt nicht
        assertEquals(PomodoroStatus.IDLE, t.state.status)
        assertEquals(0, t.state.completedFocus)
    }

    @Test
    fun `Stop ohne laufende Phase bucht nichts`() {
        assertTrue(Pomodoro.stop(Pomodoro.initial(s), 10, s).events.isEmpty())
    }

    @Test
    fun `Einstellungen aendern die Dauer einer noch nicht gestarteten Phase`() {
        val st = Pomodoro.applySettings(Pomodoro.initial(s), s.copy(focusSeconds = 50))
        assertEquals(50 * sec, Pomodoro.remainingMs(st, 0))
        val running = started(0)
        assertEquals(running, Pomodoro.applySettings(running, s.copy(focusSeconds = 50)))
    }

    @Test
    fun `Zustand laesst sich speichern und lesen`() {
        val st = Pomodoro.pause(started(10 * sec, doc = 9), 40 * sec)
        assertEquals(st, PomodoroState.decode(st.encode()))
        assertNull(PomodoroState.decode("kaputt"))
        val noDoc = Pomodoro.initial(s)
        assertEquals(noDoc, PomodoroState.decode(noDoc.encode()))
    }

    @Test
    fun `Pause laeuft nicht ueber das Phasenende hinaus`() {
        val paused = Pomodoro.pause(started(0), 500 * sec)
        assertEquals(0, Pomodoro.remainingMs(paused, 500 * sec))
        assertEquals(100 * sec, Pomodoro.elapsedMs(paused, 500 * sec))
    }
}

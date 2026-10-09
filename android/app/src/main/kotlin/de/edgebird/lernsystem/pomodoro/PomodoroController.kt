// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.pomodoro

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import de.edgebird.lernsystem.core.pomodoro.Pomodoro
import de.edgebird.lernsystem.core.pomodoro.PomodoroSettings
import de.edgebird.lernsystem.core.pomodoro.PomodoroState
import de.edgebird.lernsystem.core.pomodoro.PomodoroStatus
import de.edgebird.lernsystem.core.pomodoro.Transition
import de.edgebird.lernsystem.data.PomodoroRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * Hält den Timer-Zustand (übersteht das Beenden der App), plant den Alarm für das Phasenende, bucht beendete
 * Fokusphasen und aktualisiert die Benachrichtigungen. Alle Änderungen laufen nacheinander (Mutex).
 */
class PomodoroController(
    private val context: Context,
    private val repo: PomodoroRepository,
    private val documentTitle: suspend (Long) -> String?,
    private val clock: () -> Long = System::currentTimeMillis,
) {
    private val prefs = context.getSharedPreferences("pomodoro", Context.MODE_PRIVATE)
    private val mutex = Mutex()
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val notifier = PomodoroNotifier(context)
    private val alarms = context.getSystemService(AlarmManager::class.java)

    private val _settings = MutableStateFlow(loadSettings())
    val settings: StateFlow<PomodoroSettings> = _settings

    private val _state = MutableStateFlow(loadState())
    val state: StateFlow<PomodoroState> = _state

    private val _goalMinutes = MutableStateFlow(prefs.getInt(KEY_GOAL, 120))
    val goalMinutes: StateFlow<Int> = _goalMinutes

    private val _keepScreenOn = MutableStateFlow(prefs.getBoolean(KEY_KEEP_ON, false))
    val keepScreenOn: StateFlow<Boolean> = _keepScreenOn

    /** Darf die App genaue Alarme setzen? Sonst kommt die Erinnerung ggf. einige Minuten später. */
    fun canScheduleExact(): Boolean = Build.VERSION.SDK_INT < Build.VERSION_CODES.S || alarms.canScheduleExactAlarms()

    // ---- Aktionen --------------------------------------------------------------------------------

    suspend fun start(documentId: Long?) = change { Transition(Pomodoro.start(it, clock(), documentId)) }
    suspend fun pause() = change { Transition(Pomodoro.pause(it, clock())) }
    suspend fun resume() = change { Transition(Pomodoro.resume(it, clock())) }
    suspend fun skip() = change { Pomodoro.skip(it, clock(), _settings.value) }
    suspend fun stop() = change { Pomodoro.stop(it, clock(), _settings.value) }

    /** Wird vom Alarm und vom Sekundentakt der Oberfläche aufgerufen; verarbeitet ein erreichtes Phasenende. */
    suspend fun tick() = change(alertOnPhaseChange = true) { Pomodoro.advance(it, clock(), _settings.value) }

    /** Nach einem Neustart des Geräts: Zustand prüfen und Alarm neu setzen. */
    suspend fun restore() = change(alertOnPhaseChange = true, force = true) { Pomodoro.advance(it, clock(), _settings.value) }

    suspend fun updateSettings(s: PomodoroSettings, goalMinutes: Int, keepScreenOn: Boolean) {
        prefs.edit().putInt("focus_s", s.focusSeconds).putInt("short_s", s.shortBreakSeconds).putInt("long_s", s.longBreakSeconds)
            .putInt("cycles", s.cyclesBeforeLongBreak).putBoolean("auto_breaks", s.autoStartBreaks).putBoolean("auto_focus", s.autoStartFocus)
            .putInt(KEY_GOAL, goalMinutes).putBoolean(KEY_KEEP_ON, keepScreenOn).apply()
        _settings.value = s
        _goalMinutes.value = goalMinutes
        _keepScreenOn.value = keepScreenOn
        change { Transition(Pomodoro.applySettings(it, s)) }
    }

    // ---- Intern ----------------------------------------------------------------------------------

    private suspend fun change(alertOnPhaseChange: Boolean = false, force: Boolean = false, f: (PomodoroState) -> Transition) = mutex.withLock {
        val before = _state.value
        val t = f(before)
        if (!force && t.state == before && t.events.isEmpty()) return@withLock
        t.events.forEach { repo.record(it) }
        val phaseChanged = t.state.phase != before.phase || t.events.isNotEmpty() && t.state.status != before.status
        if (t.state != before) {
            _state.value = t.state
            prefs.edit().putString(KEY_STATE, t.state.encode()).apply()
        }
        schedule(t.state)
        notifier.update(t.state, clock(), t.state.documentId?.let { documentTitle(it) })
        if (alertOnPhaseChange && phaseChanged) notifier.phaseEnded(t.state, _settings.value)
        if (t.state.status == PomodoroStatus.IDLE) notifier.cancelAll()
    }

    private fun schedule(state: PomodoroState) {
        val pi = alarmIntent()
        alarms.cancel(pi)
        val end = Pomodoro.endMillis(state) ?: return
        if (canScheduleExact()) alarms.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, end, pi)
        else alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, end, pi)
    }

    private fun alarmIntent() = PendingIntent.getBroadcast(
        context, 0, Intent(context, PomodoroAlarmReceiver::class.java).setAction(ACTION_ALARM), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )

    private fun loadSettings() = PomodoroSettings(
        prefs.getInt("focus_s", 25 * 60), prefs.getInt("short_s", 5 * 60), prefs.getInt("long_s", 15 * 60),
        prefs.getInt("cycles", 4), prefs.getBoolean("auto_breaks", true), prefs.getBoolean("auto_focus", false),
    )

    private fun loadState(): PomodoroState = prefs.getString(KEY_STATE, null)?.let { PomodoroState.decode(it) } ?: Pomodoro.initial(loadSettings())

    companion object {
        const val ACTION_ALARM = "de.edgebird.lernsystem.pomodoro.ALARM"
        private const val KEY_STATE = "state"
        private const val KEY_GOAL = "goal_min"
        private const val KEY_KEEP_ON = "keep_on"
    }
}

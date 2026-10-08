package de.edgebird.lernsystem.pomodoro

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import de.edgebird.lernsystem.MainActivity
import de.edgebird.lernsystem.core.pomodoro.Pomodoro
import de.edgebird.lernsystem.core.pomodoro.PomodoroPhase
import de.edgebird.lernsystem.core.pomodoro.PomodoroSettings
import de.edgebird.lernsystem.core.pomodoro.PomodoroState
import de.edgebird.lernsystem.core.pomodoro.PomodoroStatus

/** Benachrichtigungen des Timers: eine laufende mit Restzeit (Chronometer) und eine Erinnerung beim Phasenwechsel. */
class PomodoroNotifier(private val context: Context) {
    private val nm = context.getSystemService(NotificationManager::class.java)

    init {
        nm.createNotificationChannel(NotificationChannel(CHANNEL_RUNNING, "Fokus-Timer", NotificationManager.IMPORTANCE_LOW).apply { description = "Zeigt die Restzeit der laufenden Phase" })
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_ALERT, "Fokus-Erinnerung", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Meldet das Ende einer Fokus- oder Pausenphase"
                enableVibration(true)
            },
        )
    }

    private fun openApp(): PendingIntent = PendingIntent.getActivity(
        context, 0, Intent(context, MainActivity::class.java).putExtra(MainActivity.EXTRA_TAB, MainActivity.TAB_FOCUS).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )

    private fun action(name: String, requestCode: Int): PendingIntent = PendingIntent.getBroadcast(
        context, requestCode, Intent(context, PomodoroActionReceiver::class.java).setAction(name), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )

    private fun label(phase: PomodoroPhase) = when (phase) {
        PomodoroPhase.FOCUS -> "Fokus"
        PomodoroPhase.SHORT_BREAK -> "Kurze Pause"
        PomodoroPhase.LONG_BREAK -> "Lange Pause"
    }

    /** Laufende Benachrichtigung passend zum Zustand; bei IDLE wird sie entfernt. */
    fun update(state: PomodoroState, now: Long, documentTitle: String?) {
        if (state.status == PomodoroStatus.IDLE) { nm.cancel(ID_RUNNING); return }
        val b = NotificationCompat.Builder(context, CHANNEL_RUNNING)
            .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentIntent(openApp())
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
        val title = label(state.phase) + if (state.phase == PomodoroPhase.FOCUS && documentTitle != null) " · $documentTitle" else ""
        when (state.status) {
            PomodoroStatus.RUNNING -> {
                b.setContentTitle(title).setContentText("Läuft")
                    .setWhen(Pomodoro.endMillis(state) ?: now).setUsesChronometer(true).setChronometerCountDown(true).setShowWhen(true)
                    .addAction(0, "Pause", action(ACTION_PAUSE, 1))
                    .addAction(0, "Überspringen", action(ACTION_SKIP, 2))
                    .addAction(0, "Beenden", action(ACTION_STOP, 3))
            }
            PomodoroStatus.PAUSED -> {
                val min = (Pomodoro.remainingMs(state, now) / 60_000.0).let { Math.ceil(it).toInt() }
                b.setContentTitle("$title (pausiert)").setContentText("Noch $min Min")
                    .addAction(0, "Fortsetzen", action(ACTION_RESUME, 4))
                    .addAction(0, "Beenden", action(ACTION_STOP, 3))
            }
            else -> {
                b.setContentTitle(label(state.phase) + " bereit").setContentText("Zum Starten tippen")
                    .addAction(0, "Starten", action(ACTION_START, 5))
                    .addAction(0, "Beenden", action(ACTION_STOP, 3))
            }
        }
        nm.notify(ID_RUNNING, b.build())
    }

    /** Erinnerung (mit Ton/Vibration), wenn eine Phase von selbst zu Ende gegangen ist. */
    fun phaseEnded(newState: PomodoroState, settings: PomodoroSettings) {
        val (title, text) = when (newState.phase) {
            PomodoroPhase.SHORT_BREAK -> "Fokus geschafft" to "Pause: ${settings.shortBreakSeconds / 60} Min"
            PomodoroPhase.LONG_BREAK -> "Runde geschafft" to "Lange Pause: ${settings.longBreakSeconds / 60} Min"
            PomodoroPhase.FOCUS -> "Pause vorbei" to "Bereit für den nächsten Fokus?"
        }
        nm.notify(
            ID_ALERT,
            NotificationCompat.Builder(context, CHANNEL_ALERT).setSmallIcon(android.R.drawable.ic_lock_idle_alarm).setContentTitle(title).setContentText(text)
                .setContentIntent(openApp()).setAutoCancel(true).setCategory(NotificationCompat.CATEGORY_ALARM).setPriority(NotificationCompat.PRIORITY_HIGH)
                .setDefaults(NotificationCompat.DEFAULT_ALL).build(),
        )
    }

    fun cancelAll() { nm.cancel(ID_RUNNING); nm.cancel(ID_ALERT) }

    companion object {
        const val CHANNEL_RUNNING = "pomodoro_running"
        const val CHANNEL_ALERT = "pomodoro_alert"
        const val ID_RUNNING = 20
        const val ID_ALERT = 21
        const val ACTION_PAUSE = "de.edgebird.lernsystem.pomodoro.PAUSE"
        const val ACTION_RESUME = "de.edgebird.lernsystem.pomodoro.RESUME"
        const val ACTION_SKIP = "de.edgebird.lernsystem.pomodoro.SKIP"
        const val ACTION_STOP = "de.edgebird.lernsystem.pomodoro.STOP"
        const val ACTION_START = "de.edgebird.lernsystem.pomodoro.START"
    }
}

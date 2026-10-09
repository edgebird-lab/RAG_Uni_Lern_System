// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.pomodoro

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import de.edgebird.lernsystem.LernsystemApp
import kotlinx.coroutines.launch

/** Läuft zum geplanten Ende einer Phase: bucht sie, wechselt zur nächsten und meldet das. */
class PomodoroAlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val controller = (context.applicationContext as LernsystemApp).graph.pomodoro
        val pending = goAsync()
        controller.scope.launch { try { controller.tick() } finally { pending.finish() } }
    }
}

/** Knöpfe der Benachrichtigung (Pause, Fortsetzen, Überspringen, Starten, Beenden). */
class PomodoroActionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val graph = (context.applicationContext as LernsystemApp).graph
        val c = graph.pomodoro
        val pending = goAsync()
        c.scope.launch {
            try {
                when (intent.action) {
                    PomodoroNotifier.ACTION_PAUSE -> c.pause()
                    PomodoroNotifier.ACTION_RESUME -> c.resume()
                    PomodoroNotifier.ACTION_SKIP -> c.skip()
                    PomodoroNotifier.ACTION_START -> c.start(c.state.value.documentId)
                    PomodoroNotifier.ACTION_STOP -> c.stop()
                }
            } finally { pending.finish() }
        }
    }
}

/** Nach dem Neustart des Geräts geht der Alarm verloren: Zustand prüfen und neu planen. */
class PomodoroBootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val c = (context.applicationContext as LernsystemApp).graph.pomodoro
        val pending = goAsync()
        c.scope.launch { try { c.restore() } finally { pending.finish() } }
    }
}

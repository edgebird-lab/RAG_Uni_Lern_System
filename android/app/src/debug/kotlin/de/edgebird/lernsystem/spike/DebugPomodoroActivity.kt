package de.edgebird.lernsystem.spike

import android.app.Activity
import android.os.Bundle
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.pomodoro.PomodoroSettings
import kotlinx.coroutines.runBlocking

/**
 * Startet den Fokus-Timer mit kurzen Dauern, um Alarm, Benachrichtigung und Phasenwechsel auf dem Gerät zu prüfen.
 * `adb shell am start -W -n de.edgebird.lernsystem/.spike.DebugPomodoroActivity --ei focus 20 --ei short 10 --ei long 15 --ei cycles 2`
 */
class DebugPomodoroActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState == null) {
            val c = (application as LernsystemApp).graph.pomodoro
            val s = PomodoroSettings(
                focusSeconds = intent.getIntExtra("focus", 20), shortBreakSeconds = intent.getIntExtra("short", 10), longBreakSeconds = intent.getIntExtra("long", 15),
                cyclesBeforeLongBreak = intent.getIntExtra("cycles", 2), autoStartBreaks = true, autoStartFocus = intent.getBooleanExtra("autofocus", false),
            )
            runBlocking {
                c.stop()
                c.updateSettings(s, c.goalMinutes.value, c.keepScreenOn.value)
                c.start(null)
            }
        }
        finish()
    }
}

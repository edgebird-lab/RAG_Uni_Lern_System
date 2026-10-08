package de.edgebird.lernsystem.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.pomodoro.DayMinutes
import de.edgebird.lernsystem.core.pomodoro.PomodoroSettings
import de.edgebird.lernsystem.core.pomodoro.PomodoroState
import de.edgebird.lernsystem.data.DocumentFocus
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class FocusStatsView(val todayMinutes: Int, val week: List<DayMinutes>, val byDocument: List<DocumentFocus>)

class PomodoroViewModel(app: Application) : AndroidViewModel(app) {
    private val graph = (app as LernsystemApp).graph
    private val controller = graph.pomodoro

    val state: StateFlow<PomodoroState> = controller.state
    val settings: StateFlow<PomodoroSettings> = controller.settings
    val goalMinutes: StateFlow<Int> = controller.goalMinutes
    val keepScreenOn: StateFlow<Boolean> = controller.keepScreenOn
    val documents = graph.db.documents().observeSummaries()

    private val _now = MutableStateFlow(System.currentTimeMillis())
    /** Sekundentakt für die Anzeige; schaltet bei Ablauf auch die Phase weiter, falls der Alarm sich verspätet. */
    val now: StateFlow<Long> = _now

    private val _stats = MutableStateFlow<FocusStatsView?>(null)
    val stats: StateFlow<FocusStatsView?> = _stats

    val exactAlarms: Boolean get() = controller.canScheduleExact()

    init {
        viewModelScope.launch {
            while (true) {
                _now.value = System.currentTimeMillis()
                controller.tick()
                delay(500)
            }
        }
        viewModelScope.launch {
            var last = state.value
            state.collect { if (it.completedFocus != last.completedFocus || it.status != last.status) refreshStats(); last = it }
        }
        refreshStats()
    }

    fun refreshStats() {
        viewModelScope.launch {
            val r = graph.pomodoroRepo
            _stats.value = FocusStatsView(r.todayMinutes(), r.week(), r.byDocument(7))
        }
    }

    fun start(documentId: Long?) = viewModelScope.launch { controller.start(documentId) }
    fun pause() = viewModelScope.launch { controller.pause() }
    fun resume() = viewModelScope.launch { controller.resume() }
    fun skip() = viewModelScope.launch { controller.skip() }
    fun stop() = viewModelScope.launch { controller.stop() }
    fun save(s: PomodoroSettings, goal: Int, keepOn: Boolean) = viewModelScope.launch { controller.updateSettings(s, goal, keepOn) }
}

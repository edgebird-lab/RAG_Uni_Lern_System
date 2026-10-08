package de.edgebird.lernsystem.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.data.SubjectSummary
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/** Zahlen für den Tagesstreifen der Startseite. */
data class DayStrip(val due: Int, val focusMinutes: Int, val focusGoal: Int, val streak: Int)

@OptIn(ExperimentalCoroutinesApi::class)
class HomeViewModel(app: Application) : AndroidViewModel(app) {
    private val graph = (app as LernsystemApp).graph
    private val tick = MutableStateFlow(0)

    /** Fächer mit Zählern; [tick] löst bei Rückkehr zur Startseite eine neue Abfrage aus (Fälligkeiten ändern sich mit der Zeit). */
    val subjects: StateFlow<List<SubjectSummary>?> = tick.flatMapLatest { graph.subjects.observeSummaries(System.currentTimeMillis()) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    private val _strip = MutableStateFlow<DayStrip?>(null)
    val strip: StateFlow<DayStrip?> = _strip

    fun refresh() {
        viewModelScope.launch {
            graph.subjects.adoptOrphans()   // Altbestand aus der Zeit vor den Fächern landet in „Allgemein“
            de.edgebird.lernsystem.data.summary.SummaryRepository(graph.db).adoptLegacy()   // alte Zusammenfassungen in die neue Tabelle
            tick.value++
            val s = graph.study.summary(null)
            _strip.value = DayStrip(s.due, graph.pomodoroRepo.todayMinutes(), graph.pomodoro.goalMinutes.value, s.streak)
        }
    }

    fun create(name: String, color: Int) = viewModelScope.launch { graph.subjects.create(name, color) }
    fun update(id: Long, name: String, color: Int) = viewModelScope.launch { graph.subjects.update(id, name, color) }
    fun delete(id: Long) = viewModelScope.launch { graph.subjects.deleteWithContent(id) }
}

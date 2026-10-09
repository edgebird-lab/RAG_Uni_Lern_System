// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ui

import android.app.Application
import de.edgebird.lernsystem.core.i18n.tr
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
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
            de.edgebird.lernsystem.work.StudyWidgetProvider.refreshAll(getApplication())
            _strip.value = DayStrip(s.due, graph.pomodoroRepo.todayMinutes(), graph.pomodoro.goalMinutes.value, s.streak)
        }
    }

    fun create(name: String, color: Int) = viewModelScope.launch { graph.subjects.create(name, color) }

    /** Legt ein Beispiel-Fach mit zwei kurzen Lehrtexten an (in der Sprache der App), damit man alles ohne eigene Unterlagen ausprobieren kann. */
    fun createExample(onCreated: (Long) -> Unit) {
        viewModelScope.launch {
            val app = getApplication<Application>()
            val dir = "samples/${de.edgebird.lernsystem.core.i18n.Lang.current.tag}"
            val items = withContext(Dispatchers.IO) {
                app.assets.list(dir).orEmpty().filter { it.endsWith(".md") }.map { name ->
                    val file = java.io.File(graph.inboxDir, java.util.UUID.randomUUID().toString())
                    app.assets.open("$dir/$name").use { i -> file.outputStream().use { o -> i.copyTo(o) } }
                    de.edgebird.lernsystem.work.ImportItem("sample:$dir/$name", name, file)
                }
            }
            if (items.isEmpty()) return@launch
            val id = graph.subjects.create(tr("Beispiel: Algorithmen", "Example: Algorithms"))
            de.edgebird.lernsystem.work.ImportWork.enqueue(app, items, graph.prefs.getBoolean("embed_only_when_charging", false), id)
            onCreated(id)
        }
    }
    fun update(id: Long, name: String, color: Int) = viewModelScope.launch { graph.subjects.update(id, name, color) }
    fun delete(id: Long) = viewModelScope.launch { graph.subjects.deleteWithContent(id) }
}

package de.edgebird.lernsystem.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.WorkInfo
import androidx.work.WorkManager
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.summary.SummaryStyle
import de.edgebird.lernsystem.data.SummaryEntity
import de.edgebird.lernsystem.data.summary.SummaryRepository
import de.edgebird.lernsystem.work.SummaryWork
import de.edgebird.lernsystem.work.SummaryWorker
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/** Zustand der Erzeugung eines Stils: läuft (mit Fortschritt), zuletzt fehlgeschlagen oder ruhend. */
data class SummaryJob(val running: Boolean, val done: Int = 0, val total: Int = 0, val error: String? = null, val message: String? = null)

@OptIn(ExperimentalCoroutinesApi::class)
class SummaryViewModel(app: Application) : AndroidViewModel(app) {
    private val graph = (app as LernsystemApp).graph
    private val work = WorkManager.getInstance(app)
    private val repo = SummaryRepository(graph.db)

    private val docId = MutableStateFlow<Long?>(null)
    private val _style = MutableStateFlow(SummaryStyle.BULLETS)
    val style: StateFlow<SummaryStyle> = _style

    private val _title = MutableStateFlow("")
    val title: StateFlow<String> = _title
    private val _sectionCount = MutableStateFlow(0)
    val sectionCount: StateFlow<Int> = _sectionCount

    fun open(id: Long) {
        docId.value = id
        viewModelScope.launch {
            _title.value = graph.db.documents().byId(id)?.title.orEmpty()
            _sectionCount.value = repo.sections(id).size
        }
    }

    fun select(s: SummaryStyle) { _style.value = s }

    /** Fertige Zusammenfassung des gewählten Stils (falls vorhanden). */
    val summary: StateFlow<SummaryEntity?> = combine(docId, _style) { d, s -> d to s }.flatMapLatest { (d, s) ->
        if (d == null) flowOf(null) else repo.observe(d).map { list -> list.firstOrNull { it.style == s.name } }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    val job: StateFlow<SummaryJob> = combine(docId, _style) { d, s -> d to s }.flatMapLatest { (d, s) ->
        if (d == null) flowOf(SummaryJob(false)) else work.getWorkInfosByTagFlow(SummaryWork.tag(d, s)).map { infos ->
            val active = infos.firstOrNull { it.state == WorkInfo.State.RUNNING } ?: infos.firstOrNull { it.state == WorkInfo.State.ENQUEUED || it.state == WorkInfo.State.BLOCKED }
            val last = infos.lastOrNull { it.state == WorkInfo.State.FAILED || it.state == WorkInfo.State.SUCCEEDED }
            when {
                active != null -> SummaryJob(true, active.progress.getInt(SummaryWorker.DONE, 0), active.progress.getInt(SummaryWorker.TOTAL, 0))
                last?.state == WorkInfo.State.FAILED -> SummaryJob(false, error = last.outputData.getString(SummaryWorker.ERROR))
                last != null -> SummaryJob(false, message = last.outputData.getString(SummaryWorker.MESSAGE))
                else -> SummaryJob(false)
            }
        }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), SummaryJob(false))

    fun create(restart: Boolean) {
        val d = docId.value ?: return
        SummaryWork.enqueue(getApplication(), d, _style.value, restart)
    }
}

package de.edgebird.lernsystem.ui

import de.edgebird.lernsystem.core.i18n.tr

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.WorkInfo
import androidx.work.WorkManager
import org.json.JSONObject
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.summary.SummaryFormat
import de.edgebird.lernsystem.core.summary.SummarySpec
import de.edgebird.lernsystem.data.GeneratedSummaryEntity
import de.edgebird.lernsystem.data.SummaryScope
import de.edgebird.lernsystem.data.summary.SummaryRepository
import de.edgebird.lernsystem.data.summary.SummaryRequest
import de.edgebird.lernsystem.data.summary.SummaryRunner
import de.edgebird.lernsystem.work.SummaryWork
import de.edgebird.lernsystem.work.SummaryWorker
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/** Ein laufender oder wartender Auftrag. */
data class RunningJob(val label: String, val done: Int, val total: Int, val queued: Boolean)
data class FailedJob(val label: String, val message: String)
data class JobsState(val running: List<RunningJob> = emptyList(), val failed: List<FailedJob> = emptyList())

/** Geschätzter Aufwand: Modellschritte und Minuten (gemessen: ca. 12 s je Abschnitt, Gegliedert 23 s). */
data class Estimate(val steps: Int, val minutes: Int, val words: Int)

@OptIn(ExperimentalCoroutinesApi::class)
class StudioViewModel(app: Application) : AndroidViewModel(app) {
    private val graph = (app as LernsystemApp).graph
    private val work = WorkManager.getInstance(app)
    private val repo = SummaryRepository(graph.db)
    private val prefs = graph.prefs
    private val subject = MutableStateFlow<Long?>(null)

    fun bind(id: Long) { subject.value = id }

    // ---- Ergebnisse und Aufträge ----------------------------------------------------------------------------------
    val results: StateFlow<List<GeneratedSummaryEntity>> = subject.flatMapLatest { if (it == null) flowOf(emptyList()) else repo.observeForSubject(it) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    /** IDs der Zusammenfassungen, deren Quellen sich seitdem geändert haben. */
    val stale: StateFlow<Set<Long>> = results.map { list -> list.filter { repo.isStale(it) }.map { it.id }.toSet() }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptySet())

    val jobs: StateFlow<JobsState> = subject.flatMapLatest { id ->
        if (id == null) flowOf(JobsState()) else work.getWorkInfosByTagFlow(SummaryWork.subjectTag(id)).map { infos ->
            fun label(i: WorkInfo) = i.tags.firstOrNull { it.startsWith(SummaryWork.LABEL_TAG) }?.removePrefix(SummaryWork.LABEL_TAG).orEmpty().ifEmpty { tr("Zusammenfassung", "Summary") }
            JobsState(
                running = infos.filter { it.state == WorkInfo.State.RUNNING || it.state == WorkInfo.State.ENQUEUED || it.state == WorkInfo.State.BLOCKED }
                    .map { RunningJob(label(it), it.progress.getInt(SummaryWorker.DONE, 0), it.progress.getInt(SummaryWorker.TOTAL, 0), it.state != WorkInfo.State.RUNNING) },
                failed = infos.filter { it.state == WorkInfo.State.FAILED }.map { FailedJob(label(it), it.outputData.getString(SummaryWorker.ERROR) ?: tr("Fehlgeschlagen", "Failed")) },
            )
        }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), JobsState())

    fun dismissFailed() { work.pruneWork() }
    fun cancelAll() { subject.value?.let { work.cancelAllWorkByTag(SummaryWork.subjectTag(it)) } }

    fun observe(id: Long) = repo.observe(id)

    // ---- Einstellungen des Entwurfs -------------------------------------------------------------------------------
    private val _spec = MutableStateFlow(SummarySpec.fromJson(prefs.getString(PREF_LAST, null)))
    val spec: StateFlow<SummarySpec> = _spec

    fun edit(f: (SummarySpec) -> SummarySpec) {
        _spec.value = f(_spec.value).let { it.copy(targetWords = it.targetWords.coerceIn(SummarySpec.MIN_TARGET, SummarySpec.MAX_TARGET)) }
        prefs.edit().putString(PREF_LAST, _spec.value.toJson()).apply()
    }

    private val _templates = MutableStateFlow(loadTemplates())
    /** Eigene Vorlagen (Name → Einstellungen). */
    val templates: StateFlow<Map<String, SummarySpec>> = _templates

    private fun loadTemplates(): Map<String, SummarySpec> = runCatching {
        val o = JSONObject(prefs.getString(PREF_TEMPLATES, "{}"))
        o.keys().asSequence().associateWith { SummarySpec.fromJson(o.getString(it)) }
    }.getOrDefault(emptyMap())

    fun saveTemplate(name: String) {
        val n = name.trim().take(40)
        if (n.isEmpty()) return
        _templates.value = _templates.value + (n to _spec.value)
        persistTemplates()
    }

    fun deleteTemplate(name: String) { _templates.value = _templates.value - name; persistTemplates() }

    private fun persistTemplates() {
        val o = JSONObject(); _templates.value.forEach { (k, v) -> o.put(k, v.toJson()) }
        prefs.edit().putString(PREF_TEMPLATES, o.toString()).apply()
    }

    // ---- Aufwand und Start ----------------------------------------------------------------------------------------
    suspend fun estimate(scope: SummaryScope, docIds: List<Long>, topic: String, spec: SummarySpec): Estimate? {
        val sid = subject.value ?: return null
        if (docIds.isEmpty()) return null
        val runner = SummaryRunner(graph.db, graph.llm, graph.retriever)
        val request = SummaryRequest(sid, scope, docIds, spec, topic)
        val steps = runner.estimateSteps(request)
        val perStep = if (spec.format == SummaryFormat.OUTLINE) 23 else 12
        val words = runner.estimateWords(request)
        return Estimate(steps, maxOf(1, steps * perStep / 60), words)
    }

    fun create(scope: SummaryScope, docIds: List<Long>, topic: String, label: String) {
        val sid = subject.value ?: return
        if (docIds.isEmpty()) return
        SummaryWork.enqueue(getApplication(), SummaryWork.Job(sid, scope, docIds, topic.trim(), _spec.value), label)
    }

    /** Dieselbe Zusammenfassung mit denselben Einstellungen neu erstellen (ersetzt die alte). */
    fun rerun(s: GeneratedSummaryEntity, label: String) {
        SummaryWork.enqueue(getApplication(), SummaryWork.Job(s.subjectId, SummaryScope.valueOf(s.scope), s.docIdList, s.topic, SummarySpec.fromJson(s.specJson), replaceId = s.id, restart = true), label)
    }

    /** Speichert die Zusammenfassung als eigene Quelle im Fach, damit Chat, Abfragen und Karten sie mit nutzen. */
    fun saveAsSource(s: GeneratedSummaryEntity) {
        val title = (tr("Zusammenfassung: ", "Summary: ") + s.title.removePrefix(tr("Zusammenfassung: ", "Summary: "))).take(70).replace(Regex("[\\\\/:*?\"<>|]"), " ")
        val file = java.io.File(graph.inboxDir, java.util.UUID.randomUUID().toString()).also { it.writeText(s.text, Charsets.UTF_8) }
        de.edgebird.lernsystem.work.ImportWork.enqueue(getApplication(), listOf(de.edgebird.lernsystem.work.ImportItem("summary:${s.id}:${s.createdAt}", "$title.md", file)), graph.prefs.getBoolean("embed_only_when_charging", false), s.subjectId)
    }

    fun rename(id: Long, title: String) { viewModelScope.launch { repo.rename(id, title) } }
    fun delete(id: Long) { viewModelScope.launch { repo.delete(id) } }

    /** Für „Einstellungen übernehmen“ aus einer vorhandenen Zusammenfassung. */
    fun adopt(s: GeneratedSummaryEntity) { edit { SummarySpec.fromJson(s.specJson) } }

    companion object {
        private const val PREF_LAST = "summary_last_spec"
        private const val PREF_TEMPLATES = "summary_templates"
    }
}

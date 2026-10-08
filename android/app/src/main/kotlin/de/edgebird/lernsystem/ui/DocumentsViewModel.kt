package de.edgebird.lernsystem.ui

import android.app.Application
import android.net.Uri
import android.provider.OpenableColumns
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.WorkInfo
import androidx.work.WorkManager
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.data.DocumentStatus
import de.edgebird.lernsystem.data.DocumentSummary
import kotlinx.coroutines.flow.flatMapLatest
import de.edgebird.lernsystem.work.CardGenWork
import de.edgebird.lernsystem.work.CardGenWorker
import de.edgebird.lernsystem.work.EmbedWorker
import de.edgebird.lernsystem.work.ImportItem
import de.edgebird.lernsystem.work.ImportWork
import de.edgebird.lernsystem.work.ImportWorker
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.util.UUID

data class EmbedStatus(val done: Int, val total: Int, val running: Boolean, val error: String?)

class DocumentsViewModel(app: Application) : AndroidViewModel(app) {
    private val graph = (app as LernsystemApp).graph
    private val work = WorkManager.getInstance(app)
    private val prefs = app.getSharedPreferences("settings", android.content.Context.MODE_PRIVATE)

    private val _onlyWhenCharging = kotlinx.coroutines.flow.MutableStateFlow(prefs.getBoolean(PREF_CHARGING, false))
    val onlyWhenCharging: StateFlow<Boolean> = _onlyWhenCharging

    fun setOnlyWhenCharging(value: Boolean) {
        prefs.edit().putBoolean(PREF_CHARGING, value).apply()
        _onlyWhenCharging.value = value
    }

    private val subject = kotlinx.coroutines.flow.MutableStateFlow<Long?>(null)
    val subjectId: Long? get() = subject.value

    /** Das Fach, dessen Quellen angezeigt werden (idempotent). */
    fun bind(id: Long) { subject.value = id }

    @OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
    val documents: StateFlow<List<DocumentSummary>> = subject.flatMapLatest { id ->
        if (id == null) kotlinx.coroutines.flow.flowOf(emptyList()) else graph.db.documents().observeSummariesForSubject(id)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    /** Abgewählte Quellen; neue Quellen sind automatisch angehakt. */
    private val excluded = kotlinx.coroutines.flow.MutableStateFlow<Set<Long>>(emptySet())

    /** Angehakte, nutzbare Quellen: der Chat sucht nur hier. */
    val selectedIds: StateFlow<Set<Long>> = kotlinx.coroutines.flow.combine(documents, excluded) { docs, ex ->
        docs.filter { it.document.status != DocumentStatus.FAILED && it.document.id !in ex }.map { it.document.id }.toSet()
    }.stateIn(viewModelScope, SharingStarted.Eagerly, emptySet())

    fun toggle(id: Long) { excluded.value = excluded.value.let { if (id in it) it - id else it + id } }
    fun selectAll() { excluded.value = emptySet() }
    fun selectOnly(id: Long) { excluded.value = documents.value.map { it.document.id }.toSet() - id }

    fun rename(id: Long, title: String) { if (title.isNotBlank()) viewModelScope.launch { graph.db.documents().rename(id, title.trim()) } }

    fun move(id: Long, subject: Long) { viewModelScope.launch { graph.subjects.moveDocument(id, subject) } }

    val embedStatus: StateFlow<EmbedStatus?> = work.getWorkInfosByTagFlow(ImportWork.TAG_EMBED).map { infos ->
        val active = infos.firstOrNull { it.state == WorkInfo.State.RUNNING } ?: infos.firstOrNull { it.state == WorkInfo.State.ENQUEUED || it.state == WorkInfo.State.BLOCKED }
        val failed = infos.firstOrNull { it.state == WorkInfo.State.FAILED }
        when {
            active != null -> EmbedStatus(
                done = active.progress.getInt(EmbedWorker.DONE, 0),
                total = active.progress.getInt(EmbedWorker.TOTAL, 0),
                running = true,
                error = null,
            )
            failed != null -> EmbedStatus(0, 0, running = false, error = failed.outputData.getString(EmbedWorker.ERROR))
            else -> null
        }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    /** Läuft gerade eine Kartenerzeugung? Dann Fortschritt, sonst die letzte Meldung. */
    val cardGenStatus: StateFlow<String?> = work.getWorkInfosByTagFlow(CardGenWork.TAG).map { infos ->
        val running = infos.firstOrNull { it.state == WorkInfo.State.RUNNING || it.state == WorkInfo.State.ENQUEUED }
        when {
            running != null -> "Karten werden erstellt: ${running.progress.getInt(CardGenWorker.CREATED, 0)} von ${running.progress.getInt(CardGenWorker.TOTAL, 0).takeIf { it > 0 } ?: "…"}"
            else -> infos.filter { it.state == WorkInfo.State.SUCCEEDED || it.state == WorkInfo.State.FAILED }.lastOrNull()?.let {
                it.outputData.getString(CardGenWorker.ERROR) ?: it.outputData.getString(CardGenWorker.MESSAGE)
            }
        }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    fun generateCards(documentId: Long, maxCards: Int) = CardGenWork.enqueue(getApplication(), documentId, maxCards)

    val importMessage: StateFlow<String?> = work.getWorkInfosForUniqueWorkFlow(ImportWork.UNIQUE_IMPORT).map { infos ->
        infos.firstOrNull()?.takeIf { it.state == WorkInfo.State.SUCCEEDED }?.outputData?.getString(ImportWorker.MESSAGE)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    /** Kopiert die gewählten Dateien in den App-Speicher und startet den Import im Hintergrund. */
    fun import(uris: List<Uri>) {
        if (uris.isEmpty()) return
        viewModelScope.launch {
            val items = withContext(Dispatchers.IO) {
                val resolver = getApplication<Application>().contentResolver
                uris.mapNotNull { uri ->
                    runCatching {
                        val name = resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
                            if (c.moveToFirst()) c.getString(0) else null
                        } ?: uri.lastPathSegment ?: "datei"
                        val copy = File(graph.inboxDir, UUID.randomUUID().toString())
                        resolver.openInputStream(uri)!!.use { input -> copy.outputStream().use { input.copyTo(it) } }
                        ImportItem(uri.toString(), name, copy)
                    }.getOrNull()
                }
            }
            if (items.isNotEmpty()) ImportWork.enqueue(getApplication(), items, _onlyWhenCharging.value, subject.value)
        }
    }

    fun delete(id: Long) {
        viewModelScope.launch { graph.db.documents().delete(id) }
    }

    private companion object {
        const val PREF_CHARGING = "embed_only_when_charging"
    }
}

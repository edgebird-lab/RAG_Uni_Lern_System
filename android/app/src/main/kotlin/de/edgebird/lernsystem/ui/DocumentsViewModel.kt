package de.edgebird.lernsystem.ui

import de.edgebird.lernsystem.core.i18n.tr

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

    /** Kapitel des Fachs in ihrer Reihenfolge. */
    @OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
    val folders: StateFlow<List<de.edgebird.lernsystem.data.FolderEntity>> = subject.flatMapLatest { id ->
        if (id == null) kotlinx.coroutines.flow.flowOf(emptyList()) else graph.sourceRepo.observeFolders(id)
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

    /** Mehrere Quellen auf einmal an- oder abhaken (Kapitel, Art). */
    fun setChecked(ids: Collection<Long>, checked: Boolean) { excluded.value = if (checked) excluded.value - ids.toSet() else excluded.value + ids }

    fun createFolder(name: String, thenAssign: List<Long> = emptyList()) {
        val sid = subject.value ?: return
        viewModelScope.launch { val id = graph.sourceRepo.createFolder(sid, name); graph.sourceRepo.assign(thenAssign, id) }
    }
    fun renameFolder(id: Long, name: String) { viewModelScope.launch { graph.sourceRepo.renameFolder(id, name) } }
    fun deleteFolder(id: Long) { viewModelScope.launch { graph.sourceRepo.deleteFolder(id) } }
    fun moveFolder(id: Long, delta: Int) { val sid = subject.value ?: return; viewModelScope.launch { graph.sourceRepo.moveFolder(sid, id, delta) } }
    fun assign(ids: List<Long>, folderId: Long?) { viewModelScope.launch { graph.sourceRepo.assign(ids, folderId) } }

    /** Ergebnis des Ziehens: Reihenfolge aller Quellen und ihr Kapitel; nur geänderte Zuordnungen werden geschrieben. */
    fun commitOrder(order: List<Long>, folderOf: Map<Long, Long?>) {
        viewModelScope.launch {
            val current = documents.value.associate { it.document.id to it.document.folderId }
            order.filter { current[it] != folderOf[it] }.groupBy { folderOf[it] }.forEach { (f, ids) -> graph.sourceRepo.assign(ids, f) }
            graph.sourceRepo.applyDocumentOrder(order)
        }
    }

    /** Quellen zum Weitergeben laden (Original und Text) und dann [use] auf dem Hauptthread aufrufen. */
    fun withSources(ids: List<Long>, use: (List<SourceFile>) -> Unit) {
        viewModelScope.launch {
            val files = withContext(Dispatchers.IO) {
                ids.mapNotNull { id ->
                    val doc = graph.db.documents().byId(id) ?: return@mapNotNull null
                    val orig = graph.sources.original(doc)
                    val ext = (orig?.extension ?: doc.filetype).lowercase()
                    val text = (if (orig != null && ext in setOf("md", "txt", "markdown")) runCatching { orig.readText() }.getOrNull() else null)
                        ?: graph.db.chunks().byDocument(id).joinToString("\n\n") { c -> c.location + "\n" + c.text.replace(Regex("^\\[[^\\]]{0,160}]\\n"), "") }
                    SourceFile(doc.title, if (doc.kind == "SUMMARY" || doc.kind == "NOTE") "md" else doc.filetype, orig) { text }
                }
            }
            use(files)
        }
    }

    /** Eine Notiz als Quelle anlegen (Text selbst schreiben). */
    fun addNote(title: String, text: String, folderId: Long?) {
        val sid = subject.value ?: return
        if (text.isBlank()) return
        viewModelScope.launch {
            val name = (title.ifBlank { tr("Notiz", "Note") }).take(60).trim().replace(Regex("[\\\\/:*?\"<>|]"), " ")
            val f = withContext(Dispatchers.IO) { File(graph.inboxDir, UUID.randomUUID().toString()).also { it.writeText("# $name\n\n${text.trim()}\n", Charsets.UTF_8) } }
            ImportWork.enqueue(getApplication(), listOf(ImportItem("note:${UUID.randomUUID()}", "$name.md", f)), _onlyWhenCharging.value, sid, folderId)
        }
    }

    /** Treffer der Volltextsuche in den Quellen des Fachs. */
    data class ContentHit(val documentId: Long, val title: String, val location: String, val chunkIdx: Int, val snippet: String)

    suspend fun searchContent(query: String): List<ContentHit> = withContext(Dispatchers.IO) {
        val ids = documents.value.map { it.document.id }.toSet()
        if (query.isBlank() || ids.isEmpty()) return@withContext emptyList()
        val chunkIds = de.edgebird.lernsystem.data.search.KeywordSearch(graph.db).search(query, 40, ids)
        val byId = graph.db.chunks().withTitles(chunkIds).associateBy { it.chunk.id }
        chunkIds.mapNotNull { byId[it] }.map { c ->
            val text = c.chunk.text.replace(Regex("^\\[[^\\]]{0,160}]\\n"), "").replace(Regex("\\s+"), " ")
            val first = query.trim().split(Regex("\\s+")).firstOrNull { it.length > 2 }?.let { text.indexOf(it, ignoreCase = true) } ?: -1
            val from = if (first > 40) first - 40 else 0
            ContentHit(c.chunk.documentId, c.documentTitle, c.chunk.location, c.chunk.idx, (if (from > 0) "…" else "") + text.substring(from).take(160))
        }
    }

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
            running != null -> tr("Karten werden erstellt: ${running.progress.getInt(CardGenWorker.CREATED, 0)} von ${running.progress.getInt(CardGenWorker.TOTAL, 0).takeIf { it > 0 } ?: "…"}", "Creating cards: ${running.progress.getInt(CardGenWorker.CREATED, 0)} of ${running.progress.getInt(CardGenWorker.TOTAL, 0).takeIf { it > 0 } ?: "…"}")
            else -> infos.filter { it.state == WorkInfo.State.SUCCEEDED || it.state == WorkInfo.State.FAILED }.lastOrNull()?.let {
                it.outputData.getString(CardGenWorker.ERROR) ?: it.outputData.getString(CardGenWorker.MESSAGE)
            }
        }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    /** Meldungen über beendete Aufträge (Import, Kartenerzeugung) ausblenden. */
    fun dismissMessages() { work.pruneWork() }

    fun generateCards(documentId: Long, maxCards: Int, mode: CardGenWork.Mode = CardGenWork.Mode.QA) = CardGenWork.enqueue(getApplication(), documentId, maxCards, mode)

    val importMessage: StateFlow<String?> = work.getWorkInfosForUniqueWorkFlow(ImportWork.UNIQUE_IMPORT).map { infos ->
        infos.firstOrNull()?.takeIf { it.state == WorkInfo.State.SUCCEEDED }?.outputData?.getString(ImportWorker.MESSAGE)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    /** Kopiert die gewählten Dateien in den App-Speicher und startet den Import im Hintergrund. */
    /** Kapitel, in das die nächsten Importe gehen (vom Menü eines Kapitels gesetzt). */
    var importFolder: Long? = null

    fun import(uris: List<Uri>) {
        if (uris.isEmpty()) return
        val folder = importFolder
        viewModelScope.launch {
            val items = withContext(Dispatchers.IO) { ImportHelper.items(getApplication(), graph, uris) }
            if (items.isNotEmpty()) ImportWork.enqueue(getApplication(), items, _onlyWhenCharging.value, subject.value, folder)
        }
    }

    fun delete(id: Long) {
        viewModelScope.launch { graph.db.documents().delete(id); graph.sources.delete(id) }
    }

    private companion object {
        const val PREF_CHARGING = "embed_only_when_charging"
    }
}

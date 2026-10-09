// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ui

import de.edgebird.lernsystem.core.i18n.tr

import android.app.Activity
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.gestures.scrollBy
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyItemScope
import androidx.compose.foundation.lazy.LazyListItemInfo
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TriStateCheckbox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.state.ToggleableState
import androidx.compose.ui.unit.dp
import androidx.compose.ui.zIndex
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import de.edgebird.lernsystem.data.DocumentStatus
import de.edgebird.lernsystem.data.DocumentSummary
import de.edgebird.lernsystem.data.FolderEntity
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Dateitypen, die sich als Quelle importieren lassen (am Ende „alles“, weil manche Geräte Office-Dateien ohne passenden Typ melden). */
private val SOURCE_MIME_TYPES = arrayOf(
    "application/pdf", "text/plain", "text/markdown", "image/jpeg", "image/png", "image/webp",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text", "application/vnd.oasis.opendocument.presentation", "application/octet-stream",
)

/** Zeile der Quellenliste: Kapitel-Kopf, Quelle oder der Kopf „Ohne Kapitel“. */
private sealed interface Row { val key: String }
private class FolderRow(val folder: FolderEntity, val docIds: List<Long>, val expanded: Boolean) : Row { override val key = "f${folder.id}" }
private class DocRow(val doc: DocumentSummary) : Row { override val key = "d${doc.document.id}" }
private object LooseRow : Row { override val key = "loose" }

/** Anordnung aller Quellen: Reihenfolge von oben nach unten und Kapitel je Quelle (`null` = ohne Kapitel). Beim Ziehen als Entwurf geführt. */
private data class Arr(val order: List<Long>, val folderOf: Map<Long, Long?>)

private fun buildRows(arr: Arr, folders: List<FolderEntity>, docs: Map<Long, DocumentSummary>, collapsed: List<Long>, hideEmptyFolders: Boolean): List<Row> {
    val rows = mutableListOf<Row>()
    for (f in folders) {
        val ids = arr.order.filter { arr.folderOf[it] == f.id && it in docs }
        if (hideEmptyFolders && ids.isEmpty()) continue
        val open = f.id !in collapsed
        rows += FolderRow(f, ids, open)
        if (open) ids.forEach { rows += DocRow(docs.getValue(it)) }
    }
    val loose = arr.order.filter { arr.folderOf[it] == null && it in docs }
    if (folders.isNotEmpty()) rows += LooseRow
    loose.forEach { rows += DocRow(docs.getValue(it)) }
    return rows
}

/** Wohin gehört die gezogene Quelle, wenn ihre Mitte über [info] liegt? `null` = keine Änderung. */
private fun retarget(arr: Arr, dragged: Long, items: List<LazyListItemInfo>, center: Float): Arr? {
    val draggedInfo = items.firstOrNull { it.key == "d$dragged" } ?: return null
    val hit = items.firstOrNull { it.key != "d$dragged" && center >= it.offset && center < it.offset + it.size } ?: return null
    val below = hit.offset > draggedInfo.offset
    val mid = hit.offset + hit.size / 2f
    val key = hit.key as? String ?: return null
    val order = arr.order.toMutableList().also { it.remove(dragged) }
    when {
        key.startsWith("d") -> {
            val other = key.drop(1).toLongOrNull() ?: return null
            // Erst wenn die Mitte die Mitte der anderen Zeile überschreitet, damit es nicht flackert
            if (below && center < mid || !below && center > mid) return null
            val at = order.indexOf(other).takeIf { it >= 0 } ?: return null
            order.add(if (below) at + 1 else at, dragged)
            return Arr(order, arr.folderOf + (dragged to arr.folderOf[other]))
        }
        key.startsWith("f") -> {
            val fid = key.drop(1).toLongOrNull() ?: return null
            if (arr.folderOf[dragged] == fid) return null
            val first = order.firstOrNull { arr.folderOf[it] == fid }
            if (first != null) order.add(order.indexOf(first), dragged) else order.add(dragged)
            return Arr(order, arr.folderOf + (dragged to fid))
        }
        key == "loose" -> {
            if (arr.folderOf[dragged] == null) return null
            val first = order.firstOrNull { arr.folderOf[it] == null }
            if (first != null) order.add(order.indexOf(first), dragged) else order.add(dragged)
            return Arr(order, arr.folderOf + (dragged to null))
        }
    }
    return null
}

/**
 * Bereich „Quellen“ eines Fachs: Quellen in Kapiteln ordnen, anhaken (Auswahl für Chat, Quiz und Zusammenfassungen), ansehen, teilen, drucken, speichern.
 * Eine Quelle lässt sich mit langem Drücken und Ziehen verschieben (auch in ein anderes Kapitel).
 */
@OptIn(ExperimentalLayoutApi::class, ExperimentalFoundationApi::class)
@Composable
fun SourcesScreen(subjectId: Long, otherSubjects: List<Pair<Long, String>>, onSummarizeFolder: (Long) -> Unit = {}, vm: DocumentsViewModel = viewModel(key = "docs$subjectId")) {
    LaunchedEffect(subjectId) { vm.bind(subjectId) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val haptic = LocalHapticFeedback.current
    var photo by rememberSaveable { mutableStateOf(false) }
    var viewing by rememberSaveable { mutableStateOf<Long?>(null) }
    var viewChunk by rememberSaveable { mutableStateOf<Int?>(null) }
    val viewRequest by vm.viewRequest.collectAsStateWithLifecycle()
    // Aus dem Chat: „In der Quelle ansehen“ öffnet die Quelle an der zitierten Stelle
    LaunchedEffect(viewRequest) { viewRequest?.let { (doc, idx) -> viewing = doc; viewChunk = idx; vm.consumeViewRequest() } }
    if (photo) { PhotoImportScreen(subjectId, folderId = vm.importFolder, onClose = { photo = false }); return }
    viewing?.let { id -> DocumentViewer(id, startChunk = viewChunk, onClose = { viewing = null; viewChunk = null }); return }

    var addMenu by remember { mutableStateOf(false) }
    val docs by vm.documents.collectAsStateWithLifecycle()
    val folders by vm.folders.collectAsStateWithLifecycle()
    val selected by vm.selectedIds.collectAsStateWithLifecycle()
    val embed by vm.embedStatus.collectAsStateWithLifecycle()
    val message by vm.importMessage.collectAsStateWithLifecycle()
    val cardGen by vm.cardGenStatus.collectAsStateWithLifecycle()
    val onlyCharging by vm.onlyWhenCharging.collectAsStateWithLifecycle()
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris: List<Uri> -> vm.import(uris) }
    var pendingSave by remember { mutableStateOf<SourceFile?>(null) }
    var saveNotice by remember { mutableStateOf<String?>(null) }
    val saver = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("*/*")) { uri ->
        val sf = pendingSave; pendingSave = null
        if (uri != null && sf != null) saveNotice = if (DocumentActions.saveTo(context, uri, sf)) tr("Gespeichert.", "Saved.") else tr("Speichern fehlgeschlagen.", "Saving failed.")
    }
    var cardDialogFor by remember { mutableStateOf<Long?>(null) }
    var renaming by remember { mutableStateOf<DocumentSummary?>(null) }
    var moving by remember { mutableStateOf<DocumentSummary?>(null) }
    var deleting by remember { mutableStateOf<DocumentSummary?>(null) }
    var assigning by remember { mutableStateOf<List<Long>?>(null) }
    var newFolderFor by remember { mutableStateOf<List<Long>?>(null) }   // nicht null: Dialog „Neues Kapitel“, Liste = Quellen, die hineinkommen
    var renamingFolder by remember { mutableStateOf<FolderEntity?>(null) }
    var deletingFolder by remember { mutableStateOf<FolderEntity?>(null) }
    var addingNote by remember { mutableStateOf(false) }
    var headerMenu by remember { mutableStateOf(false) }
    var query by rememberSaveable { mutableStateOf("") }
    var inContent by rememberSaveable { mutableStateOf(false) }
    var sort by rememberSaveable { mutableStateOf(0) }   // 0 eigene Reihenfolge, 1 neueste, 2 Name, 3 Größe
    var collapsed by rememberSaveable { mutableStateOf(listOf<Long>()) }
    var hits by remember { mutableStateOf<List<DocumentsViewModel.ContentHit>>(emptyList()) }
    LaunchedEffect(query, inContent, docs.size) { if (inContent && query.isNotBlank()) { delay(300); hits = vm.searchContent(query) } else hits = emptyList() }

    // Anordnung: aus der Datenbank, nach Sortierung; beim Ziehen ein Entwurf bis die Datenbank nachzieht
    val byId = remember(docs) { docs.associateBy { it.document.id } }
    val filtered = docs.filter { query.isBlank() || inContent || it.document.title.contains(query.trim(), ignoreCase = true) }
    val sorted = when (sort) {
        1 -> filtered.sortedByDescending { it.document.addedAt }
        2 -> filtered.sortedBy { it.document.title.lowercase() }
        3 -> filtered.sortedByDescending { it.chunkCount }
        else -> filtered
    }
    val base = Arr(sorted.map { it.document.id }, docs.associate { it.document.id to it.document.folderId })
    var draft by remember { mutableStateOf<Arr?>(null) }
    var draggedId by remember { mutableStateOf<Long?>(null) }
    var fingerY by remember { mutableStateOf(0f) }
    var startTop by remember { mutableStateOf(0f) }
    LaunchedEffect(docs) { if (draggedId == null) draft = null }
    val arr = draft ?: base
    val rows = buildRows(arr, folders, byId, collapsed, hideEmptyFolders = query.isNotBlank() && !inContent)
    val listState = rememberLazyListState()
    val canDrag = query.isBlank()

    fun startDrag(id: Long) {
        val info = listState.layoutInfo.visibleItemsInfo.firstOrNull { it.key == "d$id" } ?: return
        haptic.performHapticFeedback(HapticFeedbackType.LongPress)
        // Aus einer anderen Sortierung wird die gerade sichtbare Reihenfolge zur eigenen
        if (sort != 0) sort = 0
        draft = arr; draggedId = id; startTop = info.offset.toFloat(); fingerY = 0f
    }
    fun dragBy(dy: Float) {
        val id = draggedId ?: return
        fingerY += dy
        val items = listState.layoutInfo.visibleItemsInfo
        val me = items.firstOrNull { it.key == "d$id" } ?: return
        val top = startTop + fingerY
        retarget(draft ?: arr, id, items, top + me.size / 2f)?.let { draft = it }
        val viewport = listState.layoutInfo.viewportEndOffset
        if (top < 120f) scope.launch { listState.scrollBy(-28f) } else if (top + me.size > viewport - 120f) scope.launch { listState.scrollBy(28f) }
    }
    fun endDrag() {
        val d = draft
        draggedId = null; fingerY = 0f
        if (d != null) vm.commitOrder(d.order, d.folderOf) else draft = null
    }

    val kindCount = docs.groupingBy { it.document.kind }.eachCount()
    fun idsOfKind(k: String) = docs.filter { it.document.kind == k && it.document.status != DocumentStatus.FAILED }.map { it.document.id }

    Box(Modifier.fillMaxSize()) {
        LazyColumn(state = listState, contentPadding = androidx.compose.foundation.layout.PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 100.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item(key = "head") {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(tr("Quellen", "Sources"), Modifier.weight(1f), style = MaterialTheme.typography.headlineMedium)
                        Box {
                            IconButton(onClick = { headerMenu = true }) { Icon(Icons.Default.MoreVert, contentDescription = tr("Aktionen für Quellen", "Actions for sources")) }
                            DropdownMenu(expanded = headerMenu, onDismissRequest = { headerMenu = false }) {
                                DropdownMenuItem(text = { Text(tr("Neues Kapitel …", "New chapter …")) }, onClick = { headerMenu = false; newFolderFor = emptyList() })
                                DropdownMenuItem(text = { Text(tr("Alle anhaken", "Check all")) }, onClick = { headerMenu = false; vm.selectAll() })
                                DropdownMenuItem(text = { Text(tr("Alle abwählen", "Uncheck all")) }, onClick = { headerMenu = false; vm.setChecked(docs.map { it.document.id }, false) })
                                DropdownMenuItem(text = { Text(tr("Angehakte teilen …", "Share checked …")) }, enabled = selected.isNotEmpty(), onClick = { headerMenu = false; vm.withSources(selected.toList()) { DocumentActions.shareMany(context, it) } })
                                DropdownMenuItem(text = { Text(tr("Angehakte in Kapitel legen …", "Put checked into chapter …")) }, enabled = selected.isNotEmpty(), onClick = { headerMenu = false; assigning = selected.toList() })
                            }
                        }
                    }
                    Text(tr("Der Chat nutzt nur angehakte Quellen. Tippen: ansehen. Halten und ziehen: verschieben.", "The chat only uses checked sources. Tap: view. Press and hold, then drag: move."), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    embed?.takeIf { it.running }?.let { e ->
                        Text(if (e.total > 0) tr("Indexiere: ${e.done} von ${e.total} Abschnitten", "Indexing: ${e.done} of ${e.total} sections") else tr("Indexierung startet …", "Indexing is starting …"), style = MaterialTheme.typography.bodySmall)
                        if (e.total > 0) LinearProgressIndicator(progress = { e.done.toFloat() / e.total }, modifier = Modifier.fillMaxWidth())
                    }
                    embed?.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                    message?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                    cardGen?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                    saveNotice?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary) }
                    if (message != null || cardGen?.startsWith(tr("Karten werden erstellt", "Cards are being created")) == false) TextButton(onClick = vm::dismissMessages) { Text(tr("Meldung schließen", "Dismiss message")) }
                }
            }
            if (docs.size > 1) item(key = "tools") {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    OutlinedTextField(value = query, onValueChange = { query = it }, label = { Text(if (inContent) tr("Im Inhalt der Quellen suchen", "Search the content of the sources") else tr("Quellen suchen", "Search sources")) }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip(selected = inContent, onClick = { inContent = !inContent }, label = { Text(tr("Im Inhalt", "In content")) })
                        listOf(tr("Eigene", "Custom"), tr("Neueste", "Newest"), tr("Name", "Name"), tr("Größe", "Size")).forEachIndexed { i, l -> FilterChip(selected = sort == i, onClick = { sort = i }, label = { Text(l) }) }
                    }
                    if (kindCount.getOrDefault("SUMMARY", 0) + kindCount.getOrDefault("NOTE", 0) > 0) FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(tr("Einbeziehen:", "Include:"), Modifier.padding(top = 10.dp), style = MaterialTheme.typography.labelLarge)
                        for ((k, label) in listOf("SUMMARY" to tr("Zusammenfassungen", "Summaries"), "NOTE" to tr("Notizen", "Notes"))) {
                            val ids = idsOfKind(k)
                            if (ids.isNotEmpty()) FilterChip(selected = ids.all { it in selected }, onClick = { vm.setChecked(ids, !ids.all { it in selected }) }, label = { Text("$label (${ids.size})") })
                        }
                    }
                    if (query.isNotBlank() && !inContent && rows.none { it is DocRow }) Text(tr("Keine Quelle mit „$query“ im Namen.", "No source with “$query” in its name."), style = MaterialTheme.typography.bodySmall)
                }
            }
            if (docs.isEmpty() && folders.isEmpty()) item(key = "empty") {
                Text(tr("Noch keine Quellen. Tippe auf „Quelle hinzufügen“ und wähle PDFs oder Textdateien.", "No sources yet. Tap “Add source” and choose PDFs or text files."), style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(vertical = 24.dp))
            }
            if (inContent && query.isNotBlank()) {
                if (hits.isEmpty()) item(key = "nohits") { Text(tr("Keine Treffer im Inhalt.", "No matches in the content."), style = MaterialTheme.typography.bodySmall) }
                items(hits, key = { "h${it.documentId}-${it.chunkIdx}" }) { h ->
                    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface), modifier = Modifier.fillMaxWidth().clickable { viewChunk = h.chunkIdx; viewing = h.documentId }) {
                        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text("${h.title} · ${h.location}", style = MaterialTheme.typography.titleSmall)
                            Text(h.snippet, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            } else items(rows, key = { it.key }) { row ->
                when (row) {
                    is FolderRow -> FolderHeader(
                        row, selectedCount = row.docIds.count { it in selected },
                        onToggleOpen = { collapsed = if (row.folder.id in collapsed) collapsed - row.folder.id else collapsed + row.folder.id },
                        onCheck = { vm.setChecked(row.docIds, !(row.docIds.isNotEmpty() && row.docIds.all { it in selected })) },
                        onRename = { renamingFolder = row.folder }, onDelete = { deletingFolder = row.folder },
                        onUp = { vm.moveFolder(row.folder.id, -1) }, onDown = { vm.moveFolder(row.folder.id, 1) },
                        onAddFile = { vm.importFolder = row.folder.id; picker.launch(SOURCE_MIME_TYPES) },
                        onAddPhoto = { vm.importFolder = row.folder.id; photo = true },
                        onSummarize = { onSummarizeFolder(row.folder.id) },
                        onShare = { vm.withSources(row.docIds) { DocumentActions.shareMany(context, it) } },
                    )
                    LooseRow -> Text(tr("Ohne Kapitel", "Without chapter"), Modifier.padding(top = 6.dp, start = 4.dp), style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    is DocRow -> {
                        val d = row.doc
                        val id = d.document.id
                        val dragging = draggedId == id
                        Box(
                            Modifier.padding(start = if (arr.folderOf[id] != null) 14.dp else 0.dp)
                                .then(if (dragging) Modifier.zIndex(2f).graphicsLayer {
                                    val cur = listState.layoutInfo.visibleItemsInfo.firstOrNull { it.key == "d$id" }?.offset ?: startTop.toInt()
                                    translationY = startTop + fingerY - cur; shadowElevation = 24f; alpha = 0.95f
                                } else Modifier)
                                .pointerInput(id, canDrag) { if (canDrag) detectDragGesturesAfterLongPress(onDragStart = { startDrag(id) }, onDrag = { c, a -> c.consume(); dragBy(a.y) }, onDragEnd = { endDrag() }, onDragCancel = { endDrag() }) },
                        ) {
                            SourceRow(
                                d, checked = id in selected, onToggle = { vm.toggle(id) }, onOpen = { viewing = id; viewChunk = null },
                                onShare = { vm.withSources(listOf(id)) { DocumentActions.shareMany(context, it) } },
                                onPrint = { vm.withSources(listOf(id)) { l -> (context as? Activity)?.let { DocumentActions.print(it, l.first(), markdown = d.document.kind == "SUMMARY" || d.document.kind == "NOTE" || d.document.filetype == "md") } } },
                                onSave = { vm.withSources(listOf(id)) { l -> pendingSave = l.first(); saver.launch(DocumentActions.suggestedName(l.first())) } },
                                onAssign = { assigning = listOf(id) },
                                onCards = { cardDialogFor = id }, onRename = { renaming = d }, onMove = { moving = d }, onDelete = { deleting = d },
                                canMove = otherSubjects.isNotEmpty(), dragging = dragging,
                            )
                        }
                    }
                }
            }
            if (docs.isNotEmpty()) item(key = "charging") {
                Row(Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(tr("Nur am Ladegerät indexieren", "Index only while charging"), Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                    Switch(checked = onlyCharging, onCheckedChange = vm::setOnlyWhenCharging)
                }
            }
        }
        Box(Modifier.align(Alignment.BottomEnd).padding(16.dp)) {
            ExtendedFloatingActionButton(
                onClick = { addMenu = true },
                icon = { Icon(Icons.Default.Add, null) }, text = { Text(tr("Quelle hinzufügen", "Add source")) },
                containerColor = MaterialTheme.colorScheme.primary, contentColor = MaterialTheme.colorScheme.onPrimary,
            )
            DropdownMenu(expanded = addMenu, onDismissRequest = { addMenu = false }) {
                DropdownMenuItem(text = { Text(tr("Datei wählen (PDF, Text, Bild)", "Choose file (PDF, text, image)")) }, onClick = { addMenu = false; vm.importFolder = null; picker.launch(SOURCE_MIME_TYPES) })
                DropdownMenuItem(text = { Text(tr("Foto aufnehmen oder Bilder wählen", "Take a photo or choose images")) }, onClick = { addMenu = false; vm.importFolder = null; photo = true })
                DropdownMenuItem(text = { Text(tr("Notiz schreiben", "Write a note")) }, onClick = { addMenu = false; addingNote = true })
                DropdownMenuItem(text = { Text(tr("Neues Kapitel", "New chapter")) }, onClick = { addMenu = false; newFolderFor = emptyList() })
            }
        }
    }

    cardDialogFor?.let { id -> CardCountDialog(onPick = { n, m -> vm.generateCards(id, n, m); cardDialogFor = null }, onDismiss = { cardDialogFor = null }) }
    renaming?.let { d ->
        var text by remember(d.document.id) { mutableStateOf(d.document.title) }
        AlertDialog(
            onDismissRequest = { renaming = null }, title = { Text(tr("Quelle umbenennen", "Rename source")) },
            text = { OutlinedTextField(value = text, onValueChange = { text = it.take(120) }, singleLine = true, modifier = Modifier.fillMaxWidth()) },
            confirmButton = { TextButton(onClick = { vm.rename(d.document.id, text); renaming = null }, enabled = text.isNotBlank()) { Text(tr("Speichern", "Save")) } },
            dismissButton = { TextButton(onClick = { renaming = null }) { Text(tr("Abbrechen", "Cancel")) } },
        )
    }
    moving?.let { d ->
        AlertDialog(
            onDismissRequest = { moving = null }, title = { Text(tr("In welches Fach verschieben?", "Move to which subject?")) },
            text = { Column { otherSubjects.forEach { (id, name) -> TextButton(onClick = { vm.move(d.document.id, id); moving = null }) { Text(displaySubjectName(name)) } } } },
            confirmButton = {}, dismissButton = { TextButton(onClick = { moving = null }) { Text(tr("Abbrechen", "Cancel")) } },
        )
    }
    deleting?.let { d ->
        AlertDialog(
            onDismissRequest = { deleting = null }, title = { Text(tr("Quelle löschen?", "Delete source?")) },
            text = { Text(tr("„${d.document.title}“ wird samt Abschnitten und gespeichertem Original gelöscht. Karten daraus bleiben erhalten.", "“${d.document.title}” is deleted with its sections and stored original. Cards made from it are kept.")) },
            confirmButton = { TextButton(onClick = { vm.delete(d.document.id); deleting = null }) { Text(tr("Löschen", "Delete"), color = MaterialTheme.colorScheme.error) } },
            dismissButton = { TextButton(onClick = { deleting = null }) { Text(tr("Abbrechen", "Cancel")) } },
        )
    }
    assigning?.let { ids ->
        AlertDialog(
            onDismissRequest = { assigning = null }, title = { Text(tr("In welches Kapitel?", "Into which chapter?")) },
            text = {
                Column {
                    folders.forEach { f -> TextButton(onClick = { vm.assign(ids, f.id); assigning = null }) { Text(f.name) } }
                    TextButton(onClick = { vm.assign(ids, null); assigning = null }) { Text(tr("Ohne Kapitel", "Without chapter")) }
                    TextButton(onClick = { newFolderFor = ids; assigning = null }) { Text(tr("Neues Kapitel …", "New chapter …")) }
                }
            },
            confirmButton = {}, dismissButton = { TextButton(onClick = { assigning = null }) { Text(tr("Abbrechen", "Cancel")) } },
        )
    }
    newFolderFor?.let { ids ->
        var name by remember { mutableStateOf("") }
        AlertDialog(
            onDismissRequest = { newFolderFor = null }, title = { Text(tr("Neues Kapitel", "New chapter")) },
            text = { OutlinedTextField(value = name, onValueChange = { name = it.take(80) }, singleLine = true, label = { Text(tr("Name des Kapitels", "Name of the chapter")) }, modifier = Modifier.fillMaxWidth()) },
            confirmButton = { TextButton(onClick = { vm.createFolder(name, ids); newFolderFor = null }, enabled = name.isNotBlank()) { Text(tr("Anlegen", "Create")) } },
            dismissButton = { TextButton(onClick = { newFolderFor = null }) { Text(tr("Abbrechen", "Cancel")) } },
        )
    }
    renamingFolder?.let { f ->
        var name by remember(f.id) { mutableStateOf(f.name) }
        AlertDialog(
            onDismissRequest = { renamingFolder = null }, title = { Text(tr("Kapitel umbenennen", "Rename chapter")) },
            text = { OutlinedTextField(value = name, onValueChange = { name = it.take(80) }, singleLine = true, modifier = Modifier.fillMaxWidth()) },
            confirmButton = { TextButton(onClick = { vm.renameFolder(f.id, name); renamingFolder = null }, enabled = name.isNotBlank()) { Text(tr("Speichern", "Save")) } },
            dismissButton = { TextButton(onClick = { renamingFolder = null }) { Text(tr("Abbrechen", "Cancel")) } },
        )
    }
    deletingFolder?.let { f ->
        AlertDialog(
            onDismissRequest = { deletingFolder = null }, title = { Text(tr("Kapitel löschen?", "Delete chapter?")) },
            text = { Text(tr("Das Kapitel „${f.name}“ wird gelöscht. Die Quellen darin bleiben im Fach, ohne Kapitel.", "The chapter “${f.name}” is deleted. The sources in it stay in the subject, without chapter.")) },
            confirmButton = { TextButton(onClick = { vm.deleteFolder(f.id); deletingFolder = null }) { Text(tr("Löschen", "Delete"), color = MaterialTheme.colorScheme.error) } },
            dismissButton = { TextButton(onClick = { deletingFolder = null }) { Text(tr("Abbrechen", "Cancel")) } },
        )
    }
    if (addingNote) {
        var title by remember { mutableStateOf("") }
        var text by remember { mutableStateOf("") }
        AlertDialog(
            onDismissRequest = { addingNote = false }, title = { Text(tr("Notiz schreiben", "Write a note")) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = title, onValueChange = { title = it.take(60) }, singleLine = true, label = { Text(tr("Titel", "Title")) }, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(value = text, onValueChange = { text = it }, label = { Text(tr("Text", "Text")) }, modifier = Modifier.fillMaxWidth(), minLines = 5)
                }
            },
            confirmButton = { TextButton(onClick = { vm.addNote(title, text, null); addingNote = false }, enabled = text.isNotBlank()) { Text(tr("Als Quelle speichern", "Save as source")) } },
            dismissButton = { TextButton(onClick = { addingNote = false }) { Text(tr("Abbrechen", "Cancel")) } },
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun FolderHeader(
    row: FolderRow, selectedCount: Int, onToggleOpen: () -> Unit, onCheck: () -> Unit, onRename: () -> Unit, onDelete: () -> Unit, onUp: () -> Unit, onDown: () -> Unit,
    onAddFile: () -> Unit, onAddPhoto: () -> Unit, onSummarize: () -> Unit, onShare: () -> Unit,
) {
    var menu by remember { mutableStateOf(false) }
    val n = row.docIds.size
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer), modifier = Modifier.fillMaxWidth().clickable { onToggleOpen() }) {
        Row(Modifier.padding(start = 4.dp, end = 4.dp, top = 2.dp, bottom = 2.dp), verticalAlignment = Alignment.CenterVertically) {
            TriStateCheckbox(
                state = when { n == 0 || selectedCount == 0 -> ToggleableState.Off; selectedCount == n -> ToggleableState.On; else -> ToggleableState.Indeterminate },
                onClick = onCheck, enabled = n > 0,
            )
            Column(Modifier.weight(1f)) {
                Text(row.folder.name, style = MaterialTheme.typography.titleMedium)
                Text(tr("$n ${if (n == 1) "Quelle" else "Quellen"}${if (!row.expanded) " · eingeklappt" else ""}", "$n ${if (n == 1) "source" else "sources"}${if (!row.expanded) " · collapsed" else ""}"), style = MaterialTheme.typography.bodySmall)
            }
            Text(if (row.expanded) "▾" else "▸", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(horizontal = 8.dp))
            Box {
                IconButton(onClick = { menu = true }) { Icon(Icons.Default.MoreVert, contentDescription = tr("Aktionen für Kapitel ${row.folder.name}", "Actions for chapter ${row.folder.name}")) }
                DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                    DropdownMenuItem(text = { Text(tr("Datei in dieses Kapitel …", "Add file to this chapter …")) }, onClick = { menu = false; onAddFile() })
                    DropdownMenuItem(text = { Text(tr("Foto in dieses Kapitel …", "Add photo to this chapter …")) }, onClick = { menu = false; onAddPhoto() })
                    DropdownMenuItem(text = { Text(tr("Kapitel zusammenfassen …", "Summarise chapter …")) }, enabled = n > 0, onClick = { menu = false; onSummarize() })
                    DropdownMenuItem(text = { Text(tr("Alle Quellen teilen …", "Share all sources …")) }, enabled = n > 0, onClick = { menu = false; onShare() })
                    DropdownMenuItem(text = { Text(tr("Umbenennen …", "Rename …")) }, onClick = { menu = false; onRename() })
                    DropdownMenuItem(text = { Text(tr("Nach oben", "Move up")) }, onClick = { menu = false; onUp() })
                    DropdownMenuItem(text = { Text(tr("Nach unten", "Move down")) }, onClick = { menu = false; onDown() })
                    DropdownMenuItem(text = { Text(tr("Kapitel löschen", "Delete chapter"), color = MaterialTheme.colorScheme.error) }, onClick = { menu = false; onDelete() })
                }
            }
        }
    }
}

@Composable
private fun SourceRow(
    d: DocumentSummary, checked: Boolean, onToggle: () -> Unit, onOpen: () -> Unit, onShare: () -> Unit, onPrint: () -> Unit, onSave: () -> Unit, onAssign: () -> Unit,
    onCards: () -> Unit, onRename: () -> Unit, onMove: () -> Unit, onDelete: () -> Unit, canMove: Boolean, dragging: Boolean,
) {
    var menu by remember { mutableStateOf(false) }
    val failed = d.document.status == DocumentStatus.FAILED
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface), modifier = Modifier.fillMaxWidth().clickable(enabled = !dragging) { onOpen() },
        elevation = CardDefaults.cardElevation(defaultElevation = if (dragging) 8.dp else 0.dp),
    ) {
        Row(Modifier.padding(start = 4.dp, end = 4.dp, top = 4.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Checkbox(checked = checked, onCheckedChange = { onToggle() }, enabled = !failed)
            Column(Modifier.weight(1f)) {
                Text(d.document.title, style = MaterialTheme.typography.titleMedium)
                val status = when (d.document.status) { DocumentStatus.INDEXED -> tr("bereit", "ready"); DocumentStatus.PENDING -> tr("wird indexiert", "being indexed"); DocumentStatus.FAILED -> tr("Fehler", "Error") }
                val kind = when (d.document.kind) { "SUMMARY" -> tr("Zusammenfassung", "Summary"); "NOTE" -> tr("Notiz", "Note"); "PHOTO" -> tr("Foto", "Photo"); else -> d.document.filetype.uppercase() }
                Text(tr("$kind · ${d.chunkCount} Abschnitte · $status", "$kind · ${d.chunkCount} sections · $status"), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Box {
                IconButton(onClick = { menu = true }) { Icon(Icons.Default.MoreVert, contentDescription = tr("Aktionen für ${d.document.title}", "Actions for ${d.document.title}")) }
                DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                    DropdownMenuItem(text = { Text(tr("Ansehen", "View")) }, onClick = { menu = false; onOpen() })
                    DropdownMenuItem(text = { Text(tr("Teilen / Weiterleiten …", "Share / forward …")) }, onClick = { menu = false; onShare() })
                    DropdownMenuItem(text = { Text(tr("Drucken …", "Print …")) }, onClick = { menu = false; onPrint() })
                    DropdownMenuItem(text = { Text(tr("Speichern unter … (Download)", "Save as … (download)")) }, onClick = { menu = false; onSave() })
                    DropdownMenuItem(text = { Text(tr("In Kapitel legen …", "Put into chapter …")) }, onClick = { menu = false; onAssign() })
                    DropdownMenuItem(text = { Text(tr("Karten erzeugen …", "Generate cards …")) }, enabled = d.document.status == DocumentStatus.INDEXED, onClick = { menu = false; onCards() })
                    DropdownMenuItem(text = { Text(tr("Umbenennen …", "Rename …")) }, onClick = { menu = false; onRename() })
                    if (canMove) DropdownMenuItem(text = { Text(tr("In anderes Fach verschieben …", "Move to another subject …")) }, onClick = { menu = false; onMove() })
                    DropdownMenuItem(text = { Text(tr("Löschen …", "Delete …"), color = MaterialTheme.colorScheme.error) }, onClick = { menu = false; onDelete() })
                }
            }
        }
    }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun CardCountDialog(onPick: (Int, de.edgebird.lernsystem.work.CardGenWork.Mode) -> Unit, onDismiss: () -> Unit) {
    var mode by remember { mutableStateOf(de.edgebird.lernsystem.work.CardGenWork.Mode.QA) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(tr("Karten erzeugen", "Generate cards")) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(tr("Art der Karten", "Type of cards"), style = MaterialTheme.typography.labelLarge)
                androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    de.edgebird.lernsystem.work.CardGenWork.Mode.entries.forEach { m -> androidx.compose.material3.FilterChip(selected = mode == m, onClick = { mode = m }, label = { Text(m.label) }) }
                }
                Text(mode.hint, style = MaterialTheme.typography.bodySmall)
                Text(tr("Die App erstellt die Karten im Hintergrund aus gleichmäßig verteilten Abschnitten. Das Display sollte dabei an bleiben.", "The app creates the cards in the background from evenly distributed sections. The display should stay on."), style = MaterialTheme.typography.bodySmall)
                Text(tr("Wie viele Karten?", "How many cards?"), style = MaterialTheme.typography.labelLarge)
                Row { listOf(10, 20, 40).forEach { n -> TextButton(onClick = { onPick(n, mode) }) { Text("$n") } } }
            }
        },
        confirmButton = {},
        dismissButton = { TextButton(onClick = onDismiss) { Text(tr("Abbrechen", "Cancel")) } },
    )
}

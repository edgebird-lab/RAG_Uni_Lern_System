// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ui

import de.edgebird.lernsystem.core.i18n.tr

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import de.edgebird.lernsystem.data.chat.Source

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
fun ChatScreen(subjectId: Long, onModels: () -> Unit = {}, onOpenSources: () -> Unit = {}, vm: ChatViewModel = viewModel(key = "chat$subjectId"), docsVm: DocumentsViewModel = viewModel(key = "docs$subjectId")) {
    androidx.compose.runtime.LaunchedEffect(subjectId) { docsVm.bind(subjectId); vm.bindSubject(subjectId) }
    val context = androidx.compose.ui.platform.LocalContext.current
    val docs by docsVm.documents.collectAsStateWithLifecycle()
    val selected by docsVm.selectedIds.collectAsStateWithLifecycle()
    androidx.compose.runtime.LaunchedEffect(selected) { vm.setScope(selected) }
    val speaker = rememberSpeechOutput()
    var picking by remember { mutableStateOf(false) }
    var speechBase by remember { mutableStateOf("") }
    val messages by vm.messages.collectAsStateWithLifecycle()
    val modelState by vm.modelState.collectAsStateWithLifecycle()
    val loadError by vm.loadError.collectAsStateWithLifecycle()
    val chats by vm.sessions.collectAsStateWithLifecycle()
    val currentChat by vm.currentSession.collectAsStateWithLifecycle()
    var chatMenu by remember { mutableStateOf(false) }
    var input by rememberSaveable { mutableStateOf("") }
    val speech = rememberSpeech(
        onPartial = { input = (speechBase.trim() + " " + it).trim() },
        onFinal = { input = (speechBase.trim() + " " + it).trim() },
    )
    var openSource by remember { mutableStateOf<Source?>(null) }
    val listState = rememberLazyListState()
    val keyboard = androidx.compose.ui.platform.LocalSoftwareKeyboardController.current
    val focus = androidx.compose.ui.platform.LocalFocusManager.current
    val streaming = messages.lastOrNull()?.streaming == true
    // Während der Optimierung darf das Display nicht ausgehen, sonst bremst die GPU-Arbeit stark
    val view = androidx.compose.ui.platform.LocalView.current
    androidx.compose.runtime.DisposableEffect(modelState) {
        view.keepScreenOn = modelState == ModelState.OPTIMIZING || modelState == ModelState.LOADING
        onDispose { view.keepScreenOn = false }
    }

    LaunchedEffect(messages.size, messages.lastOrNull()?.text?.length) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.lastIndex)
    }

    Column(Modifier.fillMaxSize().imePadding().padding(horizontal = 16.dp, vertical = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            androidx.compose.material3.AssistChip(
                onClick = { picking = true },
                label = { Text(if (docs.isEmpty()) tr("Keine Quellen", "No sources") else tr("${selected.size} von ${docs.size} Quellen", "${selected.size} of ${docs.size} sources")) },
                modifier = Modifier.weight(1f, fill = false),
            )
            androidx.compose.foundation.layout.Spacer(Modifier.weight(1f))
            Box {
                TextButton(onClick = { chatMenu = true }) { Text(if (chats.size > 1 || (chats.isNotEmpty() && messages.isEmpty())) tr("Chats (${chats.size}) ▾", "Chats (${chats.size}) ▾") else tr("Chats ▾", "Chats ▾")) }
                androidx.compose.material3.DropdownMenu(expanded = chatMenu, onDismissRequest = { chatMenu = false }) {
                    androidx.compose.material3.DropdownMenuItem(text = { Text(tr("Neuer Chat", "New chat")) }, onClick = { chatMenu = false; vm.newChat() })
                    chats.forEach { c ->
                        androidx.compose.material3.DropdownMenuItem(
                            text = { Text((if (c.id == currentChat) "✓ " else "") + c.title, maxLines = 1) },
                            onClick = { chatMenu = false; vm.openSession(c.id) },
                            trailingIcon = { TextButton(onClick = { chatMenu = false; vm.deleteSession(c.id) }) { Text(tr("Löschen", "Delete")) } },
                        )
                    }
                }
            }
        }
        when (modelState) {
            ModelState.MISSING -> Banner(tr("Das Sprachmodell fehlt.", "The language model is missing."), error = true, actionLabel = tr("Modelle laden", "Download models"), onAction = onModels)
            ModelState.LOADING -> Banner(tr("Sprachmodell wird geladen (ca. 25 Sekunden).", "Loading language model (about 25 seconds)."))
            ModelState.OPTIMIZING -> Banner(tr("Erster Start: Die App optimiert das Sprachmodell für dein Gerät. Das dauert einmalig 5 bis 10 Minuten. Bitte Display an und die App geöffnet lassen.", "First start: the app optimises the language model for your device. This takes 5 to 10 minutes once. Please keep the display on and the app open."))
            ModelState.ERROR -> Banner(
                tr("Das Sprachmodell konnte nicht geladen werden", "The language model could not be loaded") + (loadError?.let { ": $it" } ?: "") + tr(". Hilft ein erneuter Versuch nicht, ist die Datei evtl. beschädigt (unter „KI-Modelle“ neu laden).", ". If trying again does not help, the file may be damaged (re-download under “AI models”)."),
                error = true, actionLabel = tr("Erneut versuchen", "Try again"), onAction = vm::retryLoad,
            )
            ModelState.READY -> Unit
        }
        Box(Modifier.weight(1f).fillMaxWidth()) {
            if (messages.isEmpty()) {
                Text(
                    if (docs.isEmpty()) tr("Dieses Fach hat noch keine Quellen. Füge unter „Quellen“ ein PDF oder eine Textdatei hinzu, dann kannst du hier Fragen dazu stellen.", "This subject has no sources yet. Add a PDF or text file under “Sources”, then you can ask questions about it here.")
                    else if (selected.isEmpty()) tr("Keine Quelle angehakt. Wähle oben die Quellen, auf die sich die Antworten stützen sollen.", "No source checked. Choose above the sources the answers should be based on.")
                    else tr("Stell eine Frage zu deinen Quellen. Die Antwort nennt die Quellen; steht nichts dazu im Material, sagt die App das.", "Ask a question about your sources. The answer names the sources; if nothing about it is in the material, the app says so."),
                    style = MaterialTheme.typography.bodyMedium,
                )
                if (docs.isNotEmpty() && selected.isNotEmpty() && modelState == ModelState.READY) {
                    androidx.compose.foundation.layout.FlowRow(Modifier.align(Alignment.BottomStart), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        listOf(tr("Worum geht es in diesen Quellen?", "What are these sources about?"), tr("Was sind die wichtigsten Begriffe?", "What are the most important terms?"), tr("Welche Definitionen kommen vor?", "Which definitions appear?")).forEach { q ->
                            androidx.compose.material3.SuggestionChip(onClick = { vm.send(q) }, label = { Text(q) })
                        }
                    }
                }
            }
            LazyColumn(state = listState, verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxSize()) {
                items(messages, key = { it.id }) { m -> MessageBubble(m, onSource = { openSource = it }, onRetry = { vm.retryWithMoreSources(m.id) }, canRetry = !streaming, onSpeak = { if (speaker.speaking) speaker.stop() else speaker.speak(m.text) }, speaking = speaker.speaking,
                    onNote = { if (vm.saveAsNote(m.id)) android.widget.Toast.makeText(context, tr("Als Notiz in den Quellen gespeichert", "Saved as a note in the sources"), android.widget.Toast.LENGTH_SHORT).show() },
                    onReport = { val i = messages.indexOfFirst { it.id == m.id }; Feedback.reportAnswer(context, tr("Chat-Antwort", "chat answer"), messages.getOrNull(i - 1)?.takeIf { it.fromUser }?.text.orEmpty(), m.text) }) }
            }
        }
        VoiceMissingHint(speaker)
        speech.error?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error) }
        Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = input,
                onValueChange = { input = it },
                modifier = Modifier.weight(1f),
                placeholder = { Text(tr("Frage stellen …", "Ask a question …")) },
                maxLines = 4,
                enabled = modelState == ModelState.READY,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
            )
            if (speech.available && !streaming) {
                androidx.compose.material3.FilledTonalIconButton(
                    onClick = { if (!speech.listening) speechBase = input; speech.toggle() },
                    enabled = modelState == ModelState.READY,
                    colors = if (speech.listening) androidx.compose.material3.IconButtonDefaults.filledTonalIconButtonColors(containerColor = MaterialTheme.colorScheme.error, contentColor = MaterialTheme.colorScheme.onError) else androidx.compose.material3.IconButtonDefaults.filledTonalIconButtonColors(),
                    modifier = Modifier.size(56.dp),
                ) {
                    androidx.compose.material3.Icon(if (speech.listening) androidx.compose.material.icons.Icons.Default.MicOff else androidx.compose.material.icons.Icons.Default.Mic, contentDescription = if (speech.listening) tr("Aufnahme beenden", "Stop recording") else tr("Frage einsprechen", "Speak your question"))
                }
            }
            if (streaming) {
                Button(onClick = vm::stop) { Text(tr("Stopp", "Stop")) }
            } else {
                Button(onClick = { vm.send(input); input = ""; keyboard?.hide(); focus.clearFocus() }, enabled = input.isNotBlank() && modelState == ModelState.READY) { Text(tr("Senden", "Send")) }
            }
        }
    }

    if (picking) SourcePickerDialog(docs, selected, docsVm::toggle, docsVm::selectAll) { picking = false }

    openSource?.let { s ->
        AlertDialog(
            onDismissRequest = { openSource = null },
            confirmButton = { TextButton(onClick = { openSource = null }) { Text(tr("Schließen", "Close")) } },
            dismissButton = { TextButton(onClick = { docsVm.requestViewChunk(s.chunkId); openSource = null; onOpenSources() }) { Text(tr("In der Quelle ansehen", "View in the source")) } },
            title = { Text("[${s.number}] ${s.documentTitle}, ${s.location}") },
            text = { Column(Modifier.verticalScroll(rememberScrollState())) { Text(s.text, style = MaterialTheme.typography.bodyMedium) } },
        )
    }
}

@Composable
private fun Banner(text: String, error: Boolean = false, actionLabel: String? = null, onAction: () -> Unit = {}) {
    Card(colors = CardDefaults.cardColors(containerColor = if (error) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.secondaryContainer)) {
        Column(Modifier.padding(12.dp)) {
            Text(text, style = MaterialTheme.typography.bodySmall)
            if (actionLabel != null) TextButton(onClick = onAction) { Text(actionLabel) }
        }
    }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun MessageBubble(m: ChatMessage, onSource: (Source) -> Unit, onRetry: () -> Unit, canRetry: Boolean, onSpeak: () -> Unit = {}, speaking: Boolean = false, onNote: () -> Unit = {}, onReport: () -> Unit = {}) {
    val container = if (m.fromUser) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant
    Card(
        colors = CardDefaults.cardColors(containerColor = container),
        modifier = Modifier.fillMaxWidth().padding(start = if (m.fromUser) 48.dp else 0.dp, end = if (m.fromUser) 0.dp else 24.dp),
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            when {
                m.notFound -> {
                    Text(tr("Dazu steht nichts in deinen Dokumenten.", "There is nothing about this in your documents."), style = MaterialTheme.typography.bodyMedium)
                    if (!m.retried && canRetry) TextButton(onClick = onRetry) { Text(tr("Mit mehr Quellen erneut versuchen", "Try again with more sources")) }
                }
                m.text.isEmpty() && m.streaming -> Text(tr("Suche und formuliere …", "Searching and writing …"), style = MaterialTheme.typography.bodySmall)
                else -> Text(de.edgebird.lernsystem.core.cards.LatexLite.toPlain(m.text), style = MaterialTheme.typography.bodyMedium, color = if (m.failed) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface)
            }
            if (!m.fromUser && !m.streaming && !m.failed && !m.notFound && m.text.isNotBlank()) androidx.compose.foundation.layout.FlowRow {
                TextButton(onClick = onSpeak) { Text(if (speaking) tr("Stopp", "Stop") else tr("Vorlesen", "Read aloud")) }
                TextButton(onClick = onNote) { Text(tr("Als Notiz speichern", "Save as note")) }
                TextButton(onClick = onReport) { Text(tr("Melden", "Report")) }
            }
            if (m.retried && !m.streaming && !m.notFound) Text(tr("Zweiter Versuch mit mehr Quellen: bitte die Quellen prüfen.", "Second attempt with more sources: please check the sources."), style = MaterialTheme.typography.labelSmall)
            if (!m.fromUser && !m.notFound && m.sources.isNotEmpty() && !m.streaming) {
                Text(tr("Quellen", "Sources"), style = MaterialTheme.typography.labelMedium)
                androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    m.sources.forEach { s ->
                        FilterChip(
                            selected = s.number in m.cited,
                            onClick = { onSource(s) },
                            label = { Text("[${s.number}] ${s.documentTitle}, ${s.location}", style = MaterialTheme.typography.labelSmall) },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun SourcePickerDialog(docs: List<de.edgebird.lernsystem.data.DocumentSummary>, selected: Set<Long>, onToggle: (Long) -> Unit, onAll: () -> Unit, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss, title = { Text(tr("Quellen für den Chat", "Sources for the chat")) },
        text = {
            androidx.compose.foundation.lazy.LazyColumn {
                items(docs.size) { i ->
                    val d = docs[i].document
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        androidx.compose.material3.Checkbox(checked = d.id in selected, onCheckedChange = { onToggle(d.id) }, enabled = d.status != de.edgebird.lernsystem.data.DocumentStatus.FAILED)
                        Text(d.title, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text(tr("Fertig", "Done")) } },
        dismissButton = { TextButton(onClick = onAll) { Text(tr("Alle", "All")) } },
    )
}

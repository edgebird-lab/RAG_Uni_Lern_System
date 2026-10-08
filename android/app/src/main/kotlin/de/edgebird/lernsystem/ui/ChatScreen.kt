package de.edgebird.lernsystem.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
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

@Composable
fun ChatScreen(onModels: () -> Unit = {}, vm: ChatViewModel = viewModel()) {
    val messages by vm.messages.collectAsStateWithLifecycle()
    val modelState by vm.modelState.collectAsStateWithLifecycle()
    val loadError by vm.loadError.collectAsStateWithLifecycle()
    val hasDocuments by vm.hasDocuments.collectAsStateWithLifecycle()
    var input by rememberSaveable { mutableStateOf("") }
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
            Text("Chat", style = MaterialTheme.typography.headlineMedium, modifier = Modifier.weight(1f))
            if (messages.isNotEmpty()) TextButton(onClick = vm::newChat) { Text("Neuer Chat") }
        }
        when (modelState) {
            ModelState.MISSING -> Banner("Das Sprachmodell fehlt.", error = true, actionLabel = "Modelle laden", onAction = onModels)
            ModelState.LOADING -> Banner("Sprachmodell wird geladen (ca. 25 Sekunden).")
            ModelState.OPTIMIZING -> Banner("Erster Start: Die App optimiert das Sprachmodell für dein Gerät. Das dauert einmalig 5 bis 10 Minuten. Bitte Display an und die App geöffnet lassen.")
            ModelState.ERROR -> Banner(
                "Das Sprachmodell konnte nicht geladen werden" + (loadError?.let { ": $it" } ?: "") + ". Hilft ein erneuter Versuch nicht, ist die Datei evtl. beschädigt (unter „KI-Modelle“ neu laden).",
                error = true, actionLabel = "Erneut versuchen", onAction = vm::retryLoad,
            )
            ModelState.READY -> Unit
        }
        Box(Modifier.weight(1f).fillMaxWidth()) {
            if (messages.isEmpty()) {
                Text(
                    if (hasDocuments == false) "Noch keine Dokumente. Importiere im Tab „Dokumente“ ein PDF oder eine Textdatei, dann kannst du hier Fragen dazu stellen."
                    else "Stell eine Frage zu deinen Dokumenten. Die Antwort nennt die Quellen; steht nichts dazu im Material, sagt die App das.",
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
            LazyColumn(state = listState, verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxSize()) {
                items(messages, key = { it.id }) { m -> MessageBubble(m, onSource = { openSource = it }, onRetry = { vm.retryWithMoreSources(m.id) }, canRetry = !streaming) }
            }
        }
        Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = input,
                onValueChange = { input = it },
                modifier = Modifier.weight(1f),
                placeholder = { Text("Frage stellen …") },
                maxLines = 4,
                enabled = modelState == ModelState.READY,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
            )
            if (streaming) {
                Button(onClick = vm::stop) { Text("Stopp") }
            } else {
                Button(onClick = { vm.send(input); input = ""; keyboard?.hide(); focus.clearFocus() }, enabled = input.isNotBlank() && modelState == ModelState.READY) { Text("Senden") }
            }
        }
    }

    openSource?.let { s ->
        AlertDialog(
            onDismissRequest = { openSource = null },
            confirmButton = { TextButton(onClick = { openSource = null }) { Text("Schließen") } },
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
private fun MessageBubble(m: ChatMessage, onSource: (Source) -> Unit, onRetry: () -> Unit, canRetry: Boolean) {
    val container = if (m.fromUser) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant
    Card(
        colors = CardDefaults.cardColors(containerColor = container),
        modifier = Modifier.fillMaxWidth().padding(start = if (m.fromUser) 48.dp else 0.dp, end = if (m.fromUser) 0.dp else 24.dp),
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            when {
                m.notFound -> {
                    Text("Dazu steht nichts in deinen Dokumenten.", style = MaterialTheme.typography.bodyMedium)
                    if (!m.retried && canRetry) TextButton(onClick = onRetry) { Text("Mit mehr Quellen erneut versuchen") }
                }
                m.text.isEmpty() && m.streaming -> Text("Suche und formuliere …", style = MaterialTheme.typography.bodySmall)
                else -> Text(m.text, style = MaterialTheme.typography.bodyMedium, color = if (m.failed) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface)
            }
            if (m.retried && !m.streaming && !m.notFound) Text("Zweiter Versuch mit mehr Quellen: bitte die Quellen prüfen.", style = MaterialTheme.typography.labelSmall)
            if (!m.fromUser && !m.notFound && m.sources.isNotEmpty() && !m.streaming) {
                Text("Quellen", style = MaterialTheme.typography.labelMedium)
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

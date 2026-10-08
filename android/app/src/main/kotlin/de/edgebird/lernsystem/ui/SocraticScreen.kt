package de.edgebird.lernsystem.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.layout.imePadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilledTonalIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.LinearProgressIndicator
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
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import de.edgebird.lernsystem.core.socratic.Phase
import de.edgebird.lernsystem.data.socratic.Action

/** „Abfragen“: Die App stellt Fragen zu den angehakten Quellen und hilft beim Draufkommen, ohne gleich zu verraten. */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
fun SocraticScreen(subjectId: Long, vm: SocraticViewModel = viewModel(key = "socratic$subjectId"), docsVm: DocumentsViewModel = viewModel(key = "docs$subjectId")) {
    LaunchedEffect(subjectId) { docsVm.bind(subjectId) }
    val ui by vm.ui.collectAsStateWithLifecycle()
    val selected by docsVm.selectedIds.collectAsStateWithLifecycle()
    var topic by rememberSaveable { mutableStateOf("") }
    var input by rememberSaveable { mutableStateOf("") }
    val speech = rememberSpeech(onPartial = { input = it }, onFinal = { input = it })
    val listState = rememberLazyListState()
    LaunchedEffect(ui.messages.size, ui.busy) { if (ui.messages.isNotEmpty()) listState.animateScrollToItem(ui.messages.lastIndex) }

    if (!ui.running) {
        Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Abfrage", style = MaterialTheme.typography.headlineMedium)
            Text("Ich stelle dir Fragen zu deinen Quellen und helfe dir beim Draufkommen, ohne gleich die Lösung zu verraten. Du kannst jederzeit einen Hinweis bekommen oder dir die Auflösung zeigen lassen.", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            OutlinedTextField(value = topic, onValueChange = { topic = it.take(80) }, label = { Text("Thema (leer lassen: ich suche eins aus)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            Text(if (selected.isEmpty()) "Keine Quelle angehakt. Hake unter „Quellen“ mindestens eine an." else "Grundlage: ${selected.size} angehakte ${if (selected.size == 1) "Quelle" else "Quellen"}", style = MaterialTheme.typography.bodySmall)
            Button(onClick = { vm.start(topic, selected) }, enabled = selected.isNotEmpty(), modifier = Modifier.fillMaxWidth()) { Text("Abfrage starten") }
        }
        return
    }

    BackHandler { vm.end() }
    Column(Modifier.fillMaxSize().imePadding().padding(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Abfrage", style = MaterialTheme.typography.titleLarge)
                if (ui.topic.isNotBlank()) Text("Thema: ${ui.topic}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            TextButton(onClick = { vm.end() }) { Text("Beenden") }
        }
        LazyColumn(state = listState, modifier = Modifier.weight(1f).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(ui.messages) { m -> Bubble(m) }
            if (ui.busy) item { Column(Modifier.padding(8.dp)) { Text("Ich denke nach …", style = MaterialTheme.typography.bodySmall); LinearProgressIndicator(Modifier.fillMaxWidth()) } }
        }
        ui.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
        speech.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
        androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val enabled = !ui.busy && ui.messages.isNotEmpty()
            if (ui.phase == Phase.OPEN) {
                AssistChip(onClick = { vm.act(Action.Hint) }, label = { Text("Hinweis") }, enabled = enabled)
                AssistChip(onClick = { vm.act(Action.Partial) }, label = { Text("Ich weiß nur einen Teil") }, enabled = enabled)
                AssistChip(onClick = { vm.act(Action.Resolve) }, label = { Text("Auflösen") }, enabled = enabled)
            } else {
                AssistChip(onClick = { vm.act(Action.Next) }, label = { Text("Nächster Aspekt") }, enabled = enabled)
            }
        }
        Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(value = input, onValueChange = { input = it }, modifier = Modifier.weight(1f), placeholder = { Text("Deine Antwort …") }, maxLines = 4, enabled = !ui.busy)
            if (speech.available) {
                FilledTonalIconButton(
                    onClick = { speech.toggle() }, enabled = !ui.busy, modifier = Modifier.size(56.dp),
                    colors = if (speech.listening) IconButtonDefaults.filledTonalIconButtonColors(containerColor = MaterialTheme.colorScheme.error, contentColor = MaterialTheme.colorScheme.onError) else IconButtonDefaults.filledTonalIconButtonColors(),
                ) { Icon(if (speech.listening) Icons.Default.MicOff else Icons.Default.Mic, contentDescription = if (speech.listening) "Aufnahme beenden" else "Antwort einsprechen") }
            }
            Button(onClick = { vm.act(Action.Answer(input)); input = "" }, enabled = input.isNotBlank() && !ui.busy) { Text("Senden") }
        }
    }
}

@Composable
private fun Bubble(m: DialogMessage) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (m.fromUser) Arrangement.End else Arrangement.Start) {
        Card(
            colors = CardDefaults.cardColors(containerColor = if (m.fromUser) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant),
            modifier = Modifier.fillMaxWidth(if (m.fromUser) 0.8f else 0.92f),
        ) {
            Column(Modifier.padding(12.dp)) {
                Text(de.edgebird.lernsystem.core.cards.LatexLite.toPlain(m.text), style = MaterialTheme.typography.bodyMedium)
                if (m.fallback) Text("Die KI hat sich im Kreis gedreht, darum diese feste Antwort.", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

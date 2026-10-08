package de.edgebird.lernsystem.ui

import de.edgebird.lernsystem.core.i18n.tr

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
import androidx.compose.foundation.verticalScroll
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
    LaunchedEffect(subjectId) { docsVm.bind(subjectId); vm.bind(subjectId) }
    val ui by vm.ui.collectAsStateWithLifecycle()
    val topics by vm.topics.collectAsStateWithLifecycle()
    val summary by vm.summary.collectAsStateWithLifecycle()
    val selected by docsVm.selectedIds.collectAsStateWithLifecycle()
    var topic by rememberSaveable { mutableStateOf("") }
    var input by rememberSaveable { mutableStateOf("") }
    val speech = rememberSpeech(onPartial = { input = it }, onFinal = { input = it })
    val speaker = rememberSpeechOutput()
    val listState = rememberLazyListState()
    LaunchedEffect(ui.messages.size, ui.busy) { if (ui.messages.isNotEmpty()) listState.animateScrollToItem(ui.messages.lastIndex) }

    if (!ui.running) {
        Column(Modifier.fillMaxSize().verticalScroll(androidx.compose.foundation.rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(tr("Abfrage", "Q&A session"), style = MaterialTheme.typography.headlineMedium)
            Text(tr("Ich stelle dir Fragen zu deinen Quellen und helfe dir beim Draufkommen, ohne gleich die Lösung zu verraten. Du kannst jederzeit einen Hinweis bekommen oder dir die Auflösung zeigen lassen.", "I ask you questions about your sources and help you work things out without giving the solution away right away. You can get a hint or see the solution at any time."), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            OutlinedTextField(value = topic, onValueChange = { topic = it.take(80) }, label = { Text(tr("Thema (leer lassen: ich suche eins aus)", "Topic (leave empty: I pick one)")) }, singleLine = true, modifier = Modifier.fillMaxWidth())
            Text(if (selected.isEmpty()) tr("Keine Quelle angehakt. Hake unter „Quellen“ mindestens eine an.", "No source checked. Check at least one under “Sources”.") else tr("Grundlage: ${selected.size} angehakte ${if (selected.size == 1) "Quelle" else "Quellen"}", "Based on ${selected.size} checked ${if (selected.size == 1) "source" else "sources"}"), style = MaterialTheme.typography.bodySmall)
            Button(onClick = { vm.start(topic, selected) }, enabled = selected.isNotEmpty(), modifier = Modifier.fillMaxWidth()) { Text(tr("Abfrage starten", "Start Q&A")) }
            if (topics.isNotEmpty()) {
                Text(tr("Dein Stand je Thema", "Your progress per topic"), style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 8.dp))
                Text(tr("Schwächste zuerst. Tippe auf „Üben“, um genau dazu abgefragt zu werden.", "Weakest first. Tap “Practise” to be quizzed on exactly that."), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                androidx.compose.foundation.layout.Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    topics.forEach { t ->
                        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface), modifier = Modifier.fillMaxWidth()) {
                            Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text(t.topic, style = MaterialTheme.typography.titleSmall)
                                    LinearProgressIndicator(progress = { t.score.toFloat() }, modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp))
                                    Text("${(t.score * 100).toInt()} % · ${t.total} ${if (t.total == 1) tr("Antwort", "answer") else tr("Antworten", "answers")}", style = MaterialTheme.typography.bodySmall)
                                }
                                TextButton(onClick = { topic = t.topic; vm.start(t.topic, selected) }, enabled = selected.isNotEmpty()) { Text(tr("Üben", "Practise")) }
                            }
                        }
                    }
                }
            }
        }
        return
    }

    BackHandler { vm.end() }
    summary?.let { QuizResultDialog(it, onSave = vm::saveWeakAsCards, onClose = vm::closeSummary) }
    Column(Modifier.fillMaxSize().imePadding().padding(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(tr("Abfrage", "Q&A session"), style = MaterialTheme.typography.titleLarge)
                if (ui.topic.isNotBlank()) Text(tr("Thema: ${ui.topic}", "Topic: ${ui.topic}"), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            TextButton(onClick = { vm.end() }) { Text(tr("Beenden", "End")) }
        }
        LazyColumn(state = listState, modifier = Modifier.weight(1f).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(ui.messages) { m -> Bubble(m, onSpeak = { if (speaker.speaking) speaker.stop() else speaker.speak(m.text) }, speaking = speaker.speaking) }
            if (ui.busy) item { Column(Modifier.padding(8.dp)) { Text(tr("Ich denke nach …", "Thinking …"), style = MaterialTheme.typography.bodySmall); LinearProgressIndicator(Modifier.fillMaxWidth()) } }
        }
        VoiceMissingHint(speaker)
        ui.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
        speech.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
        androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val enabled = !ui.busy && ui.messages.isNotEmpty()
            if (ui.phase == Phase.OPEN) {
                AssistChip(onClick = { vm.act(Action.Hint) }, label = { Text(tr("Hinweis", "Hint")) }, enabled = enabled)
                AssistChip(onClick = { vm.act(Action.Partial) }, label = { Text(tr("Ich weiß nur einen Teil", "I only know part of it")) }, enabled = enabled)
                AssistChip(onClick = { vm.act(Action.Resolve) }, label = { Text(tr("Auflösen", "Resolve")) }, enabled = enabled)
            } else {
                AssistChip(onClick = { vm.act(Action.Next) }, label = { Text(tr("Nächster Aspekt", "Next aspect")) }, enabled = enabled)
            }
        }
        Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(value = input, onValueChange = { input = it }, modifier = Modifier.weight(1f), placeholder = { Text(tr("Deine Antwort …", "Your answer …")) }, maxLines = 4, enabled = !ui.busy)
            if (speech.available) {
                FilledTonalIconButton(
                    onClick = { speech.toggle() }, enabled = !ui.busy, modifier = Modifier.size(56.dp),
                    colors = if (speech.listening) IconButtonDefaults.filledTonalIconButtonColors(containerColor = MaterialTheme.colorScheme.error, contentColor = MaterialTheme.colorScheme.onError) else IconButtonDefaults.filledTonalIconButtonColors(),
                ) { Icon(if (speech.listening) Icons.Default.MicOff else Icons.Default.Mic, contentDescription = if (speech.listening) tr("Aufnahme beenden", "Stop recording") else tr("Antwort einsprechen", "Speak your answer")) }
            }
            Button(onClick = { vm.act(Action.Answer(input)); input = "" }, enabled = input.isNotBlank() && !ui.busy) { Text(tr("Senden", "Send")) }
        }
    }
}

@Composable
private fun QuizResultDialog(s: QuizSummary, onSave: () -> Unit, onClose: () -> Unit) {
    androidx.compose.material3.AlertDialog(
        onDismissRequest = {}, title = { Text(tr("Ergebnis der Abfrage", "Q&A result")) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(tr("${s.correct} richtig · ${s.partial} teilweise · ${s.wrong} falsch (von ${s.evaluations.size})", "${s.correct} correct · ${s.partial} partly · ${s.wrong} wrong (of ${s.evaluations.size})"), style = MaterialTheme.typography.titleSmall)
                if (s.weak.isNotEmpty()) {
                    Text(tr("Zum Wiederholen:", "To review:"), style = MaterialTheme.typography.labelLarge)
                    s.weak.distinctBy { it.question }.forEach { Text("• ${it.question}", style = MaterialTheme.typography.bodySmall) }
                } else Text(tr("Alles richtig. Stark!", "All correct. Great!"), style = MaterialTheme.typography.bodyMedium)
                s.cardsSaved?.let { Text(tr("$it Karten wurden im Fach angelegt (Bereich „Karten“).", "$it cards were created in the subject (section “Cards”)."), style = MaterialTheme.typography.bodySmall) }
                if (s.saving) { Text(tr("Karten werden erstellt …", "Cards are being created …"), style = MaterialTheme.typography.bodySmall); LinearProgressIndicator(Modifier.fillMaxWidth()) }
            }
        },
        confirmButton = { TextButton(onClick = onClose, enabled = !s.saving) { Text(tr("Schließen", "Close")) } },
        dismissButton = { if (s.weak.isNotEmpty() && s.cardsSaved == null) TextButton(onClick = onSave, enabled = !s.saving) { Text(tr("Schwache Fragen als Karten", "Weak questions as cards")) } },
    )
}

@Composable
private fun Bubble(m: DialogMessage, onSpeak: () -> Unit = {}, speaking: Boolean = false) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (m.fromUser) Arrangement.End else Arrangement.Start) {
        Card(
            colors = CardDefaults.cardColors(containerColor = if (m.fromUser) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant),
            modifier = Modifier.fillMaxWidth(if (m.fromUser) 0.8f else 0.92f),
        ) {
            Column(Modifier.padding(12.dp)) {
                Text(de.edgebird.lernsystem.core.cards.LatexLite.toPlain(m.text), style = MaterialTheme.typography.bodyMedium)
                m.verdict?.let { v -> Text(when (v) { de.edgebird.lernsystem.core.socratic.Verdict.CORRECT -> tr("✓ richtig", "✓ correct"); de.edgebird.lernsystem.core.socratic.Verdict.PARTIAL -> tr("◐ teilweise richtig", "◐ partly correct"); de.edgebird.lernsystem.core.socratic.Verdict.WRONG -> tr("✗ noch nicht richtig", "✗ not correct yet") }, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary) }
                if (!m.fromUser) TextButton(onClick = onSpeak) { Text(if (speaking) tr("Stopp", "Stop") else tr("Vorlesen", "Read aloud")) }
                if (m.fallback) Text(tr("Die KI hat sich im Kreis gedreht, darum diese feste Antwort.", "The AI went in circles, so this is a fixed answer."), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

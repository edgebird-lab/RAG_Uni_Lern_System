package de.edgebird.lernsystem.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import de.edgebird.lernsystem.core.cards.LatexLite

/** Quiz (Mehrfachauswahl mit sofortiger Rückmeldung) und Probeklausur (Zeitlimit, Auswertung am Ende). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun QuizScreen(subjectId: Long, vm: QuizViewModel = viewModel(key = "quiz$subjectId"), docsVm: DocumentsViewModel = viewModel(key = "docs$subjectId")) {
    LaunchedEffect(subjectId) { vm.bind(subjectId); docsVm.bind(subjectId) }
    val state by vm.state.collectAsStateWithLifecycle()
    val selected by docsVm.selectedIds.collectAsStateWithLifecycle()
    val options by vm.optionsFlow.collectAsStateWithLifecycle()

    when (val s = state) {
        QuizState.Setup -> Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Quiz und Probeklausur", style = MaterialTheme.typography.headlineMedium)
            Text("Mehrfachauswahl-Fragen aus deinen angehakten Quellen. Das Erstellen dauert etwa 5 bis 10 Sekunden je Frage; die richtigen Antworten sind im Text belegt.", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("Anzahl der Fragen", style = MaterialTheme.typography.labelLarge)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) { listOf(5, 10, 15, 20).forEach { n -> FilterChip(selected = options.count == n, onClick = { vm.setOptions(options.copy(count = n)) }, label = { Text("$n") }) } }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Probeklausur", style = MaterialTheme.typography.bodyLarge)
                    Text("Mit Zeitlimit, Rückmeldung erst am Ende", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Switch(checked = options.exam, onCheckedChange = { vm.setOptions(options.copy(exam = it, minutes = (options.count * 1.5).toInt().coerceAtLeast(5))) })
            }
            if (options.exam) {
                Text("Zeit: ${options.minutes} Minuten", style = MaterialTheme.typography.labelLarge)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) { listOf(5, 10, 15, 20, 30, 45).forEach { m -> FilterChip(selected = options.minutes == m, onClick = { vm.setOptions(options.copy(minutes = m)) }, label = { Text("$m Min") }) } }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Schwache Themen bevorzugen", style = MaterialTheme.typography.bodyLarge)
                    Text("Fragen kommen häufiger aus Themen, in denen du bisher am schwächsten warst.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Switch(checked = options.preferWeak, onCheckedChange = { vm.setOptions(options.copy(preferWeak = it)) })
            }
            Text(if (selected.isEmpty()) "Keine Quelle angehakt. Hake unter „Quellen“ mindestens eine an." else "Grundlage: ${selected.size} angehakte ${if (selected.size == 1) "Quelle" else "Quellen"}", style = MaterialTheme.typography.bodySmall)
            Button(onClick = { vm.start(selected) }, enabled = selected.isNotEmpty(), modifier = Modifier.fillMaxWidth()) { Text(if (options.exam) "Probeklausur starten" else "Quiz starten") }
        }
        is QuizState.Generating -> Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Fragen werden erstellt", style = MaterialTheme.typography.headlineMedium)
            Text("Frage ${minOf(s.done + 1, s.total)} von ${s.total} …", style = MaterialTheme.typography.bodyLarge)
            LinearProgressIndicator(progress = { s.done.toFloat() / s.total.coerceAtLeast(1) }, modifier = Modifier.fillMaxWidth())
            Text("Das Display sollte dabei an bleiben.", style = MaterialTheme.typography.bodySmall)
            OutlinedButton(onClick = vm::cancelGeneration) { Text("Abbrechen") }
        }
        is QuizState.Running -> RunningView(s, vm)
        is QuizState.Finished -> FinishedView(s, vm)
        is QuizState.Failed -> Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(s.message, color = MaterialTheme.colorScheme.error)
            Button(onClick = vm::reset) { Text("Zurück") }
        }
    }
}

@Composable
private fun RunningView(s: QuizState.Running, vm: QuizViewModel) {
    BackHandler { vm.finish() }
    val item = s.items[s.index]
    val chosen = s.answers[s.index]
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    if (s.endAt != null) LaunchedEffect(s.endAt) { while (true) { kotlinx.coroutines.delay(500); now = System.currentTimeMillis() } }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Frage ${s.index + 1} von ${s.items.size}", Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
            s.endAt?.let { end ->
                val left = ((end - now) / 1000).coerceAtLeast(0)
                Text("%d:%02d".format(left / 60, left % 60), style = MaterialTheme.typography.titleMedium, color = if (left < 60) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface)
            }
            TextButton(onClick = { vm.finish() }) { Text(if (s.exam) "Abgeben" else "Beenden") }
        }
        LinearProgressIndicator(progress = { (s.index + 1).toFloat() / s.items.size }, modifier = Modifier.fillMaxWidth())
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Text(LatexLite.toPlain(item.question.question), Modifier.padding(16.dp), style = MaterialTheme.typography.titleMedium)
        }
        item.question.options.forEachIndexed { i, opt ->
            val reveal = s.revealed
            val isCorrect = i == item.question.correctIndex
            val colors = when {
                reveal && isCorrect -> ButtonDefaults.outlinedButtonColors(containerColor = MaterialTheme.colorScheme.tertiaryContainer)
                reveal && chosen == i -> ButtonDefaults.outlinedButtonColors(containerColor = MaterialTheme.colorScheme.errorContainer)
                chosen == i -> ButtonDefaults.outlinedButtonColors(containerColor = MaterialTheme.colorScheme.primaryContainer)
                else -> ButtonDefaults.outlinedButtonColors()
            }
            OutlinedButton(onClick = { vm.choose(i) }, colors = colors, modifier = Modifier.fillMaxWidth()) {
                Text("${'A' + i}  ${LatexLite.toPlain(opt)}", Modifier.fillMaxWidth().padding(vertical = 4.dp), style = MaterialTheme.typography.bodyLarge)
            }
        }
        if (s.revealed) {
            Text(if (chosen == item.question.correctIndex) "✓ Richtig" else "✗ Leider falsch: richtig ist ${'A' + item.question.correctIndex}", style = MaterialTheme.typography.titleSmall)
            if (item.question.explanation.isNotBlank()) Text(item.question.explanation, style = MaterialTheme.typography.bodyMedium)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (s.exam && s.index > 0) OutlinedButton(onClick = vm::previous) { Text("Zurück") }
            Button(onClick = vm::next, enabled = chosen != null || s.exam, modifier = Modifier.weight(1f)) { Text(if (s.index + 1 >= s.items.size) "Fertig" else "Weiter") }
        }
    }
}

@Composable
private fun FinishedView(s: QuizState.Finished, vm: QuizViewModel) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(if (s.exam) "Ergebnis der Probeklausur" else "Ergebnis", style = MaterialTheme.typography.headlineMedium)
        if (s.timedOut) Text("Die Zeit ist abgelaufen; nicht beantwortete Fragen zählen als falsch.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
        val pct = if (s.items.isEmpty()) 0 else s.correct * 100 / s.items.size
        Text("${s.correct} von ${s.items.size} richtig ($pct %)", style = MaterialTheme.typography.titleLarge)
        LinearProgressIndicator(progress = { pct / 100f }, modifier = Modifier.fillMaxWidth())
        val wrong = s.items.indices.filter { s.answers[it] != s.items[it].question.correctIndex }
        if (wrong.isNotEmpty()) {
            Text("Zum Wiederholen", style = MaterialTheme.typography.titleMedium)
            wrong.forEach { i ->
                val q = s.items[i].question
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(LatexLite.toPlain(q.question), style = MaterialTheme.typography.titleSmall)
                        s.answers[i]?.let { Text("Deine Antwort: ${LatexLite.toPlain(q.options[it])}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error) } ?: Text("Nicht beantwortet", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                        Text("Richtig: ${LatexLite.toPlain(q.correct)}", style = MaterialTheme.typography.bodyMedium)
                        if (q.explanation.isNotBlank()) Text(q.explanation, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
            s.cardsSaved?.let { Text("$it Karten wurden angelegt (Bereich „Karten“).", style = MaterialTheme.typography.bodySmall) }
                ?: OutlinedButton(onClick = vm::saveWrongAsCards) { Text("Falsche Fragen als Karten speichern") }
        } else Text("Alles richtig. Stark!", style = MaterialTheme.typography.bodyLarge)
        Button(onClick = vm::reset, modifier = Modifier.fillMaxWidth()) { Text("Neues Quiz") }
    }
}

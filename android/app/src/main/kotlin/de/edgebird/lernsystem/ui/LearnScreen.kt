package de.edgebird.lernsystem.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
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
import de.edgebird.lernsystem.core.cards.LatexLite
import de.edgebird.lernsystem.data.CardEntity
import de.edgebird.lernsystem.data.CardSource
import de.edgebird.lernsystem.data.study.Grade
import de.edgebird.lernsystem.data.study.StudySettings

@Composable
fun LearnScreen(subjectId: Long, vm: StudyViewModel = viewModel(key = "study$subjectId"), cardsVm: CardsViewModel = viewModel(key = "cards$subjectId")) {
    androidx.compose.runtime.LaunchedEffect(subjectId) { vm.bind(subjectId); cardsVm.bind(subjectId) }
    val session by vm.session.collectAsStateWithLifecycle()
    var manage by rememberSaveable { mutableStateOf(false) }
    when {
        session != null -> {
            BackHandler { vm.endSession() }
            SessionView(session!!, vm)
        }
        manage -> {
            BackHandler { manage = false }
            CardsView(cardsVm) { manage = false }
        }
        else -> LearnHome(vm, onManage = { manage = true })
    }
}

@Composable
private fun LearnHome(vm: StudyViewModel, onManage: () -> Unit) {
    val summary by vm.summary.collectAsStateWithLifecycle()
    val settings by vm.settings.collectAsStateWithLifecycle()
    var showSettings by remember { mutableStateOf(false) }
    androidx.compose.runtime.LaunchedEffect(Unit) { vm.refresh() }
    val pomodoroGraph = (androidx.compose.ui.platform.LocalContext.current.applicationContext as de.edgebird.lernsystem.LernsystemApp).graph
    val focusMinutes by androidx.compose.runtime.produceState(0) { value = pomodoroGraph.pomodoroRepo.todayMinutes() }
    val focusGoal by pomodoroGraph.pomodoro.goalMinutes.collectAsStateWithLifecycle()

    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        val s = summary
        if (s == null) {
            Text("Wird geladen …")
        } else {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Stat("Fällig", s.due.toString())
                        Stat("Neu heute", s.newToday.toString())
                        Stat("Serie", "${s.streak} Tg.")
                    }
                    Text("Heute ${s.reviewsToday} von ${s.dailyGoal} Wiederholungen", style = MaterialTheme.typography.bodyMedium)
                    LinearProgressIndicator(progress = { (s.reviewsToday.toFloat() / s.dailyGoal.coerceAtLeast(1)).coerceAtMost(1f) }, modifier = Modifier.fillMaxWidth())
                    WeekBars(s)
                    Text("Gefestigt: ${s.matureCards} von ${s.totalCards} Karten", style = MaterialTheme.typography.bodySmall)
                    Text("Fokuszeit heute: $focusMinutes von $focusGoal Min", style = MaterialTheme.typography.bodySmall)
                }
            }
            if (s.totalCards == 0) {
                Text("Noch keine Karten. Erzeuge sie im Tab „Dokumente“ aus deinen Unterlagen oder lege unter „Karten verwalten“ eigene an.", style = MaterialTheme.typography.bodyMedium)
            } else if (s.due + s.newToday == 0) {
                Text("Für heute ist alles geschafft.", style = MaterialTheme.typography.bodyMedium)
            }
            Button(onClick = vm::start, enabled = s.due + s.newToday > 0, modifier = Modifier.fillMaxWidth()) { Text("Lernen starten") }
            OutlinedButton(onClick = onManage, modifier = Modifier.fillMaxWidth()) { Text("Karten verwalten (${s.totalCards})") }
            TextButton(onClick = { showSettings = true }) { Text("Tagesziel und neue Karten pro Tag") }
        }
    }
    if (showSettings) SettingsDialog(settings, onSave = { vm.saveSettings(it); showSettings = false }, onDismiss = { showSettings = false })
}

@Composable
private fun WeekBars(s: de.edgebird.lernsystem.data.study.StudySummary) {
    val max = (s.week.maxOfOrNull { it.reviews } ?: 0).coerceAtLeast(1)
    val fmt = java.time.format.DateTimeFormatter.ofPattern("EE", java.util.Locale.GERMAN)
    Row(Modifier.fillMaxWidth().padding(top = 4.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Bottom) {
        s.week.forEach { d ->
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(d.reviews.toString(), style = MaterialTheme.typography.labelSmall)
                androidx.compose.foundation.layout.Box(
                    Modifier.padding(vertical = 2.dp).width(22.dp).height((6 + 40 * d.reviews / max).dp)
                        .background(MaterialTheme.colorScheme.primary.copy(alpha = if (d.reviews > 0) 1f else 0.25f), androidx.compose.foundation.shape.RoundedCornerShape(4.dp)),
                )
                Text(java.time.Instant.ofEpochMilli(d.dayStartMillis).atZone(java.time.ZoneId.systemDefault()).format(fmt), style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}

@Composable
private fun Stat(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, style = MaterialTheme.typography.headlineSmall)
        Text(label, style = MaterialTheme.typography.labelMedium)
    }
}

@Composable
private fun SettingsDialog(current: StudySettings, onSave: (StudySettings) -> Unit, onDismiss: () -> Unit) {
    var goal by remember { mutableStateOf(current.dailyReviewGoal.toString()) }
    var newPerDay by remember { mutableStateOf(current.newCardsPerDay.toString()) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Lernziel") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(goal, { goal = it.filter(Char::isDigit).take(3) }, label = { Text("Wiederholungen pro Tag") }, singleLine = true)
                OutlinedTextField(newPerDay, { newPerDay = it.filter(Char::isDigit).take(3) }, label = { Text("Neue Karten pro Tag") }, singleLine = true)
            }
        },
        confirmButton = {
            TextButton(onClick = { onSave(StudySettings((goal.toIntOrNull() ?: 40).coerceIn(1, 500), (newPerDay.toIntOrNull() ?: 20).coerceIn(0, 200))) }) { Text("Speichern") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Abbrechen") } },
    )
}

@Composable
private fun SessionView(s: SessionState, vm: StudyViewModel) {
    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(if (s.finished) "Sitzung beendet" else "${s.remaining} übrig · ${s.reviewed} bewertet", Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
            TextButton(onClick = vm::endSession) { Text(if (s.finished) "Fertig" else "Beenden") }
        }
        if (s.finished) {
            Text(
                if (s.reviewed == 0) "Es gab nichts zu lernen." else "${s.reviewed} Bewertungen. Gut gemacht!",
                style = MaterialTheme.typography.bodyLarge,
            )
            return@Column
        }
        val card = s.card ?: return@Column
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Card(Modifier.fillMaxWidth()) { Text(LatexLite.toPlain(card.front), Modifier.padding(20.dp), style = MaterialTheme.typography.titleLarge) }
            if (s.showAnswer) {
                Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Text(LatexLite.toPlain(card.answer), Modifier.padding(20.dp), style = MaterialTheme.typography.bodyLarge)
                }
            }
        }
        if (!s.showAnswer) {
            Button(onClick = vm::reveal, modifier = Modifier.fillMaxWidth()) { Text("Antwort zeigen") }
        } else {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Grade.entries.forEach { g ->
                    Button(onClick = { vm.grade(g) }, modifier = Modifier.weight(1f), contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 4.dp, vertical = 10.dp)) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(g.label, style = MaterialTheme.typography.labelLarge)
                            Text(s.previews[g].orEmpty(), style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CardsView(vm: CardsViewModel, onBack: () -> Unit) {
    val cards by vm.cards.collectAsStateWithLifecycle()
    var editing by remember { mutableStateOf<CardEntity?>(null) }
    var creating by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack) { Text("Zurück") }
            Text("Karten (${cards.size})", Modifier.weight(1f), style = MaterialTheme.typography.titleLarge)
            Button(onClick = { creating = true }) { Text("Neu") }
        }
        val exporter = androidx.activity.compose.rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.CreateDocument("text/tab-separated-values")) { uri -> uri?.let(vm::export) }
        if (cards.isNotEmpty()) TextButton(onClick = { exporter.launch("lernsystem-karten.tsv") }) { Text("Für Anki exportieren (TSV)") }
        if (cards.isEmpty()) Text("Noch keine Karten.", style = MaterialTheme.typography.bodyMedium)
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(cards, key = { it.card.id }) { c ->
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(LatexLite.toPlain(c.card.front), style = MaterialTheme.typography.titleSmall)
                        Text(LatexLite.toPlain(c.card.answer), style = MaterialTheme.typography.bodySmall, maxLines = 3)
                        val origin = when {
                            c.card.source == CardSource.MANUAL -> "eigene Karte"
                            c.documentTitle != null -> "aus ${c.documentTitle}"
                            else -> "Dokument gelöscht"
                        }
                        Text(origin, style = MaterialTheme.typography.labelSmall)
                        Row {
                            TextButton(onClick = { editing = c.card }) { Text("Bearbeiten") }
                            TextButton(onClick = { vm.delete(c.card) }) { Text("Löschen") }
                        }
                    }
                }
            }
        }
    }
    if (creating) CardDialog("Neue Karte", "", "", onSave = { f, a -> vm.add(f, a); creating = false }, onDismiss = { creating = false })
    editing?.let { c -> CardDialog("Karte bearbeiten", c.front, c.answer, onSave = { f, a -> vm.edit(c, f, a); editing = null }, onDismiss = { editing = null }) }
}

@Composable
private fun CardDialog(title: String, front: String, answer: String, onSave: (String, String) -> Unit, onDismiss: () -> Unit) {
    var f by remember { mutableStateOf(front) }
    var a by remember { mutableStateOf(answer) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(f, { f = it }, label = { Text("Frage") }, minLines = 2)
                OutlinedTextField(a, { a = it }, label = { Text("Antwort") }, minLines = 3)
            }
        },
        confirmButton = { TextButton(onClick = { onSave(f, a) }, enabled = f.isNotBlank() && a.isNotBlank()) { Text("Speichern") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Abbrechen") } },
    )
}

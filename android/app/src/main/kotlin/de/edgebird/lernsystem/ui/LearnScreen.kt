package de.edgebird.lernsystem.ui

import de.edgebird.lernsystem.core.i18n.tr

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
import androidx.compose.material3.SegmentedButton
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

/** Bereich „Lernen“: Karteikarten oder Abfragen (sokratischer Dialog). */
@Composable
fun LearnTab(subjectId: Long) {
    var mode by rememberSaveable { mutableStateOf(0) }
    Column(Modifier.fillMaxSize()) {
        androidx.compose.material3.SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)) {
            listOf(tr("Karten", "Cards"), tr("Abfragen", "Q&A"), tr("Quiz", "Quiz")).forEachIndexed { i, label ->
                SegmentedButton(selected = mode == i, onClick = { mode = i }, shape = androidx.compose.material3.SegmentedButtonDefaults.itemShape(i, 3), icon = {}) { Text(label, maxLines = 1) }
            }
        }
        when (mode) { 0 -> LearnScreen(subjectId); 1 -> SocraticScreen(subjectId); else -> QuizScreen(subjectId) }
    }
}

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
            Text(tr("Wird geladen …", "Loading …"))
        } else {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Stat(tr("Fällig", "Due"), s.due.toString())
                        Stat(tr("Neu heute", "New today"), s.newToday.toString())
                        Stat(tr("Serie", "Streak"), tr("${s.streak} Tg.", "${s.streak} d"))
                    }
                    Text(tr("Heute ${s.reviewsToday} von ${s.dailyGoal} Wiederholungen", "Today ${s.reviewsToday} of ${s.dailyGoal} reviews"), style = MaterialTheme.typography.bodyMedium)
                    LinearProgressIndicator(progress = { (s.reviewsToday.toFloat() / s.dailyGoal.coerceAtLeast(1)).coerceAtMost(1f) }, modifier = Modifier.fillMaxWidth())
                    WeekBars(s)
                    Text(tr("Gefestigt: ${s.matureCards} von ${s.totalCards} Karten", "Mastered: ${s.matureCards} of ${s.totalCards} cards"), style = MaterialTheme.typography.bodySmall)
                    Text(tr("Fokuszeit heute: $focusMinutes von $focusGoal Min", "Focus time today: $focusMinutes of $focusGoal min"), style = MaterialTheme.typography.bodySmall)
                }
            }
            if (s.totalCards == 0) {
                Text(tr("Noch keine Karten. Erzeuge sie im Tab „Dokumente“ aus deinen Unterlagen oder lege unter „Karten verwalten“ eigene an.", "No cards yet. Generate them from your materials in the “Documents” tab or create your own under “Manage cards”."), style = MaterialTheme.typography.bodyMedium)
            } else if (s.due + s.newToday == 0) {
                Text(tr("Für heute ist alles geschafft.", "All done for today."), style = MaterialTheme.typography.bodyMedium)
            }
            Button(onClick = vm::start, enabled = s.due + s.newToday > 0, modifier = Modifier.fillMaxWidth()) { Text(tr("Lernen starten", "Start studying")) }
            OutlinedButton(onClick = onManage, modifier = Modifier.fillMaxWidth()) { Text(tr("Karten verwalten (${s.totalCards})", "Manage cards (${s.totalCards})")) }
            TextButton(onClick = { showSettings = true }) { Text(tr("Tagesziel und neue Karten pro Tag", "Daily goal and new cards per day")) }
        }
    }
    if (showSettings) SettingsDialog(settings, onSave = { vm.saveSettings(it); showSettings = false }, onDismiss = { showSettings = false })
}

@Composable
private fun WeekBars(s: de.edgebird.lernsystem.data.study.StudySummary) {
    val max = (s.week.maxOfOrNull { it.reviews } ?: 0).coerceAtLeast(1)
    val fmt = java.time.format.DateTimeFormatter.ofPattern("EE", de.edgebird.lernsystem.core.i18n.Lang.current.locale)
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
        title = { Text(tr("Lernziel", "Study goal")) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(goal, { goal = it.filter(Char::isDigit).take(3) }, label = { Text(tr("Wiederholungen pro Tag", "Reviews per day")) }, singleLine = true)
                OutlinedTextField(newPerDay, { newPerDay = it.filter(Char::isDigit).take(3) }, label = { Text(tr("Neue Karten pro Tag", "New cards per day")) }, singleLine = true)
            }
        },
        confirmButton = {
            TextButton(onClick = { onSave(StudySettings((goal.toIntOrNull() ?: 40).coerceIn(1, 500), (newPerDay.toIntOrNull() ?: 20).coerceIn(0, 200))) }) { Text(tr("Speichern", "Save")) }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text(tr("Abbrechen", "Cancel")) } },
    )
}

@Composable
private fun SessionView(s: SessionState, vm: StudyViewModel) {
    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(if (s.finished) tr("Sitzung beendet", "Session finished") else tr("${s.remaining} übrig · ${s.reviewed} bewertet", "${s.remaining} left · ${s.reviewed} rated"), Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
            TextButton(onClick = vm::endSession) { Text(if (s.finished) tr("Fertig", "Done") else tr("Beenden", "End")) }
        }
        if (s.finished) {
            Text(
                if (s.reviewed == 0) tr("Es gab nichts zu lernen.", "There was nothing to study.") else tr("${s.reviewed} Bewertungen. Gut gemacht!", "${s.reviewed} ratings. Well done!"),
                style = MaterialTheme.typography.bodyLarge,
            )
            return@Column
        }
        val card = s.card ?: return@Column
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            val cloze = card.kind == "CLOZE"
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (cloze) Text(tr("Lückentext", "Fill in the blank"), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
                    Text(LatexLite.toPlain(card.front), style = MaterialTheme.typography.titleLarge)
                }
            }
            if (s.showAnswer) {
                Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Text(inline(card.answer), Modifier.padding(20.dp), style = MaterialTheme.typography.bodyLarge)
                }
            }
        }
        if (!s.showAnswer) {
            Button(onClick = vm::reveal, modifier = Modifier.fillMaxWidth()) { Text(tr("Antwort zeigen", "Show answer")) }
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
            TextButton(onClick = onBack) { Text(tr("Zurück", "Back")) }
            Text(tr("Karten (${cards.size})", "Cards (${cards.size})"), Modifier.weight(1f), style = MaterialTheme.typography.titleLarge)
            Button(onClick = { creating = true }) { Text(tr("Neu", "New")) }
        }
        val exporter = androidx.activity.compose.rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.CreateDocument("text/tab-separated-values")) { uri -> uri?.let(vm::export) }
        if (cards.isNotEmpty()) TextButton(onClick = { exporter.launch("lernsystem-karten.tsv") }) { Text(tr("Für Anki exportieren (TSV)", "Export for Anki (TSV)")) }
        if (cards.isEmpty()) Text(tr("Noch keine Karten.", "No cards yet."), style = MaterialTheme.typography.bodyMedium)
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(cards, key = { it.card.id }) { c ->
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(LatexLite.toPlain(c.card.front), style = MaterialTheme.typography.titleSmall)
                        Text(LatexLite.toPlain(c.card.answer), style = MaterialTheme.typography.bodySmall, maxLines = 3)
                        val origin = when {
                            c.card.source == CardSource.MANUAL -> tr("eigene Karte", "own card")
                            c.documentTitle != null -> tr("aus ${c.documentTitle}", "from ${c.documentTitle}")
                            else -> tr("Dokument gelöscht", "Document deleted")
                        }
                        Text(origin, style = MaterialTheme.typography.labelSmall)
                        Row {
                            TextButton(onClick = { editing = c.card }) { Text(tr("Bearbeiten", "Edit")) }
                            TextButton(onClick = { vm.delete(c.card) }) { Text(tr("Löschen", "Delete")) }
                        }
                    }
                }
            }
        }
    }
    if (creating) CardDialog(tr("Neue Karte", "New card"), "", "", onSave = { f, a -> vm.add(f, a); creating = false }, onDismiss = { creating = false })
    editing?.let { c -> CardDialog(tr("Karte bearbeiten", "Edit card"), c.front, c.answer, onSave = { f, a -> vm.edit(c, f, a); editing = null }, onDismiss = { editing = null }) }
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
                OutlinedTextField(f, { f = it }, label = { Text(tr("Frage", "Question")) }, minLines = 2)
                OutlinedTextField(a, { a = it }, label = { Text(tr("Antwort", "Answer")) }, minLines = 3)
            }
        },
        confirmButton = { TextButton(onClick = { onSave(f, a) }, enabled = f.isNotBlank() && a.isNotBlank()) { Text(tr("Speichern", "Save")) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text(tr("Abbrechen", "Cancel")) } },
    )
}

// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ui

import de.edgebird.lernsystem.core.i18n.tr

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Timer
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import de.edgebird.lernsystem.core.pomodoro.Pomodoro
import de.edgebird.lernsystem.core.pomodoro.PomodoroStatus
import de.edgebird.lernsystem.data.SubjectSummary
import de.edgebird.lernsystem.ui.theme.SubjectColorNames
import de.edgebird.lernsystem.ui.theme.SubjectColors
import de.edgebird.lernsystem.ui.theme.subjectColor

@Composable
fun HomeScreen(onOpen: (Long) -> Unit, onFocus: () -> Unit, onModels: () -> Unit, onPrivacy: () -> Unit, onAbout: () -> Unit = {}, onOpenSources: (Long) -> Unit = onOpen, vm: HomeViewModel = viewModel(), focusVm: PomodoroViewModel = viewModel()) {
    val subjects by vm.subjects.collectAsStateWithLifecycle()
    val strip by vm.strip.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { vm.refresh() }
    var editing by remember { mutableStateOf<SubjectSummary?>(null) }
    var creating by remember { mutableStateOf(false) }
    var deleting by remember { mutableStateOf<SubjectSummary?>(null) }
    val context = androidx.compose.ui.platform.LocalContext.current
    var menu by remember { mutableStateOf(false) }
    var reminder by remember { mutableStateOf(false) }
    var language by remember { mutableStateOf(false) }

    Box(Modifier.fillMaxSize()) {
        LazyColumn(contentPadding = androidx.compose.foundation.layout.PaddingValues(start = 16.dp, end = 16.dp, top = 20.dp, bottom = 110.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        AppBrand()
                        Text(tr("Meine Fächer", "My subjects"), style = MaterialTheme.typography.headlineLarge)
                        Text(java.time.LocalDate.now().format(java.time.format.DateTimeFormatter.ofPattern(tr("EEEE, d. MMMM", "EEEE, MMMM d"), de.edgebird.lernsystem.core.i18n.Lang.current.locale)), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    FocusChip(focusVm, onFocus)
                    Box {
                        IconButton(onClick = { menu = true }) { Icon(Icons.Default.MoreVert, contentDescription = tr("Menü", "Menu")) }
                        DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                            DropdownMenuItem(text = { Text("Sprache / Language") }, onClick = { menu = false; language = true })
                            DropdownMenuItem(text = { Text(tr("Lern-Erinnerung", "Study reminder")) }, onClick = { menu = false; reminder = true })
                            DropdownMenuItem(text = { Text(tr("KI-Modelle", "AI models")) }, onClick = { menu = false; onModels() })
                            DropdownMenuItem(text = { Text(tr("Datenschutz", "Privacy")) }, onClick = { menu = false; onPrivacy() })
                            DropdownMenuItem(text = { Text(tr("Über die App und Lizenz", "About the app and licence")) }, onClick = { menu = false; onAbout() })
                            DropdownMenuItem(text = { Text(tr("Rückmeldung senden", "Send feedback")) }, onClick = { menu = false; Feedback.general(context) })
                        }
                    }
                }
            }
            strip?.let { s -> item { DayStripCard(s) } }
            val list = subjects
            if (list != null && list.isEmpty()) item { EmptyHome(onExample = { vm.createExample(onOpenSources) }) }
            items(list.orEmpty(), key = { it.subject.id }) { s -> SubjectCard(s, onClick = { onOpen(s.subject.id) }, onLongClick = { editing = s }) }
        }
        ExtendedFloatingActionButton(
            onClick = { creating = true }, icon = { Icon(Icons.Default.Add, null) }, text = { Text(tr("Neues Fach", "New subject")) },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp), containerColor = MaterialTheme.colorScheme.primary, contentColor = MaterialTheme.colorScheme.onPrimary,
        )
    }

    if (language) LanguageDialog(onDismiss = { language = false })
    if (reminder) ReminderDialog(onDismiss = { reminder = false })
    if (creating) SubjectDialog(title = tr("Neues Fach", "New subject"), initialName = "", initialColor = (subjects?.size ?: 0) % SubjectColors.size, confirmLabel = tr("Anlegen", "Create"),
        onConfirm = { n, c -> vm.create(n, c); creating = false }, onDismiss = { creating = false })
    editing?.let { s ->
        SubjectDialog(title = tr("Fach bearbeiten", "Edit subject"), initialName = s.subject.name, initialColor = s.subject.colorIndex, confirmLabel = tr("Speichern", "Save"),
            onConfirm = { n, c -> vm.update(s.subject.id, n, c); editing = null }, onDismiss = { editing = null },
            onDelete = { deleting = s; editing = null })
    }
    deleting?.let { s ->
        AlertDialog(
            onDismissRequest = { deleting = null }, title = { Text(tr("„${s.subject.name}“ löschen?", "Delete “${s.subject.name}”?")) },
            text = { Text(tr("Das Fach mit seinen ${s.documentCount} Quellen, allen Abschnitten, Zusammenfassungen und ${s.cardCount} Karten wird unwiderruflich gelöscht.", "The subject with its ${s.documentCount} sources, all sections, summaries and ${s.cardCount} cards will be deleted irrevocably.")) },
            confirmButton = { TextButton(onClick = { vm.delete(s.subject.id); deleting = null }) { Text(tr("Endgültig löschen", "Delete permanently")) } },
            dismissButton = { TextButton(onClick = { deleting = null }) { Text(tr("Abbrechen", "Cancel")) } },
        )
    }
}

@Composable
internal fun FocusChip(vm: PomodoroViewModel, onClick: () -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    val now by vm.now.collectAsStateWithLifecycle()
    val active = state.status != PomodoroStatus.IDLE
    val secs = ((Pomodoro.remainingMs(state, now) + 999) / 1000).toInt()
    Surface(
        onClick = onClick, shape = RoundedCornerShape(50),
        color = if (active) MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.surfaceVariant,
        modifier = Modifier.semantics { contentDescription = if (active) tr("Fokus-Timer, noch ${secs / 60} Minuten", "Focus timer, ${secs / 60} minutes left") else tr("Fokus-Timer öffnen", "Open focus timer") },
    ) {
        Row(Modifier.padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Icon(Icons.Default.Timer, null, Modifier.size(18.dp))
            Text(if (active) "%02d:%02d".format(secs / 60, secs % 60) else tr("Fokus", "Focus"), style = MaterialTheme.typography.labelLarge)
        }
    }
}

@Composable
private fun DayStripCard(s: DayStrip) {
    Surface(shape = MaterialTheme.shapes.large, color = MaterialTheme.colorScheme.primaryContainer) {
        Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
            StripStat(tr("Fällig", "Due"), s.due.toString())
            StripStat(tr("Fokus", "Focus"), tr("${s.focusMinutes}/${s.focusGoal} Min", "${s.focusMinutes}/${s.focusGoal} min"))
            StripStat(tr("Serie", "Streak"), tr("${s.streak} Tg.", "${s.streak} d"))
        }
    }
}

@Composable
private fun StripStat(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.onPrimaryContainer)
        Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.75f))
    }
}

@Composable
private fun EmptyHome(onExample: () -> Unit) {
    Column(Modifier.fillMaxWidth().padding(vertical = 40.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(tr("Noch kein Fach", "No subject yet"), style = MaterialTheme.typography.headlineSmall)
        Text(tr("Lege ein Fach an, füge deine Unterlagen als Quellen hinzu und stelle dann Fragen, lerne mit Karten oder lass dich abfragen.", "Create a subject, add your materials as sources, then ask questions, study with cards or have yourself quizzed."), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        androidx.compose.material3.OutlinedButton(onClick = onExample, modifier = Modifier.padding(top = 12.dp)) { Text(tr("Mit einem Beispiel ausprobieren", "Try it with an example")) }
        Text(tr("Legt ein Fach mit zwei kurzen Lehrtexten an, damit du Chat, Karten und Quiz ohne eigene Unterlagen testen kannst.", "Creates a subject with two short lecture texts so you can try chat, cards and quiz without your own materials."), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

/** Fach-Karte mit farbigem „Buchrücken“. */
@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun SubjectCard(s: SubjectSummary, onClick: () -> Unit, onLongClick: () -> Unit) {
    val color = subjectColor(s.subject.colorIndex)
    Surface(
        shape = MaterialTheme.shapes.large, color = MaterialTheme.colorScheme.surface, tonalElevation = 1.dp, shadowElevation = 1.dp,
        modifier = Modifier.fillMaxWidth().clip(MaterialTheme.shapes.large).combinedClickable(onClick = onClick, onLongClick = onLongClick)
            .semantics { contentDescription = tr("${s.subject.name}, ${s.documentCount} Quellen, ${s.dueCount} fällige Karten. Lange drücken zum Bearbeiten.", "${s.subject.name}, ${s.documentCount} sources, ${s.dueCount} cards due. Long-press to edit.") },
    ) {
        Row(Modifier.height(IntrinsicSize.Min)) {
            Box(Modifier.width(12.dp).fillMaxHeight().background(color))
            Column(Modifier.padding(16.dp).weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(displaySubjectName(s.subject.name), style = MaterialTheme.typography.titleLarge)
                Text("${s.documentCount} ${if (s.documentCount == 1) tr("Quelle", "source") else tr("Quellen", "sources")} · ${s.cardCount} ${tr("Karten", "cards")}", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (s.dueCount > 0) {
                Box(Modifier.padding(16.dp).align(Alignment.CenterVertically).clip(RoundedCornerShape(50)).background(color.copy(alpha = 0.18f)).padding(horizontal = 12.dp, vertical = 6.dp)) {
                    Text(tr("${s.dueCount} fällig", "${s.dueCount} due"), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurface)
                }
            }
        }
    }
}

@Composable
private fun SubjectDialog(title: String, initialName: String, initialColor: Int, confirmLabel: String, onConfirm: (String, Int) -> Unit, onDismiss: () -> Unit, onDelete: (() -> Unit)? = null) {
    var name by remember { mutableStateOf(initialName) }
    var color by remember { mutableIntStateOf(initialColor) }
    AlertDialog(
        onDismissRequest = onDismiss, title = { Text(title) },
        text = {
            Column(Modifier.verticalScroll(androidx.compose.foundation.rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(value = name, onValueChange = { name = it.take(40) }, label = { Text(tr("Name des Fachs", "Name of the subject")) }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Text(tr("Farbe", "Colour"), style = MaterialTheme.typography.labelLarge)
                androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    SubjectColors.forEachIndexed { i, c ->
                        Box(
                            Modifier.size(36.dp).clip(CircleShape).background(c).clickable { color = i }
                                .then(if (i == color) Modifier.background(Color.Black.copy(alpha = 0.0f)) else Modifier)
                                .semantics { contentDescription = SubjectColorNames[i] + if (i == color) tr(", gewählt", ", selected") else "" },
                            contentAlignment = Alignment.Center,
                        ) { if (i == color) Text("✓", color = Color.White, style = MaterialTheme.typography.titleMedium) }
                    }
                }
                if (onDelete != null) TextButton(onClick = onDelete) { Text(tr("Fach löschen …", "Delete subject …"), color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = { TextButton(onClick = { onConfirm(name, color) }, enabled = name.isNotBlank()) { Text(confirmLabel) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text(tr("Abbrechen", "Cancel")) } },
    )
}

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
private fun ReminderDialog(onDismiss: () -> Unit) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val prefs = remember { (context.applicationContext as de.edgebird.lernsystem.LernsystemApp).graph.prefs }
    var on by remember { mutableStateOf(prefs.getBoolean(de.edgebird.lernsystem.work.ReminderWork.PREF_ON, false)) }
    val picker = androidx.compose.material3.rememberTimePickerState(prefs.getInt(de.edgebird.lernsystem.work.ReminderWork.PREF_HOUR, 18), prefs.getInt(de.edgebird.lernsystem.work.ReminderWork.PREF_MINUTE, 0), true)
    AlertDialog(
        onDismissRequest = onDismiss, title = { Text(tr("Lern-Erinnerung", "Study reminder")) },
        text = {
            Column(Modifier.verticalScroll(androidx.compose.foundation.rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(tr("Täglich zur gewählten Zeit, wenn Karten fällig sind und dein Tagesziel noch nicht erreicht ist. Android darf die Zeit um einige Minuten verschieben.", "Daily at the chosen time, when cards are due and your daily goal has not been reached yet. Android may shift the time by a few minutes."), style = MaterialTheme.typography.bodySmall)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(tr("Erinnerung an", "Remind me"), Modifier.weight(1f))
                    androidx.compose.material3.Switch(checked = on, onCheckedChange = { on = it })
                }
                if (on) androidx.compose.material3.TimePicker(state = picker)
            }
        },
        confirmButton = {
            TextButton(onClick = {
                prefs.edit().putBoolean(de.edgebird.lernsystem.work.ReminderWork.PREF_ON, on).putInt(de.edgebird.lernsystem.work.ReminderWork.PREF_HOUR, picker.hour).putInt(de.edgebird.lernsystem.work.ReminderWork.PREF_MINUTE, picker.minute).apply()
                de.edgebird.lernsystem.work.ReminderWork.apply(context, on, picker.hour, picker.minute)
                onDismiss()
            }) { Text(tr("Speichern", "Save")) }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text(tr("Abbrechen", "Cancel")) } },
    )
}

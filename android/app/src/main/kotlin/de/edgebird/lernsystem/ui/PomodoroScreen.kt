package de.edgebird.lernsystem.ui

import android.content.Intent
import android.provider.Settings
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import de.edgebird.lernsystem.core.pomodoro.Pomodoro
import de.edgebird.lernsystem.core.pomodoro.PomodoroPhase
import de.edgebird.lernsystem.core.pomodoro.PomodoroSettings
import de.edgebird.lernsystem.core.pomodoro.PomodoroStatus

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PomodoroScreen(onBack: (() -> Unit)? = null, vm: PomodoroViewModel = viewModel()) {
    val state by vm.state.collectAsStateWithLifecycle()
    val now by vm.now.collectAsStateWithLifecycle()
    val settings by vm.settings.collectAsStateWithLifecycle()
    val goal by vm.goalMinutes.collectAsStateWithLifecycle()
    val keepOn by vm.keepScreenOn.collectAsStateWithLifecycle()
    val stats by vm.stats.collectAsStateWithLifecycle()
    val docs by vm.documents.collectAsStateWithLifecycle(emptyList())
    val context = LocalContext.current
    var showSettings by remember { mutableStateOf(false) }
    var selectedDoc by rememberSaveable { mutableStateOf<Long?>(null) }
    var menuOpen by remember { mutableStateOf(false) }

    // Display an lassen, solange der Timer läuft und es gewünscht ist
    val activity = context as? android.app.Activity
    val hold = keepOn && state.status == PomodoroStatus.RUNNING
    DisposableEffect(hold) {
        if (hold) activity?.window?.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        onDispose { activity?.window?.clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
    }

    val remaining = Pomodoro.remainingMs(state, now)
    val total = state.phaseTotalMs.coerceAtLeast(1)
    val idle = state.status == PomodoroStatus.IDLE
    val phaseLabel = when (state.phase) {
        PomodoroPhase.FOCUS -> "Fokus"
        PomodoroPhase.SHORT_BREAK -> "Kurze Pause"
        PomodoroPhase.LONG_BREAK -> "Lange Pause"
    }
    val ringColor = if (state.phase == PomodoroPhase.FOCUS) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.tertiary
    val track = MaterialTheme.colorScheme.surfaceVariant

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (onBack != null) androidx.compose.material3.IconButton(onClick = onBack) { androidx.compose.material3.Icon(androidx.compose.material.icons.Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Zurück") }
            Text("Fokus", style = MaterialTheme.typography.headlineMedium)
        }
        if (!vm.exactAlarms) {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("Erinnerungen können sich verspäten, weil genaue Alarme nicht erlaubt sind.", style = MaterialTheme.typography.bodySmall)
                    TextButton(onClick = { context.startActivity(Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM).setData(android.net.Uri.parse("package:${context.packageName}"))) }) { Text("Erlauben") }
                }
            }
        }
        val secsLeft = ((remaining + 999) / 1000).toInt()
        val spoken = "$phaseLabel, noch ${secsLeft / 60} Minuten ${secsLeft % 60} Sekunden" + when (state.status) { PomodoroStatus.PAUSED -> ", pausiert"; PomodoroStatus.WAITING -> ", bereit"; else -> "" }
        Box(Modifier.fillMaxWidth().semantics(mergeDescendants = true) { contentDescription = spoken }, contentAlignment = Alignment.Center) {
            Canvas(Modifier.size(240.dp)) {
                val w = 14.dp.toPx()
                val inset = w / 2
                val sz = Size(size.width - w, size.height - w)
                drawArc(track, 0f, 360f, false, topLeft = Offset(inset, inset), size = sz, style = Stroke(w))
                val frac = if (idle) 1f else remaining.toFloat() / total
                drawArc(ringColor, -90f, 360f * frac, false, topLeft = Offset(inset, inset), size = sz, style = Stroke(w, cap = StrokeCap.Round))
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                val secs = ((remaining + 999) / 1000).toInt()
                Text("%02d:%02d".format(secs / 60, secs % 60), fontSize = 52.sp, fontWeight = FontWeight.Light)
                Text(
                    when (state.status) {
                        PomodoroStatus.PAUSED -> "$phaseLabel · pausiert"
                        PomodoroStatus.WAITING -> "$phaseLabel bereit"
                        else -> phaseLabel
                    },
                    style = MaterialTheme.typography.titleMedium,
                )
                Text("Runde ${state.completedFocus % settings.cyclesBeforeLongBreak + 1} von ${settings.cyclesBeforeLongBreak}", style = MaterialTheme.typography.bodySmall)
            }
        }

        if (idle || state.status == PomodoroStatus.WAITING) {
            ExposedDropdownMenuBox(expanded = menuOpen, onExpandedChange = { menuOpen = it }) {
                OutlinedTextField(
                    value = docs.firstOrNull { it.document.id == (selectedDoc ?: state.documentId) }?.document?.title ?: "Ohne Dokument",
                    onValueChange = {}, readOnly = true, label = { Text("Lerne gerade für") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(menuOpen) },
                    modifier = Modifier.menuAnchor().fillMaxWidth(),
                )
                ExposedDropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                    DropdownMenuItem(text = { Text("Ohne Dokument") }, onClick = { selectedDoc = null; menuOpen = false })
                    docs.forEach { d -> DropdownMenuItem(text = { Text(d.document.title) }, onClick = { selectedDoc = d.document.id; menuOpen = false }) }
                }
            }
        }

        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            when (state.status) {
                PomodoroStatus.IDLE, PomodoroStatus.WAITING -> Button(onClick = { vm.start(selectedDoc ?: state.documentId) }, modifier = Modifier.weight(1f)) { Text("Starten") }
                PomodoroStatus.RUNNING -> Button(onClick = vm::pause, modifier = Modifier.weight(1f)) { Text("Pause") }
                PomodoroStatus.PAUSED -> Button(onClick = vm::resume, modifier = Modifier.weight(1f)) { Text("Fortsetzen") }
            }
            if (!idle) {
                OutlinedButton(onClick = vm::skip, modifier = Modifier.weight(1f)) { Text("Überspringen") }
                OutlinedButton(onClick = vm::stop, modifier = Modifier.weight(1f)) { Text("Beenden") }
            }
        }

        val s = stats
        if (s != null) {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Heute ${s.todayMinutes} von $goal Min Fokus", style = MaterialTheme.typography.bodyMedium)
                    LinearProgressIndicator(progress = { de.edgebird.lernsystem.core.pomodoro.FocusStats.goalProgress(s.todayMinutes, goal) }, modifier = Modifier.fillMaxWidth())
                    val max = (s.week.maxOfOrNull { it.minutes } ?: 0).coerceAtLeast(1)
                    val fmt = java.time.format.DateTimeFormatter.ofPattern("EE", java.util.Locale.GERMAN)
                    Row(Modifier.fillMaxWidth().padding(top = 4.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Bottom) {
                        s.week.forEach { d ->
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Text(d.minutes.toString(), style = MaterialTheme.typography.labelSmall)
                                Box(Modifier.padding(vertical = 2.dp).width(22.dp).height((6 + 40 * d.minutes / max).dp).background(MaterialTheme.colorScheme.primary.copy(alpha = if (d.minutes > 0) 1f else 0.25f), RoundedCornerShape(4.dp)))
                                Text(java.time.Instant.ofEpochMilli(d.dayStartMillis).atZone(java.time.ZoneId.systemDefault()).format(fmt), style = MaterialTheme.typography.labelSmall)
                            }
                        }
                    }
                    if (s.byDocument.isNotEmpty()) {
                        Text("Letzte 7 Tage je Dokument", style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(top = 4.dp))
                        s.byDocument.forEach { Text("${it.title ?: "Ohne Dokument"}: ${Math.round(it.focusedMs / 60_000.0)} Min", style = MaterialTheme.typography.bodySmall) }
                    }
                }
            }
        }
        TextButton(onClick = { showSettings = true }) { Text("Zeiten und Tagesziel") }
    }
    if (showSettings) PomodoroSettingsDialog(settings, goal, keepOn, onSave = { st, g, k -> vm.save(st, g, k); showSettings = false }, onDismiss = { showSettings = false })
}

@Composable
private fun PomodoroSettingsDialog(s: PomodoroSettings, goal: Int, keepOn: Boolean, onSave: (PomodoroSettings, Int, Boolean) -> Unit, onDismiss: () -> Unit) {
    var focus by remember { mutableStateOf((s.focusSeconds / 60).toString()) }
    var short by remember { mutableStateOf((s.shortBreakSeconds / 60).toString()) }
    var long by remember { mutableStateOf((s.longBreakSeconds / 60).toString()) }
    var cycles by remember { mutableStateOf(s.cyclesBeforeLongBreak.toString()) }
    var g by remember { mutableStateOf(goal.toString()) }
    var autoBreaks by remember { mutableStateOf(s.autoStartBreaks) }
    var autoFocus by remember { mutableStateOf(s.autoStartFocus) }
    var keep by remember { mutableStateOf(keepOn) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Fokus-Einstellungen") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                NumberField("Fokus (Min)", focus) { focus = it }
                NumberField("Kurze Pause (Min)", short) { short = it }
                NumberField("Lange Pause (Min)", long) { long = it }
                NumberField("Runden bis zur langen Pause", cycles) { cycles = it }
                NumberField("Tagesziel Fokus (Min)", g) { g = it }
                SwitchRow("Pausen automatisch starten", autoBreaks) { autoBreaks = it }
                SwitchRow("Nächsten Fokus automatisch starten", autoFocus) { autoFocus = it }
                SwitchRow("Display an, solange der Timer läuft", keep) { keep = it }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                fun n(v: String, d: Int, min: Int, max: Int) = (v.toIntOrNull() ?: d).coerceIn(min, max)
                onSave(
                    s.copy(
                        focusSeconds = n(focus, 25, 1, 180) * 60, shortBreakSeconds = n(short, 5, 1, 60) * 60, longBreakSeconds = n(long, 15, 1, 120) * 60,
                        cyclesBeforeLongBreak = n(cycles, 4, 2, 10), autoStartBreaks = autoBreaks, autoStartFocus = autoFocus,
                    ),
                    n(g, 120, 0, 1000), keep,
                )
            }) { Text("Speichern") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Abbrechen") } },
    )
}

@Composable
private fun NumberField(label: String, value: String, onChange: (String) -> Unit) = OutlinedTextField(
    value = value, onValueChange = { onChange(it.filter(Char::isDigit).take(4)) }, label = { Text(label) }, singleLine = true,
    keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = androidx.compose.ui.text.input.KeyboardType.Number), modifier = Modifier.fillMaxWidth(),
)

@Composable
private fun SwitchRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit) = Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
    Text(label, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
    Switch(checked, onChange)
}

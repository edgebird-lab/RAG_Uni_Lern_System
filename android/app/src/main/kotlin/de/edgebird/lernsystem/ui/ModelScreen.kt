package de.edgebird.lernsystem.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import de.edgebird.lernsystem.core.models.ModelInfo
import de.edgebird.lernsystem.core.models.ModelPlan

private fun mb(bytes: Long) = if (bytes >= 1_000_000_000) "%.1f GB".format(bytes / 1e9) else "${bytes / 1_000_000} MB"

/**
 * Erststart-Assistent und Modellverwaltung: prüft Gerät und Speicher, zeigt Lizenz, lädt die Modelle.
 * [onDone] wird aufgerufen, sobald alle nötigen Modelle vorliegen (nur im Erststart-Modus).
 */
@Composable
fun ModelScreen(firstRun: Boolean, onDone: () -> Unit, onBack: (() -> Unit)? = null, vm: ModelViewModel = viewModel()) {
    val check by vm.check.collectAsStateWithLifecycle()
    val dl by vm.download.collectAsStateWithLifecycle()
    val wifiOnly by vm.wifiOnly.collectAsStateWithLifecycle()
    val context = LocalContext.current
    var confirmReinstall by androidx.compose.runtime.remember { androidx.compose.runtime.mutableStateOf(false) }
    val busy = dl?.running == true || dl?.queued == true

    if (firstRun) androidx.compose.runtime.LaunchedEffect(check, dl) { if (check is ModelCheck.Ready && vm.filesReady() && !busy) onDone() }

    if (confirmReinstall) ReinstallDialog(onConfirm = { confirmReinstall = false; vm.reinstall() }, onDismiss = { confirmReinstall = false })
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(if (firstRun) "Willkommen" else "KI-Modelle", style = MaterialTheme.typography.headlineMedium)
        if (firstRun) Text("Die KI läuft komplett auf diesem Gerät. Dafür lädt die App einmalig zwei Modelle herunter. Danach brauchst du kein Internet mehr, und deine Unterlagen verlassen das Gerät nie.", style = MaterialTheme.typography.bodyMedium)

        when (val c = check) {
            ModelCheck.Loading -> Text("Prüfe verfügbare Modelle …")
            is ModelCheck.Failed -> {
                Text("Die Modellliste ist nicht erreichbar: ${c.message}", color = MaterialTheme.colorScheme.error)
                Button(onClick = vm::refresh) { Text("Erneut versuchen") }
            }
            is ModelCheck.Ready -> {
                Text(if (c.updates.isEmpty()) "Alle Modelle sind vorhanden und aktuell." else "Neuere Modelle verfügbar: ${c.updates.joinToString { it.title }}.")
                if (c.updates.isNotEmpty()) {
                    Text("Das alte Modell bleibt, bis das neue vollständig geladen und geprüft ist. Danach die App einmal komplett schließen und neu öffnen.", style = MaterialTheme.typography.bodySmall)
                    if (!busy) Button(onClick = vm::start, modifier = Modifier.fillMaxWidth()) { Text("Update laden") }
                } else OutlinedButton(onClick = vm::refresh) { Text("Nach Updates suchen") }
            }
            is ModelCheck.Needed -> NeededCard(c.pending, c.ramMb, c.freeMb, c.manifest.licenseUrl, busy)
        }

        dl?.let { d ->
            if (busy) {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    if (d.total > 0) {
                        Text("${d.name}: ${mb(d.done)} von ${mb(d.total)}")
                        LinearProgressIndicator(progress = { d.done.toFloat() / d.total }, modifier = Modifier.fillMaxWidth())
                    } else Text(if (d.queued) "Wartet auf ${if (wifiOnly) "WLAN" else "Netzwerk"} …" else "Startet …")
                    OutlinedButton(onClick = vm::cancel) { Text("Abbrechen") }
                    Text("Ein Abbruch behält den Fortschritt; beim nächsten Start geht es dort weiter.", style = MaterialTheme.typography.bodySmall)
                }
            }
            d.error?.let { Text("$it", color = MaterialTheme.colorScheme.error) }
        }

        val needed = check as? ModelCheck.Needed
        if (needed != null && !busy) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text("Nur im WLAN laden", Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                Switch(checked = wifiOnly, onCheckedChange = vm::setWifiOnly)
            }
            val enoughSpace = needed.freeMb * 1_048_576 > needed.pending.sumOf { it.size } + 300L * 1_048_576
            if (!enoughSpace) Text("Zu wenig freier Speicher: ${needed.pending.sumOf { it.size } / 1_000_000 + 300} MB nötig, ${needed.freeMb} MB frei.", color = MaterialTheme.colorScheme.error)
            Button(onClick = vm::start, enabled = enoughSpace, modifier = Modifier.fillMaxWidth()) {
                Text(if (dl?.error != null) "Erneut versuchen" else "Modelle herunterladen (${mb(needed.pending.sumOf { it.size })})")
            }
        }
        if (check is ModelCheck.Ready && !busy) TextButton(onClick = { confirmReinstall = true }) { Text("Modelle löschen und neu laden") }
        if (onBack != null) TextButton(onClick = onBack) { Text("Zurück") }
        TextButton(onClick = { context.startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW, android.net.Uri.parse("https://github.com/edgebird-lab/lernsystem-modelle"))) }) { Text("Modell-Quelle und Lizenz (Apache 2.0)") }
    }
}

@Composable
private fun ReinstallDialog(onConfirm: () -> Unit, onDismiss: () -> Unit) = androidx.compose.material3.AlertDialog(
    onDismissRequest = onDismiss,
    title = { Text("Modelle neu laden?") },
    text = { Text("Beide Modelle (2,8 GB) werden gelöscht und danach erneut heruntergeladen. Deine Dokumente und Karten bleiben unberührt. Der erste Start danach dauert wieder einige Minuten.") },
    confirmButton = { TextButton(onClick = onConfirm) { Text("Löschen und neu laden") } },
    dismissButton = { TextButton(onClick = onDismiss) { Text("Abbrechen") } },
)

@Composable
private fun NeededCard(pending: List<ModelInfo>, ramMb: Long, freeMb: Long, licenseUrl: String, busy: Boolean) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Das wird geladen", style = MaterialTheme.typography.titleMedium)
            pending.forEach { Text("• ${it.title}: ${mb(it.size)}") }
            Text("Gerät: ${ramMb / 1024} GB Arbeitsspeicher, ${freeMb / 1024} GB frei", style = MaterialTheme.typography.bodySmall)
            pending.filter { !ModelPlan.fitsRam(it, ramMb) }.forEach {
                Text("Achtung: ${it.title} braucht mindestens ${it.minRamMb / 1000} GB Arbeitsspeicher. Auf diesem Gerät kann es langsam sein oder abstürzen.", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            }
            Text("Beide Modelle stehen unter der Apache-Lizenz 2.0 (Google LLC und Beitragende) und werden unverändert verteilt. Mit dem Download erkennst du die Lizenz an.", style = MaterialTheme.typography.bodySmall)
            if (!busy) Text("Beim ersten Start danach optimiert die App das Sprachmodell für die Grafikeinheit; das dauert einmalig einige Minuten.", style = MaterialTheme.typography.bodySmall)
        }
    }
}

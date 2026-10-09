// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ui

import de.edgebird.lernsystem.core.i18n.tr

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
    val voices by vm.voices.collectAsStateWithLifecycle()
    val withVoice by vm.withVoice.collectAsStateWithLifecycle()
    val context = LocalContext.current
    var confirmReinstall by androidx.compose.runtime.remember { androidx.compose.runtime.mutableStateOf(false) }
    val busy = dl?.running == true || dl?.queued == true

    if (firstRun) androidx.compose.runtime.LaunchedEffect(check, dl) { if (check is ModelCheck.Ready && vm.filesReady() && !busy) onDone() }

    if (confirmReinstall) ReinstallDialog(onConfirm = { confirmReinstall = false; vm.reinstall() }, onDismiss = { confirmReinstall = false })
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (firstRun) androidx.compose.foundation.layout.Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            AppLogo(44.dp)
            Text(de.edgebird.lernsystem.AppInfo.NAME, style = MaterialTheme.typography.titleLarge)
        }
        Text(if (firstRun) tr("Willkommen", "Welcome") else tr("KI-Modelle", "AI models"), style = MaterialTheme.typography.headlineMedium)
        if (firstRun) LanguageChips()
        if (firstRun) Text(tr("Die KI läuft komplett auf diesem Gerät. Dafür lädt die App einmalig zwei Modelle herunter. Danach brauchst du kein Internet mehr, und deine Unterlagen verlassen das Gerät nie.", "The AI runs entirely on this device. For that the app downloads two models once. After that you need no internet, and your materials never leave the device."), style = MaterialTheme.typography.bodyMedium)

        when (val c = check) {
            ModelCheck.Loading -> Text(tr("Prüfe verfügbare Modelle …", "Checking available models …"))
            is ModelCheck.Failed -> {
                Text(tr("Die Modellliste ist nicht erreichbar: ${c.message}", "The model list is not reachable: ${c.message}"), color = MaterialTheme.colorScheme.error)
                Button(onClick = vm::refresh) { Text(tr("Erneut versuchen", "Try again")) }
            }
            is ModelCheck.Ready -> {
                VoicesSection(vm, busy)
                Text(if (c.updates.isEmpty()) tr("Alle Modelle sind vorhanden und aktuell.", "All models are present and up to date.") else tr("Neuere Modelle verfügbar: ${c.updates.joinToString { it.title }}.", "Newer models available: ${c.updates.joinToString { it.title }}."))
                if (c.updates.isNotEmpty()) {
                    Text(tr("Das alte Modell bleibt, bis das neue vollständig geladen und geprüft ist. Danach die App einmal komplett schließen und neu öffnen.", "The old model stays until the new one is fully downloaded and verified. Then close the app completely and reopen it."), style = MaterialTheme.typography.bodySmall)
                    if (!busy) Button(onClick = vm::start, modifier = Modifier.fillMaxWidth()) { Text(tr("Update laden", "Download update")) }
                } else OutlinedButton(onClick = vm::refresh) { Text(tr("Nach Updates suchen", "Check for updates")) }
            }
            is ModelCheck.Needed -> {
                NeededCard(c.pending, c.ramMb, c.freeMb, c.manifest.licenseUrl, busy)
                voices.recommended()?.takeIf { !voices.hasVoiceFor() }?.let { v ->
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(tr("Zusatzpaket Stimme zum Vorlesen mitladen (${mb(v.size)})", "Also download the voice add-on for reading aloud (${mb(v.size)})"), style = MaterialTheme.typography.bodyMedium)
                            Text(tr("${v.displayTitle()}: läuft komplett auf dem Gerät. Später jederzeit nachladbar.", "${v.displayTitle()}: runs entirely on the device. Can be added any time later."), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Switch(checked = withVoice, onCheckedChange = vm::setWithVoice)
                    }
                }
            }
        }

        dl?.let { d ->
            if (busy) {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    if (d.total > 0) {
                        Text(tr("${d.name}: ${mb(d.done)} von ${mb(d.total)}", "${d.name}: ${mb(d.done)} of ${mb(d.total)}"))
                        LinearProgressIndicator(progress = { d.done.toFloat() / d.total }, modifier = Modifier.fillMaxWidth())
                    } else Text(if (d.queued) tr("Wartet auf ${if (wifiOnly) "WLAN" else "Netzwerk"} …", "Waiting for ${if (wifiOnly) "Wi-Fi" else "network"} …") else tr("Startet …", "Starting …"))
                    OutlinedButton(onClick = vm::cancel) { Text(tr("Abbrechen", "Cancel")) }
                    Text(tr("Ein Abbruch behält den Fortschritt; beim nächsten Start geht es dort weiter.", "Cancelling keeps the progress; the next start continues from there."), style = MaterialTheme.typography.bodySmall)
                }
            }
            d.error?.let { Text("$it", color = MaterialTheme.colorScheme.error) }
        }

        val needed = check as? ModelCheck.Needed
        if (needed != null && !busy) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(tr("Nur im WLAN laden", "Download on Wi-Fi only"), Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                Switch(checked = wifiOnly, onCheckedChange = vm::setWifiOnly)
            }
            val enoughSpace = needed.freeMb * 1_048_576 > needed.pending.sumOf { it.size } + 300L * 1_048_576
            if (!enoughSpace) Text(tr("Zu wenig freier Speicher: ${needed.pending.sumOf { it.size } / 1_000_000 + 300} MB nötig, ${needed.freeMb} MB frei.", "Not enough free storage: ${needed.pending.sumOf { it.size } / 1_000_000 + 300} MB needed, ${needed.freeMb} MB free."), color = MaterialTheme.colorScheme.error)
            Button(onClick = vm::start, enabled = enoughSpace, modifier = Modifier.fillMaxWidth()) {
                Text(if (dl?.error != null) tr("Erneut versuchen", "Try again") else tr("Modelle herunterladen (${mb(needed.pending.sumOf { it.size } + if (withVoice && !voices.hasVoiceFor()) voices.recommended()?.size ?: 0L else 0L)})", "Download models (${mb(needed.pending.sumOf { it.size } + if (withVoice && !voices.hasVoiceFor()) voices.recommended()?.size ?: 0L else 0L)})"))
            }
        }
        if (check is ModelCheck.Ready && !busy) TextButton(onClick = { confirmReinstall = true }) { Text(tr("Modelle löschen und neu laden", "Delete and re-download models")) }
        if (onBack != null) TextButton(onClick = onBack) { Text(tr("Zurück", "Back")) }
        TextButton(onClick = { context.startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW, android.net.Uri.parse("https://github.com/edgebird-lab/lernsystem-modelle"))) }) { Text(tr("Modell-Quelle und Lizenz (Apache 2.0)", "Model source and licence (Apache 2.0)")) }
    }
}

@Composable
private fun ReinstallDialog(onConfirm: () -> Unit, onDismiss: () -> Unit) = androidx.compose.material3.AlertDialog(
    onDismissRequest = onDismiss,
    title = { Text(tr("Modelle neu laden?", "Re-download models?")) },
    text = { Text(tr("Beide Modelle (2,8 GB) werden gelöscht und danach erneut heruntergeladen. Deine Dokumente und Karten bleiben unberührt. Der erste Start danach dauert wieder einige Minuten.", "Both models (2.8 GB) will be deleted and downloaded again. Your documents and cards are not affected. The first start afterwards takes a few minutes again.")) },
    confirmButton = { TextButton(onClick = onConfirm) { Text(tr("Löschen und neu laden", "Delete and re-download")) } },
    dismissButton = { TextButton(onClick = onDismiss) { Text(tr("Abbrechen", "Cancel")) } },
)

@Composable
private fun NeededCard(pending: List<ModelInfo>, ramMb: Long, freeMb: Long, licenseUrl: String, busy: Boolean) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(tr("Das wird geladen", "This will be downloaded"), style = MaterialTheme.typography.titleMedium)
            pending.forEach { Text("• ${it.displayTitle()}: ${mb(it.size)}") }
            Text(tr("Gerät: ${ramMb / 1024} GB Arbeitsspeicher, ${freeMb / 1024} GB frei", "Device: ${ramMb / 1024} GB memory, ${freeMb / 1024} GB free"), style = MaterialTheme.typography.bodySmall)
            pending.filter { !ModelPlan.fitsRam(it, ramMb) }.forEach {
                Text(tr("Achtung: ${it.title} braucht mindestens ${it.minRamMb / 1000} GB Arbeitsspeicher. Auf diesem Gerät kann es langsam sein oder abstürzen.", "Warning: ${it.title} needs at least ${it.minRamMb / 1000} GB of memory. On this device it may be slow or crash."), color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            }
            Text(tr("Beide Modelle stehen unter der Apache-Lizenz 2.0 (Google LLC und Beitragende) und werden unverändert verteilt. Mit dem Download erkennst du die Lizenz an.", "Both models are licensed under the Apache License 2.0 (Google LLC and contributors) and are distributed unchanged. By downloading you accept the licence."), style = MaterialTheme.typography.bodySmall)
            if (!busy) Text(tr("Beim ersten Start danach optimiert die App das Sprachmodell für die Grafikeinheit; das dauert einmalig einige Minuten.", "On the first start afterwards the app optimises the language model for the graphics unit; this takes a few minutes once."), style = MaterialTheme.typography.bodySmall)
        }
    }
}

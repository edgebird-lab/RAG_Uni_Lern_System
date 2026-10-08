package de.edgebird.lernsystem.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import de.edgebird.lernsystem.core.i18n.Lang
import de.edgebird.lernsystem.core.i18n.tr
import de.edgebird.lernsystem.core.models.ModelInfo
import de.edgebird.lernsystem.voice.VoiceEntry

private fun mb(bytes: Long) = "${bytes / 1_000_000} MB"

/**
 * Stimmen für das Vorlesen: Katalog aus dem Modell-Repo (Download wie bei den KI-Modellen), Auswahl je Sprache, Hörprobe und Import eigener Stimmen.
 * Die Stimme der App-Sprache wird zum Vorlesen genutzt; nichts verlässt das Gerät.
 */
@Composable
fun VoicesSection(vm: ModelViewModel, busy: Boolean) {
    val st by vm.voices.collectAsStateWithLifecycle()
    val speaker = rememberSpeechOutput()
    var importLang by remember { mutableStateOf(Lang.current) }
    var confirmDelete by remember { mutableStateOf<VoiceEntry?>(null) }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> if (uri != null) vm.importVoice(uri, importLang) }

    confirmDelete?.let { e ->
        androidx.compose.material3.AlertDialog(
            onDismissRequest = { confirmDelete = null },
            title = { Text(tr("Stimme löschen?", "Delete voice?")) },
            text = { Text(tr("„${e.name}“ wird vom Gerät entfernt. Aus dem Katalog lässt sie sich jederzeit erneut laden.", "“${e.name}” will be removed from the device. Catalogue voices can be downloaded again at any time.")) },
            confirmButton = { TextButton(onClick = { vm.deleteVoice(e); confirmDelete = null }) { Text(tr("Löschen", "Delete")) } },
            dismissButton = { TextButton(onClick = { confirmDelete = null }) { Text(tr("Abbrechen", "Cancel")) } },
        )
    }

    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(tr("Stimmen (Vorlesen)", "Voices (read aloud)"), style = MaterialTheme.typography.titleMedium)
            Text(
                tr("Das Vorlesen läuft komplett auf dem Gerät. Je Sprache wird die gewählte Stimme genutzt; Online-Stimmen des Geräts werden bewusst nicht benutzt.", "Reading aloud runs entirely on the device. For each language the chosen voice is used; the device’s online voices are deliberately not used."),
                style = MaterialTheme.typography.bodySmall,
            )
            // Sprache der App zuerst
            for (lang in Lang.entries.sortedBy { if (it == Lang.current) 0 else 1 }) {
                val catalog = st.catalog.filter { it.lang == lang.tag }
                val catalogDirs = catalog.map { it.unpack }.toSet()
                val custom = st.installed.filter { it.lang == lang && (it.custom || it.dir.name !in catalogDirs) }
                if (catalog.isEmpty() && custom.isEmpty()) continue
                Text(lang.nativeName, style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(top = 6.dp))
                catalog.forEach { m -> CatalogRow(m, st.entryFor(m), st.selected[lang], busy, vm, speaker) { confirmDelete = it } }
                custom.forEach { e -> InstalledRow(e.name + tr(" (eigene Stimme)", " (own voice)"), "", e, st.selected[lang] == e.id, vm, speaker) { confirmDelete = it } }
            }
            if (st.catalog.isEmpty()) Text(tr("Die Stimmenliste ist offline nicht verfügbar. Bereits geladene Stimmen funktionieren weiter.", "The voice list is not available offline. Voices already downloaded keep working."), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (!st.hasVoiceFor()) Text(tr("Für ${Lang.current.nativeName} ist noch keine Stimme geladen; ohne sie kann die App nicht vorlesen.", "No voice is downloaded for ${Lang.current.nativeName} yet; without one the app cannot read aloud."), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)

            Text(tr("Eigene Stimme importieren", "Import your own voice"), style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(top = 8.dp))
            Text(
                tr("ZIP-Datei mit model.onnx, tokens.txt und (optional) espeak-ng-data/ im Format der App; eine Anleitung steht im Modell-Repo (tools/make_voice_pack.sh). Die Stimme bleibt auf dem Gerät.", "ZIP file with model.onnx, tokens.txt and (optionally) espeak-ng-data/ in the app’s format; instructions are in the model repo (tools/make_voice_pack.sh). The voice stays on the device."),
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Lang.entries.forEach { l -> FilterChip(selected = importLang == l, onClick = { importLang = l }, label = { Text(l.nativeName) }) }
            }
            OutlinedButton(onClick = { picker.launch(arrayOf("application/zip", "application/x-zip-compressed", "application/octet-stream")) }, modifier = Modifier.fillMaxWidth()) { Text(tr("ZIP auswählen …", "Choose ZIP …")) }
            st.message?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary) }
            speaker.error?.takeIf { !speaker.missingVoice }?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error) }
        }
    }
}

@Composable
private fun CatalogRow(m: ModelInfo, entry: VoiceEntry?, selectedId: String?, busy: Boolean, vm: ModelViewModel, speaker: SpeechOutput, onDelete: (VoiceEntry) -> Unit) {
    if (entry != null) {
        InstalledRow(m.displayTitle(), m.displayDescription(), entry, selectedId == entry.id, vm, speaker, onDelete)
    } else {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(m.displayTitle(), style = MaterialTheme.typography.bodyMedium)
                val d = m.displayDescription()
                Text(if (d.isEmpty()) mb(m.size) else "$d · ${mb(m.size)}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Button(onClick = { vm.downloadVoice(m) }, enabled = !busy) { Text(tr("Laden", "Download")) }
        }
    }
}

@Composable
private fun InstalledRow(title: String, description: String, entry: VoiceEntry, selected: Boolean, vm: ModelViewModel, speaker: SpeechOutput, onDelete: (VoiceEntry) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        RadioButton(selected = selected, onClick = { vm.selectVoice(entry) })
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.bodyMedium)
            Text(listOf(tr("Installiert", "Installed"), description).filter { it.isNotEmpty() }.joinToString(" · "), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        TextButton(onClick = { if (speaker.speaking) speaker.stop() else speaker.preview(entry) }) { Text(if (speaker.speaking) tr("Stopp", "Stop") else tr("Anhören", "Listen")) }
        TextButton(onClick = { onDelete(entry) }) { Text(tr("Löschen", "Delete")) }
    }
}

// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ui

import de.edgebird.lernsystem.core.i18n.tr

import android.app.Application
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.data.UserData
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

class PrivacyViewModel(app: Application) : AndroidViewModel(app) {
    private val graph = (app as LernsystemApp).graph
    private val data by lazy { UserData(graph.db) }
    private val _message = MutableStateFlow<String?>(null)
    val message: StateFlow<String?> = _message

    fun export(uri: Uri) = viewModelScope.launch {
        _message.value = try {
            getApplication<Application>().contentResolver.openOutputStream(uri)?.use { data.export(it) } ?: error(tr("Datei nicht beschreibbar", "File not writable"))
            tr("Export gespeichert.", "Export saved.")
        } catch (e: Exception) { tr("Export fehlgeschlagen: ${e.message}", "Export failed: ${e.message}") }
    }

    fun deleteAll() = viewModelScope.launch {
        _message.value = try {
            graph.pomodoro.stop()
            data.deleteAll()
            graph.cleanInbox(maxAgeMs = 0)
            graph.sources.deleteAll()
            tr("Alle Dokumente, Karten, Zusammenfassungen und Fokus-Daten wurden gelöscht.", "All documents, cards, summaries and focus data have been deleted.")
        } catch (e: Exception) { tr("Löschen fehlgeschlagen: ${e.message}", "Deletion failed: ${e.message}") }
    }
}

@Composable
fun PrivacyScreen(onBack: () -> Unit, vm: PrivacyViewModel = viewModel()) {
    val message by vm.message.collectAsStateWithLifecycle()
    var confirm by remember { mutableStateOf(false) }
    val saver = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri -> uri?.let(vm::export) }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(tr("Datenschutz", "Privacy"), style = MaterialTheme.typography.headlineMedium)
        Text(tr("Alles bleibt auf deinem Gerät: Dokumente, Abschnitte, Fragen an die KI, Antworten, Karteikarten und Lernzeiten liegen nur im privaten Speicher dieser App. Die KI läuft lokal, es gibt weder Konto noch Tracking noch Werbung.", "Everything stays on your device: documents, sections, questions to the AI, answers, flashcards and study times are stored only in this app’s private storage. The AI runs locally; there is no account, no tracking and no advertising."), style = MaterialTheme.typography.bodyMedium)
        Text(tr("Die Internet-Berechtigung nutzt die App ausschließlich, um die KI-Modelle und Stimmen von GitHub (edgebird-lab/lernsystem-modelle) zu laden und nach Updates zu suchen. Dabei werden keine Daten von dir übertragen, GitHub sieht nur die übliche Verbindungsadresse.", "The app uses the internet permission solely to download the AI models and voices from GitHub (edgebird-lab/lernsystem-modelle) and to check for updates. No data of yours is transmitted; GitHub only sees the usual connection address."), style = MaterialTheme.typography.bodyMedium)
        Text(tr("Spracheingabe nutzt die Erkennung des Geräts, die Texterkennung für Fotos läuft ebenfalls auf dem Gerät. Das Vorlesen nutzt die Offline-Stimme der App (Stimmenpaket aus „KI-Modelle“); Online-Stimmen werden nicht verwendet.", "Voice input uses the device’s recognition, and text recognition for photos also runs on the device. Reading aloud uses the app’s offline voice (voice pack from “AI models”); online voices are not used."), style = MaterialTheme.typography.bodyMedium)
        Text(tr("Teilen, Drucken, Speichern und „Melden“ geben Inhalte nur weiter, wenn du es selbst auslöst: Beim Melden und bei der Rückmeldung öffnet sich ein E-Mail-Entwurf an den Anbieter, gesendet wird erst, wenn du in deinem E-Mail-Programm auf „Senden“ tippst.", "Sharing, printing, saving and “Report” pass content on only when you trigger it: for reports and feedback an email draft to the provider opens, and nothing is sent until you tap “Send” in your email app."), style = MaterialTheme.typography.bodyMedium)
        Text(tr("Die App ist von der Android-Datensicherung ausgenommen. Wer seine Daten mitnehmen will, nutzt den Export.", "The app is excluded from Android backup. If you want to take your data with you, use the export."), style = MaterialTheme.typography.bodyMedium)
        Text(tr("Anbieter und Kontakt: ${Feedback.PROVIDER}, ${Feedback.EMAIL}", "Provider and contact: ${Feedback.PROVIDER}, ${Feedback.EMAIL}"), style = MaterialTheme.typography.bodyMedium)
        Button(onClick = { saver.launch("lernsystem-export.json") }, modifier = Modifier.fillMaxWidth()) { Text(tr("Meine Daten exportieren (JSON)", "Export my data (JSON)")) }
        OutlinedButton(onClick = { confirm = true }, modifier = Modifier.fillMaxWidth()) { Text(tr("Alle meine Daten löschen", "Delete all my data")) }
        message?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
        TextButton(onClick = onBack) { Text(tr("Zurück", "Back")) }
    }
    if (confirm) AlertDialog(
        onDismissRequest = { confirm = false },
        title = { Text(tr("Alle Daten löschen?", "Delete all data?")) },
        text = { Text(tr("Dokumente, Karteikarten, Zusammenfassungen und Fokus-Statistik werden unwiderruflich gelöscht. Die KI-Modelle bleiben erhalten. Tipp: Exportiere vorher, wenn du etwas behalten willst.", "Documents, flashcards, summaries and focus statistics will be deleted irrevocably. The AI models are kept. Tip: export first if you want to keep something.")) },
        confirmButton = { TextButton(onClick = { confirm = false; vm.deleteAll() }) { Text(tr("Endgültig löschen", "Delete permanently")) } },
        dismissButton = { TextButton(onClick = { confirm = false }) { Text(tr("Abbrechen", "Cancel")) } },
    )
}

package de.edgebird.lernsystem.ui

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
            getApplication<Application>().contentResolver.openOutputStream(uri)?.use { data.export(it) } ?: error("Datei nicht beschreibbar")
            "Export gespeichert."
        } catch (e: Exception) { "Export fehlgeschlagen: ${e.message}" }
    }

    fun deleteAll() = viewModelScope.launch {
        _message.value = try {
            graph.pomodoro.stop()
            data.deleteAll()
            graph.cleanInbox(maxAgeMs = 0)
            "Alle Dokumente, Karten, Zusammenfassungen und Fokus-Daten wurden gelöscht."
        } catch (e: Exception) { "Löschen fehlgeschlagen: ${e.message}" }
    }
}

@Composable
fun PrivacyScreen(onBack: () -> Unit, vm: PrivacyViewModel = viewModel()) {
    val message by vm.message.collectAsStateWithLifecycle()
    var confirm by remember { mutableStateOf(false) }
    val saver = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri -> uri?.let(vm::export) }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Datenschutz", style = MaterialTheme.typography.headlineMedium)
        Text("Alles bleibt auf deinem Gerät: Dokumente, Abschnitte, Fragen an die KI, Antworten, Karteikarten und Lernzeiten liegen nur im privaten Speicher dieser App. Die KI läuft lokal, es gibt weder Konto noch Tracking noch Werbung.", style = MaterialTheme.typography.bodyMedium)
        Text("Die Internet-Berechtigung nutzt die App ausschließlich, um die KI-Modelle von GitHub (edgebird-lab/lernsystem-modelle) zu laden und nach Updates zu suchen. Dabei werden keine Daten von dir übertragen, GitHub sieht nur die übliche Verbindungsadresse.", style = MaterialTheme.typography.bodyMedium)
        Text("Spracheingabe nutzt die Erkennung des Geräts, die Texterkennung für Fotos läuft ebenfalls auf dem Gerät. Das Vorlesen nutzt die Offline-Stimme der App (Stimmenpaket aus „KI-Modelle“); Online-Stimmen werden nicht verwendet.", style = MaterialTheme.typography.bodyMedium)
        Text("Die App ist von der Android-Datensicherung ausgenommen. Wer seine Daten mitnehmen will, nutzt den Export.", style = MaterialTheme.typography.bodyMedium)
        Button(onClick = { saver.launch("lernsystem-export.json") }, modifier = Modifier.fillMaxWidth()) { Text("Meine Daten exportieren (JSON)") }
        OutlinedButton(onClick = { confirm = true }, modifier = Modifier.fillMaxWidth()) { Text("Alle meine Daten löschen") }
        message?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
        TextButton(onClick = onBack) { Text("Zurück") }
    }
    if (confirm) AlertDialog(
        onDismissRequest = { confirm = false },
        title = { Text("Alle Daten löschen?") },
        text = { Text("Dokumente, Karteikarten, Zusammenfassungen und Fokus-Statistik werden unwiderruflich gelöscht. Die KI-Modelle bleiben erhalten. Tipp: Exportiere vorher, wenn du etwas behalten willst.") },
        confirmButton = { TextButton(onClick = { confirm = false; vm.deleteAll() }) { Text("Endgültig löschen") } },
        dismissButton = { TextButton(onClick = { confirm = false }) { Text("Abbrechen") } },
    )
}

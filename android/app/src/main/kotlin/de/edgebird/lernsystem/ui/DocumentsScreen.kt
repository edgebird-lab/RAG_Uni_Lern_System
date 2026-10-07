package de.edgebird.lernsystem.ui

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import de.edgebird.lernsystem.data.DocumentStatus

@Composable
fun DocumentsScreen(vm: DocumentsViewModel = viewModel()) {
    val docs by vm.documents.collectAsStateWithLifecycle()
    val embed by vm.embedStatus.collectAsStateWithLifecycle()
    val message by vm.importMessage.collectAsStateWithLifecycle()
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris: List<Uri> -> vm.import(uris) }

    Column(Modifier.padding(horizontal = 16.dp, vertical = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Dokumente", style = MaterialTheme.typography.headlineMedium)
        Button(onClick = { picker.launch(arrayOf("application/pdf", "text/plain", "text/markdown", "application/octet-stream")) }) {
            Text("Dokumente hinzufügen")
        }
        val onlyCharging by vm.onlyWhenCharging.collectAsStateWithLifecycle()
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Nur am Ladegerät indexieren", Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
            androidx.compose.material3.Switch(checked = onlyCharging, onCheckedChange = vm::setOnlyWhenCharging)
        }
        embed?.takeIf { it.running }?.let { e ->
            Column {
                Text(if (e.total > 0) "Embedding: ${e.done} von ${e.total} Abschnitten" else "Embedding wird gestartet …")
                if (e.total > 0) LinearProgressIndicator(progress = { e.done.toFloat() / e.total }, modifier = Modifier.fillMaxWidth())
            }
        }
        embed?.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        message?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(docs, key = { it.document.id }) { d ->
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(d.document.title, style = MaterialTheme.typography.titleMedium)
                        val status = when (d.document.status) {
                            DocumentStatus.INDEXED -> "bereit"
                            DocumentStatus.PENDING -> "wird indexiert"
                            DocumentStatus.FAILED -> "Fehler"
                        }
                        Text("${d.chunkCount} Abschnitte · $status", style = MaterialTheme.typography.bodySmall)
                    }
                    TextButton(onClick = { vm.delete(d.document.id) }) { Text("Löschen") }
                }
            }
        }
    }
}

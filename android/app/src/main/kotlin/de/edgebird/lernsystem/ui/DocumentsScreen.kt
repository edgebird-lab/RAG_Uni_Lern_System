package de.edgebird.lernsystem.ui

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import de.edgebird.lernsystem.data.DocumentStatus
import de.edgebird.lernsystem.data.DocumentSummary

/** Bereich „Quellen“ eines Fachs: Dokumente anhaken (Auswahl für den Chat), hinzufügen, umbenennen, verschieben, löschen. */
@Composable
fun SourcesScreen(subjectId: Long, otherSubjects: List<Pair<Long, String>>, vm: DocumentsViewModel = viewModel(key = "docs$subjectId")) {
    LaunchedEffect(subjectId) { vm.bind(subjectId) }
    val docs by vm.documents.collectAsStateWithLifecycle()
    val selected by vm.selectedIds.collectAsStateWithLifecycle()
    val embed by vm.embedStatus.collectAsStateWithLifecycle()
    val message by vm.importMessage.collectAsStateWithLifecycle()
    val cardGen by vm.cardGenStatus.collectAsStateWithLifecycle()
    val onlyCharging by vm.onlyWhenCharging.collectAsStateWithLifecycle()
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris: List<Uri> -> vm.import(uris) }
    var cardDialogFor by remember { mutableStateOf<Long?>(null) }
    var renaming by remember { mutableStateOf<DocumentSummary?>(null) }
    var moving by remember { mutableStateOf<DocumentSummary?>(null) }

    Box(Modifier.fillMaxSize()) {
        LazyColumn(contentPadding = androidx.compose.foundation.layout.PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 100.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Quellen", style = MaterialTheme.typography.headlineMedium)
                    Text("Der Chat nutzt nur die angehakten Quellen.", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    embed?.takeIf { it.running }?.let { e ->
                        Text(if (e.total > 0) "Indexiere: ${e.done} von ${e.total} Abschnitten" else "Indexierung startet …", style = MaterialTheme.typography.bodySmall)
                        if (e.total > 0) LinearProgressIndicator(progress = { e.done.toFloat() / e.total }, modifier = Modifier.fillMaxWidth())
                    }
                    embed?.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                    message?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                    cardGen?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                }
            }
            if (docs.isEmpty()) item {
                Text("Noch keine Quellen. Tippe auf „Quelle hinzufügen“ und wähle PDFs oder Textdateien.", style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(vertical = 24.dp))
            }
            items(docs, key = { it.document.id }) { d ->
                SourceRow(
                    d, checked = d.document.id in selected, onToggle = { vm.toggle(d.document.id) },
                    onCards = { cardDialogFor = d.document.id }, onRename = { renaming = d }, onMove = { moving = d }, onDelete = { vm.delete(d.document.id) },
                    canMove = otherSubjects.isNotEmpty(),
                )
            }
            if (docs.isNotEmpty()) item {
                Row(Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("Nur am Ladegerät indexieren", Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                    Switch(checked = onlyCharging, onCheckedChange = vm::setOnlyWhenCharging)
                }
            }
        }
        ExtendedFloatingActionButton(
            onClick = { picker.launch(arrayOf("application/pdf", "text/plain", "text/markdown", "application/octet-stream")) },
            icon = { Icon(Icons.Default.Add, null) }, text = { Text("Quelle hinzufügen") },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp), containerColor = MaterialTheme.colorScheme.primary, contentColor = MaterialTheme.colorScheme.onPrimary,
        )
    }

    cardDialogFor?.let { id -> CardCountDialog(onPick = { vm.generateCards(id, it); cardDialogFor = null }, onDismiss = { cardDialogFor = null }) }
    renaming?.let { d ->
        var text by remember(d.document.id) { mutableStateOf(d.document.title) }
        AlertDialog(
            onDismissRequest = { renaming = null }, title = { Text("Quelle umbenennen") },
            text = { OutlinedTextField(value = text, onValueChange = { text = it.take(120) }, singleLine = true, modifier = Modifier.fillMaxWidth()) },
            confirmButton = { TextButton(onClick = { vm.rename(d.document.id, text); renaming = null }, enabled = text.isNotBlank()) { Text("Speichern") } },
            dismissButton = { TextButton(onClick = { renaming = null }) { Text("Abbrechen") } },
        )
    }
    moving?.let { d ->
        AlertDialog(
            onDismissRequest = { moving = null }, title = { Text("In welches Fach verschieben?") },
            text = { Column { otherSubjects.forEach { (id, name) -> TextButton(onClick = { vm.move(d.document.id, id); moving = null }) { Text(name) } } } },
            confirmButton = {}, dismissButton = { TextButton(onClick = { moving = null }) { Text("Abbrechen") } },
        )
    }
}

@Composable
private fun SourceRow(d: DocumentSummary, checked: Boolean, onToggle: () -> Unit, onCards: () -> Unit, onRename: () -> Unit, onMove: () -> Unit, onDelete: () -> Unit, canMove: Boolean) {
    var menu by remember { mutableStateOf(false) }
    val failed = d.document.status == DocumentStatus.FAILED
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface), modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(start = 4.dp, end = 4.dp, top = 4.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Checkbox(checked = checked, onCheckedChange = { onToggle() }, enabled = !failed)
            Column(Modifier.weight(1f)) {
                Text(d.document.title, style = MaterialTheme.typography.titleMedium)
                val status = when (d.document.status) { DocumentStatus.INDEXED -> "bereit"; DocumentStatus.PENDING -> "wird indexiert"; DocumentStatus.FAILED -> "Fehler" }
                Text("${d.chunkCount} Abschnitte · $status", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Box {
                IconButton(onClick = { menu = true }) { Icon(Icons.Default.MoreVert, contentDescription = "Aktionen für ${d.document.title}") }
                DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                    DropdownMenuItem(text = { Text("Karten erzeugen …") }, enabled = d.document.status == DocumentStatus.INDEXED, onClick = { menu = false; onCards() })
                    DropdownMenuItem(text = { Text("Umbenennen …") }, onClick = { menu = false; onRename() })
                    if (canMove) DropdownMenuItem(text = { Text("In anderes Fach verschieben …") }, onClick = { menu = false; onMove() })
                    DropdownMenuItem(text = { Text("Löschen", color = MaterialTheme.colorScheme.error) }, onClick = { menu = false; onDelete() })
                }
            }
        }
    }
}

@Composable
private fun CardCountDialog(onPick: (Int) -> Unit, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Wie viele Karten?") },
        text = { Text("Die App erstellt die Karten im Hintergrund aus gleichmäßig verteilten Abschnitten (ca. 10 Sekunden pro Karte). Das Display sollte dabei an bleiben.") },
        confirmButton = { Row { listOf(10, 20, 40).forEach { n -> TextButton(onClick = { onPick(n) }) { Text("$n") } } } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Abbrechen") } },
    )
}

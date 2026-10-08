package de.edgebird.lernsystem.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.activity.compose.BackHandler
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import de.edgebird.lernsystem.data.DocumentStatus

/** Bereich „Studio“: Zusammenfassungen der Quellen des Fachs. */
@Composable
fun StudioScreen(subjectId: Long, vm: DocumentsViewModel = viewModel(key = "docs$subjectId")) {
    LaunchedEffect(subjectId) { vm.bind(subjectId) }
    val docs by vm.documents.collectAsStateWithLifecycle()
    var open by rememberSaveable { mutableStateOf<Long?>(null) }
    open?.let { id ->
        BackHandler { open = null }
        SummaryScreen(id, onBack = { open = null })
        return
    }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Studio", style = MaterialTheme.typography.headlineMedium)
                Text("Zusammenfassungen deiner Quellen: kurz, ausführlich oder als Stichpunkte.", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        if (docs.isEmpty()) item { Text("Füge zuerst Quellen hinzu.", style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(vertical = 24.dp)) }
        items(docs, key = { it.document.id }) { d ->
            val ready = d.document.status == DocumentStatus.INDEXED
            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                modifier = Modifier.fillMaxWidth().then(if (ready) Modifier.clickable { open = d.document.id } else Modifier),
            ) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(d.document.title, style = MaterialTheme.typography.titleMedium)
                        Text(if (ready) "${d.chunkCount} Abschnitte · Zusammenfassung öffnen" else "wird noch indexiert", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

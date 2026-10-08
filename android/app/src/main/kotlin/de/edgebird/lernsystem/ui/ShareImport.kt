package de.edgebird.lernsystem.ui

import android.app.Application
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.data.SubjectSummary
import de.edgebird.lernsystem.work.ImportItem
import de.edgebird.lernsystem.work.ImportWork
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.util.UUID

/** Inhalt, der aus einer anderen App geteilt wurde: Dateien (PDF, Bilder, Text) oder reiner Text. */
data class SharedContent(val uris: List<Uri>, val text: String?, val title: String?) {
    val isEmpty get() = uris.isEmpty() && text.isNullOrBlank()
    val count get() = uris.size + if (text.isNullOrBlank()) 0 else 1

    companion object {
        /** Liest ein `ACTION_SEND`/`ACTION_SEND_MULTIPLE`-Intent; `null`, wenn es etwas anderes ist. */
        @Suppress("DEPRECATION")
        fun from(intent: Intent?): SharedContent? {
            if (intent == null) return null
            val uris: List<Uri> = when (intent.action) {
                Intent.ACTION_SEND -> listOfNotNull(intent.getParcelableExtra(Intent.EXTRA_STREAM) as? Uri)
                Intent.ACTION_SEND_MULTIPLE -> intent.getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM).orEmpty()
                else -> return null
            }
            val text = if (uris.isEmpty()) intent.getStringExtra(Intent.EXTRA_TEXT) else null
            return SharedContent(uris, text, intent.getStringExtra(Intent.EXTRA_SUBJECT)).takeIf { !it.isEmpty }
        }
    }
}

/** Kopiert Dateien aus Content-URIs in den App-Speicher und reiht den Import ein. */
internal object ImportHelper {
    fun items(app: Application, graph: de.edgebird.lernsystem.AppGraph, uris: List<Uri>): List<ImportItem> {
        val resolver = app.contentResolver
        return uris.mapNotNull { uri ->
            runCatching {
                val name = resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c -> if (c.moveToFirst()) c.getString(0) else null }
                    ?: uri.lastPathSegment ?: "datei"
                val named = if ('.' in name) name else name + when (resolver.getType(uri)) { "application/pdf" -> ".pdf"; "image/png" -> ".png"; "image/webp" -> ".webp"; "image/jpeg" -> ".jpg"; "text/markdown" -> ".md"; else -> ".txt" }
                val copy = File(graph.inboxDir, UUID.randomUUID().toString())
                resolver.openInputStream(uri)!!.use { input -> copy.outputStream().use { input.copyTo(it) } }
                ImportItem(uri.toString(), named, copy)
            }.getOrNull()
        }
    }
}

class ShareViewModel(app: Application) : AndroidViewModel(app) {
    private val graph = (app as LernsystemApp).graph
    val subjects: Flow<List<SubjectSummary>> = graph.subjects.observeSummaries()

    /** Importiert den geteilten Inhalt in das gewählte Fach; ruft [done] mit der Zahl der angenommenen Quellen auf. */
    fun import(content: SharedContent, subjectId: Long, done: (Int) -> Unit) {
        viewModelScope.launch {
            val items = withContext(Dispatchers.IO) {
                val files = ImportHelper.items(getApplication(), graph, content.uris).toMutableList()
                content.text?.takeIf { it.isNotBlank() }?.let { t ->
                    val f = File(graph.inboxDir, UUID.randomUUID().toString()).also { it.writeText(t, Charsets.UTF_8) }
                    val name = (content.title?.takeIf { it.isNotBlank() }?.take(60) ?: "Geteilter Text").let { if (it.endsWith(".txt")) it else "$it.txt" }
                    files += ImportItem("share:${UUID.randomUUID()}", name, f)
                }
                files
            }
            if (items.isNotEmpty()) ImportWork.enqueue(getApplication(), items, graph.prefs.getBoolean("embed_only_when_charging", false), subjectId)
            done(items.size)
        }
    }
}

/** „In welches Fach?“ für geteilte Inhalte. */
@Composable
fun ShareTargetDialog(content: SharedContent, onDone: (String) -> Unit, onDismiss: () -> Unit, vm: ShareViewModel = viewModel()) {
    val subjects by vm.subjects.collectAsStateWithLifecycle(emptyList())
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (content.count == 1) "In welches Fach importieren?" else "${content.count} Quellen: in welches Fach?") },
        text = {
            Column(Modifier.fillMaxWidth()) {
                if (subjects.isEmpty()) Text("Lege zuerst ein Fach an.", style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(vertical = 8.dp))
                subjects.forEach { s ->
                    TextButton(onClick = { vm.import(content, s.subject.id) { n -> onDone(if (n == 0) "Nichts importiert" else "$n ${if (n == 1) "Quelle wird" else "Quellen werden"} in „${s.subject.name}“ importiert") } }) { Text(s.subject.name) }
                }
            }
        },
        confirmButton = {}, dismissButton = { TextButton(onClick = onDismiss) { Text("Abbrechen") } },
    )
}

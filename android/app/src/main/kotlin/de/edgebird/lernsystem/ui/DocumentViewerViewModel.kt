// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.data.ChunkEntity
import de.edgebird.lernsystem.data.DocumentEntity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/** Geladene Quelle für die Ansicht. [markdown]: formatierter Text bei Zusammenfassungen, Notizen und Markdown-Dateien. [fullText]: der gesamte Text für Teilen/Speichern. */
data class ViewerData(val doc: DocumentEntity, val chunks: List<ChunkEntity>, val original: File?, val markdown: String?, val fullText: String, val folderName: String?)

class DocumentViewerViewModel(app: Application) : AndroidViewModel(app) {
    private val graph = (app as LernsystemApp).graph
    private val _data = MutableStateFlow<ViewerData?>(null)
    val data: StateFlow<ViewerData?> = _data

    fun load(id: Long) {
        viewModelScope.launch {
            _data.value = withContext(Dispatchers.IO) {
                val doc = graph.db.documents().byId(id) ?: return@withContext null
                val chunks = graph.db.chunks().byDocument(id)
                val orig = graph.sources.original(doc)
                val ext = (orig?.extension ?: doc.filetype).lowercase()
                // Zusammenfassungen, Notizen und Markdown-Dateien: die Originaldatei ist selbst der lesbare Text
                val md = if (orig != null && (doc.kind == "SUMMARY" || doc.kind == "NOTE" || ext == "md" || ext == "markdown")) runCatching { orig.readText() }.getOrNull() else null
                val text = md ?: (orig?.takeIf { ext == "txt" }?.let { runCatching { it.readText() }.getOrNull() }
                    ?: chunks.joinToString("\n\n") { c -> c.location + "\n" + c.text.replace(Regex("^\\[[^\\]]{0,160}]\\n"), "") })
                ViewerData(doc, chunks, orig, md, text, doc.folderId?.let { graph.db.folders().byId(it)?.name })
            }
        }
    }
}

// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.spike

import android.app.Activity
import android.graphics.Paint
import android.graphics.pdf.PdfDocument
import android.os.Bundle
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.ingest.DocumentSource
import de.edgebird.lernsystem.ingest.ImportResult
import kotlinx.coroutines.runBlocking
import java.io.File

/**
 * Nur Debug: legt ein Test-Fach „ZZ-Test“ mit Kapitel, Quellen, Zusammenfassung und PDF-Original an (zum Ausprobieren der Quellenverwaltung per Hand);
 * `--es clean 1` löscht das Fach samt Originalen wieder.
 */
class DebugSourcesActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState != null) return
        val graph = (application as LernsystemApp).graph
        Thread {
            runBlocking {
                graph.db.subjects().getAll().filter { it.name == "ZZ-Test" }.forEach { graph.subjects.deleteWithContent(it.id) }
                if (intent.getStringExtra("clean") == null) {
                    val sid = graph.subjects.create("ZZ-Test")
                    val chapter = graph.sourceRepo.createFolder(sid, "Sortieren")
                    suspend fun add(name: String, text: String, key: String, folder: Long? = null, original: File? = null) {
                        val f = File(graph.inboxDir, name).also { it.writeText(text) }
                        val r = graph.pipeline.import(DocumentSource(key, name) { f.inputStream() }, subjectId = sid, kind = when { key.startsWith("summary:") -> "SUMMARY"; key.startsWith("note:") -> "NOTE"; else -> "FILE" }, folderId = folder)
                        if (r is ImportResult.Imported) {
                            val src = original ?: f
                            graph.sources.save(r.documentId, src, if (original != null) original.extension else name.substringAfterLast('.'))
                            graph.db.documents().setHasOriginal(r.documentId, true)
                        }
                    }
                    val body = "Ein Heap ist ein vollständiger Binärbaum. Quicksort teilt das Feld um ein Pivotelement. Mergesort halbiert das Feld und mischt die sortierten Hälften. ".repeat(8)
                    // PDF mit zwei Seiten als Original
                    val pdfFile = File(graph.inboxDir, "skript.pdf")
                    PdfDocument().also { d ->
                        for (p in 1..2) {
                            val page = d.startPage(PdfDocument.PageInfo.Builder(595, 842, p).create())
                            page.canvas.drawText("Skript Seite $p: Sortierverfahren und Heaps", 50f, 80f, Paint().apply { textSize = 18f })
                            d.finishPage(page)
                        }
                        pdfFile.outputStream().use { d.writeTo(it) }; d.close()
                    }
                    add("skript.txt", "Seite 1\n$body\n\nSeite 2\n$body", "debug:skript", chapter, original = pdfFile)
                    add("Quicksort.md", "# Quicksort\n\n$body", "debug:quicksort", chapter)
                    add("Heaps.md", "# Heaps\n\n$body", "debug:heaps")
                    add("Zusammenfassung Sortieren.md", "# Zusammenfassung: Sortieren\n\n- **Quicksort** teilt um ein Pivotelement.\n- **Mergesort** halbiert und mischt.\n\n$body", "summary:1:1", chapter)
                    graph.db.generatedSummaries().insert(
                        de.edgebird.lernsystem.data.GeneratedSummaryEntity(
                            subjectId = sid, scope = "SUBJECT", documentIds = graph.db.documents().idsForSubject(sid).joinToString(","), title = "Fach: ZZ-Test – Stichpunkte",
                            specJson = de.edgebird.lernsystem.core.summary.SummarySpec().toJson(), text = "# Fach: ZZ-Test\n\n- **Quicksort** teilt um ein Pivotelement.\n- **Mergesort** halbiert und mischt.\n", model = "Test", createdAt = System.currentTimeMillis(),
                        ),
                    )
                    add("Notiz.md", "# Notiz\n\nLaufzeit von Quicksort im Mittel O(n log n). $body", "note:1")
                }
            }
            runOnUiThread { finish() }
        }.start()
    }
}

package de.edgebird.lernsystem.spike

import android.app.Activity
import android.os.Bundle
import android.view.WindowManager
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.summary.SummaryFormat
import de.edgebird.lernsystem.core.summary.SummaryRole
import de.edgebird.lernsystem.core.summary.SummarySpec
import de.edgebird.lernsystem.data.SummaryScope
import de.edgebird.lernsystem.data.summary.SummaryRequest
import de.edgebird.lernsystem.data.summary.SummaryRunner
import de.edgebird.lernsystem.ingest.DocumentSource
import de.edgebird.lernsystem.ingest.EmbeddingIndexer
import kotlinx.coroutines.runBlocking
import java.io.File

/**
 * Nur Debug: erstellt Zusammenfassungen (Dokument, Fach, Thema; mehrere Einstellungen) mit dem echten Modell auf öffentlichen Testtexten
 * aus `files/debug-in/`, schreibt Protokoll nach `files/debug-out/summary.txt` und räumt das Test-Fach danach weg.
 *   adb shell am start -W -n de.edgebird.lernsystem/.spike.DebugSummaryActivity
 */
class DebugSummaryActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContentView(android.widget.TextView(this).apply { text = "Zusammenfassungs-Test läuft …"; textSize = 24f; setPadding(48, 200, 48, 48) })
        if (savedInstanceState != null) return
        val out = File(filesDir, "debug-out").apply { mkdirs() }.resolve("summary.txt").also { it.writeText("") }
        Thread {
            val graph = (application as LernsystemApp).graph
            runBlocking {
                graph.db.subjects().getAll().filter { it.name == "ZZ-Test" }.forEach { graph.subjects.deleteWithContent(it.id) }
                val subject = graph.subjects.create("ZZ-Test")
                try {
                    for (f in File(filesDir, "debug-in").listFiles().orEmpty().filter { it.isFile }) graph.pipeline.import(DocumentSource("debug:${f.name}", f.name) { f.inputStream() }, subjectId = subject)
                    EmbeddingIndexer(graph.db, graph.sharedEmbedder, graph.embeddingModelId).run()
                    graph.llm.load()
                    val docs = graph.db.documents().idsForSubject(subject)
                    out.appendText("Quellen: ${docs.size}\n\n")
                    val runner = SummaryRunner(graph.db, graph.llm, graph.retriever)
                    suspend fun case(name: String, req: SummaryRequest) {
                        val t0 = System.currentTimeMillis()
                        try {
                            val steps = runner.estimateSteps(req)
                            val r = runner.run(req)
                            val text = graph.db.generatedSummaries().byId(r.id)!!.text
                            out.appendText("=== $name (${(System.currentTimeMillis() - t0) / 1000} s, geschätzte Schritte $steps, ${text.split(Regex("\\s+")).size} Wörter, genutzt ${r.used}, übersprungen ${r.skipped}, Warnungen ${r.warnings}) ===\n$text\n\n")
                        } catch (e: Throwable) { out.appendText("=== $name: FEHLER $e\n\n") }
                    }
                    val first = docs.first()
                    case("1 Dokument, Fließtext 120 Wörter, Lektor", SummaryRequest(subject, SummaryScope.DOC, listOf(first), SummarySpec(format = SummaryFormat.PROSE, targetWords = 120, role = SummaryRole.EDITOR)))
                    case("2 Dokument, Stichpunkte, 'nur Wesentliches', 150 Wörter", SummaryRequest(subject, SummaryScope.DOC, listOf(first), SummarySpec(targetWords = 150, extra = "Fasse nur das Wesentliche zusammen.")))
                    case("3 Fach, Stichpunkte, 400 Wörter", SummaryRequest(subject, SummaryScope.SUBJECT, docs, SummarySpec(targetWords = 400)))
                    case("4 Thema 'Zelle', Fließtext 100 Wörter", SummaryRequest(subject, SummaryScope.TOPIC, docs, SummarySpec(format = SummaryFormat.PROSE, targetWords = 100), topic = intent.getStringExtra("topic") ?: "Zelle"))
                    case("5 Dokument, Glossar", SummaryRequest(subject, SummaryScope.DOC, listOf(first), SummarySpec(format = SummaryFormat.GLOSSARY)))
                    out.appendText("FERTIG\n")
                } catch (e: Throwable) {
                    out.appendText("FEHLER: $e\n")
                } finally {
                    graph.subjects.deleteWithContent(subject)
                    runOnUiThread { finish() }
                }
            }
        }.start()
    }
}

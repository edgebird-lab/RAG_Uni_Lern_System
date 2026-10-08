package de.edgebird.lernsystem.spike

import android.app.Activity
import android.os.Bundle
import android.view.WindowManager
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.data.socratic.Action
import de.edgebird.lernsystem.data.socratic.SocraticSession
import de.edgebird.lernsystem.ingest.DocumentSource
import de.edgebird.lernsystem.ingest.EmbeddingIndexer
import kotlinx.coroutines.runBlocking
import java.io.File

/**
 * Nur Debug: spielt einen sokratischen Dialog mit dem echten Modell auf einem öffentlichen Testtext durch (Dateien aus `files/debug-in/`),
 * schreibt das Protokoll nach `files/debug-out/socratic.txt` und entfernt das Test-Fach danach wieder.
 *   adb shell am start -W -n de.edgebird.lernsystem/.spike.DebugSocraticActivity --es topic Photosynthese
 */
class DebugSocraticActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        // Die Aktivität bleibt offen: Im Hintergrund hängt der GPU-Zugriff des Modells
        setContentView(android.widget.TextView(this).apply { text = "Sokratischer Test läuft …"; textSize = 24f; setPadding(48, 200, 48, 48) })
        if (savedInstanceState != null) return
        de.edgebird.lernsystem.core.i18n.Lang.fromTag(intent.getStringExtra("lang"))?.let { de.edgebird.lernsystem.core.i18n.Lang.current = it }
        val topic = intent.getStringExtra("topic") ?: "Photosynthese"
        val out = File(filesDir, "debug-out").apply { mkdirs() }.resolve("socratic.txt").also { it.writeText("") }
        Thread {
            val graph = (application as LernsystemApp).graph
            runBlocking {
                // Reste abgebrochener Läufe wegräumen (nur Fächer mit genau diesem Testnamen)
                graph.db.subjects().getAll().filter { it.name == "ZZ-Test" }.forEach { graph.subjects.deleteWithContent(it.id) }
                val subject = graph.subjects.create("ZZ-Test")
                try {
                    for (f in File(filesDir, "debug-in").listFiles().orEmpty().filter { it.isFile }) {
                        graph.pipeline.import(DocumentSource("debug:${f.name}", f.name) { f.inputStream() }, subjectId = subject)
                    }
                    EmbeddingIndexer(graph.db, graph.sharedEmbedder, graph.embeddingModelId).run()
                    graph.llm.load()
                    val ids = graph.db.documents().idsForSubject(subject).toSet()
                    val s = SocraticSession(graph.retriever, graph.llm, ids, topic, randomChunks = { d, n -> graph.db.chunks().byDocument(d.first()).shuffled().take(n) })
                    var step = 0
                    suspend fun go(label: String, f: suspend () -> de.edgebird.lernsystem.data.socratic.TurnOutput) {
                        val t0 = System.currentTimeMillis()
                        val r = f()
                        out.appendText("#${++step} [$label] (ctx=${s.contextSize}, ${(System.currentTimeMillis() - t0) / 1000.0}s, phase=${r.phase}${if (r.fallback) ", FALLBACK" else ""}${r.verdict?.let { ", BEWERTUNG=${it.label}" } ?: ""})\n${r.text}\n" + (if (r.fallback || r.trace.size > 1) r.trace.mapIndexed { i, (t, p) -> "   Versuch ${i + 1} $p: ${t.replace("\n", " ").take(260)}\n" }.joinToString("") else "") + "\n")
                    }
                    go("Start") { s.start() }
                    go("Antwort: richtig (Inhalt aus Text)") { s.act(Action.Answer(intent.getStringExtra("good") ?: "Pflanzen wandeln Lichtenergie in chemische Energie um und bilden dabei Glucose und Sauerstoff.")) }
                    go("Antwort: falsch") { s.act(Action.Answer("Die Photosynthese findet nachts in den Mitochondrien statt und verbraucht Sauerstoff.")) }
                    go("Hinweis") { s.act(Action.Hint) }
                    go("Teil") { s.act(Action.Partial) }
                    go("Auflösen") { s.act(Action.Resolve) }
                    go("Nächster Aspekt") { s.act(Action.Next) }
                    go("Antwort: keine Ahnung") { s.act(Action.Answer("Keine Ahnung.")) }
                    go("Hinweis 1") { s.act(Action.Hint) }
                    go("Hinweis 2") { s.act(Action.Hint) }
                    go("Hinweis 3 (-> Auflösung)") { s.act(Action.Hint) }
                    go("Nächster Aspekt") { s.act(Action.Next) }
                    out.appendText("FERTIG\n")
                    runOnUiThread { finish() }
                } catch (e: Throwable) {
                    out.appendText("FEHLER: $e\n")
                } finally {
                    graph.subjects.deleteWithContent(subject)
                }
            }
        }.start()
    }
}

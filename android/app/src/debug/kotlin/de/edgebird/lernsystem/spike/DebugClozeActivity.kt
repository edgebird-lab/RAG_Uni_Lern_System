package de.edgebird.lernsystem.spike

import android.app.Activity
import android.os.Bundle
import android.view.WindowManager
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.cards.CardChunkFilter
import de.edgebird.lernsystem.core.cards.CardGenerator
import de.edgebird.lernsystem.core.cards.ContentKind
import de.edgebird.lernsystem.core.cards.GenerationStats
import de.edgebird.lernsystem.ingest.DocumentSource
import kotlinx.coroutines.runBlocking
import java.io.File

/** Nur Debug: erzeugt Lückentext- und Code-Karten mit dem echten Modell aus den Testtexten in `files/debug-in/` (Protokoll: `files/debug-out/cloze.txt`). */
class DebugClozeActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContentView(android.widget.TextView(this).apply { text = "Karten-Test läuft …"; textSize = 24f; setPadding(48, 200, 48, 48) })
        if (savedInstanceState != null) return
        val out = File(filesDir, "debug-out").apply { mkdirs() }.resolve("cloze.txt").also { it.writeText("") }
        Thread {
            val graph = (application as LernsystemApp).graph
            runBlocking {
                graph.db.subjects().getAll().filter { it.name == "ZZ-Test" }.forEach { graph.subjects.deleteWithContent(it.id) }
                val subject = graph.subjects.create("ZZ-Test")
                try {
                    for (f in File(filesDir, "debug-in").listFiles().orEmpty().filter { it.isFile }) graph.pipeline.import(DocumentSource("debug:${f.name}", f.name) { f.inputStream() }, subjectId = subject)
                    graph.llm.load()
                    val gen = CardGenerator(graph.llm, graph.sharedEmbedder)
                    val chunks = graph.db.documents().idsForSubject(subject).flatMap { graph.db.chunks().byDocument(it) }
                    val text = chunks.filter { it.text.length > 400 && CardChunkFilter.isStudyWorthy(it.text) && !ContentKind.isCode(it.text) }.let { l -> (0 until 4).map { l[it * l.size / 4] } }
                    val code = chunks.filter { ContentKind.isCode(it.text) && it.text.length > 200 }.take(2)
                    out.appendText("Textabschnitte ${text.size}, Code-Abschnitte ${code.size} (von ${chunks.size})\n\n")
                    for (c in text) {
                        val st = GenerationStats()
                        val t0 = System.currentTimeMillis()
                        val cards = gen.generateCloze(c.text, n = 2, stats = st)
                        out.appendText("--- LÜCKENTEXT aus „${c.location}“ (${(System.currentTimeMillis() - t0) / 1000.0} s, verworfen ${st.rejectedQuestions}, Dubletten ${st.duplicates}) ---\n")
                        cards.forEach { out.appendText("VORNE: ${it.question}\nHINTEN: ${it.answer}\n\n") }
                    }
                    for (c in code) {
                        val st = GenerationStats()
                        val t0 = System.currentTimeMillis()
                        val cards = gen.generate(c.text, n = 2, stats = st)
                        out.appendText("--- CODE-FRAGEN aus „${c.location}“ (${(System.currentTimeMillis() - t0) / 1000.0} s, verworfen ${st.rejectedQuestions}/${st.rejectedAnswers}) ---\nQUELLE: ${c.text.take(260).replace("\n", " ⏎ ")}\n")
                        cards.forEach { out.appendText("F: ${it.question}\nA: ${it.answer}\n\n") }
                    }
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

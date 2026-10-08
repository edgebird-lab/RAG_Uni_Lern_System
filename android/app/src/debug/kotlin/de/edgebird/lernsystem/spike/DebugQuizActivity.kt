package de.edgebird.lernsystem.spike

import android.app.Activity
import android.os.Bundle
import android.view.WindowManager
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.ingest.DocumentSource
import kotlinx.coroutines.runBlocking
import java.io.File

/** Nur Debug: erzeugt Lückentext- und Code-Karten mit dem echten Modell aus den Testtexten in `files/debug-in/` (Protokoll: `files/debug-out/quiz.txt`). */
class DebugQuizActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContentView(android.widget.TextView(this).apply { text = "Quiz-Test läuft …"; textSize = 24f; setPadding(48, 200, 48, 48) })
        if (savedInstanceState != null) return
        val out = File(filesDir, "debug-out").apply { mkdirs() }.resolve("quiz.txt").also { it.writeText("") }
        Thread {
            val graph = (application as LernsystemApp).graph
            runBlocking {
                graph.db.subjects().getAll().filter { it.name == "ZZ-Test" }.forEach { graph.subjects.deleteWithContent(it.id) }
                val subject = graph.subjects.create("ZZ-Test")
                try {
                    for (f in File(filesDir, "debug-in").listFiles().orEmpty().filter { it.isFile }) graph.pipeline.import(DocumentSource("debug:${f.name}", f.name) { f.inputStream() }, subjectId = subject)
                    graph.llm.load()
                    val docs = graph.db.documents().idsForSubject(subject).toSet()
                    val t0 = System.currentTimeMillis()
                    val items = de.edgebird.lernsystem.data.quiz.McQuizRunner(graph.db, graph.llm).prepare(subject, docs, 5, true, onProgress = { d, t -> out.appendText("Fortschritt $d/$t\n") })
                    out.appendText("${items.size} Fragen in ${(System.currentTimeMillis() - t0) / 1000.0} s\n\n")
                    items.forEach { i ->
                        val q = i.question
                        out.appendText("[${i.topic}] ${q.question}\n")
                        q.options.forEachIndexed { k, o -> out.appendText("  ${'A' + k}${if (k == q.correctIndex) "*" else " "} $o\n") }
                        out.appendText("  Erklaerung: ${q.explanation}\n\n")
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

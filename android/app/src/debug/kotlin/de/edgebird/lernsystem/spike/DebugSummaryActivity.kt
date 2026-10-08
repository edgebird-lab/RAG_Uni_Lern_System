package de.edgebird.lernsystem.spike

import android.app.Activity
import android.os.Bundle
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.summary.SummaryStyle
import de.edgebird.lernsystem.work.SummaryWork
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Nur Debug. Zusammenfassungen per adb anstoßen und auslesen:
 *   --es action gen --es doc <Titel> --es style OUTLINE|BULLETS|SHORT [--ez restart true]

 *   --es action deldoc --es doc <Titel>   löscht das Dokument (samt Zusammenfassungen)
 *   --es action dump          schreibt alle Zusammenfassungen nach files/spike/summaries.json
 */
class DebugSummaryActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val graph = (application as LernsystemApp).graph
        if (savedInstanceState == null) when (intent.getStringExtra("action")) {
            "gen" -> runBlocking(Dispatchers.IO) {
                val doc = graph.db.documents().getAll().firstOrNull { it.title == intent.getStringExtra("doc") }
                val style = SummaryStyle.valueOf(intent.getStringExtra("style") ?: "BULLETS")
                if (doc != null) SummaryWork.enqueue(this@DebugSummaryActivity, doc.id, style, intent.getBooleanExtra("restart", false))
            }
            "deldoc" -> runBlocking(Dispatchers.IO) {
                graph.db.documents().getAll().filter { it.title == intent.getStringExtra("doc") }.forEach { graph.db.documents().delete(it.id) }
            }
            "dump" -> runBlocking(Dispatchers.IO) {
                val arr = JSONArray()
                for (d in graph.db.documents().getAll()) for (st in SummaryStyle.entries) {
                    graph.db.summaries().get(d.id, st.name)?.let {
                        arr.put(JSONObject().put("doc", d.title).put("style", it.style).put("text", it.text).put("warnings", it.warnings).put("used", it.sectionsUsed).put("skipped", it.sectionsSkipped))
                    }
                }
                File(filesDir, "spike").apply { mkdirs() }.let { File(it, "summaries.json").writeText(arr.toString(1)) }
            }
        }
        finish()
    }
}

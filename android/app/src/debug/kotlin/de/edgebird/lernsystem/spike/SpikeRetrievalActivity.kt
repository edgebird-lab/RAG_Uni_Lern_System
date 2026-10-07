package de.edgebird.lernsystem.spike

import android.app.Activity
import android.os.Bundle
import android.os.SystemClock
import android.util.Log
import android.view.WindowManager
import android.widget.ScrollView
import android.widget.TextView
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.search.SearchTokenizer
import de.edgebird.lernsystem.data.AppDatabase
import de.edgebird.lernsystem.data.search.HybridRetriever
import de.edgebird.lernsystem.data.search.KeywordSearch
import de.edgebird.lernsystem.data.search.SearchMode
import de.edgebird.lernsystem.data.search.VectorIndex
import de.edgebird.lernsystem.ingest.DocumentSource
import de.edgebird.lernsystem.ingest.EmbeddingIndexer
import de.edgebird.lernsystem.ingest.ImportPipeline
import de.edgebird.lernsystem.ingest.Loaders
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Retrieval-Auswertung auf dem Geraet (Phase 4.7): importiert das Korpus aus `files/eval-corpus/` in eine eigene
 * Datenbank, berechnet Embeddings und misst je Frage, wo die Beleg-Abschnitte im Ergebnis landen (Stichwort, Vektor, hybrid).
 *   adb shell am start -n de.edgebird.lernsystem/.spike.SpikeRetrievalActivity --es tag retr-1
 */
class SpikeRetrievalActivity : Activity() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private lateinit var view: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        view = TextView(this).apply { textSize = 12f; setPadding(24, 48, 24, 24) }
        setContentView(ScrollView(this).apply { addView(view) })
        val tag = intent.getStringExtra("tag") ?: "retr"
        scope.launch { run(tag) }
    }

    private fun log(msg: String) {
        Log.i("SPIKE", msg)
        runOnUiThread { view.append(msg + "\n") }
    }

    private suspend fun run(tag: String) {
        val out = JSONObject().put("tag", tag)
        try {
            val graph = (application as LernsystemApp).graph
            deleteDatabase("eval.db")
            val db = AppDatabase.build(this, "eval.db")
            val pipeline = ImportPipeline(db, Loaders.default(this))
            val files = File(filesDir, "eval-corpus").listFiles().orEmpty().filter { it.isFile }.sortedBy { it.name }
            val t0 = SystemClock.elapsedRealtime()
            for (f in files) pipeline.import(DocumentSource("eval:${f.name}", f.name) { f.inputStream() })
            out.put("import_ms", SystemClock.elapsedRealtime() - t0).put("chunks", db.chunks().count())
            log("importiert: ${db.chunks().count()} Chunks aus ${files.size} Dateien in ${(SystemClock.elapsedRealtime() - t0) / 1000}s")

            val embedder = graph.newEmbedder()
            embedder.load()
            val t1 = SystemClock.elapsedRealtime()
            EmbeddingIndexer(db, embedder, graph.embeddingModelId).run(onProgress = { d, t -> if (d % 320 == 0) log("embedded $d/$t") })
            out.put("embed_ms", SystemClock.elapsedRealtime() - t1)
            log("Embeddings fertig in ${(SystemClock.elapsedRealtime() - t1) / 1000}s")

            val retriever = HybridRetriever(db, KeywordSearch(db), VectorIndex(db, graph.embeddingModelId), embedder)
            val gold = JSONArray(assets.open("spike/gold_quotes.json").bufferedReader().readText())
            val perQ = JSONArray()
            val times = mutableMapOf<String, Long>()
            for (g in 0 until gold.length()) {
                val q = gold.getJSONObject(g)
                if (q.getString("typ") == "unbeantwortbar") continue
                val belege = q.getJSONArray("belege")
                val res = JSONObject().put("id", q.getString("id")).put("typ", q.getString("typ"))
                for (mode in SearchMode.values()) {
                    val ts = SystemClock.elapsedRealtime()
                    val hits = retriever.retrieve(q.getString("frage"), topK = 10, candidates = 50, mode = mode)
                    times[mode.name] = (times[mode.name] ?: 0) + SystemClock.elapsedRealtime() - ts
                    val ranks = JSONArray()
                    for (b in 0 until belege.length()) {
                        val beleg = belege.getJSONObject(b)
                        val quoteTokens = SearchTokenizer.tokenize(beleg.getString("zitat")).toSet()
                        val pos = hits.indexOfFirst { h ->
                            h.documentTitle == beleg.getString("dokument") && quoteTokens.isNotEmpty() &&
                                SearchTokenizer.tokenize(h.chunk.text).toSet().let { c -> quoteTokens.count { it in c }.toDouble() / quoteTokens.size >= 0.8 }
                        }
                        ranks.put(if (pos >= 0) pos + 1 else JSONObject.NULL)
                    }
                    res.put(mode.name.lowercase(), ranks)
                }
                perQ.put(res)
            }
            out.put("per_question", perQ).put("ms_per_mode_total", JSONObject(times as Map<*, *>)).put("n", perQ.length())
            embedder.close()
            db.close()
            out.put("status", "ok")
        } catch (t: Throwable) {
            Log.e("SPIKE", "Fehler", t)
            out.put("status", "fehler").put("fehler", t.toString())
            log("FEHLER: $t")
        }
        File(filesDir, "spike").apply { mkdirs() }.let { File(it, "$tag.json").writeText(out.toString(1)) }
        log("FERTIG $tag status=${out.optString("status")}")
    }

    override fun onDestroy() {
        super.onDestroy()
        scope.coroutineContext[kotlinx.coroutines.Job]?.cancel()
    }
}

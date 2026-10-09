// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

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
import de.edgebird.lernsystem.data.chat.ChatEvent
import de.edgebird.lernsystem.data.chat.RagChat
import de.edgebird.lernsystem.data.search.HybridRetriever
import de.edgebird.lernsystem.data.search.KeywordSearch
import de.edgebird.lernsystem.data.search.VectorIndex
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Gesamtauswertung RAG auf dem Geraet (Phase 4.7): echte Pipeline (Suche + Sprachmodell) ueber das Goldset.
 * Setzt die Datenbank `eval.db` voraus (vorher `SpikeRetrievalActivity` laufen lassen).
 *   adb shell am start -n de.edgebird.lernsystem/.spike.SpikeRagEvalActivity --es tag rag-1 --ei n 102
 */
class SpikeRagEvalActivity : Activity() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private lateinit var view: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        view = TextView(this).apply { textSize = 12f; setPadding(24, 48, 24, 24) }
        setContentView(ScrollView(this).apply { addView(view) })
        if (savedInstanceState == null) scope.launch { run(intent.getStringExtra("tag") ?: "rag", intent.getIntExtra("n", 1000), intent.getIntExtra("skip", 0), intent.getIntExtra("topk", 4), intent.getStringExtra("style") == "lenient") }
    }

    private fun log(msg: String) {
        Log.i("SPIKE", msg)
        runOnUiThread { view.append(msg + "\n") }
    }

    private suspend fun run(tag: String, n: Int, skip: Int, topK: Int, lenient: Boolean) {
        val out = JSONObject().put("tag", tag).put("topk", topK).put("lenient", lenient)
        try {
            val graph = (application as LernsystemApp).graph
            val db = AppDatabase.build(this, "eval.db")
            val embedder = graph.newEmbedder()
            val retriever = HybridRetriever(db, KeywordSearch(db), VectorIndex(db, graph.embeddingModelId), embedder)
            val chat = RagChat(retriever, graph.llm, topK = topK, style = if (lenient) de.edgebird.lernsystem.core.rag.PromptStyle.LENIENT else de.edgebird.lernsystem.core.rag.PromptStyle.STRICT)
            val t0 = SystemClock.elapsedRealtime()
            graph.llm.load()
            embedder.load()
            out.put("load_ms", SystemClock.elapsedRealtime() - t0).put("chunks", db.chunks().count())
            log("geladen in ${(SystemClock.elapsedRealtime() - t0) / 1000}s, ${db.chunks().count()} Chunks")

            val gold = JSONArray(assets.open("spike/gold_quotes.json").bufferedReader().readText())
            val results = JSONArray()
            for (g in skip until minOf(gold.length(), skip + n)) {
                val q = gold.getJSONObject(g)
                val s = SystemClock.elapsedRealtime()
                var first = -1L
                var sources = emptyList<de.edgebird.lernsystem.data.chat.Source>()
                var done: ChatEvent.Done? = null
                try {
                chat.ask(q.getString("frage")).collect { e ->
                    when (e) {
                        is ChatEvent.Sources -> sources = e.sources
                        is ChatEvent.Token -> if (first < 0) first = SystemClock.elapsedRealtime() - s
                        is ChatEvent.Done -> done = e
                    }
                }
                } catch (t: Throwable) {
                    log("Fehler bei ${q.getString("id")}: ${t.message?.take(80)}; Quellen=${sources.size}, Zeichen=${sources.map { it.text.length }}")
                    bisect(graph, q.getString("frage"), sources)
                    throw t
                }
                val belege = q.getJSONArray("belege")
                val hits = JSONArray()
                for (b in 0 until belege.length()) {
                    val beleg = belege.getJSONObject(b)
                    val quote = SearchTokenizer.tokenize(beleg.getString("zitat")).toSet()
                    val pos = sources.indexOfFirst { src ->
                        src.documentTitle == beleg.getString("dokument") && quote.isNotEmpty() &&
                            SearchTokenizer.tokenize(src.text).toSet().let { c -> quote.count { it in c }.toDouble() / quote.size >= 0.8 }
                    }
                    hits.put(if (pos >= 0) pos + 1 else JSONObject.NULL)
                }
                val d = done
                results.put(
                    JSONObject().put("id", q.getString("id")).put("typ", q.getString("typ")).put("frage", q.getString("frage"))
                        .put("erwartet", q.getString("erwartet")).put("antwort", d?.answer.orEmpty()).put("not_found", d?.notFound ?: false)
                        .put("cited", JSONArray(d?.cited?.toList().orEmpty())).put("source_hits", hits)
                        .put("n_sources", sources.size).put("ttft_ms", first).put("total_ms", SystemClock.elapsedRealtime() - s),
                )
                log("${q.getString("id")}: ${SystemClock.elapsedRealtime() - s}ms notFound=${d?.notFound}")
            }
            out.put("results", results)
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

    /** Fehlersuche: gleicher Prompt mit weniger/kuerzeren Quellen, jeweils nur 16 Token erzeugen. */
    private suspend fun bisect(graph: de.edgebird.lernsystem.AppGraph, question: String, sources: List<de.edgebird.lernsystem.data.chat.Source>) {
        for ((n, maxChars) in listOf(4 to 100000, 4 to 500, 2 to 1000, 1 to 1000, 1 to 300)) {
            val passages = sources.take(n).map { de.edgebird.lernsystem.core.rag.Passage("${it.documentTitle}, ${it.location}", it.text.take(maxChars)) }
            val p = de.edgebird.lernsystem.core.rag.RagPromptBuilder.build(question, passages)
            val r = try {
                val sb = StringBuilder()
                graph.llm.generate(p.user, de.edgebird.lernsystem.core.ai.GenerationParams(maxTokens = 16, system = p.system)).collect { sb.append(it) }
                "ok '${sb.toString().take(30)}'"
            } catch (t: Throwable) { "FEHLER" }
            log("BISECT quellen=$n maxChars=$maxChars promptChars=${p.user.length}: $r")
        }
        val first = sources.firstOrNull()
        if (first != null) log("BISECT erste Quelle (Anfang): ${first.text.take(160).replace("\n", "|")}")
    }

    override fun onDestroy() {
        super.onDestroy()
        scope.coroutineContext[kotlinx.coroutines.Job]?.cancel()
    }
}

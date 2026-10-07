package de.edgebird.lernsystem.spike

import android.app.Activity
import android.os.Bundle
import android.os.SystemClock
import android.util.Log
import android.view.WindowManager
import android.widget.ScrollView
import android.widget.TextView
import de.edgebird.lernsystem.ai.LiteRtLmEmbedder
import de.edgebird.lernsystem.ai.LlmBackend
import de.edgebird.lernsystem.core.rag.EmbeddingPrompts
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Embedding-Spike: Durchsatz + Retrieval-Qualitaet (Treffer@k) auf dem Geraet.
 *   adb shell am start -n de.edgebird.lernsystem/.spike.SpikeEmbedActivity \
 *     --es model embeddinggemma-2-text-270m.litertlm --es backend cpu --ei dim 768 \
 *     --ez prefix true --ei maxlen 512 --ei batch 16 --ei limit 3012 --es tag emb-cpu
 * Ergebnis: files/spike/<tag>.json, Logcat-Tag SPIKE.
 */
class SpikeEmbedActivity : Activity() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private lateinit var view: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        view = TextView(this).apply { textSize = 12f; setPadding(24, 48, 24, 24) }
        setContentView(ScrollView(this).apply { addView(view) })
        val i = intent
        scope.launch {
            run(
                model = i.getStringExtra("model") ?: "embeddinggemma-2-text-270m.litertlm",
                backend = if (i.getStringExtra("backend") == "gpu") LlmBackend.GPU else LlmBackend.CPU,
                dim = i.getIntExtra("dim", 768), prefix = i.getBooleanExtra("prefix", true),
                maxLen = i.getIntExtra("maxlen", 512), batch = i.getIntExtra("batch", 16),
                limit = i.getIntExtra("limit", 3012), tag = i.getStringExtra("tag") ?: "emb",
            )
        }
    }

    private fun log(msg: String) {
        Log.i("SPIKE", msg)
        runOnUiThread { view.append(msg + "\n") }
    }

    private suspend fun run(model: String, backend: LlmBackend, dim: Int, prefix: Boolean, maxLen: Int, batch: Int, limit: Int, tag: String) {
        val out = JSONObject().put("tag", tag).put("model", model).put("backend", backend.name).put("dim", dim)
            .put("prefix", prefix).put("maxlen", maxLen).put("batch", batch)
        try {
            val corpus = JSONArray(assets.open("spike/corpus.json").bufferedReader().readText())
            val gold = JSONArray(assets.open("spike/gold.json").bufferedReader().readText())
            // Teilkorpus: alle Gold-Abschnitte + die ersten Abschnitte bis `limit`
            val need = sortedSetOf<Int>()
            for (g in 0 until gold.length()) gold.getJSONObject(g).getJSONArray("belege").let { b -> for (j in 0 until b.length()) need.add(b.getInt(j)) }
            val ids = LinkedHashSet<Int>(need)
            var c = 0
            while (ids.size < minOf(limit, corpus.length()) && c < corpus.length()) ids.add(c++)
            val idList = ids.toList().sorted()
            out.put("n_passages", idList.size)

            val emb = LiteRtLmEmbedder(File(filesDir, "models/$model").absolutePath, cacheDir.absolutePath, backend, dim, maxLen)
            val t0 = SystemClock.elapsedRealtime()
            emb.load()
            out.put("load_ms", SystemClock.elapsedRealtime() - t0)
            log("geladen in ${out.getLong("load_ms")} ms")
            emb.embed(listOf("Aufwärmen")) // Aufwaermen

            val docs = idList.map { id -> corpus.getJSONObject(id).let { o -> if (prefix) EmbeddingPrompts.document(o.getString("text"), o.getString("titel")) else o.getString("text") } }
            val vecs = ArrayList<FloatArray>(docs.size)
            val t1 = SystemClock.elapsedRealtime()
            var truncated = 0
            for (s in docs.indices step batch) {
                val part = docs.subList(s, minOf(s + batch, docs.size))
                vecs += try {
                    emb.embed(part)
                } catch (e: Exception) {
                    // zu lange Eingabe (>maxlen Token): einzeln, bei Bedarf schrittweise kuerzen
                    part.map { t ->
                        var x = t
                        while (true) {
                            try { return@map emb.embed(listOf(x))[0] } catch (e2: Exception) {
                                if (x.length < 200) throw e2
                                x = x.take((x.length * 0.9).toInt()); truncated++
                            }
                        }
                        @Suppress("UNREACHABLE_CODE") FloatArray(0)
                    }
                }
                if ((s / batch) % 20 == 0) log("embedded ${vecs.size}/${docs.size} (${(SystemClock.elapsedRealtime() - t1) / 1000}s)")
            }
            out.put("truncation_steps", truncated)
            val tDocs = SystemClock.elapsedRealtime() - t1
            out.put("docs_ms", tDocs).put("docs_per_s", docs.size * 1000.0 / tDocs)
            log("Dokumente: ${docs.size} in ${tDocs / 1000}s = ${"%.1f".format(docs.size * 1000.0 / tDocs)}/s")

            val pos = idList.withIndex().associate { it.value to it.index }
            val perQ = JSONArray()
            val qVecs = ArrayList<FloatArray>()
            val tq = SystemClock.elapsedRealtime()
            for (g in 0 until gold.length()) {
                val q = gold.getJSONObject(g)
                val text = q.getString("frage").let { if (prefix) EmbeddingPrompts.query(it) else it }
                val qv = emb.embed(listOf(text))[0]
                qVecs += qv
                val scores = vecs.map { v -> var d = 0f; for (k in v.indices) d += v[k] * qv[k]; d }
                val order = scores.indices.sortedByDescending { scores[it] }
                val rankOf = IntArray(scores.size).also { r -> order.forEachIndexed { rk, i -> r[i] = rk + 1 } }
                val ranks = JSONArray()
                q.getJSONArray("belege").let { b -> for (j in 0 until b.length()) ranks.put(rankOf[pos.getValue(b.getInt(j))]) }
                perQ.put(JSONObject().put("id", q.getString("id")).put("typ", q.getString("typ")).put("ranks", ranks))
            }
            out.put("query_ms_avg", (SystemClock.elapsedRealtime() - tq).toDouble() / gold.length()).put("per_question", perQ)
            emb.close()
            if (intent.getBooleanExtra("dump", false)) {
                // Binaer: erst alle Dokumentvektoren (in idList-Reihenfolge), dann alle Fragevektoren; float32 little-endian
                val bb = java.nio.ByteBuffer.allocate((vecs.size + qVecs.size) * dim * 4).order(java.nio.ByteOrder.LITTLE_ENDIAN)
                (vecs + qVecs).forEach { v -> for (k in 0 until dim) bb.putFloat(v[k]) }
                File(filesDir, "spike").apply { mkdirs() }.let { File(it, "$tag.vec").writeBytes(bb.array()) }
                out.put("id_list", JSONArray(idList)).put("n_queries", qVecs.size)
            }
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

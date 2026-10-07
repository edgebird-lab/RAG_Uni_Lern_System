package de.edgebird.lernsystem.spike

import android.app.Activity
import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Bundle
import android.os.PowerManager
import android.os.SystemClock
import android.util.Log
import android.view.WindowManager
import android.widget.ScrollView
import android.widget.TextView
import de.edgebird.lernsystem.ai.LiteRtLmEngine
import de.edgebird.lernsystem.ai.LlmBackend
import de.edgebird.lernsystem.core.ai.GenerationParams
import de.edgebird.lernsystem.core.rag.Passage
import de.edgebird.lernsystem.core.rag.RagPromptBuilder
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.collect
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Mess-Spike fuer Phase 1. Start per adb:
 *   adb shell am start -n de.edgebird.lernsystem/.spike.SpikeActivity \
 *     --es model gemma-4-E2B-it.litertlm --es backend gpu --ez mtp false --ei n 21 --es tag e2b-gpu
 * Modell liegt unter files/models/. Ergebnis: files/spike/<tag>.json und Logcat-Tag SPIKE.
 */
class SpikeActivity : Activity() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private lateinit var view: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        view = TextView(this).apply { textSize = 12f; setPadding(24, 48, 24, 24) }
        setContentView(ScrollView(this).apply { addView(view) })
        val model = intent.getStringExtra("model") ?: "gemma-4-E2B-it.litertlm"
        val backend = if (intent.getStringExtra("backend") == "cpu") LlmBackend.CPU else LlmBackend.GPU
        val mtp = intent.getBooleanExtra("mtp", false)
        val n = intent.getIntExtra("n", 21)
        val maxTokens = intent.getIntExtra("maxtokens", 256)
        val tag = intent.getStringExtra("tag") ?: "run"
        scope.launch { runSpike(model, backend, mtp, n, maxTokens, tag) }
    }

    private fun log(msg: String) {
        Log.i("SPIKE", msg)
        runOnUiThread { view.append(msg + "\n") }
    }

    private fun rssMb(key: String): Long =
        File("/proc/self/status").readLines().firstOrNull { it.startsWith(key) }
            ?.filter { it.isDigit() }?.toLongOrNull()?.div(1024) ?: -1

    private fun env(): JSONObject {
        val bat = registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        val am = getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val mi = ActivityManager.MemoryInfo().also { am.getMemoryInfo(it) }
        return JSONObject()
            .put("rss_mb", rssMb("VmRSS")).put("hwm_mb", rssMb("VmHWM"))
            .put("avail_ram_mb", mi.availMem / 1048576)
            .put("thermal", pm.currentThermalStatus)
            .put("batt_temp_c", (bat?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0) ?: 0) / 10.0)
            .put("batt_pct", bat?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1)
    }

    private suspend fun runSpike(model: String, backend: LlmBackend, mtp: Boolean, n: Int, maxTokens: Int, tag: String) {
        val out = JSONObject().put("tag", tag).put("model", model).put("backend", backend.name).put("mtp", mtp)
        try {
            val modelFile = File(filesDir, "models/$model")
            require(modelFile.exists()) { "Modell fehlt: $modelFile" }
            val prompts = JSONArray(assets.open("spike/prompts.json").bufferedReader().readText())
            out.put("env_before", env())
            val engine = LiteRtLmEngine(
                modelPath = modelFile.absolutePath, cacheDir = cacheDir.absolutePath, backend = backend,
                maxNumTokens = 4096, speculativeDecoding = mtp, collectBenchmark = true,
            )
            val t0 = SystemClock.elapsedRealtime()
            engine.load()
            out.put("load_ms", SystemClock.elapsedRealtime() - t0).put("env_after_load", env())
            log("Modell geladen in ${out.getLong("load_ms")} ms")

            engine.generate("Sag kurz Hallo.", GenerationParams(maxTokens = 16)).collect { }  // Aufwaermen
            val results = JSONArray()
            for (i in 0 until minOf(n, prompts.length())) {
                val it = prompts.getJSONObject(i)
                val ctx = it.getJSONArray("kontext")
                val passages = (0 until ctx.length()).map { j -> ctx.getJSONObject(j).let { c -> Passage(c.getString("quelle"), c.getString("text")) } }
                val p = RagPromptBuilder.build(it.getString("frage"), passages)
                val sb = StringBuilder()
                var chunks = 0
                var first = -1L
                val s = SystemClock.elapsedRealtime()
                engine.generate(p.user, GenerationParams(maxTokens = maxTokens, system = p.system)).collect { part ->
                    if (first < 0) first = SystemClock.elapsedRealtime() - s
                    chunks++; sb.append(part)
                }
                val total = SystemClock.elapsedRealtime() - s
                val b = engine.lastStats
                val r = JSONObject().put("id", it.getString("id")).put("typ", it.getString("typ"))
                    .put("frage", it.getString("frage")).put("erwartet", it.getString("erwartet"))
                    .put("antwort", sb.toString()).put("ttft_ms", first).put("total_ms", total).put("chunks", chunks)
                    .put("prompt_chars", p.user.length + p.system.length)
                if (b != null) r.put("bench", JSONObject().put("ttft_s", b.ttftSeconds)
                    .put("prefill_tok", b.prefillTokens).put("prefill_tps", b.prefillTokensPerSecond)
                    .put("decode_tok", b.decodeTokens).put("decode_tps", b.decodeTokensPerSecond))
                results.put(r)
                log("${it.getString("id")}: ttft=${first}ms total=${total}ms decode=${b?.decodeTokensPerSecond?.let { d -> "%.1f".format(d) }} tok/s")
            }
            out.put("results", results).put("env_end", env())
            engine.close()
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

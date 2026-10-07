package de.edgebird.lernsystem.spike

import android.app.Activity
import android.os.Bundle
import android.util.Log
import android.view.WindowManager
import android.widget.ScrollView
import android.widget.TextView
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.ai.LiteRtLmEmbedder
import de.edgebird.lernsystem.ai.LiteRtLmEngine
import de.edgebird.lernsystem.ai.LlmBackend
import de.edgebird.lernsystem.core.ai.GenerationParams
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.io.File

/**
 * Diagnose: Sprachmodell und Embedder im SELBEN Prozess.
 *   --es order llm-first|emb-first   --es emb gpu|cpu   --ez mtp true|false
 * Ausgabe: Logcat-Tag SPIKE, Zeilen "COMBO ...".
 */
class SpikeComboActivity : Activity() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private lateinit var view: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        view = TextView(this).apply { textSize = 12f; setPadding(24, 48, 24, 24) }
        setContentView(ScrollView(this).apply { addView(view) })
        val order = intent.getStringExtra("order") ?: "llm-first"
        val embBackend = if (intent.getStringExtra("emb") == "cpu") LlmBackend.CPU else LlmBackend.GPU
        val mtp = intent.getBooleanExtra("mtp", true)
        if (savedInstanceState == null) scope.launch { run(order, embBackend, mtp, intent.getIntExtra("plen", 0), intent.getIntExtra("maxtokens", 24)) }
    }

    private fun log(msg: String) {
        Log.i("SPIKE", "COMBO $msg")
        runOnUiThread { view.append(msg + "\n") }
    }

    private suspend fun step(name: String, block: suspend () -> String) {
        try {
            log("$name: ok ${block()}")
        } catch (t: Throwable) {
            log("$name: FEHLER ${t.message?.take(120)}")
        }
    }

    private suspend fun run(order: String, embBackend: LlmBackend, mtp: Boolean, plen: Int, maxTokens: Int) {
        val graph = (application as LernsystemApp).graph
        val cache = File(filesDir, "litert-cache").absolutePath
        val llm = LiteRtLmEngine(graph.llmModelFile.absolutePath, cache, LlmBackend.GPU, 4096, speculativeDecoding = mtp)
        val emb = LiteRtLmEmbedder(graph.embeddingModelFile.absolutePath, cache, embBackend, 768, 512)
        log("start order=$order emb=$embBackend mtp=$mtp plen=$plen maxtokens=$maxTokens")
        suspend fun gen(label: String) = step(label) {
            val ctx = "Die Würde des Menschen ist unantastbar. Sie zu achten und zu schützen ist Verpflichtung aller staatlichen Gewalt. ".repeat(plen / 100 + 1).take(plen)
            val prompt = if (plen > 0) "Kontext:\n$ctx\n\nFrage: Sag in einem Satz Hallo." else "Sag in einem Satz Hallo."
            val sb = StringBuilder(); llm.generate(prompt, GenerationParams(maxTokens = maxTokens, system = if (intent.getBooleanExtra("sys", false)) de.edgebird.lernsystem.core.rag.RagPromptBuilder.build("x", emptyList()).system else null)).collect { sb.append(it) }; sb.toString().take(40)
        }
        suspend fun embed(label: String) = step(label) { emb.embed(listOf("Testfrage")).first().size.toString() }
        if (order == "llm-first") {
            step("llm.load") { llm.load(); "" }; gen("gen1")
            step("emb.load") { emb.load(); "" }; embed("embed1"); gen("gen2"); embed("embed2")
        } else {
            step("emb.load") { emb.load(); "" }; embed("embed1")
            step("llm.load") { llm.load(); "" }; gen("gen1"); embed("embed2"); gen("gen2")
        }
        log("ENDE")
    }

    override fun onDestroy() {
        super.onDestroy()
        scope.coroutineContext[kotlinx.coroutines.Job]?.cancel()
    }
}

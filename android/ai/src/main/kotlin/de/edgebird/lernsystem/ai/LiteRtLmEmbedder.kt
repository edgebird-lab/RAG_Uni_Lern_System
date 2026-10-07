package de.edgebird.lernsystem.ai

import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.EmbeddingEngine
import com.google.ai.edge.litertlm.EmbeddingEngineConfig
import com.google.ai.edge.litertlm.EmbeddingOptions
import com.google.ai.edge.litertlm.InputData
import de.edgebird.lernsystem.core.ai.Embedder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** [Embedder] auf Basis von LiteRT-LM (EmbeddingGemma 2, `.litertlm`). Vektoren sind L2-normalisiert. */
class LiteRtLmEmbedder(
    private val modelPath: String,
    private val cacheDir: String,
    private val backend: LlmBackend = LlmBackend.CPU,
    override val dimensions: Int = 768,
    private val maxInputLength: Int = 512,
) : Embedder {
    private var engine: EmbeddingEngine? = null

    override suspend fun load() {
        if (engine != null) return
        withContext(Dispatchers.Default) {
            val config = EmbeddingEngineConfig(
                modelPath = modelPath,
                backend = if (backend == LlmBackend.GPU) Backend.GPU() else Backend.CPU(),
                cacheDir = cacheDir,
                maxInputLength = maxInputLength,
            )
            engine = EmbeddingEngine(config).also { it.initialize() }
        }
    }

    override suspend fun embed(texts: List<String>): List<FloatArray> = withContext(Dispatchers.Default) {
        val e = checkNotNull(engine) { "load() wurde nicht aufgerufen" }
        val options = EmbeddingOptions(normalize = true, outputSize = dimensions)
        try {
            e.computeEmbeddingBatch(texts.map { listOf<InputData>(InputData.Text(it)) }, options).map { it.embedding }
        } catch (batchError: Exception) {
            // Mindestens ein Text überschreitet das Token-Limit: einzeln, bei Bedarf schrittweise kürzen.
            texts.map { embedTruncating(e, it, options) }
        }
    }

    private fun embedTruncating(e: EmbeddingEngine, text: String, options: EmbeddingOptions): FloatArray {
        var t = text
        while (true) {
            try {
                return e.computeEmbedding(listOf<InputData>(InputData.Text(t)), options).embedding
            } catch (err: Exception) {
                if (t.length < MIN_CHARS) throw err
                t = t.take((t.length * SHRINK).toInt())
            }
        }
    }

    private companion object {
        const val MIN_CHARS = 200
        const val SHRINK = 0.9
    }

    override fun close() {
        engine?.close()
        engine = null
    }
}

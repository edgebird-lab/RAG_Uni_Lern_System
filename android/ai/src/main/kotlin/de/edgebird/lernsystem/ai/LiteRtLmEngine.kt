package de.edgebird.lernsystem.ai

import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Content
import com.google.ai.edge.litertlm.ConversationConfig
import com.google.ai.edge.litertlm.Contents
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import com.google.ai.edge.litertlm.ExperimentalApi
import com.google.ai.edge.litertlm.ExperimentalFlags
import com.google.ai.edge.litertlm.SamplerConfig
import de.edgebird.lernsystem.core.ai.GenerationParams
import de.edgebird.lernsystem.core.ai.GenerationStats
import de.edgebird.lernsystem.core.ai.LlmEngine
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.withContext

enum class LlmBackend { CPU, GPU }

/** [LlmEngine] auf Basis von LiteRT-LM (Gemma 4, `.litertlm`). Jede Generierung nutzt eine frische Conversation (RAG ist zustandslos). */
class LiteRtLmEngine(
    private val modelPath: String,
    private val cacheDir: String,
    private val backend: LlmBackend = LlmBackend.GPU,
    private val maxNumTokens: Int = 4096,
    private val speculativeDecoding: Boolean = false,
    private val collectBenchmark: Boolean = false,
) : LlmEngine {
    private var engine: Engine? = null

    /** Messwerte der zuletzt abgeschlossenen Generierung (nur mit `collectBenchmark`). */
    @Volatile
    var lastStats: GenerationStats? = null
        private set

    @OptIn(ExperimentalApi::class)
    override suspend fun load() {
        if (engine != null) return
        withContext(Dispatchers.Default) {
            ExperimentalFlags.enableBenchmark = collectBenchmark
            ExperimentalFlags.enableSpeculativeDecoding = speculativeDecoding
            val config = EngineConfig(
                modelPath = modelPath,
                backend = if (backend == LlmBackend.GPU) Backend.GPU() else Backend.CPU(),
                maxNumTokens = maxNumTokens,
                cacheDir = cacheDir,
            )
            engine = Engine(config).also { it.initialize() }
        }
    }

    @OptIn(ExperimentalApi::class)
    override fun generate(prompt: String, params: GenerationParams): Flow<String> = flow {
        val e = checkNotNull(engine) { "load() wurde nicht aufgerufen" }
        val config = ConversationConfig(
            systemInstruction = params.system?.let { Contents.of(it) },
            samplerConfig = SamplerConfig(topK = 40, topP = params.topP.toDouble(), temperature = params.temperature.toDouble(), seed = 0),
            maxOutputToken = params.maxTokens,
        )
        e.createConversation(config).use { conversation ->
            try {
                conversation.sendMessageAsync(prompt).map { m ->
                    m.contents.contents.filterIsInstance<Content.Text>().joinToString("") { it.text }
                }.collect { emit(it) }
            } catch (c: CancellationException) {
                conversation.cancelProcess()
                throw c
            } finally {
                if (collectBenchmark) {
                    lastStats = conversation.getBenchmarkInfo().let {
                        GenerationStats(it.timeToFirstTokenInSecond, it.lastPrefillTokenCount, it.lastPrefillTokensPerSecond,
                            it.lastDecodeTokenCount, it.lastDecodeTokensPerSecond)
                    }
                }
            }
        }
    }.flowOn(Dispatchers.Default)

    override fun close() {
        engine?.close()
        engine = null
    }
}

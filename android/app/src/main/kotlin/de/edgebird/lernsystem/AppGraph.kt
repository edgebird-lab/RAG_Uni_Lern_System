package de.edgebird.lernsystem

import android.content.Context
import de.edgebird.lernsystem.ai.LiteRtLmEmbedder
import de.edgebird.lernsystem.ai.LiteRtLmEngine
import de.edgebird.lernsystem.ai.LlmBackend
import de.edgebird.lernsystem.data.AppDatabase
import de.edgebird.lernsystem.data.chat.RagChat
import de.edgebird.lernsystem.data.search.HybridRetriever
import de.edgebird.lernsystem.data.search.KeywordSearch
import de.edgebird.lernsystem.data.search.VectorIndex
import de.edgebird.lernsystem.ingest.ImportPipeline
import de.edgebird.lernsystem.ingest.Loaders
import java.io.File

/** Einfacher Abhängigkeits-Container der App (ohne DI-Framework). */
class AppGraph(private val context: Context) {
    val db: AppDatabase by lazy { AppDatabase.build(context) }
    val pipeline: ImportPipeline by lazy { ImportPipeline(db, Loaders.default(context)) }

    val modelsDir = File(context.filesDir, "models")
    val inboxDir = File(context.filesDir, "inbox").apply { mkdirs() }

    /** Bis zum Modell-Download (Phase 8) manuell per adb abgelegt. */
    val embeddingModelFile = File(modelsDir, "embeddinggemma-2-text-270m.litertlm")
    val embeddingModelId = "embeddinggemma-2-text-270m-768"

    /** Liegt in filesDir statt cacheDir, damit das System den teuren GPU-Cache nicht löscht. */
    private val litertCache = File(context.filesDir, "litert-cache").apply { mkdirs() }

    fun newEmbedder() = LiteRtLmEmbedder(embeddingModelFile.absolutePath, litertCache.absolutePath, LlmBackend.GPU, dimensions = 768, maxInputLength = 512)

    /** Sprachmodell (bis zum Download in Phase 8 manuell abgelegt). GPU mit Multi-Token-Prediction, siehe SPIKE_ERGEBNIS.md. */
    val llmModelFile = File(modelsDir, "gemma-4-E2B-it.litertlm")
    val llm: LiteRtLmEngine by lazy {
        LiteRtLmEngine(llmModelFile.absolutePath, litertCache.absolutePath, LlmBackend.GPU, maxNumTokens = 4096, speculativeDecoding = true)
    }

    private val queryEmbedder by lazy { newEmbedder() }
    val retriever: HybridRetriever by lazy {
        HybridRetriever(db, KeywordSearch(db), VectorIndex(db, embeddingModelId), if (embeddingModelFile.exists()) queryEmbedder else null)
    }
    val chat: RagChat by lazy { RagChat(retriever, llm) }
}

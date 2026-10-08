package de.edgebird.lernsystem

import android.content.Context
import de.edgebird.lernsystem.ai.LiteRtLmEmbedder
import de.edgebird.lernsystem.ai.LiteRtLmEngine
import de.edgebird.lernsystem.ai.LlmBackend
import de.edgebird.lernsystem.data.AppDatabase
import de.edgebird.lernsystem.data.PomodoroRepository
import de.edgebird.lernsystem.pomodoro.PomodoroController
import de.edgebird.lernsystem.data.chat.RagChat
import de.edgebird.lernsystem.data.search.HybridRetriever
import de.edgebird.lernsystem.data.search.KeywordSearch
import de.edgebird.lernsystem.data.search.VectorIndex
import de.edgebird.lernsystem.data.study.StudyRepository
import de.edgebird.lernsystem.data.study.StudySettings
import de.edgebird.lernsystem.ingest.ImportPipeline
import de.edgebird.lernsystem.ingest.Loaders
import java.io.File

/** Einfacher Abhängigkeits-Container der App (ohne DI-Framework). */
class AppGraph(private val context: Context) {
    val db: AppDatabase by lazy { AppDatabase.build(context) }
    val pipeline: ImportPipeline by lazy { ImportPipeline(db, Loaders.default(context)) }

    val modelsDir = File(context.filesDir, "models")
    val inboxDir = File(context.filesDir, "inbox").apply { mkdirs() }
    val sources: de.edgebird.lernsystem.source.SourceStore by lazy { de.edgebird.lernsystem.source.SourceStore(context.filesDir) }
    val sourceRepo: de.edgebird.lernsystem.data.source.SourceRepository by lazy { de.edgebird.lernsystem.data.source.SourceRepository(db) }

    /** Entpacktes Stimmenpaket für die Offline-Sprachausgabe (optionaler Download). */
    val voices: de.edgebird.lernsystem.voice.VoiceLibrary by lazy { de.edgebird.lernsystem.voice.VoiceLibrary(modelsDir, prefs) }
    val voice: de.edgebird.lernsystem.ui.VoiceHolder by lazy { de.edgebird.lernsystem.ui.VoiceHolder(voices) }

    /** Reste abgebrochener Importe (Dateien, die nie verarbeitet wurden) nach einem Tag entfernen. */
    fun cleanInbox(maxAgeMs: Long = 24L * 3600_000) {
        val limit = System.currentTimeMillis() - maxAgeMs
        inboxDir.listFiles().orEmpty().filter { it.isFile && it.lastModified() < limit }.forEach { it.delete() }
    }

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

    /** Ein gemeinsamer Embedder für Suchanfragen und die Dublettenprüfung der Kartenerzeugung. */
    val sharedEmbedder by lazy { newEmbedder() }
    val retriever: HybridRetriever by lazy {
        HybridRetriever(db, KeywordSearch(db), VectorIndex(db, embeddingModelId), if (embeddingModelFile.exists()) sharedEmbedder else null)
    }
    /** Gibt es schon einen GPU-Cache des Sprachmodells? Ohne ihn dauert der erste Start mehrere Minuten. */
    fun llmCacheWarm(): Boolean = litertCache.listFiles { f -> f.name.startsWith(llmModelFile.name) && "mldrift" in f.name }.orEmpty().isNotEmpty()

    val chat: RagChat by lazy { RagChat(retriever, llm) }

    val prefs by lazy { context.getSharedPreferences("settings", Context.MODE_PRIVATE) }

    fun studySettings() = StudySettings(prefs.getInt(PREF_DAILY_GOAL, 40), prefs.getInt(PREF_NEW_PER_DAY, 20))

    fun saveStudySettings(s: StudySettings) {
        prefs.edit().putInt(PREF_DAILY_GOAL, s.dailyReviewGoal).putInt(PREF_NEW_PER_DAY, s.newCardsPerDay).apply()
    }

    val subjects: de.edgebird.lernsystem.data.SubjectRepository by lazy { de.edgebird.lernsystem.data.SubjectRepository(db) }

    val pomodoroRepo: PomodoroRepository by lazy { PomodoroRepository(db) }

    /** Fokus-Timer (Pomodoro): hält den Zustand auch ohne offene Oberfläche. */
    val pomodoro: PomodoroController by lazy { PomodoroController(context, pomodoroRepo, documentTitle = { id -> db.documents().byId(id)?.title }) }

    val study: StudyRepository by lazy { StudyRepository(db, settings = ::studySettings) }

    private companion object {
        const val PREF_DAILY_GOAL = "daily_goal"
        const val PREF_NEW_PER_DAY = "new_per_day"
    }
}

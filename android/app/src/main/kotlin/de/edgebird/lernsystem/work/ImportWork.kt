package de.edgebird.lernsystem.work

import de.edgebird.lernsystem.core.i18n.tr

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.ServiceInfo
import androidx.core.app.NotificationCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.Data
import androidx.work.ExistingWorkPolicy
import androidx.work.ForegroundInfo
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.ai.PauseReason
import kotlinx.coroutines.delay
import de.edgebird.lernsystem.ingest.DocumentSource
import de.edgebird.lernsystem.ingest.EmbeddingIndexer
import de.edgebird.lernsystem.ingest.ImportResult
import java.io.File

/** Eine bereits in den App-Speicher kopierte Datei, die eingelesen werden soll. */
data class ImportItem(val key: String, val name: String, val file: File)

object ImportWork {
    const val UNIQUE_IMPORT = "import"
    const val TAG_EMBED = "embed"
    private const val CHANNEL = "indexing"

    fun enqueue(context: Context, items: List<ImportItem>, onlyWhenCharging: Boolean = false, subjectId: Long? = null) {
        val input = workDataOf(
            ImportWorker.KEYS to items.map { it.key }.toTypedArray(),
            ImportWorker.NAMES to items.map { it.name }.toTypedArray(),
            ImportWorker.PATHS to items.map { it.file.absolutePath }.toTypedArray(),
            ImportWorker.SUBJECT to (subjectId ?: -1L),
        )
        val import = OneTimeWorkRequestBuilder<ImportWorker>().setInputData(input).build()
        val embed = OneTimeWorkRequestBuilder<EmbedWorker>().addTag(TAG_EMBED)
            .setConstraints(Constraints.Builder().setRequiresCharging(onlyWhenCharging).build()).build()
        WorkManager.getInstance(context)
            .beginUniqueWork(UNIQUE_IMPORT, ExistingWorkPolicy.APPEND_OR_REPLACE, import)
            .then(embed)
            .enqueue()
    }

    fun foregroundInfo(context: Context, text: String, done: Int, total: Int, title: String = tr("Dokumente werden vorbereitet", "Preparing documents"), id: Int = 1): ForegroundInfo {
        val nm = context.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL, tr("Indexierung", "Indexing"), NotificationManager.IMPORTANCE_LOW))
        val n = NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle(title)
            .setContentText(text)
            .setOngoing(true)
            .setProgress(total, done, total == 0)
            .build()
        return ForegroundInfo(id, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
    }
}

class ImportWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val graph = (applicationContext as LernsystemApp).graph
        val keys = inputData.getStringArray(KEYS) ?: return Result.failure()
        val names = inputData.getStringArray(NAMES) ?: return Result.failure()
        val paths = inputData.getStringArray(PATHS) ?: return Result.failure()
        val lines = mutableListOf<String>()
        for (i in keys.indices) {
            val file = File(paths[i])
            val result = try {
                graph.pipeline.import(DocumentSource(keys[i], names[i]) { file.inputStream() }, subjectId = inputData.getLong(SUBJECT, -1L).takeIf { it >= 0 })
            } finally {
                file.delete()
            }
            lines += when (result) {
                is ImportResult.Imported -> {
                    // Geändertes Dokument: vorhandene Zusammenfassungen werden für die neue Fassung neu berechnet
                    val subject = graph.db.documents().byId(result.documentId)?.subjectId
                    if (subject != null) result.previousSummarySpecs.forEach { SummaryWork.enqueue(applicationContext, SummaryWork.Job(subject, de.edgebird.lernsystem.data.SummaryScope.DOC, listOf(result.documentId), "", de.edgebird.lernsystem.core.summary.SummarySpec.fromJson(it))) }
                    tr("${names[i]}: ${result.chunks} Abschnitte", "${names[i]}: ${result.chunks} sections") + (if (result.emptyPages > 0) tr(" (${result.emptyPages} Seiten ohne Text)", " (${result.emptyPages} pages without text)") else "") +
                        (if (result.previousSummarySpecs.isNotEmpty()) tr(", Zusammenfassung wird neu erstellt", ", summary will be recreated") else "")
                }
                is ImportResult.SkippedUnchanged -> tr("${names[i]}: bereits vorhanden", "${names[i]}: already present")
                is ImportResult.SkippedDuplicate -> tr("${names[i]}: Duplikat eines vorhandenen Dokuments", "${names[i]}: duplicate of an existing document")
                is ImportResult.Failed -> "${names[i]}: ${result.reason}"
            }
        }
        return Result.success(Data.Builder().putString(MESSAGE, lines.joinToString("\n")).build())
    }

    companion object {
        const val KEYS = "keys"
        const val NAMES = "names"
        const val PATHS = "paths"
        const val MESSAGE = "message"
        const val SUBJECT = "subject"
    }
}

/** Berechnet fehlende Embeddings im Vordergrunddienst, damit die GPU-Arbeit nicht gedrosselt wird. */
class EmbedWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val graph = (applicationContext as LernsystemApp).graph
        if (graph.db.chunks().countWithoutEmbedding(graph.embeddingModelId) == 0) return Result.success()
        if (!graph.embeddingModelFile.exists()) return Result.failure(workDataOf(ERROR to tr("Embedding-Modell fehlt", "Embedding model is missing")))
        setForeground(ImportWork.foregroundInfo(applicationContext, tr("Starte …", "Starting …"), 0, 0))
        val embedder = graph.newEmbedder()
        return try {
            val total = graph.db.chunks().countWithoutEmbedding(graph.embeddingModelId)
            var done = 0
            EmbeddingIndexer(graph.db, embedder, graph.embeddingModelId).run(
                beforeBatch = {
                    // Bei Hitze oder leerem Akku pausieren, bis sich der Zustand bessert (Arbeit bleibt gespeichert)
                    while (true) {
                        val reason = DeviceState.pauseReason(applicationContext) ?: break
                        val text = if (reason == PauseReason.HOT) tr("Pausiert: Gerät ist zu warm", "Paused: device is too warm") else tr("Pausiert: Akku ist fast leer", "Paused: battery almost empty")
                        setForeground(ImportWork.foregroundInfo(applicationContext, text, done, total))
                        delay(15_000)
                    }
                },
                onProgress = { d, t ->
                    done = d
                    setProgressAsync(workDataOf(DONE to d, TOTAL to t))
                    setForegroundAsync(ImportWork.foregroundInfo(applicationContext, tr("$d von $t Abschnitten", "$d of $t sections"), d, t))
                },
            )
            Result.success()
        } finally {
            embedder.close()
        }
    }

    companion object {
        const val DONE = "done"
        const val TOTAL = "total"
        const val ERROR = "error"
    }
}

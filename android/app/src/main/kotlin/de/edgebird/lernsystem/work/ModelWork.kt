package de.edgebird.lernsystem.work

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.models.ModelDownloader
import de.edgebird.lernsystem.core.models.ModelPlan
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import kotlin.coroutines.coroutineContext

object ModelWork {
    const val UNIQUE = "model_download"

    /** Wo das Manifest liegt: zuerst die Datei im Repo, danach das Release-Asset (zwei unabhängige Wege). */
    val MANIFEST_URLS = listOf(
        "https://raw.githubusercontent.com/edgebird-lab/lernsystem-modelle/main/manifest.json",
        "https://github.com/edgebird-lab/lernsystem-modelle/releases/latest/download/manifest.json",
    )

    fun enqueue(context: Context, wifiOnly: Boolean) {
        val req = OneTimeWorkRequestBuilder<ModelDownloadWorker>()
            .setConstraints(Constraints.Builder().setRequiredNetworkType(if (wifiOnly) NetworkType.UNMETERED else NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(UNIQUE, ExistingWorkPolicy.REPLACE, req)
    }

    fun cancel(context: Context) { WorkManager.getInstance(context).cancelUniqueWork(UNIQUE) }
}

/** Lädt alle fehlenden oder veralteten Modelle im Vordergrunddienst; ein Abbruch behält den Teilstand zum Fortsetzen. */
class ModelDownloadWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val graph = (applicationContext as LernsystemApp).graph
        val dl = ModelDownloader(graph.modelsDir)
        setForeground(ImportWork.foregroundInfo(applicationContext, "Starte …", 0, 0, "Modelle werden geladen", id = 3))
        return withContext(Dispatchers.IO) {
            try {
                val manifest = dl.fetchManifest(ModelWork.MANIFEST_URLS)
                val todo = ModelPlan.pending(manifest, dl.installed())
                val grand = todo.sumOf { it.size }
                var finished = 0L
                var lastReport = 0L
                for (m in todo) {
                    dl.install(m, onProgress = { done, _ ->
                        val now = System.currentTimeMillis()
                        if (now - lastReport > 700) {
                            lastReport = now
                            val all = finished + done
                            setProgressAsync(workDataOf(DONE to all, TOTAL to grand, NAME to m.title))
                            setForegroundAsync(ImportWork.foregroundInfo(applicationContext, "${m.title}: ${all * 100 / grand.coerceAtLeast(1)} %", (all / 1_048_576).toInt(), (grand / 1_048_576).toInt(), "Modelle werden geladen", id = 3))
                        }
                    }, isCancelled = { !coroutineContext.isActive })
                    finished += m.size
                }
                Result.success()
            } catch (e: ModelDownloader.Cancelled) {
                throw CancellationException("Abgebrochen")
            } catch (e: Exception) {
                Result.failure(workDataOf(ERROR to (e.message ?: "Unbekannter Fehler")))
            }
        }
    }

    companion object {
        const val DONE = "done"
        const val TOTAL = "total"
        const val NAME = "name"
        const val ERROR = "error"
    }
}

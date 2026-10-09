// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.work

import de.edgebird.lernsystem.core.i18n.tr

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

    const val VOICE_IDS = "voice_ids"

    /** @param voiceIds optionale Modelle (Stimmen für die Sprachausgabe), die zusätzlich geladen werden sollen; bereits installierte werden bei neuer Version aktualisiert */
    fun enqueue(context: Context, wifiOnly: Boolean, voiceIds: Set<String> = emptySet()) {
        val req = OneTimeWorkRequestBuilder<ModelDownloadWorker>().setInputData(workDataOf(VOICE_IDS to voiceIds.toTypedArray()))
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
        setForeground(ImportWork.foregroundInfo(applicationContext, tr("Starte …", "Starting …"), 0, 0, tr("Modelle werden geladen", "Downloading models"), id = 3))
        return withContext(Dispatchers.IO) {
            try {
                val manifest = dl.fetchManifest(ModelWork.MANIFEST_URLS)
                val todo = ModelPlan.pending(manifest, dl.installed(), optionalIds = inputData.getStringArray(ModelWork.VOICE_IDS).orEmpty().toSet(), llmFile = graph.pendingLlmFile ?: graph.activeLlmFile)
                val grand = todo.sumOf { it.size }
                var finished = 0L
                var lastReport = 0L
                for (m in todo) {
                    dl.install(m, onProgress = { done, _ ->
                        val now = System.currentTimeMillis()
                        if (now - lastReport > 700) {
                            lastReport = now
                            val all = finished + done
                            setProgressAsync(workDataOf(DONE to all, TOTAL to grand, NAME to m.displayTitle()))
                            setForegroundAsync(ImportWork.foregroundInfo(applicationContext, "${m.displayTitle()}: ${all * 100 / grand.coerceAtLeast(1)} %", (all / 1_048_576).toInt(), (grand / 1_048_576).toInt(), tr("Modelle werden geladen", "Downloading models"), id = 3))
                        }
                    }, isCancelled = { !coroutineContext.isActive })
                    finished += m.size
                }
                Result.success()
            } catch (e: ModelDownloader.Cancelled) {
                throw CancellationException(tr("Abgebrochen", "Cancelled"))
            } catch (e: Exception) {
                Result.failure(workDataOf(ERROR to (e.message ?: tr("Unbekannter Fehler", "Unknown error"))))
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

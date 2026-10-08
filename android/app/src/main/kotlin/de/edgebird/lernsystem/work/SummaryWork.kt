package de.edgebird.lernsystem.work

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.ai.PauseReason
import de.edgebird.lernsystem.core.summary.SummaryStyle
import de.edgebird.lernsystem.data.summary.SummaryRunner
import kotlinx.coroutines.delay

object SummaryWork {
    const val DOC_ID = "doc"
    const val STYLE = "style"
    const val RESTART = "restart"

    fun tag(documentId: Long, style: SummaryStyle) = "summary-doc-$documentId-${style.name}"

    /** @param restart verwirft vorhandene Teile und startet neu; ein laufender Auftrag desselben Stils wird dabei ersetzt */
    fun enqueue(context: Context, documentId: Long, style: SummaryStyle, restart: Boolean = false) {
        val req = OneTimeWorkRequestBuilder<SummaryWorker>().addTag(tag(documentId, style))
            .setInputData(workDataOf(DOC_ID to documentId, STYLE to style.name, RESTART to restart)).build()
        WorkManager.getInstance(context).enqueueUniqueWork(tag(documentId, style), if (restart) ExistingWorkPolicy.REPLACE else ExistingWorkPolicy.KEEP, req)
    }
}

/** Erstellt eine Zusammenfassung im Vordergrunddienst; wiederaufnehmbar, pausiert bei Hitze oder leerem Akku. */
class SummaryWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val graph = (applicationContext as LernsystemApp).graph
        val docId = inputData.getLong(SummaryWork.DOC_ID, -1)
        val style = runCatching { SummaryStyle.valueOf(inputData.getString(SummaryWork.STYLE).orEmpty()) }.getOrNull() ?: return Result.failure()
        if (docId < 0) return Result.failure()
        if (!graph.llmModelFile.exists()) return Result.failure(workDataOf(ERROR to "Das Sprachmodell fehlt"))

        val title = "Zusammenfassung wird erstellt"
        setForeground(ImportWork.foregroundInfo(applicationContext, "Starte …", 0, 0, title, NOTIFICATION_ID))
        val started = System.currentTimeMillis()
        return try {
            val out = SummaryRunner(graph.db, graph.llm).run(
                docId, style, restart = inputData.getBoolean(SummaryWork.RESTART, false),
                beforeSection = {
                    while (true) {
                        val reason = DeviceState.pauseReason(applicationContext) ?: break
                        setForeground(ImportWork.foregroundInfo(applicationContext, if (reason == PauseReason.HOT) "Pausiert: Gerät ist zu warm" else "Pausiert: Akku ist fast leer", 0, 0, title, NOTIFICATION_ID))
                        delay(15_000)
                    }
                },
                onProgress = { done, total ->
                    setProgressAsync(workDataOf(DONE to done, TOTAL to total))
                    setForegroundAsync(ImportWork.foregroundInfo(applicationContext, "Abschnitt $done von $total", done, total, title, NOTIFICATION_ID))
                },
            )
            val msg = buildString {
                append("${out.used} Abschnitte zusammengefasst")
                if (out.skipped > 0) append(", ${out.skipped} übersprungen")
                if (out.failed > 0) append(", ${out.failed} fehlgeschlagen (erneut versuchen)")
            }
            android.util.Log.i("SUMMARY", "doc=$docId stil=${style.name}: $msg; Warnungen=${out.warnings}; ${(System.currentTimeMillis() - started) / 1000} s")
            Result.success(workDataOf(MESSAGE to msg))
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Exception) {
            android.util.Log.w("SUMMARY", "doc=$docId stil=${style.name} fehlgeschlagen", e)
            Result.failure(workDataOf(ERROR to (e.message ?: "Die Zusammenfassung ist fehlgeschlagen")))
        }
    }

    companion object {
        const val DONE = "done"
        const val TOTAL = "total"
        const val ERROR = "error"
        const val MESSAGE = "message"
        private const val NOTIFICATION_ID = 3
    }
}

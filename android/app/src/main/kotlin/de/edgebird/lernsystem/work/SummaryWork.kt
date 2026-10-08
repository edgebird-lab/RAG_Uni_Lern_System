package de.edgebird.lernsystem.work

import de.edgebird.lernsystem.core.i18n.tr

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.ai.PauseReason
import de.edgebird.lernsystem.core.summary.SummarySpec
import de.edgebird.lernsystem.data.SummaryScope
import de.edgebird.lernsystem.data.summary.SummaryRequest
import de.edgebird.lernsystem.data.summary.SummaryRunner
import kotlinx.coroutines.delay

object SummaryWork {
    /** Ein Zusammenfassungs-Auftrag. */
    data class Job(val subjectId: Long, val scope: SummaryScope, val documentIds: List<Long>, val topic: String, val spec: SummarySpec, val replaceId: Long? = null, val restart: Boolean = false)

    const val SUBJECT = "subject"
    const val SCOPE = "scope"
    const val DOCS = "docs"
    const val TOPIC = "topic"
    const val SPEC = "spec"
    const val REPLACE = "replace"
    const val RESTART = "restart"
    const val LABEL = "label"
    const val LABEL_TAG = "lbl:"

    fun subjectTag(subjectId: Long) = "summary-subject-$subjectId"

    private fun uniqueName(j: Job) = "summary-${j.subjectId}-${j.scope}-${j.documentIds.sorted().joinToString("_")}-${j.topic.trim().lowercase().hashCode()}-${j.spec.toJson().hashCode()}"

    /** Kurzer Name des Auftrags für die Anzeige. */
    fun label(j: Job, docTitle: String?): String = when (j.scope) {
        SummaryScope.DOC -> docTitle ?: tr("Quelle", "Source")
        SummaryScope.SUBJECT -> tr("Ganzes Fach", "Whole subject")
        SummaryScope.TOPIC -> tr("Thema: ${j.topic.trim()}", "Topic: ${j.topic.trim()}")
        SummaryScope.CHAPTER -> tr("Kapitel: ${j.topic.trim()}", "Chapter: ${j.topic.trim()}")
    } + " · " + j.spec.format.label

    fun enqueue(context: Context, job: Job, label: String = "") {
        val req = OneTimeWorkRequestBuilder<SummaryWorker>().addTag(subjectTag(job.subjectId)).addTag(LABEL_TAG + label.take(80))
            .setInputData(
                workDataOf(
                    SUBJECT to job.subjectId, SCOPE to job.scope.name, DOCS to job.documentIds.joinToString(","), TOPIC to job.topic, SPEC to job.spec.toJson(),
                    REPLACE to (job.replaceId ?: -1L), RESTART to job.restart, LABEL to label,
                ),
            ).build()
        WorkManager.getInstance(context).enqueueUniqueWork(uniqueName(job), if (job.restart) ExistingWorkPolicy.REPLACE else ExistingWorkPolicy.KEEP, req)
    }
}

/** Erstellt eine Zusammenfassung im Vordergrunddienst; wiederaufnehmbar, pausiert bei Hitze oder leerem Akku. */
class SummaryWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val graph = (applicationContext as LernsystemApp).graph
        val scope = runCatching { SummaryScope.valueOf(inputData.getString(SummaryWork.SCOPE).orEmpty()) }.getOrNull() ?: return Result.failure()
        val subject = inputData.getLong(SummaryWork.SUBJECT, -1)
        val docs = inputData.getString(SummaryWork.DOCS).orEmpty().split(',').mapNotNull { it.toLongOrNull() }
        if (subject < 0 || docs.isEmpty()) return Result.failure()
        if (!graph.llmModelFile.exists()) return Result.failure(workDataOf(ERROR to tr("Das Sprachmodell fehlt", "The language model is missing")))
        val spec = SummarySpec.fromJson(inputData.getString(SummaryWork.SPEC))
        val label = inputData.getString(SummaryWork.LABEL).orEmpty()

        val title = tr("Zusammenfassung wird erstellt", "Creating summary")
        setForeground(ImportWork.foregroundInfo(applicationContext, label.ifEmpty { tr("Starte …", "Starting …") }, 0, 0, title, NOTIFICATION_ID))
        val started = System.currentTimeMillis()
        return try {
            val req = SummaryRequest(subject, scope, docs, spec, inputData.getString(SummaryWork.TOPIC).orEmpty(), inputData.getLong(SummaryWork.REPLACE, -1).takeIf { it >= 0 })
            val out = SummaryRunner(graph.db, graph.llm, graph.retriever).run(
                req, restart = inputData.getBoolean(SummaryWork.RESTART, false),
                beforeSection = {
                    while (true) {
                        val reason = DeviceState.pauseReason(applicationContext) ?: break
                        setForeground(ImportWork.foregroundInfo(applicationContext, if (reason == PauseReason.HOT) tr("Pausiert: Gerät ist zu warm", "Paused: device is too warm") else tr("Pausiert: Akku ist fast leer", "Paused: battery almost empty"), 0, 0, title, NOTIFICATION_ID))
                        delay(15_000)
                    }
                },
                onProgress = { done, total ->
                    setProgressAsync(workDataOf(DONE to done, TOTAL to total))
                    setForegroundAsync(ImportWork.foregroundInfo(applicationContext, tr("${label.ifEmpty { "Schritt" }}: $done von $total", "${label.ifEmpty { "Step" }}: $done of $total"), done, total, title, NOTIFICATION_ID))
                },
            )
            val msg = buildString {
                append(tr("${out.used} Abschnitte zusammengefasst", "${out.used} sections summarised"))
                if (out.skipped > 0) append(tr(", ${out.skipped} übersprungen", ", ${out.skipped} skipped"))
                if (out.failed > 0) append(tr(", ${out.failed} fehlgeschlagen (erneut versuchen)", ", ${out.failed} failed (try again)"))
            }
            android.util.Log.i("SUMMARY", "$label: $msg; Warnungen=${out.warnings}; ${(System.currentTimeMillis() - started) / 1000} s")
            Result.success(workDataOf(MESSAGE to msg, RESULT_ID to out.id))
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Throwable) {
            android.util.Log.w("SUMMARY", tr("$label fehlgeschlagen", "$label failed"), e)
            Result.failure(workDataOf(ERROR to (if (e is OutOfMemoryError) tr("Zu wenig Arbeitsspeicher. Schließe andere Apps und versuche es erneut.", "Not enough memory. Close other apps and try again.") else e.message ?: tr("Die Zusammenfassung ist fehlgeschlagen", "The summary failed"))))
        }
    }

    companion object {
        const val DONE = "done"
        const val TOTAL = "total"
        const val ERROR = "error"
        const val MESSAGE = "message"
        const val RESULT_ID = "result"
        private const val NOTIFICATION_ID = 3
    }
}

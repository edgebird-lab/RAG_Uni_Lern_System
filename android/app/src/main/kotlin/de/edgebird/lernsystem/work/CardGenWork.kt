// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

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
import de.edgebird.lernsystem.core.ai.VectorCodec
import de.edgebird.lernsystem.core.cards.CardChunkFilter
import de.edgebird.lernsystem.core.cards.CardGenerator
import de.edgebird.lernsystem.core.cards.GenerationStats
import kotlinx.coroutines.delay
import kotlin.math.ceil

object CardGenWork {
    const val TAG = "cardgen"
    const val DOC_ID = "doc"
    const val MAX_CARDS = "max"
    const val MODE = "mode"

    /** Welche Karten erzeugt werden. */
    enum class Mode(val label: String, val hint: String) {
        QA(tr("Fragen", "Questions"), tr("Frage und Musterlösung, ca. 7 Sekunden je Karte", "Question and model answer, about 7 seconds per card")),
        CLOZE(tr("Lückentext", "Fill in the blank"), tr("Satz mit Lücke zum Ergänzen, ca. 3 Sekunden je Karte", "Sentence with a blank to fill in, about 3 seconds per card")),
        MIXED(tr("Gemischt", "Mixed"), tr("Je Abschnitt eine Frage und ein Lückentext", "One question and one fill-in-the-blank per section")),
    }

    fun enqueue(context: Context, documentId: Long, maxCards: Int, mode: Mode = Mode.QA) {
        val req = OneTimeWorkRequestBuilder<CardGenWorker>().addTag(TAG)
            .setInputData(workDataOf(DOC_ID to documentId, MAX_CARDS to maxCards, MODE to mode.name)).build()
        WorkManager.getInstance(context).enqueueUniqueWork("cardgen-$documentId-${mode.name}", ExistingWorkPolicy.KEEP, req)
    }
}

/**
 * Erzeugt Karten aus einem Dokument. Die Abschnitte werden gleichmäßig über das Dokument verteilt gewählt (breite Abdeckung
 * statt nur der ersten Seiten); bereits mit Karten versehene Abschnitte werden übersprungen.
 */
class CardGenWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val graph = (applicationContext as LernsystemApp).graph
        val docId = inputData.getLong(CardGenWork.DOC_ID, -1)
        val target = inputData.getInt(CardGenWork.MAX_CARDS, 20)
        val mode = runCatching { CardGenWork.Mode.valueOf(inputData.getString(CardGenWork.MODE).orEmpty()) }.getOrDefault(CardGenWork.Mode.QA)
        if (docId < 0) return Result.failure()
        if (!graph.llmModelFile.exists()) return Result.failure(workDataOf(ERROR to tr("Das Sprachmodell fehlt", "The language model is missing")))

        val title = tr("Karten werden erstellt", "Cards are being created")
        setForeground(ImportWork.foregroundInfo(applicationContext, tr("Starte …", "Starting …"), 0, target, title, NOTIFICATION_ID))
        val used = graph.db.cards().chunkIdsWithCards(docId).toSet()
        val usable = graph.db.chunks().byDocument(docId).filter { it.id !in used && it.text.length >= MIN_CHARS && CardChunkFilter.isStudyWorthy(it.text) }
        if (usable.isEmpty()) return Result.success(workDataOf(CREATED to 0, MESSAGE to tr("Keine passenden Abschnitte gefunden", "No suitable sections found")))

        val chunksWanted = ceil(target / PER_CHUNK.toDouble()).toInt().coerceAtMost(usable.size)
        val picked = (0 until chunksWanted).map { usable[(it * usable.size.toDouble() / chunksWanted).toInt()] }

        val embedder = if (graph.embeddingModelFile.exists()) graph.sharedEmbedder else null
        val generator = CardGenerator(graph.llm, embedder)
        val existing = graph.db.cards().questionVectorsWithText().map { VectorCodec.decode(it.questionVector) as FloatArray? to it.front }.toMutableList()
        val fronts = graph.db.cards().frontsForDocument(docId).toMutableSet()
        val stats = GenerationStats()
        var created = 0
        for ((i, chunk) in picked.withIndex()) {
            if (created >= target) break
            while (true) { // bei Hitze oder leerem Akku warten
                val reason = DeviceState.pauseReason(applicationContext) ?: break
                setForeground(ImportWork.foregroundInfo(applicationContext, if (reason == PauseReason.HOT) tr("Pausiert: Gerät ist zu warm", "Paused: device is too warm") else tr("Pausiert: Akku ist fast leer", "Paused: battery almost empty"), created, target, title, NOTIFICATION_ID))
                delay(15_000)
            }
            val cards = try {
                val left = target - created
                when (mode) {
                    CardGenWork.Mode.QA -> generator.generate(chunk.text, n = minOf(PER_CHUNK, left), existing = existing, stats = stats)
                    CardGenWork.Mode.CLOZE -> generator.generateCloze(chunk.text, n = minOf(PER_CHUNK, left), existingFronts = fronts, stats = stats)
                    CardGenWork.Mode.MIXED -> generator.generate(chunk.text, n = minOf(1, left), existing = existing, stats = stats) +
                        generator.generateCloze(chunk.text, n = minOf(1, maxOf(0, left - 1)).coerceAtLeast(if (left > 1) 1 else 0), existingFronts = fronts, stats = stats)
                }
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                return Result.failure(workDataOf(ERROR to tr("Die Erzeugung ist fehlgeschlagen: ${e.message}", "Generation failed: ${e.message}"), CREATED to created))
            }
            for (c in cards) {
                graph.study.addGenerated(docId, chunk.id, c.question, c.answer, c.questionVector, c.kind)
                c.questionVector?.let { existing += it to c.question }
                fronts += c.question
                created++
            }
            setProgressAsync(workDataOf(CREATED to created, TOTAL to target, DONE_CHUNKS to i + 1, TOTAL_CHUNKS to picked.size))
            setForegroundAsync(ImportWork.foregroundInfo(applicationContext, tr("$created von $target Karten", "$created of $target cards"), created, target, title, NOTIFICATION_ID))
        }
        val msg = tr("$created Karten erstellt", "$created cards created") + if (stats.rejectedQuestions + stats.rejectedAnswers + stats.duplicates > 0)
            tr(" (verworfen: ${stats.rejectedQuestions} Fragen, ${stats.rejectedAnswers} Antworten, ${stats.duplicates} Dubletten)", " (discarded: ${stats.rejectedQuestions} questions, ${stats.rejectedAnswers} answers, ${stats.duplicates} duplicates)") else ""
        android.util.Log.i("CARDGEN", "doc=$docId ziel=$target: $msg; Neuversuche=${stats.retries}; Abschnitte=${picked.size}")
        return Result.success(workDataOf(CREATED to created, MESSAGE to msg))
    }

    companion object {
        const val CREATED = "created"
        const val TOTAL = "total"
        const val DONE_CHUNKS = "done_chunks"
        const val TOTAL_CHUNKS = "total_chunks"
        const val ERROR = "error"
        const val MESSAGE = "message"
        private const val PER_CHUNK = 2
        private const val MIN_CHARS = 200
        private const val NOTIFICATION_ID = 2
    }
}

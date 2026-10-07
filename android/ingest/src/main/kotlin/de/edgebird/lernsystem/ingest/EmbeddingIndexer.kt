package de.edgebird.lernsystem.ingest

import de.edgebird.lernsystem.core.ai.Embedder
import de.edgebird.lernsystem.core.ai.VectorCodec
import de.edgebird.lernsystem.data.AppDatabase
import de.edgebird.lernsystem.data.DocumentStatus
import de.edgebird.lernsystem.data.EmbeddingEntity
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive

/**
 * Berechnet Embeddings für alle Chunks, die noch keines haben. Wiederaufnehmbar: jeder Batch wird sofort gespeichert,
 * ein Abbruch kostet höchstens den laufenden Batch. Dokumente werden INDEXED, sobald alle Chunks Embeddings haben.
 */
class EmbeddingIndexer(
    private val db: AppDatabase,
    private val embedder: Embedder,
    private val modelId: String,
    private val batchSize: Int = 16,
) {
    /** @return Anzahl neu berechneter Embeddings. */
    suspend fun run(onProgress: (done: Int, total: Int) -> Unit = { _, _ -> }): Int {
        val total = db.chunks().countWithoutEmbedding(modelId)
        if (total == 0) return 0
        embedder.load()
        var done = 0
        while (true) {
            currentCoroutineContext().ensureActive()
            val batch = db.chunks().withoutEmbedding(modelId, batchSize)
            if (batch.isEmpty()) break
            val vectors = embedder.embed(batch.map { it.text })
            db.embeddings().upsertAll(
                batch.zip(vectors).map { (c, v) -> EmbeddingEntity(c.id, modelId, v.size, VectorCodec.encode(v)) },
            )
            done += batch.size
            onProgress(done, total)
        }
        for (doc in db.documents().getAll().filter { it.status == DocumentStatus.PENDING }) {
            if (db.chunks().countWithoutEmbeddingForDocument(modelId, doc.id) == 0) db.documents().setStatus(doc.id, DocumentStatus.INDEXED)
        }
        return done
    }
}

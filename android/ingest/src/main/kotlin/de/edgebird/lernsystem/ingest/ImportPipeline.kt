package de.edgebird.lernsystem.ingest

import de.edgebird.lernsystem.core.ingest.ChunkDedup
import de.edgebird.lernsystem.core.ingest.Chunker
import de.edgebird.lernsystem.core.ingest.ChunkerConfig
import de.edgebird.lernsystem.core.ingest.Dedup
import de.edgebird.lernsystem.core.ingest.DedupAction
import de.edgebird.lernsystem.core.ingest.Hashing
import de.edgebird.lernsystem.core.ingest.KnownDocument
import de.edgebird.lernsystem.core.ingest.SearchText
import de.edgebird.lernsystem.data.AppDatabase
import de.edgebird.lernsystem.data.ChunkEntity
import de.edgebird.lernsystem.data.DocumentEntity
import de.edgebird.lernsystem.data.DocumentStatus
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

sealed interface ImportResult {
    /** [previousSummaryStyles]: Stile, die für die ersetzte Fassung des Dokuments existierten (werden neu berechnet). */
    data class Imported(val documentId: Long, val chunks: Int, val replaced: Boolean, val emptyPages: Int, val previousSummaryStyles: List<String> = emptyList()) : ImportResult
    data class SkippedUnchanged(val documentId: Long) : ImportResult
    data class SkippedDuplicate(val existingId: Long, val existingPath: String) : ImportResult
    data class Failed(val reason: String) : ImportResult
}

enum class ImportStage { LOADING, CHUNKING, SAVING }

/**
 * Liest eine Quelle ein: laden, Duplikate erkennen, in Chunks schneiden, speichern. Danach sind die Chunks
 * per Stichwort durchsuchbar; Embeddings entstehen getrennt (siehe [EmbeddingIndexer]) und sind wieder aufnehmbar.
 */
class ImportPipeline(
    private val db: AppDatabase,
    private val loaders: List<DocumentLoader>,
    private val chunkerConfig: ChunkerConfig = ChunkerConfig(),
    private val clock: () -> Long = System::currentTimeMillis,
) {
    suspend fun import(source: DocumentSource, onStage: (ImportStage) -> Unit = {}, subjectId: Long? = null): ImportResult = withContext(Dispatchers.IO) {
        val loader = loaders.firstOrNull { source.extension in it.extensions }
            ?: return@withContext ImportResult.Failed("Dateityp „.${source.extension}“ wird nicht unterstützt")

        onStage(ImportStage.LOADING)
        val loaded = try {
            loader.load(source)
        } catch (e: LoadException) {
            return@withContext ImportResult.Failed(e.message ?: "Datei konnte nicht gelesen werden")
        }
        if (loaded.text.isBlank()) {
            return@withContext ImportResult.Failed(
                if (loaded.emptyPages > 0) "Kein Text gefunden (gescanntes PDF? OCR folgt später)" else "Die Datei enthält keinen Text",
            )
        }

        val hash = Hashing.contentHash(loaded.text)
        val known = db.documents().getAll().map { KnownDocument(it.id, it.path, it.contentHash) }
        val decision = Dedup.decide(source.key, hash, known)
        when (decision.action) {
            DedupAction.SKIP_UNCHANGED -> return@withContext ImportResult.SkippedUnchanged(decision.existing!!.id)
            DedupAction.SKIP_DUPLICATE -> return@withContext ImportResult.SkippedDuplicate(decision.existing!!.id, decision.existing!!.path)
            DedupAction.NEW, DedupAction.REPLACE -> Unit
        }

        onStage(ImportStage.CHUNKING)
        val chunks = ChunkDedup.distinct(Chunker.chunk(loaded, chunkerConfig))
        if (chunks.isEmpty()) return@withContext ImportResult.Failed("Die Datei enthält keinen verwertbaren Text")

        onStage(ImportStage.SAVING)
        val previousStyles = decision.existing?.let { db.summaries().stylesFor(it.id) }.orEmpty()
        val docId = db.importing().replaceDocument(
            replaceId = decision.existing?.id,
            doc = DocumentEntity(
                path = source.key, title = source.displayName.substringBeforeLast('.'), filetype = source.extension,
                contentHash = hash, charCount = loaded.text.length, addedAt = clock(), status = DocumentStatus.PENDING, subjectId = subjectId ?: decision.existing?.let { db.documents().byId(it.id)?.subjectId },
            ),
        ) { id ->
            chunks.mapIndexed { i, c ->
                ChunkEntity(
                    documentId = id, idx = i, text = c.text, location = c.location, page = c.page,
                    chunkHash = Hashing.chunkHash(c.text), searchText = SearchText.prepare(c.text),
                )
            }
        }
        ImportResult.Imported(docId, chunks.size, replaced = decision.action == DedupAction.REPLACE, emptyPages = loaded.emptyPages, previousSummaryStyles = previousStyles)
    }
}

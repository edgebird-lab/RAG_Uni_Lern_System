package de.edgebird.lernsystem.ingest

import de.edgebird.lernsystem.core.i18n.tr

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
    /** [previousSummarySpecs]: Einstellungen (JSON) der Zusammenfassungen, die zur ersetzten Fassung des Dokuments existierten; sie werden mit denselben Einstellungen neu erstellt. */
    data class Imported(val documentId: Long, val chunks: Int, val replaced: Boolean, val emptyPages: Int, val previousSummarySpecs: List<String> = emptyList()) : ImportResult
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
    suspend fun import(source: DocumentSource, onStage: (ImportStage) -> Unit = {}, subjectId: Long? = null, kind: String = "FILE", folderId: Long? = null): ImportResult = withContext(Dispatchers.IO) {
        val loader = loaders.firstOrNull { source.extension in it.extensions }
            ?: return@withContext ImportResult.Failed(tr("Dateityp „.${source.extension}“ wird nicht unterstützt", "File type \".${source.extension}\" is not supported"))

        onStage(ImportStage.LOADING)
        val loaded = try {
            loader.load(source)
        } catch (e: LoadException) {
            return@withContext ImportResult.Failed(e.message ?: "Datei konnte nicht gelesen werden")
        }
        if (loaded.text.isBlank()) {
            return@withContext ImportResult.Failed(
                if (loaded.emptyPages > 0) tr("Kein Text erkannt. Bei Fotos und Scans: gerade, scharf und gut beleuchtet aufnehmen", "No text recognised. For photos and scans: shoot straight, sharp and well lit") else tr("Die Datei enthält keinen Text", "The file contains no text"),
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
        if (chunks.isEmpty()) return@withContext ImportResult.Failed(tr("Die Datei enthält keinen verwertbaren Text", "The file contains no usable text"))

        onStage(ImportStage.SAVING)
        val previous = decision.existing?.let { db.generatedSummaries().forDocument(it.id.toString()) }.orEmpty()
        previous.forEach { db.generatedSummaries().delete(it.id) }   // beziehen sich auf die alte Fassung
        val previousSpecs = previous.map { it.specJson }
        // Wird eine Quelle ersetzt, behält die neue Fassung Kapitel, Platz in der Reihenfolge und Art der alten
        val old = decision.existing?.let { db.documents().byId(it.id) }
        val targetSubject = subjectId ?: old?.subjectId
        val order = old?.sortOrder ?: ((targetSubject?.let { db.documents().maxSortOrder(it) } ?: 0) + 1)
        val docId = db.importing().replaceDocument(
            replaceId = decision.existing?.id,
            doc = DocumentEntity(
                path = source.key, title = source.displayName.substringBeforeLast('.'), filetype = source.extension,
                contentHash = hash, charCount = loaded.text.length, addedAt = clock(), status = DocumentStatus.PENDING, subjectId = targetSubject,
                folderId = old?.folderId ?: folderId, sortOrder = order, kind = old?.kind ?: kind,
            ),
        ) { id ->
            chunks.mapIndexed { i, c ->
                ChunkEntity(
                    documentId = id, idx = i, text = c.text, location = c.location, page = c.page,
                    chunkHash = Hashing.chunkHash(c.text), searchText = SearchText.prepare(c.text),
                )
            }
        }
        ImportResult.Imported(docId, chunks.size, replaced = decision.action == DedupAction.REPLACE, emptyPages = loaded.emptyPages, previousSummarySpecs = previousSpecs)
    }
}

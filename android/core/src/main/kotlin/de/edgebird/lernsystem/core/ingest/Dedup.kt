package de.edgebird.lernsystem.core.ingest

/** Bereits gespeichertes Dokument (nur die für die Entscheidung nötigen Felder). */
data class KnownDocument(val id: Long, val path: String, val contentHash: String)

enum class DedupAction {
    /** Neues Dokument: einlesen. */
    NEW,

    /** Gleicher Pfad, gleicher Inhalt: nichts tun. */
    SKIP_UNCHANGED,

    /** Gleicher Inhalt unter anderem Pfad bereits vorhanden: überspringen. */
    SKIP_DUPLICATE,

    /** Gleicher Pfad, geänderter Inhalt: alte Chunks löschen, neu einlesen. */
    REPLACE,
}

data class DedupDecision(val action: DedupAction, val existing: KnownDocument? = null)

/** Entscheidung auf Dokument-Ebene (wie `ragapp/ingestion/dedup.py` + Manifest). */
object Dedup {
    fun decide(path: String, contentHash: String, known: List<KnownDocument>): DedupDecision {
        val samePath = known.firstOrNull { it.path == path }
        if (samePath != null) {
            return if (samePath.contentHash == contentHash) DedupDecision(DedupAction.SKIP_UNCHANGED, samePath)
            else DedupDecision(DedupAction.REPLACE, samePath)
        }
        val sameContent = known.firstOrNull { it.contentHash == contentHash }
        return if (sameContent != null) DedupDecision(DedupAction.SKIP_DUPLICATE, sameContent) else DedupDecision(DedupAction.NEW)
    }
}

/** Entfernt Chunks mit identischem Inhalt (Hash über Kleinschreibung/Whitespace), z. B. wiederholte Kopf-/Fußseiten. */
object ChunkDedup {
    fun distinct(chunks: List<Chunk>): List<Chunk> {
        val seen = HashSet<String>()
        return chunks.filter { seen.add(Hashing.chunkHash(it.text)) }
    }
}

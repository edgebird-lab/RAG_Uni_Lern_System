package de.edgebird.lernsystem.core.ingest

import de.edgebird.lernsystem.core.search.SearchTokenizer

/** Aufbereitung von Chunk-Text für den FTS5-Index: gestemmte Tokens, durch Leerzeichen getrennt. */
object SearchText {
    fun prepare(text: String): String = SearchTokenizer.tokenizeAuto(text).joinToString(" ")
}

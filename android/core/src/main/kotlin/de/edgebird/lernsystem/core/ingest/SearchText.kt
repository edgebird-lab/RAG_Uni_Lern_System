package de.edgebird.lernsystem.core.ingest

import java.text.Normalizer

/** Aufbereitung von Text für den Stichwort-Index (FTS5). Phase 4 ergänzt deutsches Stemming. */
object SearchText {
    fun prepare(text: String): String = Normalizer.normalize(text, Normalizer.Form.NFC).lowercase()
}

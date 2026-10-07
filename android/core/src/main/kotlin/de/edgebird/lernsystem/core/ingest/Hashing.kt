package de.edgebird.lernsystem.core.ingest

import java.security.MessageDigest

object Hashing {
    fun sha256Hex(text: String): String =
        MessageDigest.getInstance("SHA-256").digest(text.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }

    /** Hash über den normalisierten Volltext eines Dokuments. */
    fun contentHash(text: String): String = sha256Hex(TextNormalizer.normalize(text))

    /** Whitespace- und Groß-/Kleinschreibungs-robuster Hash eines Chunks. */
    fun chunkHash(text: String): String = sha256Hex(text.lowercase().split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" "))
}

// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.cards

/** Schließt Abschnitte aus, aus denen keine sinnvollen Lernkarten entstehen (Lizenz-/Quellenköpfe, Linklisten, Zahlenwüsten). */
object CardChunkFilter {
    private val URL = Regex("https?://\\S+")
    private val SOURCE_HEADER = Regex("(?im)^>?\\s*(quelle|lizenz|license|source)\\s*:")

    fun isStudyWorthy(chunk: String): Boolean {
        val text = chunk.trim()
        if (text.isEmpty()) return false
        if ("creativecommons.org" in text || SOURCE_HEADER.containsMatchIn(text)) return false
        val urlChars = URL.findAll(text).sumOf { it.value.length }
        if (urlChars.toDouble() / text.length > 0.25) return false
        val letters = text.count { it.isLetter() }
        // Programmcode hat viele Sonderzeichen, ist aber lernenswert
        return letters.toDouble() / text.length >= (if (ContentKind.isCode(text)) 0.3 else 0.5)
    }
}

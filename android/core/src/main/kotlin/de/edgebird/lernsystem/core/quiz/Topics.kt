// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.quiz

/** Themenname eines Abschnitts: seine Überschrift, außer sie sagt nichts („Dokument“, „Seite 3“); dann zählt der Name der Quelle. */
object Topics {
    private val GENERIC = Regex("(?i)^(dokument|document|seite \\d+.*|page \\d+.*|folie \\d+.*|slide \\d+.*|abschnitt.*|section.*|kapitel \\d+|chapter \\d+)$")

    fun of(location: String, documentTitle: String): String {
        val loc = location.trim()
        val short = loc.substringAfterLast(" › ").trim().ifEmpty { loc }
        return if (loc.isEmpty() || GENERIC.matches(short)) documentTitle else short
    }
}

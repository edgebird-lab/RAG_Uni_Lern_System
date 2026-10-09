// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.summary

/** Prüfungen an Modellantworten für Zusammenfassungen (Port von `_looks_truncated`/`_is_empty_section`, plus Zahlenabgleich). */
object SummaryChecks {
    /** Wörter, auf die kein vollständiger Satz endet: Steht eines am Ende, ist die Antwort abgebrochen. */
    private val DANGLING = setOf("und", "oder", "der", "die", "das", "den", "dem", "des", "ein", "eine", "einer", "einem", "einen", "eines", "mit", "von", "zu", "zur", "zum", "in", "im", "auf", "als", "wie", "dass", "bei", "für", "aus", "nach", "durch", "sowie", "sich", "wird", "ist", "sind", "werden", "an", "am", "um", "über", "unter", "zwischen", "gegen", "ohne",
        "and", "or", "the", "a", "an", "of", "with", "to", "in", "on", "at", "as", "like", "that", "by", "for", "from", "after", "through", "between", "against", "without", "is", "are", "be", "will", "its", "their", "which", "than", "into", "over", "under")

    const val EMPTY_MARKER_DE = "(kein prüfungsrelevanter Inhalt)"
    const val EMPTY_MARKER_EN = "(no exam-relevant content)"
    val EMPTY_MARKER get() = if (de.edgebird.lernsystem.core.i18n.Lang.current == de.edgebird.lernsystem.core.i18n.Lang.EN) EMPTY_MARKER_EN else EMPTY_MARKER_DE
    private val EMPTY_MARKERS = listOf("(kein pruefungsrelevanter inhalt)", "(kein prüfungsrelevanter inhalt)", "(no exam-relevant content)", "(no exam relevant content)")

    /** Endet die Antwort mitten im Satz oder in einem leeren Listenpunkt (Token-Budget aufgebraucht)? */
    fun looksTruncated(md: String): Boolean {
        val s = md.trimEnd()
        if (s.length < 40) return false
        if (s.last() in "*-:,;(" || s.endsWith("...") || s.endsWith("…")) return true
        val last = s.lines().last().trim()
        if (last in listOf("*", "-", "•") || Regex("^[-*]\\s*$").matches(last)) return true
        if (last.startsWith("#")) return true                                   // Überschrift ohne Inhalt darunter
        if (last.length >= 25 && last.last().isLetter() && last.split(Regex("[^\\p{L}]+")).lastOrNull { it.isNotEmpty() }?.lowercase() in DANGLING) return true   // endet auf „… oder“, „… der“
        if (Regex("\\*\\*").findAll(last).count() % 2 == 1) return true      // ein geöffnetes **fett** wurde nie geschlossen
        // Ein langer letzter Satz, der mitten im Wort oder ohne Satzzeichen endet, ist fast immer am Token-Limit abgebrochen
        return last.length > 80 && s.last().isLetterOrDigit()
    }

    /**
     * Entfernt einen offensichtlich unvollständigen Schluss: ein halber Aufzählungspunkt entfällt, ein halber Satz wird
     * bis zum letzten vollständigen Satz gekürzt. Vollständige Antworten bleiben unverändert.
     */
    fun trimIncomplete(md: String, force: Boolean = false): String = trimEnd(cutEllipsisLines(md), force)

    private val SENTENCE_END = Regex("[.!?](?=\\s|$)")

    /** Absätze oder Zeilen, die mit „…“/„...“ mitten im Text abbrechen, werden bis zum letzten vollständigen Satz gekürzt. */
    private fun cutEllipsisLines(md: String): String {
        if ("..." !in md && "…" !in md) return md
        return md.lines().joinToString("\n") { line ->
            val t = line.trimEnd()
            if (!(t.endsWith("...") || t.endsWith("…"))) return@joinToString line
            val body = t.removeSuffix("...").removeSuffix("…").trimEnd()
            val end = SENTENCE_END.findAll(body).lastOrNull { it.range.last >= 20 }
            if (end != null) body.substring(0, end.range.last + 1) else body
        }
    }

    private fun trimEnd(md: String, force: Boolean = false): String {
        if (!force && !looksTruncated(md)) return md
        val lines = md.trimEnd().lines().toMutableList()
        val last = lines.last()
        val isBullet = Regex("^\\s*(?:[-*•]|\\d+[.)])\\s+").containsMatchIn(last)
        if (isBullet && lines.size > 1) { lines.removeAt(lines.lastIndex); return lines.joinToString("\n").trimEnd() }
        val end = SENTENCE_END.findAll(last.removeSuffix("...").removeSuffix("…")).lastOrNull { it.range.last >= 20 }
        return if (end != null) {
            lines[lines.lastIndex] = last.substring(0, end.range.last + 1)
            lines.joinToString("\n").trimEnd()
        } else {
            lines.removeAt(lines.lastIndex)
            lines.joinToString("\n").trimEnd().ifEmpty { md }
        }
    }

    fun isEmptySection(md: String): Boolean {
        val low = md.trim().lowercase()
        return low.isEmpty() || EMPTY_MARKERS.any { low.startsWith(it) }
    }

    private val NUMBER = Regex("\\d+(?:[.,]\\d+)*")
    private val LIST_NUMBER = Regex("(?m)^\\s*\\d+[.)]\\s+")

    /**
     * Zahlen der Zusammenfassung, die im Quelltext nicht vorkommen (Halluzinationsverdacht). Einstellige Zahlen und
     * Listenmarker zählen nicht; Tausendertrennzeichen und Dezimalkomma werden vor dem Vergleich vereinheitlicht.
     */
    fun unsupportedNumbers(summary: String, source: String): List<String> {
        fun norm(n: String) = n.replace(".", "").replace(",", ".")
        val src = NUMBER.findAll(source).map { norm(it.value) }.toSet()
        val srcText = source.replace(".", "").replace(",", ".")
        return NUMBER.findAll(LIST_NUMBER.replace(summary, "")).map { it.value }.filter { it.length >= 2 }
            .filter { norm(it) !in src && norm(it) !in srcText }.distinct().toList()
    }

    /** Räumt Reste kleiner Modelle auf: leere Fettmarker („****“), Leerzeichen vor Satzzeichen, mehrfache Leerzeichen. */
    fun tidy(md: String): String = md.replace(Regex("\\*{4,}"), "").replace(Regex("[ \\t]+([,.;:!?])"), "$1").replace(Regex("(?<=\\S)[ \\t]{2,}"), " ").trim()

    /**
     * Endet die Liste mit einem Stichpunkt ohne Satzende? Wo der Prompt ganze Sätze verlangt (Format „Stichpunkte“), ist das fast immer ein mitten im
     * Wort abgebrochener Punkt; bei „Gegliedert“ sind Punkte ohne Satzende üblich und dürfen bleiben.
     */
    fun endsWithUnterminatedBullet(md: String): Boolean {
        val last = md.trimEnd().lines().lastOrNull()?.trim().orEmpty()
        return Regex("^(?:[-*•]|\\d+[.)])\\s+").containsMatchIn(last) && last.length >= 25 && last.last() !in ".!?:;)]»”\"*_"
    }
}

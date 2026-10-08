package de.edgebird.lernsystem.core.summary

/** Prüfungen an Modellantworten für Zusammenfassungen (Port von `_looks_truncated`/`_is_empty_section`, plus Zahlenabgleich). */
object SummaryChecks {
    const val EMPTY_MARKER = "(kein prüfungsrelevanter Inhalt)"
    private val EMPTY_MARKERS = listOf("(kein pruefungsrelevanter inhalt)", "(kein prüfungsrelevanter inhalt)")

    /** Endet die Antwort mitten im Satz oder in einem leeren Listenpunkt (Token-Budget aufgebraucht)? */
    fun looksTruncated(md: String): Boolean {
        val s = md.trimEnd()
        if (s.length < 40) return false
        if (s.last() in "*-:,;(" || s.endsWith("...") || s.endsWith("…")) return true
        val last = s.lines().last().trim()
        if (last in listOf("*", "-", "•") || Regex("^[-*]\\s*$").matches(last)) return true
        if (last.startsWith("#")) return true                                   // Überschrift ohne Inhalt darunter
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
}

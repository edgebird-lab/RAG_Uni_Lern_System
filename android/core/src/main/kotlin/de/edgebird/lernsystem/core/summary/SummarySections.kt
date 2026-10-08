package de.edgebird.lernsystem.core.summary

/** Ein zusammenzufassender Abschnitt: Titel (Fundstelle) und Text. */
data class SummarySection(val title: String, val text: String)

/** Eingabe: ein Abschnitt (Chunk) des Dokuments in Lesereihenfolge. */
data class SourcePiece(val location: String, val text: String)

/**
 * Baut aus den Chunks eines Dokuments sinnvolle Abschnitte für je einen Modellaufruf (Port von `_sections_from_chunks`):
 * aufeinanderfolgende Chunks mit gleicher Fundstelle werden bis zum Zeichenbudget zusammengefasst, die vom Chunker
 * eingefügte Überlappung wird entfernt, und sehr kurze Nachbarn werden vereinigt (z. B. „Seite 3–4“).
 */
object SummarySections {
    const val DEFAULT_BUDGET = 3000
    private const val MERGE_BELOW = 700

    private val HEADER_PREFIX = Regex("^\\[[^\\]]{0,160}]\\n")

    fun build(pieces: List<SourcePiece>, budget: Int = DEFAULT_BUDGET, overlap: Int = 150): List<SummarySection> {
        val groups = mutableListOf<MutableList<SourcePiece>>()
        for (p in pieces) {
            val text = HEADER_PREFIX.replace(p.text, "").trim()
            if (text.isEmpty()) continue
            val piece = p.copy(text = text)
            val last = groups.lastOrNull()
            if (last != null && last.first().location == piece.location && last.sumOf { it.text.length } + piece.text.length <= budget) last += piece
            else groups += mutableListOf(piece)
        }
        val sections = groups.map { g -> SummarySection(g.first().location, joinWithoutOverlap(g.map { it.text }, overlap)) }
        return mergeSmall(sections, budget)
    }

    /** Fügt Texte aneinander und schneidet die vom Chunker vorangestellte Überlappung (letzte Zeichen des Vorgängers) ab. */
    internal fun joinWithoutOverlap(texts: List<String>, maxOverlap: Int): String {
        val sb = StringBuilder()
        for (t in texts) {
            if (sb.isEmpty()) { sb.append(t); continue }
            var cut = 0
            for (k in minOf(sb.length, maxOverlap + 40) downTo 30) {
                if (t.startsWith(sb.substring(sb.length - k) + " ")) { cut = k + 1; break }
            }
            sb.append("\n\n").append(t.substring(cut).trim())
        }
        return sb.toString().trim()
    }

    private fun mergeSmall(sections: List<SummarySection>, budget: Int): List<SummarySection> {
        val out = mutableListOf<SummarySection>()
        for (s in sections) {
            val last = out.lastOrNull()
            if (last != null && last.text.length < MERGE_BELOW && last.text.length + s.text.length <= budget) {
                out[out.lastIndex] = SummarySection(mergeTitles(last.title, s.title), last.text + "\n\n" + s.text)
            } else out += s
        }
        return out
    }

    private val PAGE = Regex("^(Seite|Folie) (\\d+)(?:–(\\d+))?$")

    internal fun mergeTitles(a: String, b: String): String {
        val ma = PAGE.matchEntire(a)
        val mb = PAGE.matchEntire(b)
        if (ma != null && mb != null && ma.groupValues[1] == mb.groupValues[1]) {
            return "${ma.groupValues[1]} ${ma.groupValues[2]}–${mb.groupValues[3].ifEmpty { mb.groupValues[2] }}"
        }
        return if (a == b) a else "$a / $b"
    }
}

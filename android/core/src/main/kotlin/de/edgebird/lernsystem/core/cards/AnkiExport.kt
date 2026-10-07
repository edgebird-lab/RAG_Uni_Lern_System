package de.edgebird.lernsystem.core.cards

/** Export als Text für den Anki-Import (Tab-getrennt: Vorderseite, Rückseite, Tags). */
object AnkiExport {
    data class Row(val front: String, val answer: String, val tag: String?)

    private fun field(s: String) = s.trim().replace("\t", " ").replace("\r\n", "\n").replace("\n", "<br>")

    private fun tag(t: String?) = t?.trim()?.replace(Regex("\\s+"), "_").orEmpty()

    /** Eine Zeile je Karte; LaTeX wird für Anki als `\( … \)` ausgezeichnet, damit es dort gerendert wird. */
    fun toTsv(rows: List<Row>): String =
        rows.joinToString("\n", postfix = if (rows.isEmpty()) "" else "\n") { "${field(latexForAnki(it.front))}\t${field(latexForAnki(it.answer))}\t${tag(it.tag)}" }

    private fun latexForAnki(text: String): String =
        Regex("\\$\\$(.+?)\\$\\$", RegexOption.DOT_MATCHES_ALL).replace(text) { "\\[" + it.groupValues[1] + "\\]" }
            .let { Regex("\\$(.+?)\\$").replace(it) { m -> "\\(" + m.groupValues[1] + "\\)" } }
}

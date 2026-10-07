package de.edgebird.lernsystem.core.rag

/** Liest Quellenverweise wie „[2]“ oder „[1, 3]“ aus einer Modellantwort. */
object Citations {
    private val GROUP = Regex("""\[(\d+(?:\s*,\s*\d+)*)]""")

    /** @return die zitierten Quellennummern (1-basiert), die zwischen 1 und [sourceCount] liegen. */
    fun cited(answer: String, sourceCount: Int): Set<Int> =
        GROUP.findAll(answer).flatMap { it.groupValues[1].split(",").map { n -> n.trim().toInt() } }
            .filter { it in 1..sourceCount }.toSortedSet()

    /** Erkennt die Verweigerungsformel (auch mit Zusatz oder leicht abweichender Schreibweise). */
    fun isNotFound(answer: String): Boolean =
        answer.lowercase().replace(Regex("\\s+"), " ").contains("nicht im material gefunden")

    /**
     * Rückfrage-Erkennung für die Suche: Kurze Fragen („Und wer ernennt ihn?“) tragen ihren Bezug nicht in sich,
     * deshalb wird die vorige Frage für die Suche vorangestellt.
     */
    fun retrievalQuery(question: String, previousQuestion: String?, shortWords: Int = 6): String {
        val words = question.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }
        return if (previousQuestion != null && words.size < shortWords) "$previousQuestion $question" else question
    }
}

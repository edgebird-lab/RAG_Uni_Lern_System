package de.edgebird.lernsystem.core.search

import java.text.Normalizer

/** Zerlegt Text für die Stichwortsuche: Kleinschreibung, Stoppwörter raus, Snowball-Stemming (wie `tokenize` der PC-App). */
object SearchTokenizer {
    private val TOKEN = Regex("[A-Za-zÀ-ÿ0-9]+")

    private val STOPWORDS = setOf(
        "der", "die", "das", "und", "oder", "aber", "wenn", "dann", "als", "auch",
        "an", "auf", "aus", "bei", "bis", "durch", "für", "gegen", "in", "mit",
        "nach", "über", "um", "unter", "vom", "von", "vor", "zu", "zum", "zur",
        "ein", "eine", "einer", "eines", "einem", "einen", "ist", "sind", "war",
        "waren", "sein", "wird", "werden", "wurde", "wurden", "hat", "haben",
        "hatte", "kann", "können", "muss", "müssen", "soll", "sollen", "wie",
        "was", "wer", "wo", "warum", "dass", "es", "sie", "er", "wir", "ihr",
        "man", "sich", "nicht", "kein", "keine", "nur", "so", "im", "am", "dem",
        "den", "des", "diese", "dieser", "dieses", "welche", "welcher",
        // Englisch (Unterlagen und Fragen können englisch sein); der Stemmer bleibt deutsch, damit der Index sprachunabhängig stimmig bleibt
        "the", "of", "and", "to", "is", "are", "was", "were", "be", "been", "what", "which", "how", "does", "do", "did", "with", "for", "that",
        "this", "these", "those", "from", "by", "on", "at", "as", "it", "its", "or", "but", "if", "then", "than", "can", "could", "should",
        "would", "will", "has", "have", "had", "not", "no", "there", "their", "they", "you", "your", "we", "who", "when", "where", "why",
    )

    fun tokenize(text: String): List<String> =
        TOKEN.findAll(Normalizer.normalize(text, Normalizer.Form.NFC)).map { it.value.lowercase() }
            .filter { it !in STOPWORDS && it.length > 1 }
            .map { GermanStemmer.stem(it) }
            .toList()
}

/** Baut aus einer Frage eine FTS5-Abfrage (ODER über die Stämme); `null`, wenn nichts Suchbares übrig bleibt. */
object FtsQuery {
    fun fromQuestion(question: String): String? {
        val tokens = SearchTokenizer.tokenize(question).distinct()
        if (tokens.isEmpty()) return null
        return tokens.joinToString(" OR ") { "\"$it\"" }
    }
}

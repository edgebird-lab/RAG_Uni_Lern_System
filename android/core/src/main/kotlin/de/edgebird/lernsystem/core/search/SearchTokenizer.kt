// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.search

import de.edgebird.lernsystem.core.i18n.Lang
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

    private val GERMAN_HINTS = setOf("der", "die", "das", "und", "ist", "nicht", "mit", "von", "zu", "den", "dem", "ein", "eine", "auf", "für", "als", "auch", "sich", "werden", "wird", "sind", "oder", "bei", "nach", "aus", "über")
    private val ENGLISH_HINTS = setOf("the", "of", "and", "to", "is", "are", "that", "with", "for", "this", "from", "by", "as", "it", "which", "in", "on", "be", "can", "or", "an", "at", "not", "has", "have")

    /** Rät die Sprache eines Textes an Funktionswörtern; bei Gleichstand oder zu wenig Text gilt Deutsch (wie bisher). */
    fun guessLanguage(text: String): Lang {
        var de = 0; var en = 0
        for (m in TOKEN.findAll(text)) { val t = m.value.lowercase(); if (t in GERMAN_HINTS) de++; if (t in ENGLISH_HINTS) en++ }
        return if (en > de * 1.2 && en >= 2) Lang.EN else Lang.DE
    }

    private fun stem(token: String, lang: Lang) = if (lang == Lang.EN) EnglishStemmer.stem(token) else GermanStemmer.stem(token)

    /** Zerlegt [text] und stemmt je nach [lang] (Standard: Deutsch, wie in der PC-App). */
    fun tokenize(text: String, lang: Lang = Lang.DE): List<String> =
        TOKEN.findAll(Normalizer.normalize(text, Normalizer.Form.NFC)).map { it.value.lowercase() }
            .filter { it !in STOPWORDS && it.length > 1 }
            .map { stem(it, lang) }
            .toList()

    /** Für den Index: Stemmer nach der erkannten Sprache des Textes. */
    fun tokenizeAuto(text: String): List<String> = tokenize(text, guessLanguage(text))
}

/** Baut aus einer Frage eine FTS5-Abfrage (ODER über die Stämme); `null`, wenn nichts Suchbares übrig bleibt. */
object FtsQuery {
    fun fromQuestion(question: String): String? {
        // Der Index enthält je Text die Stämme seiner Sprache; die Frage wird in beiden Sprachen gestemmt, damit deutsche und englische Quellen treffen
        val tokens = (SearchTokenizer.tokenize(question, Lang.DE) + SearchTokenizer.tokenize(question, Lang.EN)).distinct()
        if (tokens.isEmpty()) return null
        return tokens.joinToString(" OR ") { "\"$it\"" }
    }
}

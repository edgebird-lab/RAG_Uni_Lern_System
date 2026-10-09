// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.cards

import com.google.gson.JsonParser
import de.edgebird.lernsystem.core.i18n.Lang
import de.edgebird.lernsystem.core.i18n.tr

/** Art einer Karte. */
enum class CardKind {
    QA, CLOZE;

    val label: String get() = when (this) { QA -> tr("Frage", "Question"); CLOZE -> tr("Lückentext", "Fill in the blank") }
}

/**
 * Lückentext-Karten: Das Modell wählt Sätze aus dem Abschnitt und je einen Schlüsselbegriff; der CODE baut die Karte und prüft,
 * dass Satz und Begriff wirklich im Quelltext stehen (das Modell kann so nichts erfinden).
 */
object Cloze {
    const val BLANK = "[…]"

    fun prompt(chunk: String, n: Int, lang: Lang = Lang.current): String = if (lang == Lang.EN) promptEn(chunk, n) else """Lies den folgenden Abschnitt aus einer Zusammenfassung.

Wähle genau $n wichtige, prüfungsrelevante Sätze aus. Je Satz wählst du EINEN Schlüsselbegriff (eine Fachbezeichnung, eine Zahl oder einen Formelteil), den man auswendig wissen muss und der im Satz gelöscht werden soll. Regeln:
- Der Satz muss WÖRTLICH aus dem Abschnitt kopiert sein (nichts umformulieren, nichts kürzen).
- Der Schlüsselbegriff muss WÖRTLICH im Satz stehen (1 bis 4 Wörter).
- Der Satz muss auch ohne den Abschnitt verständlich sein (kein „dieser“, „oben“, „Abbildung 2“).
- Wähle verschiedene Sätze mit verschiedenen Begriffen; keine Überschriften, keine Quellenangaben.

Abschnitt:
${"\"\"\""}
${chunk.take(2500)}
${"\"\"\""}

Gib NUR gültiges JSON in diesem Format zurück:
{"cloze": [{"satz": "...", "luecke": "..."}]}"""

    private fun promptEn(chunk: String, n: Int): String = """Read the following passage from a study summary.

Choose exactly $n important, exam-relevant sentences. For each sentence choose ONE key term (a technical term, a number or part of a formula) that must be memorised and that will be deleted from the sentence. Rules:
- The sentence must be copied VERBATIM from the passage (do not rephrase or shorten anything).
- The key term must appear VERBATIM in the sentence (1 to 4 words).
- The sentence must be understandable without the passage (no "this", "above", "Figure 2").
- Choose different sentences with different terms; no headings, no source notes.

Passage:
${"\"\"\""}
${chunk.take(2500)}
${"\"\"\""}

Return ONLY valid JSON in this format (keep the German key names):
{"cloze": [{"satz": "...", "luecke": "..."}]}"""

    data class Item(val sentence: String, val term: String)

    fun parse(raw: String): List<Item> {
        val start = raw.indexOf('{'); val end = raw.lastIndexOf('}')
        if (start < 0 || end <= start) return emptyList()
        return try {
            val arr = JsonParser.parseString(raw.substring(start, end + 1)).asJsonObject.getAsJsonArray("cloze") ?: return emptyList()
            arr.mapNotNull { e ->
                val o = e.takeIf { it.isJsonObject }?.asJsonObject ?: return@mapNotNull null
                val s = o.get("satz")?.takeIf { it.isJsonPrimitive }?.asString?.trim()
                val t = o.get("luecke")?.takeIf { it.isJsonPrimitive }?.asString?.trim()
                if (s.isNullOrEmpty() || t.isNullOrEmpty()) null else Item(s, t)
            }
        } catch (e: Exception) { emptyList() }
    }

    private fun norm(s: String) = s.lowercase().replace(Regex("""\s+"""), " ").trim()

    /** Fertige Karte: [front] mit Lücke, [answer] mit dem Begriff und dem vollständigen Satz. */
    data class Built(val front: String, val answer: String)

    private val STOPWORDS = setOf("der", "die", "das", "den", "dem", "des", "ein", "eine", "einer", "und", "oder", "ist", "sind", "wird", "werden", "von", "mit", "für", "zu", "im", "in", "an", "auf", "the", "a", "an", "and", "or", "is", "are", "of", "with", "for", "to", "on", "at", "by")

    /** `null`, wenn der Eintrag nicht taugt (nicht im Text, Begriff zu kurz oder Füllwort, Satz zu kurz oder zu lang, Quellenbezug). */
    fun build(item: Item, chunk: String): Built? {
        val sentence = item.sentence.trim().trimEnd()
        val term = item.term.trim().trim('.', ',', ';', ':', '"', '„', '“')
        if (sentence.length !in 30..320 || term.length !in 2..48 || term.split(" ").size > 4) return null
        if (norm(sentence) !in norm(chunk)) return null                       // Satz muss im Quelltext stehen
        val at = sentence.indexOf(term, ignoreCase = true)
        if (at < 0 || norm(term) in STOPWORDS || norm(term) == norm(sentence)) return null
        val blanked = sentence.replace(Regex(Regex.escape(term), RegexOption.IGNORE_CASE), BLANK)
        if (blanked.split(Regex("""\s+""")).count { it.length > 2 && BLANK !in it } < 5) return null      // genug Kontext übrig
        if (CardQuality.questionProblems(sentence).any { it == CardProblem.SOURCE_REFERENCE || it == CardProblem.GARBLED || it == CardProblem.CONTEXT }) return null
        val shown = sentence.replace(Regex(Regex.escape(term), RegexOption.IGNORE_CASE)) { "**${it.value}**" }
        return Built(tr("Ergänze die Lücke:", "Fill in the blank:") + "\n$blanked", "**${sentence.substring(at, at + term.length)}**\n\n$shown")
    }
}

/** Erkennt Quelltext (Programmcode) in einem Abschnitt, damit dafür passende Fragen gestellt werden. */
object ContentKind {
    private val CODE_LINE = Regex("""^\s*(?:[{}();]|(?:def|fun|func|function|class|public|private|static|void|int|double|float|char|bool|boolean|var|val|let|const|return|if|else|for|while|import|include|#include|package|print\w*|System\.out)\b|[\w.\[\]]+\s*(?:=|\+=|-=|==|->|=>)\s*\S|.*[;{}]\s*$|//|#\s|/\*|\*/)""")

    fun isCode(chunk: String): Boolean {
        if ("```" in chunk) return true
        val lines = chunk.lines().filter { it.isNotBlank() }
        if (lines.size < 3) return false
        return lines.count { CODE_LINE.containsMatchIn(it) }.toDouble() / lines.size >= 0.45
    }
}

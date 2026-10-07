package de.edgebird.lernsystem.core.cards

import com.google.gson.JsonParser

/** Prompts und Auswertung der Kartenerzeugung (Port von `ragapp/ingestion/question_gen.py`, zweistufig: Fragen, dann Antworten). */
object CardPrompts {
    const val QUESTION_SYSTEM = "Du bist ein erfahrener Prüfungs-Coach an einer deutschen Hochschule. Du formulierst knappe, eigenständige Klausur-/Verständnisfragen auf Deutsch."
    const val ANSWER_SYSTEM = "Du bist ein präziser Tutor an einer deutschen Hochschule. Du beantwortest Prüfungsfragen kurz, korrekt und nur mit dem gegebenen Stoff."
    const val NOT_IN_TEXT = "NICHT_IM_TEXT"

    private const val MAX_CHUNK_CHARS_QUESTION = 2500
    private const val MAX_CHUNK_CHARS_ANSWER = 2800

    fun questionPrompt(chunk: String, n: Int): String = """Lies den folgenden Abschnitt aus einer Klausur-Zusammenfassung.

Formuliere genau $n verschiedene, eigenständige Fragen auf Deutsch, die
AUSSCHLIESSLICH mit den Informationen aus DIESEM Abschnitt beantwortet werden
können. Regeln:
- Jede Frage muss allein aus dem Abschnitt beantwortbar sein (kein Zusatzwissen).
- Verschiedene Aspekte abdecken (Definition, Berechnung, Beispiel, Abgrenzung).
- Natürliche Prüfungssprache, so wie ein Studierender fragen würde.
- Keine Verweise wie "laut Abschnitt" oder "im Text".
- Nicht die Überschrift umformulieren ("Was ist …?" mit dem Abschnittstitel).
  Frage nach einem prüfungsrelevanten Aspekt: Definition in eigenen Worten,
  Berechnung, Abgrenzung, Beispiel, Anwendung.
- Formeln und Gleichungen als LaTeX mit einfachem Backslash, in ${'$'}...${'$'} (inline)
  oder ${'$'}${'$'}...${'$'}${'$'} (abgesetzt). Keine Unicode-Brüche.

Abschnitt:
${"\"\"\""}
${chunk.take(MAX_CHUNK_CHARS_QUESTION)}
${"\"\"\""}

Gib NUR gültiges JSON in diesem Format zurück:
{"questions": ["...", "..."]}"""

    fun answerPrompt(question: String, chunk: String): String = """Beantworte die folgende Prüfungsfrage AUSSCHLIESSLICH mit den
Informationen aus dem gegebenen Abschnitt. Schreibe eine klare, vollständige
Musterlösung auf Deutsch (2–6 Sätze; bei Rechnungen die Schritte). Formeln in
LaTeX (z. B. ${'$'}\frac{a}{b}${'$'}). Kein Vorspann wie „Antwort:", keine Verweise auf
„den Abschnitt". Steht die Antwort nicht im Abschnitt, schreibe nur: $NOT_IN_TEXT

Frage:
${question.trim()}

Abschnitt:
${"\"\"\""}
${chunk.take(MAX_CHUNK_CHARS_ANSWER)}
${"\"\"\""}

Musterlösung:"""

    private val IMPERATIVES = listOf(
        "nenne", "erklär", "erklaer", "berechne", "beschreib", "definier", "begründe", "begruende", "leite", "zeige",
        "bestimme", "skizzier", "vergleich", "unterscheide", "ordne", "analysier", "diskutier", "gib ",
        "berechnen sie", "nennen sie", "erklären sie", "erklaeren sie", "beschreiben sie", "bestimmen sie", "geben sie", "leiten sie",
    )

    /** Auch Aufforderungen („Berechnen Sie …“) sind gültige Prüfungsfragen, nicht nur Sätze mit Fragezeichen. */
    fun isQuestion(q: String): Boolean {
        if (q.length < 10) return false
        if ('?' in q) return true
        val low = q.lowercase()
        return IMPERATIVES.any { low.startsWith(it) }
    }

    private val ECHO_FILLER = setOf(
        "was", "ist", "sind", "der", "die", "das", "ein", "eine", "einer", "eines", "und", "oder", "wie", "wird", "werden",
        "bitte", "nenne", "erklären", "erklaeren", "erklär", "erklaer", "sie", "den", "dem", "im", "in", "zu", "zur", "zum",
        "von", "vom", "über", "ueber", "genau", "kurz", "sich",
    )

    private fun normalizeQuestion(text: String) =
        text.trim().lowercase().replace(Regex("[^\\p{L}\\p{N}_äöüß]+"), " ").trim().split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")

    private fun chunkHeading(chunk: String): String {
        val first = chunk.lines().firstOrNull { it.isNotBlank() }?.trim().orEmpty()
        return first.trimStart('#').trim()
    }

    /** Nur die Überschrift umformuliert („Was ist X?“ zu einem Abschnitt „X“)? */
    fun isHeadingEcho(question: String, chunk: String): Boolean {
        val hn = normalizeQuestion(chunkHeading(chunk))
        val qn = normalizeQuestion(question)
        if (hn.length < 6 || qn.isEmpty()) return false
        val hContent = hn.split(" ").filter { it !in ECHO_FILLER }
        val qContent = qn.split(" ").filter { it !in ECHO_FILLER }
        if (hContent.isEmpty()) return false
        if (qContent == hContent) return true
        return hn in qn && qContent.size <= hContent.size + 1
    }

    /** Vorspann-/Codefence-Reste entfernen; leer bei leerer Antwort oder [NOT_IN_TEXT]. */
    fun cleanAnswer(raw: String): String {
        var ans = raw.trim()
        if (ans.startsWith("```")) ans = ans.trim('`').substringAfter('\n', ans).trim()
        for (pref in listOf("Antwort:", "Musterlösung:", "Lösung:")) {
            if (ans.lowercase().startsWith(pref.lowercase())) ans = ans.substring(pref.length).trim()
        }
        if (ans.isEmpty() || NOT_IN_TEXT in ans) return ""
        return ans
    }

    /** Liest `{"questions": [...]}` aus einer Modellantwort; toleriert Text und Codefences drumherum. Leer bei Fehlern. */
    fun parseQuestions(raw: String): List<String> {
        val start = raw.indexOf('{')
        val end = raw.lastIndexOf('}')
        if (start < 0 || end <= start) return emptyList()
        return try {
            val obj = JsonParser.parseString(raw.substring(start, end + 1)).asJsonObject
            obj.getAsJsonArray("questions")?.mapNotNull { e -> if (e.isJsonPrimitive && e.asJsonPrimitive.isString) e.asString.trim() else null }.orEmpty()
        } catch (e: Exception) {
            emptyList()
        }
    }
}

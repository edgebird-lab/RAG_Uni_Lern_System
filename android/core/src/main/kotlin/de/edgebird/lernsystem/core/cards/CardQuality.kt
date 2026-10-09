// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.cards

import de.edgebird.lernsystem.core.ai.VectorCodec
import de.edgebird.lernsystem.core.i18n.tr

/**
 * Qualitätsprüfung für Karteikarten (Port von `ragapp/card_quality.py`): Frage und Antwort müssen OHNE das Dokument
 * verständlich sein. Regelbasiert und offline; nur die Duplikat-Erkennung nutzt Embeddings des Aufrufers.
 */
enum class CardProblem(val code: String) {
    SOURCE_REFERENCE("quellenbezug"), GARBLED("unleserlich"), CONTEXT("kontext"), VAGUE("vage"), CIRCULAR("zirkulaer"), DUPLICATE("duplikat");

    val label: String get() = when (this) {
        SOURCE_REFERENCE -> tr("verweist auf die Quelle (Abschnitt, Abbildung, Definition N …)", "refers to the source (section, figure, definition N …)")
        GARBLED -> tr("enthält kaputte PDF-Zeichen", "contains broken PDF characters")
        CONTEXT -> tr("hängt von fehlendem Kontext ab (Abbildung, Beweisschritt, „diese …“)", "depends on missing context (figure, proof step, \"this …\")")
        VAGUE -> tr("zu unbestimmt", "too vague")
        CIRCULAR -> tr("Antwort wiederholt nur die Frage", "the answer just repeats the question")
        DUPLICATE -> tr("doppelt (fast dieselbe Frage gibt es schon)", "duplicate (almost the same question exists)")
    }
}

object CardQuality {
    /**
     * Kosinus-Ähnlichkeit, ab der zwei Fragen als Dublette gelten. An EmbeddingGemma 2 gemessen (15 echte Paraphrasen: 0,947 bis 0,991;
     * 25 verwandte, aber verschiedene Fragen: 0,72 bis 0,975): 0,89 hätte 16 von 25 verschiedenen Fragen verworfen, 0,955 nur 4.
     */
    const val DUP_THRESHOLD = 0.955

    /**
     * Groß-/Kleinschreibung ignorieren, Wörter und Wortgrenzen Unicode-weit. Die JVM braucht dafür das Flag `U`,
     * Androids ICU-Regex kennt es nicht (wirft eine Ausnahme), ist aber ohnehin Unicode-fähig.
     */
    private fun rx(p: String): Regex = try {
        Regex("(?iU)$p")
    } catch (e: java.util.regex.PatternSyntaxException) {
        Regex("(?i)$p")
    }

    private const val FIG = "abbildung|abb\\.|bild|grafik|diagramm|skizze|zeichnung|tabelle|tab\\.|folie|slide|seite|kapitel|abschnitt|aufgabe|beispiel|übung|uebung|figure|fig\\.|picture|graphic|sketch|drawing|table|page|chapter|section|exercise|example"
    private val NUMBERED_FIG = rx("\\b(?:$FIG)\\s*\\d+(?:\\.\\d+)*\\b")
    private val NUMBERED_THEOREM = rx("\\b(?:satz|definition|lemma|korollar|theorem|proposition|bemerkung|axiom|corollary|remark)\\s+\\d+(?:\\.\\d+)*\\b")
    private val NUMBERED_EQ = rx("\\b(?:formel|gleichung|ungleichung|gl\\.|formula|equation|inequality|eq\\.)\\s*\\(\\s*\\d+(?:\\.\\d+)*\\s*\\)")
    private val SOURCE_PHRASE = rx(
        "\\b(?:im|in diesem|in dem|im folgenden|im obigen|im vorliegenden|im gegebenen|im genannten|im betrachteten)\\s+" +
            "(?:abschnitt|text|skript|dokument|kapitel|beispiel|bild|textabschnitt|auszug)\\b" +
            "|\\b(?:laut|gemäß|gemaess|siehe|nach)\\s+(?:dem\\s+|der\\s+|den\\s+)?" +
            "(?:text|skript|vorlesung|folie|abschnitt|abbildung|aufgabe|beispiel|unterlagen)\\b" +
            "|\\b(?:in|auf)\\s+(?:der|dieser|folgender|obiger)\\s+(?:abbildung|grafik|skizze|tabelle|folie|zeichnung|darstellung)\\b" +
            "|\\b(?:oben|unten)\\s+(?:genannt|stehend|beschrieben|angegeben|gezeigt|erwähnt|abgebildet|dargestellt)\\w*" +
            "|\\b(?:obige|obigen|obiger|obiges|untenstehende\\w*|obenstehende\\w*)\\b" +
            "|\\b(?:dargestellt|abgebildet|gezeigt|beschrieben|erwähnt|genannt)\\s+(?:im|in der|in dem|auf der)\\b" +
            "|\\b(?:in|according to|see|as (?:shown|described|stated) in)\\s+(?:the\\s+)?(?:(?:following|above|given|present|this|preceding)\\s+)?(?:section|text|script|document|chapter|example|figure|excerpt|passage|lecture|slide|exercise|table|materials?)\\b" +
            "|\\b(?:above|below)[- ](?:mentioned|described|shown|given|listed)\\b|\\b(?:aforementioned|the above|the following)\\s+(?:figure|sketch|graphic|table|diagram|slide)\\b",
    )

    /** U+239B–23B3 Klammerbausteine, U+23D0, Private-Use U+E000–F8FF, U+FFFD, U+20D7 (Vektorpfeil) und Steuerzeichen. */
    private val GARBLED_RX = Regex("[⎛-⎳⏐-�⃗\u0000-\u0008\u000B\u000C\u000E-\u001F]")

    private const val DEICTIC_NOUNS = "abbildung|grafik|skizze|tabelle|formel|gleichung|aufgabe|beispiel|zeichnung|darstellung|schritt|umformung|rechnung|herleitung|figure|graphic|sketch|table|formula|equation|exercise|example|drawing|step|derivation|calculation|transformation"
    private val DEICTIC = rx("\\b(?:diese[rnms]?|this|these|that|those)\\s+($DEICTIC_NOUNS)s?\\b")
    private val CONTEXT_RX = rx(
        "\\bin\\s+diesem\\s+(?:kontext|zusammenhang|fall|schritt|beispiel|abschnitt|kapitel|text)\\b" +
            "|\\bangegeben\\w*" +
            "|\\bgegebene[nrsm]?\\s+(?:abbildung|skizze|figur|aufgabe|zeichnung|grafik|tabelle|text|beispiel)\\b" +
            "|\\bbetrachtete[nrsm]?\\b" +
            "|,\\s*(?:die|der|das|den|dem|welche[rnms]?)\\b[^?,;]*\\b(?:bewiesen|gezeigt|hergeleitet|abgeleitet|erhalten|ermittelt)\\s+(?:wird|werden)\\b" +
            "|\\b(?:wie|was)\\s+(?:oben|unten|zuvor|vorher)\\b" +
            "|\\bin\\s+this\\s+(?:context|case|step|example|section|chapter|text)\\b|\\bgiven\\s+(?:figure|sketch|exercise|drawing|graphic|table|text|example)\\b|\\b(?:as|what)\\s+(?:above|below|before|previously)\\b|\\bconsidered\\b",
    )

    private val WORD = Regex("[a-zäöüß]{4,}")
    private val STOP = setOf(
        "wird", "werden", "sind", "wurde", "wurden", "sein", "welche", "welcher", "welches",
        "welchen", "welchem", "diese", "dieser", "dieses", "diesen", "diesem", "nenne", "nennen",
        "erkläre", "erklären", "erklaere", "erklaeren", "beschreibe", "beschreiben", "definiere",
        "definieren", "berechne", "berechnen", "bestimme", "bestimmen", "gibt", "gebe", "geben",
        "lautet", "lauten", "heißt", "heisst", "versteht", "dass", "wenn", "dann", "auch", "noch",
        "eine", "einer", "eines", "einem", "einen", "oder", "sich", "nicht", "kann", "können",
        "koennen", "wieso", "warum", "weshalb", "wozu", "wann", "dies", "dazu", "dabei", "damit",
        "dafür", "dafuer", "durch", "für", "fuer", "mit", "von", "vom", "zum", "zur", "über",
        "ueber", "unter", "nach", "bei", "aus", "wie", "was", "wer", "wo",
        "funktioniert", "funktionieren", "kurz", "genau", "bedeutet", "bedeuten", "gilt", "gelten",
        "passiert", "geschieht", "ergibt", "ergeben", "macht", "machen", "stimmt", "erklärt",
        "erklaert", "sagen", "sagt", "meint", "meinen", "bitte", "einfach", "etwas", "alles",
        "ganz", "mehr", "sehr",
        "what", "which", "that", "this", "these", "those", "with", "from", "does", "have", "been", "were", "will", "would", "should", "could",
        "explain", "describe", "define", "calculate", "determine", "name", "state", "give", "mean", "means", "work", "works", "when", "where",
        "why", "how", "also", "into", "than", "then", "there", "their", "they", "your", "about", "between", "briefly", "simply", "exactly",
    )
    private val MATH = Regex("[$=<>≤≥≈∑∫√±^_\\\\]|\\p{Nd}")

    private fun contentWords(text: String) = WORD.findAll(text.lowercase()).map { it.value }.filter { it !in STOP }.toList()
    private fun hasMath(text: String) = MATH.containsMatchIn(text)

    private fun sourceReference(t: String) =
        NUMBERED_FIG.containsMatchIn(t) || NUMBERED_THEOREM.containsMatchIn(t) || NUMBERED_EQ.containsMatchIn(t) || SOURCE_PHRASE.containsMatchIn(t)

    private fun lacksContext(question: String): Boolean {
        if (CONTEXT_RX.containsMatchIn(question)) return true
        val low = question.lowercase()
        for (m in DEICTIC.findAll(question)) {
            // „diese Formel“ ist in Ordnung, wenn die Frage die Formel vorher selbst nennt.
            if (m.groupValues[1].lowercase() !in low.substring(0, m.range.first)) return true
        }
        return false
    }

    fun questionProblems(question: String): List<CardProblem> {
        val q = question.trim()
        if (q.isEmpty()) return listOf(CardProblem.VAGUE)
        val out = mutableListOf<CardProblem>()
        if (sourceReference(q)) out += CardProblem.SOURCE_REFERENCE
        if (GARBLED_RX.containsMatchIn(q)) out += CardProblem.GARBLED
        if (lacksContext(q)) out += CardProblem.CONTEXT
        if (contentWords(q).isEmpty() && !hasMath(q)) out += CardProblem.VAGUE
        return out
    }

    fun answerProblems(answer: String, question: String = ""): List<CardProblem> {
        val a = answer.trim()
        if (a.isEmpty()) return emptyList()
        val out = mutableListOf<CardProblem>()
        if (sourceReference(a)) out += CardProblem.SOURCE_REFERENCE
        if (GARBLED_RX.containsMatchIn(a)) out += CardProblem.GARBLED
        if (question.isNotEmpty() && !hasMath(a)) {
            val aWords = contentWords(a)
            if (aWords.size >= 3) {
                val qStems = contentWords(question).map { it.take(5) }.toSet()
                val new = aWords.count { it.take(5) !in qStems }
                if (new.toDouble() / aWords.size <= 0.15) out += CardProblem.CIRCULAR
            }
        }
        return out
    }

    private fun retryHint(p: CardProblem): String? = when (p) {
        CardProblem.SOURCE_REFERENCE -> tr("Keine Verweise auf Abschnitte, Abbildungen, Seiten, Formel- oder Definitionsnummern (z. B. „im Abschnitt“, „Abbildung 2“, „Definition 4“) - nenne stattdessen den Inhalt selbst.", "No references to sections, figures, pages, formula or definition numbers (e.g. \"in the section\", \"Figure 2\", \"Definition 4\") - state the content itself instead.")
        CardProblem.GARBLED -> tr("Schreibe Formeln und Vektoren als LaTeX in \$...\$ (z. B. \$\\vec{v}\$), keine Sonderzeichen aus PDF-Schriften.", "Write formulas and vectors as LaTeX in \$...\$ (e.g. \$\\vec{v}\$), no special characters from PDF fonts.")
        CardProblem.CONTEXT -> tr("Die Frage muss ohne Abbildung, Beispiel oder vorherigen Rechenschritt verständlich sein: benenne Begriffe und Größen ausdrücklich, kein „diese …“, „angegebene …“, „betrachtete …“, „in diesem Kontext“.", "The question must be understandable without a figure, example or earlier calculation step: name terms and quantities explicitly, no \"this …\", \"the given …\", \"considered …\", \"in this context\".")
        CardProblem.VAGUE -> tr("Die Frage muss einen konkreten Begriff oder eine konkrete Größe nennen.", "The question must name a concrete term or quantity.")
        CardProblem.CIRCULAR -> tr("Die Antwort muss neue Information enthalten und darf die Frage nicht nur wiederholen.", "The answer must contain new information and not merely repeat the question.")
        else -> null
    }

    /** Zusatzanweisung für den Neuversuch, passend zu den festgestellten Mängeln. */
    fun retryHint(problems: Collection<CardProblem>): String {
        val lines = problems.distinct().mapNotNull { retryHint(it) }
        if (lines.isEmpty()) return ""
        return tr("\n\nWICHTIG - der letzte Versuch hatte Mängel. Beachte jetzt:\n", "\n\nIMPORTANT - the last attempt had flaws. Now observe:\n") + lines.joinToString("\n") { "- $it" }
    }

    fun describe(problems: Collection<CardProblem>): String = problems.distinct().joinToString("; ") { it.label }

    /** Ist [vec] einer der [others] fast gleich (Kosinus ≥ [threshold])? Die Vektoren werden vorher normiert. */
    fun isDuplicate(vec: FloatArray, others: List<FloatArray>, threshold: Double = DUP_THRESHOLD): Boolean {
        val v = VectorCodec.normalize(vec)
        return others.any { VectorCodec.dot(v, VectorCodec.normalize(it)) >= threshold }
    }

    /** Gemeinsame Inhaltswörter (Stamm 5 Zeichen) zweier Fragen als Anteil der Vereinigung, 0..1. */
    fun wordOverlap(a: String, b: String): Double {
        val sa = contentWords(a).map { it.take(5) }.toSet()
        val sb = contentWords(b).map { it.take(5) }.toSet()
        if (sa.isEmpty() || sb.isEmpty()) return 0.0
        return sa.intersect(sb).size.toDouble() / sa.union(sb).size
    }

    /** Wortüberlappung, ab der bei mäßiger Embedding-Ähnlichkeit ([TEXT_DUP_COS]) von einer Dublette ausgegangen wird. */
    const val TEXT_DUP_OVERLAP = 0.7
    const val TEXT_DUP_COS = 0.93

    /** Fast gleiche Wörter (Überlappung ab [NEAR_SAME_OVERLAP]) genügen schon bei [NEAR_SAME_COS]. */
    const val NEAR_SAME_OVERLAP = 0.85
    const val NEAR_SAME_COS = 0.90

    /**
     * Dublette, wenn der Kosinus hoch genug ist ODER Kosinus mäßig hoch und die Fragen viele Wörter teilen. Das fängt Fragen wie
     * „zyklischer Elektronentransport“ zweimal, die EmbeddingGemma knapp unter der reinen Schwelle bewertet. Gemessen: 13 von 15 echten
     * Dubletten erkannt, 4 von 25 verschiedenen Fragen fälschlich verworfen (docs/KARTEN_EVAL.md).
     */
    fun isDuplicate(vec: FloatArray, question: String, others: List<Pair<FloatArray?, String>>, threshold: Double = DUP_THRESHOLD): Boolean {
        val v = VectorCodec.normalize(vec)
        return others.any { (ov, oq) ->
            val cos: Double = ov?.let { VectorCodec.dot(v, VectorCodec.normalize(it)).toDouble() } ?: 0.0
            val overlap = wordOverlap(question, oq)
            cos >= threshold || (cos >= TEXT_DUP_COS && overlap >= TEXT_DUP_OVERLAP) || (cos >= NEAR_SAME_COS && overlap >= NEAR_SAME_OVERLAP)
        }
    }
}

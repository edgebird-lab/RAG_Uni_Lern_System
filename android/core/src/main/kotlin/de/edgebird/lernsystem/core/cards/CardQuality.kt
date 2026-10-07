package de.edgebird.lernsystem.core.cards

import de.edgebird.lernsystem.core.ai.VectorCodec

/**
 * Qualitätsprüfung für Karteikarten (Port von `ragapp/card_quality.py`): Frage und Antwort müssen OHNE das Dokument
 * verständlich sein. Regelbasiert und offline; nur die Duplikat-Erkennung nutzt Embeddings des Aufrufers.
 */
enum class CardProblem(val code: String, val label: String) {
    SOURCE_REFERENCE("quellenbezug", "verweist auf die Quelle (Abschnitt, Abbildung, Definition N …)"),
    GARBLED("unleserlich", "enthält kaputte PDF-Zeichen"),
    CONTEXT("kontext", "hängt von fehlendem Kontext ab (Abbildung, Beweisschritt, „diese …“)"),
    VAGUE("vage", "zu unbestimmt"),
    CIRCULAR("zirkulaer", "Antwort wiederholt nur die Frage"),
    DUPLICATE("duplikat", "doppelt (fast dieselbe Frage gibt es schon)"),
}

object CardQuality {
    /** Kosinus-Ähnlichkeit, ab der zwei Fragen als Dublette gelten (an bge-m3 kalibriert; für EmbeddingGemma zu prüfen). */
    const val DUP_THRESHOLD = 0.89

    /**
     * Groß-/Kleinschreibung ignorieren, Wörter und Wortgrenzen Unicode-weit. Die JVM braucht dafür das Flag `U`,
     * Androids ICU-Regex kennt es nicht (wirft eine Ausnahme), ist aber ohnehin Unicode-fähig.
     */
    private fun rx(p: String): Regex = try {
        Regex("(?iU)$p")
    } catch (e: java.util.regex.PatternSyntaxException) {
        Regex("(?i)$p")
    }

    private const val FIG = "abbildung|abb\\.|bild|grafik|diagramm|skizze|zeichnung|tabelle|tab\\.|folie|slide|seite|kapitel|abschnitt|aufgabe|beispiel|übung|uebung"
    private val NUMBERED_FIG = rx("\\b(?:$FIG)\\s*\\d+(?:\\.\\d+)*\\b")
    private val NUMBERED_THEOREM = rx("\\b(?:satz|definition|lemma|korollar|theorem|proposition|bemerkung|axiom)\\s+\\d+(?:\\.\\d+)*\\b")
    private val NUMBERED_EQ = rx("\\b(?:formel|gleichung|ungleichung|gl\\.)\\s*\\(\\s*\\d+(?:\\.\\d+)*\\s*\\)")
    private val SOURCE_PHRASE = rx(
        "\\b(?:im|in diesem|in dem|im folgenden|im obigen|im vorliegenden|im gegebenen|im genannten|im betrachteten)\\s+" +
            "(?:abschnitt|text|skript|dokument|kapitel|beispiel|bild|textabschnitt|auszug)\\b" +
            "|\\b(?:laut|gemäß|gemaess|siehe|nach)\\s+(?:dem\\s+|der\\s+|den\\s+)?" +
            "(?:text|skript|vorlesung|folie|abschnitt|abbildung|aufgabe|beispiel|unterlagen)\\b" +
            "|\\b(?:in|auf)\\s+(?:der|dieser|folgender|obiger)\\s+(?:abbildung|grafik|skizze|tabelle|folie|zeichnung|darstellung)\\b" +
            "|\\b(?:oben|unten)\\s+(?:genannt|stehend|beschrieben|angegeben|gezeigt|erwähnt|abgebildet|dargestellt)\\w*" +
            "|\\b(?:obige|obigen|obiger|obiges|untenstehende\\w*|obenstehende\\w*)\\b" +
            "|\\b(?:dargestellt|abgebildet|gezeigt|beschrieben|erwähnt|genannt)\\s+(?:im|in der|in dem|auf der)\\b",
    )

    /** U+239B–23B3 Klammerbausteine, U+23D0, Private-Use U+E000–F8FF, U+FFFD, U+20D7 (Vektorpfeil) und Steuerzeichen. */
    private val GARBLED_RX = Regex("[⎛-⎳⏐-�⃗\u0000-\u0008\u000B\u000C\u000E-\u001F]")

    private const val DEICTIC_NOUNS = "abbildung|grafik|skizze|tabelle|formel|gleichung|aufgabe|beispiel|zeichnung|darstellung|schritt|umformung|rechnung|herleitung"
    private val DEICTIC = rx("\\bdiese[rnms]?\\s+($DEICTIC_NOUNS)\\b")
    private val CONTEXT_RX = rx(
        "\\bin\\s+diesem\\s+(?:kontext|zusammenhang|fall|schritt|beispiel|abschnitt|kapitel|text)\\b" +
            "|\\bangegeben\\w*" +
            "|\\bgegebene[nrsm]?\\s+(?:abbildung|skizze|figur|aufgabe|zeichnung|grafik|tabelle|text|beispiel)\\b" +
            "|\\bbetrachtete[nrsm]?\\b" +
            "|,\\s*(?:die|der|das|den|dem|welche[rnms]?)\\b[^?,;]*\\b(?:bewiesen|gezeigt|hergeleitet|abgeleitet|erhalten|ermittelt)\\s+(?:wird|werden)\\b" +
            "|\\b(?:wie|was)\\s+(?:oben|unten|zuvor|vorher)\\b",
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

    private val RETRY_HINTS = mapOf(
        CardProblem.SOURCE_REFERENCE to "Keine Verweise auf Abschnitte, Abbildungen, Seiten, Formel- oder Definitionsnummern (z. B. „im Abschnitt“, „Abbildung 2“, „Definition 4“) - nenne stattdessen den Inhalt selbst.",
        CardProblem.GARBLED to "Schreibe Formeln und Vektoren als LaTeX in \$...\$ (z. B. \$\\vec{v}\$), keine Sonderzeichen aus PDF-Schriften.",
        CardProblem.CONTEXT to "Die Frage muss ohne Abbildung, Beispiel oder vorherigen Rechenschritt verständlich sein: benenne Begriffe und Größen ausdrücklich, kein „diese …“, „angegebene …“, „betrachtete …“, „in diesem Kontext“.",
        CardProblem.VAGUE to "Die Frage muss einen konkreten Begriff oder eine konkrete Größe nennen.",
        CardProblem.CIRCULAR to "Die Antwort muss neue Information enthalten und darf die Frage nicht nur wiederholen.",
    )

    /** Zusatzanweisung für den Neuversuch, passend zu den festgestellten Mängeln. */
    fun retryHint(problems: Collection<CardProblem>): String {
        val lines = problems.distinct().mapNotNull { RETRY_HINTS[it] }
        if (lines.isEmpty()) return ""
        return "\n\nWICHTIG - der letzte Versuch hatte Mängel. Beachte jetzt:\n" + lines.joinToString("\n") { "- $it" }
    }

    fun describe(problems: Collection<CardProblem>): String = problems.distinct().joinToString("; ") { it.label }

    /** Ist [vec] einer der [others] fast gleich (Kosinus ≥ [threshold])? Die Vektoren werden vorher normiert. */
    fun isDuplicate(vec: FloatArray, others: List<FloatArray>, threshold: Double = DUP_THRESHOLD): Boolean {
        val v = VectorCodec.normalize(vec)
        return others.any { VectorCodec.dot(v, VectorCodec.normalize(it)) >= threshold }
    }
}

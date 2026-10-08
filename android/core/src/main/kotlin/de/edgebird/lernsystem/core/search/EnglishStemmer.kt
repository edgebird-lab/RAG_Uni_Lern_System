package de.edgebird.lernsystem.core.search

/**
 * Snowball-Stemmer für Englisch („Porter2“, english.sbl). Erwartet kleingeschriebene Wörter; Verfahren und Sonderfälle nach der
 * Beschreibung auf snowballstem.org.
 */
object EnglishStemmer {
    private const val VOWELS = "aeiouy"
    private val EXCEPTIONS = mapOf(
        "skis" to "ski", "skies" to "sky", "dying" to "die", "lying" to "lie", "tying" to "tie", "idly" to "idl", "gently" to "gentl",
        "ugly" to "ugli", "early" to "earli", "only" to "onli", "singly" to "singl",
        "sky" to "sky", "news" to "news", "howe" to "howe", "atlas" to "atlas", "cosmos" to "cosmos", "bias" to "bias", "andes" to "andes",
    )
    private val AFTER_1A_KEEP = setOf("inning", "outing", "canning", "herring", "earring", "proceed", "exceed", "succeed")
    private val DOUBLES = listOf("bb", "dd", "ff", "gg", "mm", "nn", "pp", "rr", "tt")
    private val LI_ENDING = "cdeghkmnrt"

    private fun isVowel(c: Char) = c in VOWELS

    fun stem(input: String): String {
        var w = input.lowercase().trimStart('\'')
        if (w.length <= 2) return w
        EXCEPTIONS[w]?.let { return it }
        // Prelude: y als Konsonant markieren
        val sb = StringBuilder(w)
        for (i in sb.indices) if (sb[i] == 'y' && (i == 0 || isVowel(sb[i - 1]))) sb[i] = 'Y'
        w = sb.toString()

        val (r1, r2) = regions(w)
        // Schritt 0
        for (s in listOf("'s'", "'s", "'")) if (w.endsWith(s)) { w = w.dropLast(s.length); break }
        // Schritt 1a
        w = step1a(w)
        if (w in AFTER_1A_KEEP) return w.replace('Y', 'y')
        w = step1b(w, r1)
        w = step1c(w)
        w = step2(w, r1)
        w = step3(w, r1, r2)
        w = step4(w, r2)
        w = step5(w, r1, r2)
        return w.replace('Y', 'y')
    }

    /** Position, ab der die Region R1 beginnt: hinter dem ersten Nichtvokal, der auf einen Vokal folgt (Sonderpräfixe verschieben sie). */
    private fun regionAfter(w: String, from: Int): Int {
        var i = from
        while (i + 1 < w.length) { if (isVowel(w[i]) && !isVowel(w[i + 1])) return i + 2; i++ }
        return w.length
    }

    private fun regions(w: String): Pair<Int, Int> {
        val r1 = listOf("gener", "commun", "arsen").firstOrNull { w.startsWith(it) }?.length ?: regionAfter(w, 0)
        return r1 to regionAfter(w, r1)
    }

    private fun endsShortSyllable(w: String, end: Int = w.length): Boolean {
        if (end == 2) return isVowel(w[0]) && !isVowel(w[1])
        if (end < 3) return false
        val c = w[end - 1]; val v = w[end - 2]; val p = w[end - 3]
        return !isVowel(c) && c !in "wxY" && isVowel(v) && !isVowel(p)
    }

    private fun isShortWord(w: String, r1: Int) = r1 >= w.length && endsShortSyllable(w)

    private fun step1a(w: String): String {
        if (w.endsWith("sses")) return w.dropLast(2)
        if (w.endsWith("ied") || w.endsWith("ies")) return if (w.length > 4) w.dropLast(2) else w.dropLast(1)
        if (w.endsWith("us") || w.endsWith("ss")) return w
        if (w.endsWith("s")) {
            // streichen, wenn vor dem „s“ (nicht direkt davor) ein Vokal steht
            val stem = w.dropLast(1)
            if (stem.length >= 2 && stem.dropLast(1).any { isVowel(it) }) return stem
        }
        return w
    }

    private fun step1b(w0: String, r1: Int): String {
        var w = w0
        for (s in listOf("eedly", "eed")) if (w.endsWith(s)) return if (w.length - s.length >= r1) w.dropLast(s.length) + "ee" else w
        for (s in listOf("ingly", "edly", "ing", "ed")) if (w.endsWith(s)) {
            val stem = w.dropLast(s.length)
            if (stem.none { isVowel(it) }) return w
            w = stem
            return when {
                w.endsWith("at") || w.endsWith("bl") || w.endsWith("iz") -> w + "e"
                DOUBLES.any { w.endsWith(it) } -> w.dropLast(1)
                isShortWord(w, r1) -> w + "e"
                else -> w
            }
        }
        return w
    }

    private fun step1c(w: String): String =
        if (w.length > 2 && (w.last() == 'y' || w.last() == 'Y') && !isVowel(w[w.length - 2])) w.dropLast(1) + "i" else w

    private val STEP2 = listOf(
        "ization" to "ize", "ational" to "ate", "fulness" to "ful", "ousness" to "ous", "iveness" to "ive", "tional" to "tion", "biliti" to "ble",
        "lessli" to "less", "entli" to "ent", "ation" to "ate", "alism" to "al", "aliti" to "al", "ousli" to "ous", "iviti" to "ive", "fulli" to "ful",
        "enci" to "ence", "anci" to "ance", "abli" to "able", "izer" to "ize", "ator" to "ate", "alli" to "al", "bli" to "ble", "ogi" to "og", "li" to "",
    )

    private fun step2(w: String, r1: Int): String {
        for ((suf, rep) in STEP2) if (w.endsWith(suf)) {
            if (w.length - suf.length < r1) return w
            return when (suf) {
                "ogi" -> if (w.length - 3 > 0 && w[w.length - 4] == 'l') w.dropLast(3) + rep else w
                "li" -> if (w.length >= 3 && w[w.length - 3] in LI_ENDING) w.dropLast(2) else w
                else -> w.dropLast(suf.length) + rep
            }
        }
        return w
    }

    private val STEP3 = listOf("ational" to "ate", "tional" to "tion", "alize" to "al", "icate" to "ic", "iciti" to "ic", "ative" to "", "ical" to "ic", "ness" to "", "ful" to "")

    private fun step3(w: String, r1: Int, r2: Int): String {
        for ((suf, rep) in STEP3) if (w.endsWith(suf)) {
            if (w.length - suf.length < r1) return w
            if (suf == "ative") return if (w.length - suf.length >= r2) w.dropLast(suf.length) else w
            return w.dropLast(suf.length) + rep
        }
        return w
    }

    private val STEP4 = listOf("ement", "ance", "ence", "able", "ible", "ment", "ant", "ent", "ism", "ate", "iti", "ous", "ive", "ize", "al", "er", "ic", "ion")

    private fun step4(w: String, r2: Int): String {
        for (suf in STEP4) if (w.endsWith(suf)) {
            if (w.length - suf.length < r2) return w
            if (suf == "ion") return if (w.length > 3 && w[w.length - 4] in "st") w.dropLast(3) else w
            return w.dropLast(suf.length)
        }
        return w
    }

    private fun step5(w: String, r1: Int, r2: Int): String {
        if (w.endsWith("e")) {
            val stemLen = w.length - 1
            if (stemLen >= r2 || (stemLen >= r1 && !endsShortSyllable(w, stemLen))) return w.dropLast(1)
        } else if (w.endsWith("l") && w.length - 1 >= r2 && w.endsWith("ll")) return w.dropLast(1)
        return w
    }
}

package de.edgebird.lernsystem.core.search

/**
 * Snowball-Stemmer für Deutsch, Port von `german.sbl` (Snowball 3.1.1), wie ihn `snowballstemmer` in der
 * PC-App nutzt. Erwartet kleingeschriebene Wörter. Ein Paritätstest vergleicht die Ausgabe mit dem Python-Original.
 */
object GermanStemmer {
    private const val VOWELS = "aeiouyäöü"
    private const val S_ENDING = "bdfghklmnrt"
    private const val ST_ENDING = "bdfghklmnt"
    private const val ET_ENDING = "Udfgklmnrstzä"
    private val ET_EXCEPTIONS = listOf("tick", "plan", "geordn", "intern", "tr")

    private fun isVowel(c: Char) = c in VOWELS

    fun stem(input: String): String {
        if (input.isEmpty()) return input
        val w = prelude(input)

        // Regionen R1/R2
        val n = w.length
        val r1: Int
        val r2: Int
        if (n < 3) {
            r1 = n
            r2 = n
        } else {
            val p1 = markRegion(w, 0, n)
            r2 = markRegion(w, p1, n) // ab der ursprünglichen R1-Grenze gesucht
            r1 = if (p1 < 3) 3 else p1
        }

        step1(w, r1)
        step2(w, r1)
        step3(w, r1, r2)
        step4(w)

        for (i in w.indices) {
            when (w[i]) {
                'Y' -> w.setCharAt(i, 'y')
                'U' -> w.setCharAt(i, 'u')
                'ä' -> w.setCharAt(i, 'a')
                'ö' -> w.setCharAt(i, 'o')
                'ü' -> w.setCharAt(i, 'u')
            }
        }
        return w.toString()
    }

    /** 1. Durchgang: u/y zwischen Vokalen als Konsonanten (U/Y); 2. Durchgang: ß -> ss, ae/oe/ue -> ä/ö/ü ("qu" bleibt). */
    private fun prelude(input: String): StringBuilder {
        val marked = StringBuilder(input)
        for (i in 1 until marked.length - 1) {
            val c = marked[i]
            if ((c == 'u' || c == 'y') && isVowel(marked[i - 1]) && isVowel(marked[i + 1])) marked.setCharAt(i, c.uppercaseChar())
        }
        val w = StringBuilder()
        var k = 0
        while (k < marked.length) {
            val c = marked[k]
            val next = if (k + 1 < marked.length) marked[k + 1] else ' '
            when {
                c == 'ß' -> { w.append("ss"); k++ }
                c == 'a' && next == 'e' -> { w.append('ä'); k += 2 }
                c == 'o' && next == 'e' -> { w.append('ö'); k += 2 }
                c == 'u' && next == 'e' -> { w.append('ü'); k += 2 }
                c == 'q' && next == 'u' -> { w.append("qu"); k += 2 }
                else -> { w.append(c); k++ }
            }
        }
        return w
    }

    /** Position hinter dem ersten Nicht-Vokal, der auf einen Vokal folgt (ab [from]); sonst Wortende. */
    private fun markRegion(w: CharSequence, from: Int, limit: Int): Int {
        var i = from
        while (i < limit && !isVowel(w[i])) i++
        if (i >= limit) return limit
        i++
        while (i < limit && isVowel(w[i])) i++
        if (i >= limit) return limit
        return i + 1
    }

    private fun longestSuffix(w: CharSequence, candidates: List<String>): String? =
        candidates.filter { w.endsWith(it) }.maxByOrNull { it.length }

    private fun step1(w: StringBuilder, r1: Int) {
        val m = longestSuffix(w, listOf("e", "em", "en", "erinnen", "erin", "ln", "ern", "er", "s", "es", "lns")) ?: return
        val start = w.length - m.length
        if (start < r1) return
        when (m) {
            "em" -> if (!w.substring(0, start).endsWith("syst")) w.setLength(start)
            "erinnen", "erin", "ern", "er" -> w.setLength(start)
            "e", "en", "es" -> {
                w.setLength(start)
                if (w.endsWith("niss")) w.setLength(w.length - 1)
            }
            "s" -> if (start > 0 && w[start - 1] in S_ENDING) w.setLength(start)
            "ln", "lns" -> { w.setLength(start); w.append('l') }
        }
    }

    private fun step2(w: StringBuilder, r1: Int) {
        val m = longestSuffix(w, listOf("en", "er", "et", "st", "est")) ?: return
        val start = w.length - m.length
        if (start < r1) return
        when (m) {
            "en", "er", "est" -> w.setLength(start)
            "st" -> if (start >= 4 && w[start - 1] in ST_ENDING) w.setLength(start)
            "et" -> if (start > 0 && w[start - 1] in ET_ENDING && ET_EXCEPTIONS.none { w.substring(0, start).endsWith(it) }) w.setLength(start)
        }
    }

    private fun step3(w: StringBuilder, r1: Int, r2: Int) {
        val m = longestSuffix(w, listOf("end", "ig", "ung", "lich", "isch", "ik", "heit", "keit")) ?: return
        val start = w.length - m.length
        if (start < r2) return
        when (m) {
            "end", "ung" -> {
                w.setLength(start)
                if (w.endsWith("ig")) {
                    val s = w.length - 2
                    if (!(s > 0 && w[s - 1] == 'e') && s >= r2) w.setLength(s)
                }
            }
            "ig", "ik", "isch" -> if (!(start > 0 && w[start - 1] == 'e')) w.setLength(start)
            "lich", "heit" -> {
                w.setLength(start)
                if ((w.endsWith("er") || w.endsWith("en")) && w.length - 2 >= r1) w.setLength(w.length - 2)
            }
            "keit" -> {
                w.setLength(start)
                val t = longestSuffix(w, listOf("ig", "lich"))
                if (t != null && w.length - t.length >= r2) w.setLength(w.length - t.length)
            }
        }
    }

    /** Apostroph-Endungen ('s, 'sch, '), nur wenn mindestens zwei Zeichen davor stehen. */
    private fun step4(w: StringBuilder) {
        val m = longestSuffix(w, listOf("'", "'sch", "'s")) ?: return
        val start = w.length - m.length
        if (start >= 2) w.setLength(start)
    }
}

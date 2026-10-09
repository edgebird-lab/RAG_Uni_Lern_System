// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.audio

import de.edgebird.lernsystem.core.cards.LatexLite
import de.edgebird.lernsystem.core.i18n.Lang
import de.edgebird.lernsystem.core.i18n.tr
import de.edgebird.lernsystem.core.summary.MarkdownLite

/** Bereitet Text für die Sprachausgabe auf: Formatierung weg, Abkürzungen ausschreiben, in Sätze für kurze Wartezeiten teilen. */
object SpeechText {
    private val ABBREVIATIONS = listOf(
        Regex("""\bz\.\s?B\."""), Regex("""\bd\.\s?h\."""), Regex("""\bu\.\s?a\."""), Regex("""\bz\.\s?T\."""), Regex("""\bbzw\."""), Regex("""\bggf\."""),
        Regex("""\busw\."""), Regex("""\bvgl\."""), Regex("""\bca\."""), Regex("""\bevtl\."""), Regex("""\bbspw\."""), Regex("""\binkl\."""), Regex("""\bsog\."""), Regex("""\bNr\."""), Regex("""\bAbb\."""),
    ).zip(listOf("zum Beispiel", "das heißt", "unter anderem", "zum Teil", "beziehungsweise", "gegebenenfalls", "und so weiter", "vergleiche", "circa", "eventuell", "beispielsweise", "inklusive", "sogenannte", "Nummer", "Abbildung"))

    private val ABBREVIATIONS_EN = listOf(
        Regex("""\be\.g\."""), Regex("""\bi\.e\."""), Regex("""\betc\."""), Regex("""\bcf\."""), Regex("""\bvs\."""), Regex("""\bapprox\."""), Regex("""\bincl\."""), Regex("""\bFig\."""), Regex("""\bNo\."""), Regex("""\bDr\."""),
    ).zip(listOf("for example", "that is", "et cetera", "compare", "versus", "approximately", "including", "Figure", "Number", "Doctor"))

    /** Fließender, vorlesbarer Text aus einer Markdown-Zusammenfassung oder Antwort (Absätze durch Leerzeilen getrennt). */
    fun prepare(markdown: String, lang: Lang = Lang.current): String {
        var t = LatexLite.toPlain(MarkdownLite.toPlain(markdown)).replace(Regex("""\*+|_{2,}|`|•"""), "")
        for ((rx, full) in if (lang == Lang.EN) ABBREVIATIONS_EN else ABBREVIATIONS) t = rx.replace(t, full)
        t = if (lang == Lang.EN) t.replace("%", " percent").replace("&", " and ").replace("→", " gives ").replace("≈", " approximately ").replace("≤", " less than or equal to ").replace("≥", " greater than or equal to ")
            .replace("°C", " degrees Celsius").replace("€", " euros").replace("\$", " dollars ")
        else t.replace("%", " Prozent").replace("&", " und ").replace("→", " ergibt ").replace("≈", " ungefähr ").replace("≤", " kleiner gleich ").replace("≥", " größer gleich ")
            .replace("°C", " Grad Celsius").replace("€", " Euro")
        t = t.replace(Regex("""\[(?:Quelle|Source)[^\]]*\]"""), "").replace(Regex("""\s*\((?:Seite|Page|Folie|Slide)[^)]*\)"""), "")
        t = t.replace(Regex("""[ \t]{2,}"""), " ")
        return t.lines().joinToString("\n") { it.trim() }.replace(Regex("""\n{3,}"""), "\n\n").trim()
    }

    /**
     * Teilt in Stücke für die Synthese: Absätze bleiben getrennt (Pause), Sätze werden bis [max] Zeichen zusammengefasst, zu lange Sätze an Kommas geteilt.
     * Jedes Stück ist (Text, Pause danach in Millisekunden).
     */
    fun chunks(prepared: String, max: Int = 220): List<Pair<String, Int>> {
        val out = mutableListOf<Pair<String, Int>>()
        for ((pi, para) in prepared.split(Regex("""\n\s*\n|\n""")).map { it.trim() }.filter { it.isNotEmpty() }.withIndex()) {
            val sentences = para.split(Regex("""(?<=[.!?:])\s+""")).flatMap { s -> if (s.length <= max) listOf(s) else splitLong(s, max) }
            val cur = StringBuilder()
            val pieces = mutableListOf<String>()
            for (s in sentences) {
                if (cur.isNotEmpty() && cur.length + s.length + 1 > max) { pieces += cur.toString(); cur.clear() }
                if (cur.isNotEmpty()) cur.append(' ')
                cur.append(s)
            }
            if (cur.isNotEmpty()) pieces += cur.toString()
            pieces.forEachIndexed { i, p -> out += p to if (i == pieces.lastIndex) 450 else 120 }
        }
        return out
    }

    private fun splitLong(s: String, max: Int): List<String> {
        val parts = s.split(Regex("""(?<=[,;])\s+"""))
        val res = mutableListOf<String>(); val cur = StringBuilder()
        for (p in parts.flatMap { if (it.length > max) it.chunked(max) else listOf(it) }) {
            if (cur.isNotEmpty() && cur.length + p.length + 1 > max) { res += cur.toString(); cur.clear() }
            if (cur.isNotEmpty()) cur.append(' ')
            cur.append(p)
        }
        if (cur.isNotEmpty()) res += cur.toString()
        return res
    }

    /** Float-Samples (−1..1) als 16-Bit-PCM, little endian. */
    fun toPcm16(samples: FloatArray): ByteArray {
        val out = ByteArray(samples.size * 2)
        for (i in samples.indices) {
            val v = (samples[i].coerceIn(-1f, 1f) * 32767f).toInt()
            out[2 * i] = (v and 0xFF).toByte(); out[2 * i + 1] = ((v shr 8) and 0xFF).toByte()
        }
        return out
    }
}

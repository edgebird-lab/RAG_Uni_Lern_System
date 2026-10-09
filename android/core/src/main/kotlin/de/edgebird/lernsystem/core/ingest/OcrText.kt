// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.ingest

/** Aufbereitung von Texterkennungs-Ergebnissen (OCR): Silbentrennung am Zeilenende auflösen, Leerzeichen glätten. */
object OcrText {
    /** Trenner zwischen Seiten in gespeicherten Foto-Dokumenten (Form Feed); der Textlader macht daraus Seiten. */
    const val PAGE_BREAK = '\u000C'

    /** Zeilen eines Textblocks zu einem Absatz zusammenführen; „Wort-“ am Zeilenende plus Kleinbuchstabe am Anfang der nächsten Zeile ergibt „Wortteil“. */
    fun joinLines(lines: List<String>): String {
        val sb = StringBuilder()
        for (raw in lines.map { it.trim() }.filter { it.isNotEmpty() }) {
            if (sb.isEmpty()) { sb.append(raw); continue }
            val prevHyphen = sb.endsWith("-") && sb.length >= 2 && sb[sb.length - 2].isLetter()
            if (prevHyphen && raw.first().isLowerCase()) sb.setLength(sb.length - 1).also { sb.append(raw) }
            else sb.append(' ').append(raw)
        }
        return sb.toString().replace(Regex("""[ \t]{2,}"""), " ")
    }

    /** Absätze (Textblöcke) zu einem Text zusammenfügen. */
    fun joinBlocks(blocks: List<List<String>>): String = blocks.map { joinLines(it) }.filter { it.isNotBlank() }.joinToString("\n\n")

    /** Mehrere Seiten zu einem Text mit [PAGE_BREAK] zwischen den Seiten; leere Seiten bleiben als leere Seite erhalten (Seitenzahlen stimmen weiter). */
    fun joinPages(pages: List<String>): String = pages.joinToString(PAGE_BREAK.toString())
}

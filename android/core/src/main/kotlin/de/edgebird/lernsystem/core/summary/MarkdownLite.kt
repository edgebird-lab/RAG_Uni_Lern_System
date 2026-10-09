// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.summary

/** Kleiner Markdown-Ausschnitt, den die Zusammenfassungen verwenden: Überschriften, Listen, Absätze, **fett**. */
object MarkdownLite {
    sealed interface Block {
        data class Heading(val level: Int, val text: String) : Block
        data class Bullet(val text: String, val indent: Int) : Block
        data class Paragraph(val text: String) : Block
    }

    /** Textstück mit Auszeichnung. */
    data class Span(val text: String, val bold: Boolean, val italic: Boolean = false)

    private val HEADING = Regex("^(#{1,6})\\s+(.*)$")
    private val BULLET = Regex("^(\\s*)(?:[-*•])\\s+(.*)$")
    private val NUMBERED = Regex("^(\\s*)\\d+[.)]\\s+(.*)$")

    fun parse(md: String): List<Block> {
        val out = mutableListOf<Block>()
        val para = StringBuilder()
        fun flush() { if (para.isNotBlank()) out += Block.Paragraph(para.toString().trim()); para.clear() }
        for (raw in md.lines()) {
            val line = raw.trimEnd()
            val h = HEADING.matchEntire(line)
            val b = BULLET.matchEntire(line) ?: NUMBERED.matchEntire(line)
            when {
                line.isBlank() -> flush()
                h != null -> { flush(); out += Block.Heading(h.groupValues[1].length, h.groupValues[2].trim()) }
                b != null -> { flush(); out += Block.Bullet(b.groupValues[2].trim(), b.groupValues[1].length / 2) }
                else -> { if (para.isNotEmpty()) para.append(' '); para.append(line.trim()) }
            }
        }
        flush()
        return out
    }

    /** **fett** oder *kursiv* (kursiv nur, wenn direkt nach dem Stern bzw. vor dem schließenden Stern kein Leerzeichen steht). */
    private val EMPHASIS = Regex("\\*\\*(.+?)\\*\\*|\\*(?=\\S)([^*]+?)(?<=\\S)\\*")

    fun spans(text: String): List<Span> {
        val out = mutableListOf<Span>()
        var pos = 0
        for (m in EMPHASIS.findAll(text)) {
            if (m.range.first > pos) out += Span(text.substring(pos, m.range.first), false)
            out += if (m.groupValues[1].isNotEmpty()) Span(m.groupValues[1], bold = true) else Span(m.groupValues[2], bold = false, italic = true)
            pos = m.range.last + 1
        }
        if (pos < text.length) out += Span(text.substring(pos), false)
        return out
    }

    /** Reiner Text ohne Markdown-Zeichen (für Kopieren/Teilen als Fließtext). */
    fun toPlain(md: String): String = parse(md).joinToString("\n") {
        when (it) {
            is Block.Heading -> it.text
            is Block.Bullet -> "  ".repeat(it.indent) + "• " + spans(it.text).joinToString("") { s -> s.text }
            is Block.Paragraph -> spans(it.text).joinToString("") { s -> s.text }
        }
    }
}

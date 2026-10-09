// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.summary

import de.edgebird.lernsystem.core.cards.LatexLite

/** Wandelt das kleine Markdown der Zusammenfassungen und Notizen in druckbares HTML (Überschriften, Listen, Absätze, fett/kursiv, Formeln als Text). */
object MarkdownHtml {
    private fun esc(s: String) = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    private fun inline(text: String) = MarkdownLite.spans(LatexLite.toPlain(text)).joinToString("") { s ->
        val t = esc(s.text)
        when { s.bold -> "<b>$t</b>"; s.italic -> "<i>$t</i>"; else -> t }
    }

    private const val CSS = "body{font-family:serif;font-size:12pt;line-height:1.45;margin:0}h1{font-size:20pt}h2{font-size:15pt;margin-top:1.2em}h3,h4,h5,h6{font-size:12.5pt}ul{margin:.3em 0;padding-left:1.4em}li{margin:.15em 0}p{margin:.5em 0}pre{white-space:pre-wrap;font-family:serif}"

    fun toHtml(markdown: String, title: String = ""): String = buildString {
        append("<html><head><meta charset=\"utf-8\"><title>").append(esc(title)).append("</title><style>").append(CSS).append("</style></head><body>")
        var depth = 0
        fun closeLists(to: Int) { while (depth > to) { append("</ul>"); depth-- } }
        for (b in MarkdownLite.parse(markdown)) {
            when (b) {
                is MarkdownLite.Block.Bullet -> { val want = b.indent + 1; while (depth < want) { append("<ul>"); depth++ }; closeLists(want); append("<li>").append(inline(b.text)).append("</li>") }
                is MarkdownLite.Block.Heading -> { closeLists(0); val l = b.level.coerceIn(1, 6); append("<h$l>").append(inline(b.text)).append("</h$l>") }
                is MarkdownLite.Block.Paragraph -> { closeLists(0); append("<p>").append(inline(b.text)).append("</p>") }
            }
        }
        closeLists(0)
        append("</body></html>")
    }

    /** Reiner Text (Textdatei, Quelltext) als HTML mit erhaltenen Zeilenumbrüchen. */
    fun fromPlainText(text: String, title: String = ""): String =
        "<html><head><meta charset=\"utf-8\"><title>${esc(title)}</title><style>$CSS</style></head><body><pre>${esc(text)}</pre></body></html>"
}

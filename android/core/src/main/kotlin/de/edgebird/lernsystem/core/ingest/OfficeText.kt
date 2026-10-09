// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.ingest

import org.xml.sax.Attributes
import org.xml.sax.InputSource
import org.xml.sax.helpers.DefaultHandler
import java.io.ByteArrayInputStream
import java.io.InputStream
import java.util.zip.ZipInputStream
import javax.xml.parsers.SAXParserFactory

/**
 * Text aus Office-Dateien (ZIP mit XML): Word (`.docx`), PowerPoint (`.pptx`) und OpenDocument (`.odt`, `.odp`). Ohne Zusatzbibliothek, nur mit dem
 * SAX-Parser der Plattform. Überschriften werden zu Markdown-Überschriften, Listen zu Aufzählungen, Tabellenzeilen zu Zeilen mit „ | “; Folien kommen
 * einzeln (Titel, Text, Notizen). Ältere Binärformate (`.doc`, `.ppt`) werden nicht gelesen.
 */
object OfficeText {
    /** Größenobergrenze je gelesener XML-Datei (Schutz vor Zip-Bomben). */
    private const val MAX_ENTRY_BYTES = 80L * 1024 * 1024
    private const val MAX_TOTAL_BYTES = 300L * 1024 * 1024

    class OfficeException(message: String) : Exception(message)

    /** Liest die gewünschten Einträge der ZIP-Datei vollständig in den Speicher (andere werden übersprungen). */
    internal fun entries(zip: InputStream, maxEntryBytes: Long = MAX_ENTRY_BYTES, wanted: (String) -> Boolean): Map<String, ByteArray> {
        val out = linkedMapOf<String, ByteArray>()
        var total = 0L
        try {
            ZipInputStream(zip.buffered()).use { z ->
                while (true) {
                    val e = z.nextEntry ?: break
                    if (e.isDirectory || !wanted(e.name)) continue
                    val bos = java.io.ByteArrayOutputStream()
                    val buf = ByteArray(32 * 1024)
                    var size = 0L
                    while (true) {
                        val n = z.read(buf); if (n < 0) break
                        size += n; total += n
                        if (size > maxEntryBytes || total > MAX_TOTAL_BYTES) throw OfficeException("Die Datei ist zu groß zum Lesen")
                        bos.write(buf, 0, n)
                    }
                    out[e.name] = bos.toByteArray()
                }
            }
        } catch (e: OfficeException) { throw e } catch (e: Exception) { throw OfficeException("Die Datei ist keine gültige Office-Datei: ${e.message}") }
        return out
    }

    private fun parse(bytes: ByteArray, handler: DefaultHandler) {
        val factory = SAXParserFactory.newInstance().apply {
            isNamespaceAware = false
            // Keine externen Entitäten oder DTDs laden (nicht jede Plattform kennt jede Einstellung)
            for ((f, v) in listOf("http://xml.org/sax/features/external-general-entities" to false, "http://xml.org/sax/features/external-parameter-entities" to false, "http://apache.org/xml/features/nonvalidating/load-external-dtd" to false)) runCatching { setFeature(f, v) }
        }
        val reader = factory.newSAXParser().xmlReader
        reader.contentHandler = handler
        reader.entityResolver = org.xml.sax.EntityResolver { _, _ -> InputSource(ByteArrayInputStream(ByteArray(0))) }
        reader.parse(InputSource(ByteArrayInputStream(bytes)))
    }

    private val SPACES = Regex("[ \\t\\u00A0]+")
    private fun clean(s: String) = s.replace(SPACES, " ").trim()

    /** Marker für Tabellenzeilen: aufeinanderfolgende Zeilen kommen ohne Leerzeile untereinander. */
    private const val ROW = "\u0001"

    /** Fertigt aus Absätzen einen Markdown-Text: Leerzeile zwischen Absätzen, Listenpunkte und Tabellenzeilen untereinander. */
    private fun joinMarkdown(parts: List<String>): String {
        val sb = StringBuilder()
        var prev = ' '
        for (p in parts) {
            if (p.isBlank()) continue
            val kind = when { p.startsWith(ROW) -> 'r'; p.startsWith("- ") || p.startsWith("  - ") -> 'l'; else -> 'p' }
            if (sb.isNotEmpty()) sb.append(if (kind != 'p' && kind == prev) "\n" else "\n\n")
            sb.append(p.removePrefix(ROW)); prev = kind
        }
        return sb.toString().trim()
    }

    // ---- Word (docx) -----------------------------------------------------------------------------------------------------

    fun docxToMarkdown(zip: InputStream): String {
        val xml = entries(zip) { it == "word/document.xml" }["word/document.xml"] ?: throw OfficeException("Das ist keine Word-Datei (word/document.xml fehlt)")
        val parts = mutableListOf<String>()
        parse(xml, object : DefaultHandler() {
            /** Zustand eines Absatzes; Textfelder enthalten Absätze in Absätzen, darum ein Stapel. */
            inner class Para { val text = StringBuilder(); var style = ""; var outline = -1; var listLevel = -1 }
            val stack = ArrayDeque<Para>()
            var inT = false; var inPPr = false
            var tableDepth = 0; var row: MutableList<String>? = null; var cell: StringBuilder? = null
            val headingStyle = Regex("(?i)^(heading|berschrift|überschrift|titel|title)\\s*(\\d)?$")

            override fun startElement(uri: String?, localName: String?, qName: String, a: Attributes) {
                val p = stack.lastOrNull()
                when (qName) {
                    "w:p" -> stack.addLast(Para())
                    "w:pPr" -> inPPr = true
                    "w:pStyle" -> if (inPPr && p != null) p.style = a.getValue("w:val").orEmpty()
                    "w:outlineLvl" -> if (inPPr && p != null) p.outline = a.getValue("w:val")?.toIntOrNull() ?: -1
                    "w:numPr" -> if (inPPr && p != null && p.listLevel < 0) p.listLevel = 0
                    "w:ilvl" -> if (inPPr && p != null) p.listLevel = a.getValue("w:val")?.toIntOrNull() ?: 0
                    "w:t" -> inT = true
                    "w:tab" -> if (!inPPr) p?.text?.append(' ')
                    "w:br", "w:cr" -> if (a.getValue("w:type") != "page") p?.text?.append(' ')
                    "w:tbl" -> tableDepth++
                    "w:tr" -> if (tableDepth == 1) row = mutableListOf()
                    "w:tc" -> if (tableDepth == 1) cell = StringBuilder()
                }
            }

            override fun characters(ch: CharArray, start: Int, length: Int) { if (inT) stack.lastOrNull()?.text?.append(ch, start, length) }

            override fun endElement(uri: String?, localName: String?, qName: String) {
                when (qName) {
                    "w:t" -> inT = false
                    "w:pPr" -> inPPr = false
                    "w:p" -> {
                        val p = stack.removeLastOrNull() ?: return
                        val t = clean(p.text.toString())
                        val c = cell
                        if (c != null) { if (t.isNotEmpty()) { if (c.isNotEmpty()) c.append(' '); c.append(t) } }
                        else if (t.isNotEmpty()) {
                            val level = headingStyle.matchEntire(p.style.trim())?.let { m -> m.groupValues[2].toIntOrNull() ?: 1 } ?: if (p.outline in 0..5) p.outline + 1 else 0
                            parts += when {
                                level > 0 -> "#".repeat(level.coerceAtMost(6)) + " " + t
                                p.listLevel >= 0 -> "  ".repeat(p.listLevel.coerceAtMost(4)) + "- " + t
                                else -> t
                            }
                        }
                    }
                    "w:tc" -> if (tableDepth == 1) { row?.add(cell?.toString().orEmpty()); cell = null }
                    "w:tr" -> if (tableDepth == 1) { row?.takeIf { r -> r.any { it.isNotBlank() } }?.let { r -> parts += ROW + r.joinToString(" | ") }; row = null }
                    "w:tbl" -> tableDepth--
                }
            }
        })
        return joinMarkdown(parts)
    }

    // ---- PowerPoint (pptx) ------------------------------------------------------------------------------------------------

    /** Ein Text je Folie in Reihenfolge der Präsentation: Titel, Inhalt, Notizen. Folien ohne Text liefern einen leeren String. */
    fun pptxSlides(zip: InputStream): List<String> {
        val files = entries(zip) { name ->
            name == "ppt/presentation.xml" || name == "ppt/_rels/presentation.xml.rels" ||
                (name.startsWith("ppt/slides/") && (name.endsWith(".xml") || name.endsWith(".rels"))) || (name.startsWith("ppt/notesSlides/") && name.endsWith(".xml"))
        }
        val presentation = files["ppt/presentation.xml"] ?: throw OfficeException("Das ist keine PowerPoint-Datei (ppt/presentation.xml fehlt)")
        // Reihenfolge der Folien: sldIdLst verweist über r:id auf Relationships
        val order = mutableListOf<String>()
        parse(presentation, object : DefaultHandler() {
            override fun startElement(uri: String?, localName: String?, qName: String, a: Attributes) { if (qName == "p:sldId") a.getValue("r:id")?.let { order += it } }
        })
        val targets = relationships(files["ppt/_rels/presentation.xml.rels"])
        val slidePaths = order.mapNotNull { id -> targets[id]?.target?.let { "ppt/" + it.removePrefix("/ppt/").removePrefix("../") } }
            .ifEmpty { files.keys.filter { Regex("ppt/slides/slide\\d+\\.xml").matches(it) }.sortedBy { Regex("\\d+").find(it.substringAfterLast('/'))!!.value.toInt() } }
        return slidePaths.map { path ->
            val bytes = files[path] ?: return@map ""
            val rels = relationships(files[path.substringBeforeLast('/') + "/_rels/" + path.substringAfterLast('/') + ".rels"])
            val notesPath = rels.values.firstOrNull { it.type.endsWith("/notesSlide") }?.target?.let { "ppt/" + it.removePrefix("../") }
            val slide = drawingParagraphs(bytes)
            val notes = notesPath?.let { files[it] }?.let { drawingParagraphs(it, notes = true) }?.second.orEmpty()
            buildString {
                slide.first.takeIf { it.isNotBlank() }?.let { append(it) }
                if (slide.second.isNotEmpty()) { if (isNotEmpty()) append("\n\n"); append(slide.second.joinToString("\n")) }
                if (notes.isNotEmpty()) { if (isNotEmpty()) append("\n\n"); append("Notizen: ").append(notes.joinToString(" ")) }
            }.trim()
        }
    }

    private data class Rel(val target: String, val type: String)

    private fun relationships(bytes: ByteArray?): Map<String, Rel> {
        if (bytes == null) return emptyMap()
        val out = linkedMapOf<String, Rel>()
        parse(bytes, object : DefaultHandler() {
            override fun startElement(uri: String?, localName: String?, qName: String, a: Attributes) {
                if (qName == "Relationship") out[a.getValue("Id").orEmpty()] = Rel(a.getValue("Target").orEmpty(), a.getValue("Type").orEmpty())
            }
        })
        return out
    }

    /** Titel und übrige Absätze einer Folie (DrawingML). [notes]: Notizseite, dort zählt nur das Textfeld, nicht Foliennummer oder Vorschaubild. */
    private fun drawingParagraphs(xml: ByteArray, notes: Boolean = false): Pair<String, List<String>> {
        var title = ""; val body = mutableListOf<String>()
        parse(xml, object : DefaultHandler() {
            var shapeType = ""; var inShape = false; var text = StringBuilder(); var inT = false; var inPara = false; var tableCells = mutableListOf<String>(); var inCell = false; var cell = StringBuilder()
            override fun startElement(uri: String?, localName: String?, qName: String, a: Attributes) {
                when (qName) {
                    "p:sp" -> { inShape = true; shapeType = "" }
                    "p:ph" -> if (inShape) shapeType = a.getValue("type").orEmpty()
                    "a:tc" -> { inCell = true; cell = StringBuilder() }
                    "a:p" -> { inPara = true; text = StringBuilder() }
                    "a:t" -> inT = true
                    "a:br" -> text.append(' ')
                }
            }
            override fun characters(ch: CharArray, start: Int, length: Int) { if (inT) text.append(ch, start, length) }
            override fun endElement(uri: String?, localName: String?, qName: String) {
                when (qName) {
                    "a:t" -> inT = false
                    "p:sp" -> inShape = false
                    "a:tc" -> { inCell = false; tableCells += cell.toString().trim() }
                    "a:tr" -> { if (tableCells.any { it.isNotBlank() }) body += tableCells.joinToString(" | "); tableCells = mutableListOf() }
                    "a:p" -> {
                        inPara = false
                        val t = clean(text.toString())
                        if (t.isEmpty()) return
                        if (inCell) { if (cell.isNotEmpty()) cell.append(' '); cell.append(t); return }
                        when {
                            shapeType in setOf("sldNum", "dt", "ftr", "hdr", "sldImg") -> Unit
                            notes && shapeType != "body" -> Unit
                            shapeType == "title" || shapeType == "ctrTitle" -> title = if (title.isEmpty()) t else "$title $t"
                            else -> body += t
                        }
                    }
                }
            }
        })
        return title to body
    }

    // ---- OpenDocument (odt, odp) ------------------------------------------------------------------------------------------

    fun odtToMarkdown(zip: InputStream): String {
        val xml = entries(zip) { it == "content.xml" }["content.xml"] ?: throw OfficeException("Das ist keine OpenDocument-Datei (content.xml fehlt)")
        val parts = mutableListOf<String>()
        parse(xml, object : DefaultHandler() {
            var text = StringBuilder(); var level = 0; var kind = ""; var listDepth = 0; var cells: MutableList<String>? = null; var cell: StringBuilder? = null
            override fun startElement(uri: String?, localName: String?, qName: String, a: Attributes) {
                when (qName) {
                    "text:h" -> { kind = "h"; level = a.getValue("text:outline-level")?.toIntOrNull() ?: 1; text = StringBuilder() }
                    "text:p" -> { kind = "p"; text = StringBuilder() }
                    "text:list" -> listDepth++
                    "text:tab" -> text.append(' ')
                    "text:line-break" -> text.append(' ')
                    "text:s" -> text.append(" ".repeat((a.getValue("text:c")?.toIntOrNull() ?: 1).coerceIn(1, 20)))
                    "table:table-row" -> cells = mutableListOf()
                    "table:table-cell" -> cell = StringBuilder()
                }
            }
            override fun characters(ch: CharArray, start: Int, length: Int) { if (kind.isNotEmpty()) text.append(ch, start, length) }
            override fun endElement(uri: String?, localName: String?, qName: String) {
                when (qName) {
                    "text:h", "text:p" -> {
                        val t = clean(text.toString()); val wasHeading = kind == "h"; kind = ""
                        val c = cell
                        if (c != null) { if (t.isNotEmpty()) { if (c.isNotEmpty()) c.append(' '); c.append(t) } }
                        else if (t.isNotEmpty()) parts += if (wasHeading) "#".repeat(level.coerceIn(1, 6)) + " " + t else if (listDepth > 0) "  ".repeat((listDepth - 1).coerceAtMost(4)) + "- " + t else t
                    }
                    "text:list" -> listDepth--
                    "table:table-cell" -> { cells?.add(cell?.toString().orEmpty()); cell = null }
                    "table:table-row" -> { cells?.takeIf { r -> r.any { it.isNotBlank() } }?.let { r -> parts += ROW + r.joinToString(" | ") }; cells = null }
                }
            }
        })
        return joinMarkdown(parts)
    }

    fun odpSlides(zip: InputStream): List<String> {
        val xml = entries(zip) { it == "content.xml" }["content.xml"] ?: throw OfficeException("Das ist keine OpenDocument-Datei (content.xml fehlt)")
        val slides = mutableListOf<String>()
        parse(xml, object : DefaultHandler() {
            var inPage = false; var inNotes = false; var frameClass = ""; var title = ""; val body = mutableListOf<String>(); val notes = mutableListOf<String>()
            var text = StringBuilder(); var inP = false
            override fun startElement(uri: String?, localName: String?, qName: String, a: Attributes) {
                when (qName) {
                    "draw:page" -> { inPage = true; title = ""; body.clear(); notes.clear() }
                    "presentation:notes" -> inNotes = true
                    "draw:frame" -> frameClass = a.getValue("presentation:class").orEmpty()
                    "text:p" -> { inP = true; text = StringBuilder() }
                    "text:tab", "text:line-break" -> if (inP) text.append(' ')
                    "text:s" -> if (inP) text.append(' ')
                }
            }
            override fun characters(ch: CharArray, start: Int, length: Int) { if (inP) text.append(ch, start, length) }
            override fun endElement(uri: String?, localName: String?, qName: String) {
                when (qName) {
                    "text:p" -> {
                        inP = false
                        val t = clean(text.toString())
                        if (t.isEmpty() || !inPage) return
                        when {
                            inNotes -> if (frameClass == "notes" || frameClass.isEmpty()) notes += t
                            frameClass in setOf("page-number", "date-time", "footer", "header") -> Unit
                            frameClass == "title" -> title = if (title.isEmpty()) t else "$title $t"
                            else -> body += t
                        }
                    }
                    "presentation:notes" -> inNotes = false
                    "draw:frame" -> frameClass = ""
                    "draw:page" -> {
                        inPage = false
                        slides += buildString {
                            if (title.isNotBlank()) append(title)
                            if (body.isNotEmpty()) { if (isNotEmpty()) append("\n\n"); append(body.joinToString("\n")) }
                            if (notes.isNotEmpty()) { if (isNotEmpty()) append("\n\n"); append("Notizen: ").append(notes.joinToString(" ")) }
                        }.trim()
                    }
                }
            }
        })
        return slides
    }
}

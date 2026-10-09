// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.ingest

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

class OfficeTextTest {
    private fun zip(vararg files: Pair<String, String>): ByteArrayInputStream {
        val bo = ByteArrayOutputStream()
        ZipOutputStream(bo).use { z -> files.forEach { (n, c) -> z.putNextEntry(ZipEntry(n)); z.write(c.toByteArray(Charsets.UTF_8)); z.closeEntry() } }
        return ByteArrayInputStream(bo.toByteArray())
    }

    private val W = "xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\""

    private fun p(text: String, style: String? = null, list: Int? = null) =
        "<w:p><w:pPr>${style?.let { "<w:pStyle w:val=\"$it\"/>" }.orEmpty()}${list?.let { "<w:numPr><w:ilvl w:val=\"$it\"/><w:numId w:val=\"1\"/></w:numPr>" }.orEmpty()}</w:pPr><w:r><w:t>$text</w:t></w:r></w:p>"

    @Test fun docxHeadingsListsAndTables() {
        val body = p("Sortierverfahren", "Heading1") + p("Quicksort teilt das Feld &amp; sortiert rekursiv.") + p("Pivot wählen", "berschrift2") +
            p("Erstes", list = 0) + p("Unterpunkt", list = 1) + p("Zweites", list = 0) +
            "<w:tbl><w:tr><w:tc>${p("Verfahren")}</w:tc><w:tc>${p("Laufzeit")}</w:tc></w:tr><w:tr><w:tc>${p("Heapsort")}</w:tc><w:tc>${p("O(n log n)")}</w:tc></w:tr></w:tbl>" +
            p("Schluss.")
        val md = OfficeText.docxToMarkdown(zip("word/document.xml" to "<w:document $W><w:body>$body</w:body></w:document>"))
        assertEquals("# Sortierverfahren\n\nQuicksort teilt das Feld & sortiert rekursiv.\n\n## Pivot wählen\n\n- Erstes\n  - Unterpunkt\n- Zweites\n\nVerfahren | Laufzeit\nHeapsort | O(n log n)\n\nSchluss.", md)
    }

    @Test fun docxTabsBreaksAndTextboxes() {
        val body = "<w:p><w:r><w:t>Vor</w:t></w:r><w:r><w:tab/></w:r><w:r><w:t>nach</w:t></w:r><w:r><w:br/></w:r><w:r><w:t>Zeile</w:t></w:r>" +
            "<w:r><w:txbxContent>${p("Im Textfeld")}</w:txbxContent></w:r><w:r><w:t> Ende</w:t></w:r></w:p>"
        val md = OfficeText.docxToMarkdown(zip("word/document.xml" to "<w:document $W><w:body>$body</w:body></w:document>"))
        assertTrue("Im Textfeld" in md, md)
        assertTrue("Vor nach Zeile Ende" in md, md)
    }

    @Test fun docxWithoutDocumentXmlFails() {
        assertThrows(OfficeText.OfficeException::class.java) { OfficeText.docxToMarkdown(zip("x.txt" to "nichts")) }
        assertThrows(OfficeText.OfficeException::class.java) { OfficeText.docxToMarkdown(ByteArrayInputStream("keine zip".toByteArray())) }
    }

    private val A = "xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\""

    private fun shape(type: String?, vararg paras: String) =
        "<p:sp><p:nvSpPr><p:nvPr>${type?.let { "<p:ph type=\"$it\"/>" }.orEmpty()}</p:nvPr></p:nvSpPr><p:txBody>${paras.joinToString("") { "<a:p><a:r><a:t>$it</a:t></a:r></a:p>" }}</p:txBody></p:sp>"

    @Test fun pptxSlidesInPresentationOrderWithTitlesAndNotes() {
        val slide1 = "<p:sld $A><p:cSld><p:spTree>${shape("title", "Heaps")}${shape(null, "Vollständiger Binärbaum", "Max-Heap")}${shape("sldNum", "1")}</p:spTree></p:cSld></p:sld>"
        val slide2 = "<p:sld $A><p:cSld><p:spTree>${shape("ctrTitle", "Graphen")}${shape("body", "BFS", "DFS")}</p:spTree></p:cSld></p:sld>"
        val notes2 = "<p:notes $A><p:cSld><p:spTree>${shape("sldImg")}${shape("body", "Hier Beispiel zeigen")}${shape("sldNum", "2")}</p:spTree></p:cSld></p:notes>"
        val slides = OfficeText.pptxSlides(
            zip(
                "ppt/presentation.xml" to "<p:presentation $A><p:sldIdLst><p:sldId id=\"256\" r:id=\"rId3\"/><p:sldId id=\"257\" r:id=\"rId2\"/></p:sldIdLst></p:presentation>",
                "ppt/_rels/presentation.xml.rels" to "<Relationships><Relationship Id=\"rId2\" Type=\"x/slide\" Target=\"slides/slide1.xml\"/><Relationship Id=\"rId3\" Type=\"x/slide\" Target=\"slides/slide2.xml\"/></Relationships>",
                "ppt/slides/slide1.xml" to slide1, "ppt/slides/slide2.xml" to slide2,
                "ppt/slides/_rels/slide2.xml.rels" to "<Relationships><Relationship Id=\"rId1\" Type=\"http://x/relationships/notesSlide\" Target=\"../notesSlides/notesSlide2.xml\"/></Relationships>",
                "ppt/notesSlides/notesSlide2.xml" to notes2,
            ),
        )
        // Reihenfolge laut sldIdLst: erst slide2, dann slide1
        assertEquals(listOf("Graphen\n\nBFS\nDFS\n\nNotizen: Hier Beispiel zeigen", "Heaps\n\nVollständiger Binärbaum\nMax-Heap"), slides)
    }

    @Test fun pptxTableRows() {
        val table = "<p:graphicFrame><a:tbl><a:tr><a:tc><a:txBody><a:p><a:r><a:t>A</a:t></a:r></a:p></a:txBody></a:tc><a:tc><a:txBody><a:p><a:r><a:t>B</a:t></a:r></a:p></a:txBody></a:tc></a:tr></a:tbl></p:graphicFrame>"
        val slide = "<p:sld $A><p:cSld><p:spTree>${shape("title", "Tabelle")}$table</p:spTree></p:cSld></p:sld>"
        val slides = OfficeText.pptxSlides(zip("ppt/presentation.xml" to "<p:presentation $A><p:sldIdLst/></p:presentation>", "ppt/slides/slide1.xml" to slide))
        assertEquals(listOf("Tabelle\n\nA | B"), slides)    // ohne sldIdLst: Dateinamen-Reihenfolge
    }

    private val O = "xmlns:text=\"urn:oasis:names:tc:opendocument:xmlns:text:1.0\" xmlns:table=\"urn:oasis:names:tc:opendocument:xmlns:table:1.0\" xmlns:draw=\"urn:oasis:names:tc:opendocument:xmlns:drawing:1.0\" xmlns:presentation=\"urn:oasis:names:tc:opendocument:xmlns:presentation:1.0\""

    @Test fun odtHeadingsListsTables() {
        val content = "<office:document-content $O><office:body><office:text>" +
            "<text:h text:outline-level=\"1\">Titel</text:h><text:p>Ein <text:span>Absatz</text:span> mit<text:s text:c=\"2\"/>Leerzeichen und<text:tab/>Tab.</text:p>" +
            "<text:list><text:list-item><text:p>Eins</text:p></text:list-item><text:list-item><text:p>Zwei</text:p></text:list-item></text:list>" +
            "<table:table><table:table-row><table:table-cell><text:p>x</text:p></table:table-cell><table:table-cell><text:p>y</text:p></table:table-cell></table:table-row></table:table>" +
            "</office:text></office:body></office:document-content>"
        val md = OfficeText.odtToMarkdown(zip("content.xml" to content))
        assertEquals("# Titel\n\nEin Absatz mit Leerzeichen und Tab.\n\n- Eins\n- Zwei\n\nx | y", md)
    }

    @Test fun odpSlidesWithTitleAndNotes() {
        fun page(title: String, body: String, note: String) = "<draw:page draw:name=\"$title\"><draw:frame presentation:class=\"title\"><draw:text-box><text:p>$title</text:p></draw:text-box></draw:frame>" +
            "<draw:frame presentation:class=\"outline\"><draw:text-box><text:p>$body</text:p></draw:text-box></draw:frame>" +
            "<presentation:notes><draw:frame presentation:class=\"notes\"><draw:text-box><text:p>$note</text:p></draw:text-box></draw:frame></presentation:notes></draw:page>"
        val content = "<office:document-content $O><office:body><office:presentation>${page("Eins", "Text eins", "Notiz eins")}${page("Zwei", "Text zwei", "")}</office:presentation></office:body></office:document-content>"
        assertEquals(listOf("Eins\n\nText eins\n\nNotizen: Notiz eins", "Zwei\n\nText zwei"), OfficeText.odpSlides(zip("content.xml" to content)))
    }

    @Test fun oversizedEntriesAreRefused() {
        // Zip-Bombe: entpackt weit über der Grenze; wird abgelehnt, ohne alles zu lesen
        val bomb = zip("word/document.xml" to "a".repeat(5000))
        assertThrows(OfficeText.OfficeException::class.java) { OfficeText.entries(bomb, maxEntryBytes = 1000) { true } }
    }

    @Test fun longParagraphsAreKept() {
        val big = "<w:document $W><w:body><w:p><w:r><w:t>" + "a".repeat(1000) + "</w:t></w:r></w:p></w:body></w:document>"
        assertEquals(1000, OfficeText.docxToMarkdown(zip("word/document.xml" to big)).length)
    }
}

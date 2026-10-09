// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ingest

import de.edgebird.lernsystem.core.ingest.BlockKind
import de.edgebird.lernsystem.core.ingest.Chunker
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.io.ByteArrayOutputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

class OfficeLoaderTest {
    private fun zip(vararg files: Pair<String, String>): ByteArray {
        val bo = ByteArrayOutputStream()
        ZipOutputStream(bo).use { z -> files.forEach { (n, c) -> z.putNextEntry(ZipEntry(n)); z.write(c.toByteArray()); z.closeEntry() } }
        return bo.toByteArray()
    }

    private val A = "xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\""
    private fun shape(type: String?, vararg paras: String) = "<p:sp><p:nvSpPr><p:nvPr>${type?.let { "<p:ph type=\"$it\"/>" }.orEmpty()}</p:nvPr></p:nvSpPr><p:txBody>${paras.joinToString("") { "<a:p><a:r><a:t>$it</a:t></a:r></a:p>" }}</p:txBody></p:sp>"

    @Test fun pptxBecomesSlidesWithNumbers() {
        val s1 = "<p:sld $A><p:cSld><p:spTree>${shape("title", "Einführung")}${shape(null, "Ziel der Vorlesung")}</p:spTree></p:cSld></p:sld>"
        val s2 = "<p:sld $A><p:cSld><p:spTree></p:spTree></p:cSld></p:sld>"      // Folie nur mit Bild
        val s3 = "<p:sld $A><p:cSld><p:spTree>${shape("title", "Heaps")}${shape(null, "Max-Heap")}</p:spTree></p:cSld></p:sld>"
        val bytes = zip("ppt/presentation.xml" to "<p:presentation $A/>", "ppt/slides/slide1.xml" to s1, "ppt/slides/slide2.xml" to s2, "ppt/slides/slide3.xml" to s3)
        val doc = OfficeDocumentLoader().load(DocumentSource("k", "vorlesung.pptx") { bytes.inputStream() })
        assertEquals(listOf(1, 3), doc.blocks.map { it.page })              // Foliennummern bleiben, die leere Folie 2 fehlt
        assertTrue(doc.blocks.all { it.kind == BlockKind.SLIDE })
        assertEquals(1, doc.emptyPages)
        // Der Chunker nennt die Fundstelle „Folie n“
        assertEquals(listOf("Folie 1", "Folie 3"), Chunker.chunk(doc).map { it.location })
    }

    @Test fun docxWithHeadingsGivesHeaderPaths() {
        val W = "xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\""
        fun p(t: String, st: String? = null) = "<w:p><w:pPr>${st?.let { "<w:pStyle w:val=\"$it\"/>" }.orEmpty()}</w:pPr><w:r><w:t>$t</w:t></w:r></w:p>"
        val body = p("Algorithmen", "Heading1") + p("Sortieren", "Heading2") + p("Quicksort teilt das Feld rekursiv am Pivotelement in zwei Teile. ".repeat(6)) + p("Suchen", "Heading2") + p("Binäre Suche halbiert den Suchraum. ".repeat(6))
        val bytes = zip("word/document.xml" to "<w:document $W><w:body>$body</w:body></w:document>")
        val doc = OfficeDocumentLoader().load(DocumentSource("k", "skript.docx") { bytes.inputStream() })
        assertTrue(doc.isMarkdown)
        val locations = Chunker.chunk(doc).map { it.location }
        assertTrue(locations.any { "Sortieren" in it } && locations.any { "Suchen" in it }, locations.toString())
    }

    @Test fun brokenFilesGiveReadableErrors() {
        val e = assertThrows(LoadException::class.java) { OfficeDocumentLoader().load(DocumentSource("k", "kaputt.docx") { "keine zip datei".toByteArray().inputStream() }) }
        assertTrue(e.message!!.isNotBlank())
        assertEquals(setOf("docx", "pptx", "odt", "odp"), OfficeDocumentLoader().extensions)
    }
}

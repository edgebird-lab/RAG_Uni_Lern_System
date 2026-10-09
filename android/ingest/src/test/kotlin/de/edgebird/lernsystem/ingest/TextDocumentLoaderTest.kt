// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ingest

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class TextDocumentLoaderTest {
    private val loader = TextDocumentLoader()

    private fun load(name: String, bytes: ByteArray) = loader.load(DocumentSource("k", name) { bytes.inputStream() })

    @Test
    fun `UTF-8 mit BOM wird ohne BOM gelesen`() {
        val doc = load("a.txt", byteArrayOf(0xEF.toByte(), 0xBB.toByte(), 0xBF.toByte()) + "Grüße".toByteArray())
        assertEquals("Grüße", doc.text)
    }

    @Test
    fun `Latin-1 wird als Rueckfall gelesen`() {
        assertEquals("Äpfel", load("a.txt", "Äpfel".toByteArray(Charsets.ISO_8859_1)).text)
    }

    @Test
    fun `Markdown-Endungen setzen isMarkdown, txt nicht`() {
        assertTrue(load("a.md", "# T\ntext".toByteArray()).isMarkdown)
        assertTrue(load("a.markdown", "# T\ntext".toByteArray()).isMarkdown)
        assertFalse(load("a.txt", "# T\ntext".toByteArray()).isMarkdown)
    }

    @Test
    fun `Endung wird unabhaengig von Gross-Kleinschreibung erkannt`() {
        assertEquals("pdf", DocumentSource("k", "Skript.PDF") { ByteArray(0).inputStream() }.extension)
    }
}

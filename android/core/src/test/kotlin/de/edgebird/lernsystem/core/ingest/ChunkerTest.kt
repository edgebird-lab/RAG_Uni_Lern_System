// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.ingest

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class ChunkerTest {
    private val cfg = ChunkerConfig(size = 200, overlap = 40, minChars = 50)

    private fun para(prefix: String, n: Int) = (1..n).joinToString(" ") { "$prefix$it." }

    @Test
    fun `kurzer Seitenblock bleibt ein Chunk mit Seitenangabe`() {
        val chunks = Chunker.chunk(LoadedDoc("x", listOf(Block("Ein kurzer Text mit genug Zeichen.", page = 3))), cfg)
        assertEquals(1, chunks.size)
        assertEquals("Seite 3", chunks[0].location)
        assertEquals(3, chunks[0].page)
        assertEquals(0, chunks[0].index)
    }

    @Test
    fun `Folien werden als Folie bezeichnet`() {
        val chunks = Chunker.chunk(LoadedDoc("x", listOf(Block("Folientext.", page = 2, kind = BlockKind.SLIDE))), cfg.copy(minChars = 1))
        assertEquals("Folie 2", chunks.single().location)
    }

    @Test
    fun `Block ohne Seite hat Ort Dokument`() {
        assertEquals("Dokument", Chunker.chunk(LoadedDoc("x", listOf(Block("Text."))), cfg.copy(minChars = 1)).single().location)
    }

    @Test
    fun `langer Text wird geschnitten und Chunks bleiben nahe der Zielgroesse`() {
        val text = (1..30).joinToString("\n\n") { para("Satz", 6) }
        val chunks = Chunker.chunk(LoadedDoc(text, listOf(Block(text, 1))), cfg)
        assertTrue(chunks.size > 5)
        // Zielgroesse plus Ueberlappung plus Trennzeichen
        assertTrue(chunks.all { it.text.length <= cfg.size + cfg.overlap + 2 }, "zu lange Chunks: ${chunks.maxOf { it.text.length }}")
        assertEquals(chunks.indices.toList(), chunks.map { it.index })
    }

    @Test
    fun `aufeinanderfolgende Chunks ueberlappen`() {
        val text = (1..40).joinToString(" ") { "Wort$it" }
        val chunks = Chunker.chunk(LoadedDoc(text, listOf(Block(text, 1))), cfg)
        for (i in 1 until chunks.size) {
            val tail = chunks[i - 1].text.takeLast(15).trim()
            assertTrue(tail.isNotEmpty() && chunks[i].text.contains(tail.split(" ").last()), "kein Overlap bei $i")
        }
    }

    @Test
    fun `unterbrechungsloser Text wird hart geschnitten`() {
        val text = "a".repeat(500)
        val pieces = Chunker.splitRecursive(text, 200, 40)
        assertTrue(pieces.size >= 3)
        assertTrue(pieces.all { it.length <= 200 })
    }

    @Test
    fun `Markdown wird an Ueberschriften geschnitten, Pfad steht vor dem Text`() {
        val md = "# Teil I\n\n## Kosten\n\nKosten sind bewertete Gueter.\n\n## Erloese\n\nErloese sind Einnahmen aus Verkauf.\n"
        val chunks = Chunker.chunk(LoadedDoc(md, emptyList(), isMarkdown = true), cfg.copy(minChars = 1))
        assertEquals(2, chunks.size)
        assertEquals("Teil I › Kosten", chunks[0].headerPath)
        assertTrue(chunks[0].text.startsWith("[Teil I › Kosten]\n"))
        assertEquals("Teil I › Erloese", chunks[1].location)
    }

    @Test
    fun `Ueberschriften-Stack springt auf gleiche Ebene zurueck`() {
        val sections = Chunker.splitMarkdownSections("# A\n## B\ntext b\n## C\ntext c\n# D\ntext d")
        assertEquals(listOf("A › B", "A › C", "D"), sections.map { it.first })
    }

    @Test
    fun `Tabellen werden nur an Zeilengrenzen geschnitten`() {
        val rows = (1..30).joinToString("\n") { "| Zeile $it | Wert ${it * 10} | Info |" }
        val chunks = Chunker.splitRecursive(rows, 200, 60)
        assertTrue(chunks.size > 1)
        for (c in chunks) for (ln in c.split("\n")) assertTrue(ln.startsWith("| Zeile") && ln.endsWith("|"), "Zelle zerrissen: '$ln'")
    }

    @Test
    fun `zu kleine Chunks werden mit dem vorherigen zusammengefuehrt`() {
        val a = para("Satz", 20) // > size, ergibt mehrere Stuecke
        val doc = LoadedDoc(a, listOf(Block(a, 1)))
        val chunks = Chunker.chunk(doc, ChunkerConfig(size = 200, overlap = 0, minChars = 150))
        assertTrue(chunks.all { it.text.length >= 150 || chunks.size == 1 }, "Rest-Chunk nicht zusammengefuehrt")
    }

    @Test
    fun `leeres Dokument ergibt keine Chunks`() {
        assertTrue(Chunker.chunk(LoadedDoc("", listOf(Block("   ", 1))), cfg).isEmpty())
    }
}

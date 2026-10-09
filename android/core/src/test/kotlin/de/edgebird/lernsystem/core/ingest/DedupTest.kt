// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.ingest

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class DedupTest {
    private val known = listOf(KnownDocument(1, "a.pdf", "h1"), KnownDocument(2, "b.pdf", "h2"))

    @Test
    fun `neues Dokument`() = assertEquals(DedupAction.NEW, Dedup.decide("c.pdf", "h3", known).action)

    @Test
    fun `gleicher Pfad und Inhalt`() = assertEquals(DedupAction.SKIP_UNCHANGED, Dedup.decide("a.pdf", "h1", known).action)

    @Test
    fun `gleicher Inhalt unter anderem Pfad`() {
        val d = Dedup.decide("kopie.pdf", "h2", known)
        assertEquals(DedupAction.SKIP_DUPLICATE, d.action)
        assertEquals(2L, d.existing?.id)
    }

    @Test
    fun `geaenderter Inhalt ersetzt das Dokument`() {
        val d = Dedup.decide("a.pdf", "neu", known)
        assertEquals(DedupAction.REPLACE, d.action)
        assertEquals(1L, d.existing?.id)
    }

    @Test
    fun `identische Chunks werden nur einmal behalten`() {
        val a = Chunk("Kopfzeile Skript\nSeite", "Seite 1")
        val b = Chunk("KOPFZEILE   skript seite", "Seite 2")
        val c = Chunk("Anderer Inhalt", "Seite 3")
        assertEquals(listOf(a, c), ChunkDedup.distinct(listOf(a, b, c)))
    }
}

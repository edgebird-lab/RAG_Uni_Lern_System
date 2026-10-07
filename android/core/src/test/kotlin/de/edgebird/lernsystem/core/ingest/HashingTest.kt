package de.edgebird.lernsystem.core.ingest

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotEquals
import org.junit.jupiter.api.Test

class HashingTest {
    @Test
    fun `SHA-256 Referenzwert`() {
        assertEquals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", Hashing.sha256Hex("abc"))
    }

    @Test
    fun `Inhalts-Hash ignoriert Whitespace-Unterschiede`() {
        assertEquals(Hashing.contentHash("a  b\r\nc"), Hashing.contentHash("a b\nc"))
        assertNotEquals(Hashing.contentHash("a b"), Hashing.contentHash("a c"))
    }

    @Test
    fun `Chunk-Hash ignoriert Gross-Kleinschreibung und Umbrueche`() {
        assertEquals(Hashing.chunkHash("Hallo   Welt"), Hashing.chunkHash("hallo\nwelt"))
    }
}

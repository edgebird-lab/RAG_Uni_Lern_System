package de.edgebird.lernsystem.core.audio

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test

class WavTest {
    private val fmt = Wav.Format(1, 22050, 16)
    private fun wav(n: Int, v: Byte = 1) = Wav.build(fmt, ByteArray(n) { v })

    @Test fun `gebaute Datei laesst sich wieder lesen`() {
        val p = Wav.parse(wav(1000))!!
        assertEquals(1, p.format.channels); assertEquals(22050, p.format.sampleRate); assertEquals(16, p.format.bitsPerSample)
        assertEquals(1000, p.data.size)
    }

    @Test fun `Stuecke werden mit kurzer Pause zusammengefuegt`() {
        val merged = Wav.merge(listOf(wav(2000, 1), wav(3000, 2)), pauseMs = 100)!!
        val p = Wav.parse(merged)!!
        val silence = 22050 * 100 / 1000 * 2
        assertEquals(2000 + silence + 3000, p.data.size)
        assertEquals(1, p.data[0].toInt()); assertEquals(2, p.data[p.data.size - 1].toInt())
        assertEquals(0, p.data[2000].toInt())
    }

    @Test fun `unlesbare Stuecke und fremde Formate werden uebersprungen`() {
        val stereo = Wav.build(Wav.Format(2, 22050, 16), ByteArray(400))
        val merged = Wav.merge(listOf(byteArrayOf(1, 2, 3), wav(100), stereo, wav(100)), pauseMs = 0)!!
        assertEquals(200, Wav.parse(merged)!!.data.size)
        assertNull(Wav.merge(listOf(byteArrayOf(1, 2, 3))))
    }

    @Test fun `fehlende Laengenangabe der Nutzdaten wird toleriert`() {
        val w = wav(500).also { for (i in 40..43) it[i] = 0 }     // data-Größe = 0 (Streaming)
        assertEquals(500, Wav.parse(w)!!.data.size)
    }
}

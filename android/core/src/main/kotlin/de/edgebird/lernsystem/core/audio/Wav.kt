// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.audio

import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Setzt mehrere WAV-Stücke (PCM, gleiches Format) zu einer Datei zusammen, z. B. die Teile einer vorgelesenen Zusammenfassung. */
object Wav {
    class Format(val channels: Int, val sampleRate: Int, val bitsPerSample: Int)
    class Parsed(val format: Format, val data: ByteArray)

    private fun le32(b: ByteArray, o: Int) = ByteBuffer.wrap(b, o, 4).order(ByteOrder.LITTLE_ENDIAN).int
    private fun le16(b: ByteArray, o: Int) = ByteBuffer.wrap(b, o, 2).order(ByteOrder.LITTLE_ENDIAN).short.toInt() and 0xFFFF
    private fun tag(b: ByteArray, o: Int) = if (o + 4 <= b.size) String(b, o, 4, Charsets.US_ASCII) else ""

    /** Liest Format und Nutzdaten; `null`, wenn es keine PCM-WAV-Datei ist. Eine fehlende oder falsche Längenangabe der Nutzdaten wird toleriert (Streaming-Dateien). */
    fun parse(bytes: ByteArray): Parsed? {
        if (bytes.size < 44 || tag(bytes, 0) != "RIFF" || tag(bytes, 8) != "WAVE") return null
        var pos = 12
        var format: Format? = null
        while (pos + 8 <= bytes.size) {
            val id = tag(bytes, pos)
            val size = le32(bytes, pos + 4)
            val body = pos + 8
            when (id) {
                "fmt " -> {
                    if (le16(bytes, body) != 1) return null                        // nur PCM
                    format = Format(le16(bytes, body + 2), le32(bytes, body + 4), le16(bytes, body + 14))
                }
                "data" -> {
                    val f = format ?: return null
                    val end = if (size <= 0 || body + size > bytes.size) bytes.size else body + size
                    return Parsed(f, bytes.copyOfRange(body, end))
                }
            }
            if (size < 0) return null
            pos = body + size + (size and 1)
        }
        return null
    }

    /** Eine WAV-Datei aus [format] und den PCM-Daten. */
    fun build(format: Format, data: ByteArray): ByteArray {
        val out = ByteArrayOutputStream(44 + data.size)
        val h = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
        val blockAlign = format.channels * format.bitsPerSample / 8
        h.put("RIFF".toByteArray()).putInt(36 + data.size).put("WAVE".toByteArray())
        h.put("fmt ".toByteArray()).putInt(16).putShort(1).putShort(format.channels.toShort()).putInt(format.sampleRate).putInt(format.sampleRate * blockAlign)
            .putShort(blockAlign.toShort()).putShort(format.bitsPerSample.toShort())
        h.put("data".toByteArray()).putInt(data.size)
        out.write(h.array()); out.write(data)
        return out.toByteArray()
    }

    /** Fügt die Stücke zusammen. Stücke mit anderem Format als das erste werden übersprungen; `null`, wenn kein Stück lesbar ist. */
    fun merge(parts: List<ByteArray>, pauseMs: Int = 350): ByteArray? {
        val parsed = parts.mapNotNull { parse(it) }
        val first = parsed.firstOrNull() ?: return null
        val f = first.format
        val silence = ByteArray(f.sampleRate * pauseMs / 1000 * f.channels * f.bitsPerSample / 8)   // kurze Pause zwischen den Stücken
        val data = ByteArrayOutputStream()
        parsed.filter { it.format.channels == f.channels && it.format.sampleRate == f.sampleRate && it.format.bitsPerSample == f.bitsPerSample }.forEachIndexed { i, p ->
            if (i > 0) data.write(silence)
            data.write(p.data)
        }
        return build(f, data.toByteArray())
    }
}

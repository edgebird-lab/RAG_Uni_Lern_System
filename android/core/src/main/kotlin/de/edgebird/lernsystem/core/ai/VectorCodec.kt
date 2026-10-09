// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.ai

import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.sqrt

/** Umwandlung von Embedding-Vektoren in/aus Bytes (float32 little-endian) und einfache Vektor-Mathematik. */
object VectorCodec {
    fun encode(v: FloatArray): ByteArray {
        val bb = ByteBuffer.allocate(v.size * 4).order(ByteOrder.LITTLE_ENDIAN)
        v.forEach { bb.putFloat(it) }
        return bb.array()
    }

    fun decode(bytes: ByteArray): FloatArray {
        val fb = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN).asFloatBuffer()
        return FloatArray(fb.remaining()).also { fb.get(it) }
    }

    fun dot(a: FloatArray, b: FloatArray): Float {
        require(a.size == b.size) { "Dimensionen passen nicht: ${a.size} vs ${b.size}" }
        var s = 0f
        for (i in a.indices) s += a[i] * b[i]
        return s
    }

    fun normalize(v: FloatArray): FloatArray {
        var n = 0f
        v.forEach { n += it * it }
        val norm = sqrt(n)
        return if (norm == 0f) v else FloatArray(v.size) { v[it] / norm }
    }
}

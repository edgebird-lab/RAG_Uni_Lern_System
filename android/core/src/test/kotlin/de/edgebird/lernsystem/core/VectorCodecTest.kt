// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core

import de.edgebird.lernsystem.core.ai.VectorCodec
import org.junit.jupiter.api.Assertions.assertArrayEquals
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class VectorCodecTest {
    @Test
    fun `Roundtrip erhaelt die Werte`() {
        val v = floatArrayOf(0.1f, -2.5f, 3.14159f, 0f)
        assertArrayEquals(v, VectorCodec.decode(VectorCodec.encode(v)))
        assertEquals(16, VectorCodec.encode(v).size)
    }

    @Test
    fun `normalize ergibt Laenge 1`() {
        val n = VectorCodec.normalize(floatArrayOf(3f, 4f))
        assertEquals(1f, VectorCodec.dot(n, n), 1e-6f)
    }

    @Test
    fun `dot`() = assertEquals(11f, VectorCodec.dot(floatArrayOf(1f, 2f), floatArrayOf(3f, 4f)))
}

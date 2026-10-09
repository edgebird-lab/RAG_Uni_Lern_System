// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.search

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class FusionTest {
    @Test
    fun `Treffer in beiden Listen gewinnen`() {
        val r = Fusion.rrf(listOf(listOf(1L, 2L, 3L), listOf(3L, 4L, 1L)))
        assertEquals(listOf(1L, 3L, 2L, 4L), r.map { it.first })
    }

    @Test
    fun `Score folgt der RRF-Formel`() {
        val r = Fusion.rrf(listOf(listOf(7L)), k = 60)
        assertEquals(1.0 / 61, r.single().second, 1e-12)
    }

    @Test
    fun `Gewichte verschieben die Reihenfolge`() {
        val r = Fusion.rrf(listOf(listOf(1L), listOf(2L)), weights = listOf(1.0, 3.0))
        assertEquals(listOf(2L, 1L), r.map { it.first })
    }

    @Test
    fun `leere Listen`() = assertEquals(emptyList<Pair<Long, Double>>(), Fusion.rrf(listOf(emptyList(), emptyList())))
}

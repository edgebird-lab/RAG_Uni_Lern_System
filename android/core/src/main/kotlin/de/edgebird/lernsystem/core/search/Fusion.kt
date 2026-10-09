// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.search

/** Rangfusion mehrerer Trefferlisten (Reciprocal Rank Fusion, wie in der PC-App). */
object Fusion {
    /**
     * @param rankings je Verfahren die IDs, beste zuerst
     * @param weights Gewicht je Verfahren
     * @return IDs mit Score, beste zuerst; bei Gleichstand gewinnt der zuerst gesehene Treffer
     */
    fun rrf(rankings: List<List<Long>>, weights: List<Double> = rankings.map { 1.0 }, k: Int = 60): List<Pair<Long, Double>> {
        require(rankings.size == weights.size) { "Gewichte passen nicht zu den Listen" }
        val scores = LinkedHashMap<Long, Double>()
        rankings.forEachIndexed { r, ids ->
            ids.forEachIndexed { rank, id -> scores[id] = (scores[id] ?: 0.0) + weights[r] / (k + rank + 1) }
        }
        return scores.entries.sortedByDescending { it.value }.map { it.key to it.value }
    }
}

// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.ai

import kotlinx.coroutines.flow.Flow

/** Sampling-Parameter fuer eine Generierung. */
data class GenerationParams(
    val maxTokens: Int = 512,
    val temperature: Float = 0.3f,
    val topP: Float = 0.95f,
    val stop: List<String> = emptyList(),
    /** Systemanweisung; wird vom Chat-Template des Modells eingebaut. */
    val system: String? = null,
    /** Bisheriger Gesprächsverlauf als (Frage, Antwort), älteste zuerst. */
    val history: List<Pair<String, String>> = emptyList(),
)

/** Port fuer das lokale Sprachmodell. Implementierungen liegen im Modul `ai`. */
interface LlmEngine : AutoCloseable {
    /** Laedt das Modell (idempotent). */
    suspend fun load()

    /** Streamt die Antwort Token fuer Token. Abbruch des Collectors bricht die Generierung ab. */
    fun generate(prompt: String, params: GenerationParams = GenerationParams()): Flow<String>
}

/** Port fuer das lokale Embedding-Modell. */
interface Embedder : AutoCloseable {
    val dimensions: Int

    suspend fun load()

    suspend fun embed(texts: List<String>): List<FloatArray>
}

/** Messwerte der letzten Generierung (nur wenn die Engine sie erfasst). */
data class GenerationStats(
    val ttftSeconds: Double,
    val prefillTokens: Int,
    val prefillTokensPerSecond: Double,
    val decodeTokens: Int,
    val decodeTokensPerSecond: Double,
)

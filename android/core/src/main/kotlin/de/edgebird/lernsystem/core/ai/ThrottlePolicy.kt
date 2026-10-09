// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.ai

enum class PauseReason { HOT, LOW_BATTERY }

/** Entscheidet, ob rechenintensive Hintergrundarbeit (Embedding) pausieren soll. */
object ThrottlePolicy {
    /** Entspricht `PowerManager.THERMAL_STATUS_MODERATE`: ab hier drosselt das System bereits selbst. */
    const val THERMAL_MODERATE = 2
    const val MIN_BATTERY_PERCENT = 20

    fun decide(charging: Boolean, batteryPercent: Int, thermalStatus: Int): PauseReason? = when {
        thermalStatus >= THERMAL_MODERATE -> PauseReason.HOT
        !charging && batteryPercent in 0 until MIN_BATTERY_PERCENT -> PauseReason.LOW_BATTERY
        else -> null
    }
}

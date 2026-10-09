// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core

import de.edgebird.lernsystem.core.ai.PauseReason
import de.edgebird.lernsystem.core.ai.ThrottlePolicy
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Test

class ThrottlePolicyTest {
    @Test
    fun `normaler Betrieb laeuft weiter`() = assertNull(ThrottlePolicy.decide(charging = false, batteryPercent = 60, thermalStatus = 0))

    @Test
    fun `Hitze pausiert auch am Ladegeraet`() {
        assertEquals(PauseReason.HOT, ThrottlePolicy.decide(true, 90, 2))
        assertEquals(PauseReason.HOT, ThrottlePolicy.decide(false, 90, 4))
    }

    @Test
    fun `leerer Akku pausiert nur ohne Ladegeraet`() {
        assertEquals(PauseReason.LOW_BATTERY, ThrottlePolicy.decide(false, 15, 0))
        assertNull(ThrottlePolicy.decide(true, 15, 0))
    }

    @Test
    fun `unbekannter Akkustand pausiert nicht`() = assertNull(ThrottlePolicy.decide(false, -1, 0))

    @Test
    fun `Grenzwert 20 Prozent laeuft noch`() = assertNull(ThrottlePolicy.decide(false, 20, 1))
}

// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.work

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import java.time.Duration
import java.time.LocalDateTime

class ReminderWorkTest {
    @Test fun `noch heute, wenn die Uhrzeit nicht vorbei ist`() =
        assertEquals(Duration.ofHours(2), ReminderWork.delayUntil(LocalDateTime.of(2026, 10, 8, 16, 0), 18, 0))

    @Test fun `morgen, wenn die Uhrzeit schon vorbei ist`() =
        assertEquals(Duration.ofHours(22), ReminderWork.delayUntil(LocalDateTime.of(2026, 10, 8, 20, 0), 18, 0))

    @Test fun `genau jetzt zaehlt als vorbei`() =
        assertEquals(Duration.ofDays(1), ReminderWork.delayUntil(LocalDateTime.of(2026, 10, 8, 18, 0), 18, 0))
}

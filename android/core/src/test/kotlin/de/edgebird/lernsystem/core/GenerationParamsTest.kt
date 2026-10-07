package de.edgebird.lernsystem.core

import de.edgebird.lernsystem.core.ai.GenerationParams
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class GenerationParamsTest {
    @Test
    fun `Standardwerte sind konservativ`() {
        val p = GenerationParams()
        assertEquals(512, p.maxTokens)
        assertEquals(0.3f, p.temperature)
    }
}

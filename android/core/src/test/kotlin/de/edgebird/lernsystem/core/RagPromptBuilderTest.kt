// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core

import de.edgebird.lernsystem.core.rag.Passage
import de.edgebird.lernsystem.core.rag.RagPromptBuilder
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class RagPromptBuilderTest {
    @Test
    fun `Quellen werden nummeriert und die Frage steht am Ende`() {
        val p = RagPromptBuilder.build("Was ist X?", listOf(Passage("a.md", "Text A"), Passage("b.md", "Text B")))
        assertTrue("[1] (a.md)\nText A" in p.user)
        assertTrue("[2] (b.md)\nText B" in p.user)
        assertTrue(p.user.trimEnd().endsWith("Frage: Was ist X?"))
    }

    @Test
    fun `System-Prompt nennt die Verweigerungsformel`() {
        assertTrue(RagPromptBuilder.NOT_FOUND in RagPromptBuilder.build("?", emptyList()).system)
    }
}

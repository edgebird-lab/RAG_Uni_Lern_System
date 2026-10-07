package de.edgebird.lernsystem.core

import de.edgebird.lernsystem.core.rag.EmbeddingPrompts
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class EmbeddingPromptsTest {
    @Test
    fun `Frage und Dokument folgen dem EmbeddingGemma-Format`() {
        assertEquals("task: question answering | query: Was?", EmbeddingPrompts.query(" Was? "))
        assertEquals("title: none | text: Inhalt", EmbeddingPrompts.document("Inhalt"))
        assertEquals("title: Art 1 | text: Inhalt", EmbeddingPrompts.document("Inhalt", "Art 1"))
    }
}

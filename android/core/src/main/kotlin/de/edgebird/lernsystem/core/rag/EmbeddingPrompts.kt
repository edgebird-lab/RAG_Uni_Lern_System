package de.edgebird.lernsystem.core.rag

/** Aufgabenpräfixe für EmbeddingGemma (asymmetrische Suche: Frage gegen Dokument). */
object EmbeddingPrompts {
    fun query(question: String) = "task: question answering | query: ${question.trim()}"

    fun document(text: String, title: String? = null) = "title: ${title?.takeIf { it.isNotBlank() } ?: "none"} | text: ${text.trim()}"
}

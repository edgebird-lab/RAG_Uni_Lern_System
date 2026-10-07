package de.edgebird.lernsystem.core.rag

/** Ein abgerufener Textabschnitt mit Herkunftsangabe. */
data class Passage(val source: String, val text: String)

/** Ergebnis des Prompt-Baus: Systemanweisung und Nutzer-Nachricht getrennt (Chat-Template-tauglich). */
data class RagPrompt(val system: String, val user: String)

/** STRICT ist der bisherige Standard; LENIENT erlaubt Umschreibungen (gegen falsche Verweigerungen bei umformulierten Fragen). */
enum class PromptStyle { STRICT, LENIENT }

object RagPromptBuilder {
    const val NOT_FOUND = "Nicht im Material gefunden."

    private val SYSTEM = """
        Du beantwortest Fragen ausschließlich anhand der nummerierten Quellen im Kontext.
        Antworte knapp auf Deutsch und nenne die Nummer der verwendeten Quelle, z. B. [2].
        Steht die Antwort nicht in den Quellen, antworte genau: $NOT_FOUND
        Verwende kein Wissen außerhalb der Quellen.
    """.trimIndent()

    private val SYSTEM_LENIENT = """
        Du beantwortest Fragen anhand der nummerierten Quellen im Kontext.
        Antworte knapp auf Deutsch und nenne die Nummer der verwendeten Quelle, z. B. [2].
        Nutze alles, was die Quellen zur Frage enthalten, auch wenn die Frage anders formuliert ist als der Quellentext; Fachbegriffe der Frage können dort umschrieben sein.
        Nur wenn keine Quelle etwas zur Frage enthält, antworte genau: $NOT_FOUND
        Verwende kein Wissen außerhalb der Quellen.
    """.trimIndent()

    fun build(question: String, passages: List<Passage>, style: PromptStyle = PromptStyle.STRICT): RagPrompt {
        val context = passages.mapIndexed { i, p -> "[${i + 1}] (${p.source})\n${p.text.trim()}" }.joinToString("\n\n")
        return RagPrompt(system = if (style == PromptStyle.LENIENT) SYSTEM_LENIENT else SYSTEM, user = "Kontext:\n$context\n\nFrage: ${question.trim()}")
    }
}

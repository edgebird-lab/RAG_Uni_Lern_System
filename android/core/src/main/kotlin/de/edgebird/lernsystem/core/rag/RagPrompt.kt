// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.rag

import de.edgebird.lernsystem.core.i18n.Lang
import de.edgebird.lernsystem.core.i18n.tr

/** Ein abgerufener Textabschnitt mit Herkunftsangabe. */
data class Passage(val source: String, val text: String)

/** Ergebnis des Prompt-Baus: Systemanweisung und Nutzer-Nachricht getrennt (Chat-Template-tauglich). */
data class RagPrompt(val system: String, val user: String)

/** STRICT ist der bisherige Standard; LENIENT erlaubt Umschreibungen (gegen falsche Verweigerungen bei umformulierten Fragen). */
enum class PromptStyle { STRICT, LENIENT }

object RagPromptBuilder {
    const val NOT_FOUND_DE = "Nicht im Material gefunden."
    const val NOT_FOUND_EN = "Not found in the material."
    val NOT_FOUND get() = tr(NOT_FOUND_DE, NOT_FOUND_EN)

    /** Ist die Antwort die feste „nicht gefunden“-Meldung (in einer der Sprachen)? */
    fun isNotFound(answer: String) = answer.trim().trimEnd('.').let { it.equals(NOT_FOUND_DE.trimEnd('.'), true) || it.equals(NOT_FOUND_EN.trimEnd('.'), true) }

    private fun system(lang: Lang) = tr(
        """
        Du beantwortest Fragen ausschließlich anhand der nummerierten Quellen im Kontext.
        Antworte knapp auf Deutsch und nenne die Nummer der verwendeten Quelle, z. B. [2].
        Steht die Antwort nicht in den Quellen, antworte genau: $NOT_FOUND_DE
        Verwende kein Wissen außerhalb der Quellen.
    """.trimIndent(),
        """
        You answer questions exclusively on the basis of the numbered sources in the context.
        Answer briefly in English and give the number of the source used, e.g. [2].
        If the answer is not in the sources, answer exactly: $NOT_FOUND_EN
        Use no knowledge from outside the sources.
    """.trimIndent(), lang,
    )

    private fun systemLenient(lang: Lang) = tr(
        """
        Du beantwortest Fragen anhand der nummerierten Quellen im Kontext.
        Antworte knapp auf Deutsch und nenne die Nummer der verwendeten Quelle, z. B. [2].
        Nutze alles, was die Quellen zur Frage enthalten, auch wenn die Frage anders formuliert ist als der Quellentext; Fachbegriffe der Frage können dort umschrieben sein.
        Nur wenn keine Quelle etwas zur Frage enthält, antworte genau: $NOT_FOUND_DE
        Verwende kein Wissen außerhalb der Quellen.
    """.trimIndent(),
        """
        You answer questions on the basis of the numbered sources in the context.
        Answer briefly in English and give the number of the source used, e.g. [2].
        Use everything the sources contain on the question, even if the question is worded differently from the source text; technical terms of the question may be paraphrased there.
        Only if no source contains anything on the question, answer exactly: $NOT_FOUND_EN
        Use no knowledge from outside the sources.
    """.trimIndent(), lang,
    )

    fun build(question: String, passages: List<Passage>, style: PromptStyle = PromptStyle.STRICT, lang: Lang = Lang.current): RagPrompt {
        val context = passages.mapIndexed { i, p -> "[${i + 1}] (${p.source})\n${p.text.trim()}" }.joinToString("\n\n")
        return RagPrompt(
            system = if (style == PromptStyle.LENIENT) systemLenient(lang) else system(lang),
            user = tr("Kontext:\n$context\n\nFrage: ${question.trim()}", "Context:\n$context\n\nQuestion: ${question.trim()}", lang),
        )
    }
}

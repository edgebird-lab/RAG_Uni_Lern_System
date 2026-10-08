package de.edgebird.lernsystem.core.summary

import de.edgebird.lernsystem.core.ai.GenerationParams
import de.edgebird.lernsystem.core.ai.LlmEngine
import kotlinx.coroutines.flow.fold

/** Ergebnis eines Abschnitts. [text] ist `null`, wenn er übersprungen wurde (kurz, leer oder fehlgeschlagen). */
data class PartResult(val title: String, val text: String?, val reason: SkipReason? = null, val unsupportedNumbers: List<String> = emptyList())

enum class SkipReason { TOO_SHORT, NOT_RELEVANT, FAILED }

/**
 * Map-Reduce-Zusammenfassung mit dem lokalen Modell. Abschnitte werden einzeln zusammengefasst (map); die Kurzfassung
 * verdichtet deren Stichpunkte in einem oder mehreren Schritten (reduce). Antworten werden auf abgeschnittene Sätze und
 * nicht belegte Zahlen geprüft und bei Bedarf einmal neu angefragt.
 */
class SummaryGenerator(
    private val llm: LlmEngine,
    private val label: String,
    private val minSectionChars: Int = 80,
    private val reduceBudget: Int = 3500,
) {
    private suspend fun ask(prompt: String, temperature: Float, maxTokens: Int): String {
        llm.load()
        return llm.generate(prompt, GenerationParams(maxTokens = maxTokens, temperature = temperature, system = SummaryPrompts.SYSTEM))
            .fold(StringBuilder()) { sb, part -> sb.append(part) }.toString().trim()
    }

    /** Eine Abschnittszusammenfassung des Teilergebnis-Typs [kind]. */
    suspend fun summarizeSection(section: SummarySection, kind: PartKind): PartResult {
        if (section.text.length < minSectionChars) return PartResult(section.title, null, SkipReason.TOO_SHORT)
        val prompt = when (kind) {
            PartKind.OUTLINE -> SummaryPrompts.outline(label, section.title, section.text)
            PartKind.BULLETS -> SummaryPrompts.bullets(label, section.title, section.text)
        }
        val maxTokens = if (kind == PartKind.OUTLINE) 600 else 320
        return try {
            var md = ask(prompt, 0.2f, maxTokens)
            if (md.isEmpty() || SummaryChecks.looksTruncated(md)) md = ask(prompt, 0.2f, maxTokens * 3 / 2).ifEmpty { md }
            md = SummaryChecks.trimIncomplete(md)
            if (SummaryChecks.isEmptySection(md)) return PartResult(section.title, null, SkipReason.NOT_RELEVANT)
            var bad = SummaryChecks.unsupportedNumbers(md, section.text)
            if (bad.isNotEmpty()) {
                val again = ask(prompt + SummaryPrompts.RETRY_NUMBERS, 0.1f, maxTokens)
                val againBad = if (again.isBlank() || SummaryChecks.isEmptySection(again)) bad else SummaryChecks.unsupportedNumbers(again, section.text)
                if (again.isNotBlank() && !SummaryChecks.isEmptySection(again) && againBad.size < bad.size) { md = again; bad = againBad }
            }
            PartResult(section.title, md, unsupportedNumbers = bad)
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Exception) {
            PartResult(section.title, null, SkipReason.FAILED)
        }
    }

    /** Setzt aus Teilergebnissen das Markdown-Dokument zusammen (Stile OUTLINE und BULLETS). */
    fun assemble(title: String, parts: List<Pair<String, String>>, modelNote: String): String = buildString {
        append("# Zusammenfassung: ").append(title).append("\n\n")
        append("*KI-Zusammenfassung aus deinen Dokumenten (").append(modelNote).append("). Im Zweifel mit dem Original abgleichen.*\n")
        for ((sectionTitle, text) in parts) append("\n## ").append(sectionTitle).append("\n\n").append(text.trim()).append("\n")
    }

    /**
     * Kurzfassung aus den Stichpunkten der Abschnitte. Passen sie nicht in ein Budget, werden sie stapelweise zu
     * Zwischenständen verdichtet (höchstens 4 Ebenen).
     */
    suspend fun shortSummary(parts: List<Pair<String, String>>): String? {
        var items = parts.map { (t, text) -> "### $t\n${text.trim()}" }
        if (items.isEmpty()) return null
        var level = 0
        while (items.sumOf { it.length } > reduceBudget && level < 4) {
            val batches = mutableListOf<MutableList<String>>()
            for (it in items) {
                val last = batches.lastOrNull()
                if (last != null && last.sumOf { s -> s.length } + it.length <= reduceBudget) last += it else batches += mutableListOf(it)
            }
            if (batches.size == items.size) break // jedes Element allein schon zu groß: nicht weiter zerlegbar
            items = batches.map { b ->
                val joined = b.joinToString("\n\n")
                ask(SummaryPrompts.shortIntermediate(label, joined), 0.2f, 320).ifBlank { joined.take(reduceBudget / 2) }
            }
            level++
        }
        val joined = items.joinToString("\n\n").take(reduceBudget * 2)
        var md = ask(SummaryPrompts.shortFinal(label, joined), 0.2f, 450)
        if (md.isEmpty() || SummaryChecks.looksTruncated(md)) md = ask(SummaryPrompts.shortFinal(label, joined), 0.2f, 700).ifEmpty { md }
        md = SummaryChecks.trimIncomplete(md)
        return md.takeIf { it.isNotBlank() && !SummaryChecks.isEmptySection(it) }
    }

    fun wrapShort(title: String, body: String, modelNote: String): String =
        "# Kurzfassung: $title\n\n*KI-Zusammenfassung aus deinen Dokumenten ($modelNote). Im Zweifel mit dem Original abgleichen.*\n\n${body.trim()}\n"
}

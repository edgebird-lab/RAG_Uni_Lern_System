package de.edgebird.lernsystem.core.summary

import de.edgebird.lernsystem.core.i18n.tr

import de.edgebird.lernsystem.core.ai.GenerationParams
import de.edgebird.lernsystem.core.ai.LlmEngine
import kotlinx.coroutines.flow.fold

/** Ergebnis eines Abschnitts. [text] ist `null`, wenn er übersprungen wurde (kurz, leer oder fehlgeschlagen). */
data class PartResult(val title: String, val text: String?, val reason: SkipReason? = null, val unsupportedNumbers: List<String> = emptyList())

enum class SkipReason { TOO_SHORT, NOT_RELEVANT, FAILED }

/**
 * Map-Reduce-Zusammenfassung mit dem lokalen Modell, gesteuert durch eine [SummarySpec]. Abschnitte werden einzeln
 * zusammengefasst (map); Fließtext, Verdichtung und Fach-Überblick fassen deren Ergebnisse in einem oder mehreren Schritten
 * zusammen (reduce). Antworten werden auf abgeschnittene Sätze und nicht belegte Zahlen geprüft und bei Bedarf neu angefragt.
 */
class SummaryGenerator(
    private val llm: LlmEngine,
    private val label: String,
    private val spec: SummarySpec = SummarySpec(),
    private val minSectionChars: Int = 80,
    private val reduceBudget: Int = 3500,
) {
    /** Hat die letzte Antwort das Token-Budget ausgeschöpft (dann ist sie sicher abgeschnitten)? Aus der Zahl der gestreamten Stücke geschätzt. */
    private var lastHitLimit = false

    private suspend fun ask(prompt: String, temperature: Float, maxTokens: Int): String {
        llm.load()
        var pieces = 0
        val text = llm.generate(prompt, GenerationParams(maxTokens = maxTokens, temperature = temperature, system = spec.system))
            .fold(StringBuilder()) { sb, part -> pieces++; sb.append(part) }.toString().trim()
        lastHitLimit = pieces >= maxTokens - 2
        return text
    }

    /** Antwort bereinigen: war sie abgeschnitten (Token-Limit oder Heuristik), fällt der unvollständige Schluss weg. */
    private fun finish(md: String, hitLimit: Boolean): String {
        val strict = spec.format == SummaryFormat.BULLETS && SummaryChecks.endsWithUnterminatedBullet(md)
        return SummaryChecks.tidy(SummaryChecks.trimIncomplete(md, force = hitLimit || strict))
    }

    /** Token-Budget für ungefähr [words] Wörter (deutsch ca. 1,5 bis 2 Token je Wort) mit Puffer. */
    private fun tokensFor(words: Int, factor: Double = 1.0) = (words * 2.2 * factor).toInt().coerceIn(160, 1400)

    /** Eine Abschnittszusammenfassung; [words] = Zielumfang dieses Abschnitts (siehe [SummarySpec.wordsPerSection]). */
    suspend fun summarizeSection(section: SummarySection, words: Int): PartResult {
        if (section.text.length < minSectionChars) return PartResult(section.title, null, SkipReason.TOO_SHORT)
        val prompt = SummaryPrompts.section(spec, label, section.title, section.text, words)
        val maxTokens = tokensFor(words, if (spec.format == SummaryFormat.OUTLINE) 1.5 else 1.0)
        return try {
            var md = ask(prompt, 0.2f, maxTokens)
            var hit = lastHitLimit
            if (md.isEmpty() || hit || SummaryChecks.looksTruncated(md)) { md = ask(prompt, 0.2f, maxTokens * 3 / 2).ifEmpty { md }; hit = lastHitLimit }
            md = finish(md, hit)
            if (SummaryChecks.isEmptySection(md)) return PartResult(section.title, null, SkipReason.NOT_RELEVANT)
            var bad = SummaryChecks.unsupportedNumbers(md, section.text)
            if (bad.isNotEmpty()) {
                val again = finish(ask(prompt + SummaryPrompts.RETRY_NUMBERS, 0.1f, maxTokens), lastHitLimit)
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

    private fun note(modelNote: String) = tr("*KI-Zusammenfassung aus deinen Dokumenten ($modelNote). Im Zweifel mit dem Original abgleichen.*", "*AI summary of your documents ($modelNote). When in doubt, check against the original.*")

    /** Setzt aus Teilergebnissen das Markdown-Dokument zusammen (Formate Gegliedert und Stichpunkte). */
    fun assemble(title: String, parts: List<Pair<String, String>>, modelNote: String, heading: String = tr("Zusammenfassung", "Summary")): String = buildString {
        append("# ").append(heading).append(": ").append(title).append("\n\n").append(note(modelNote)).append("\n")
        for ((sectionTitle, text) in parts) append("\n## ").append(sectionTitle).append("\n\n").append(text.trim()).append("\n")
    }

    /** Glossar: alle Begriffszeilen, nach Begriff sortiert, gleiche Begriffe nur einmal (die ausführlichere Erklärung gewinnt). */
    fun assembleGlossary(title: String, parts: List<Pair<String, String>>, modelNote: String): String {
        val entries = GlossaryMerge.merge(parts.map { it.second }, maxEntries = maxOf(8, spec.targetWords / 12))
        return "# ${tr("Glossar", "Glossary")}: $title\n\n${note(modelNote)}\n\n" + entries.joinToString("\n") + "\n"
    }

    /**
     * Fließtext mit Längenkontrolle: abgeschnittene Antworten werden mit mehr Budget neu angefragt, deutlich zu lange mit dem Hinweis auf die
     * tatsächliche Wortzahl; der Versuch, der dem Ziel näher kommt, gewinnt.
     */
    private suspend fun askWithLength(prompt: String, target: Int): String {
        val tokens = tokensFor(target, 1.2)
        var md = ask(prompt, 0.2f, tokens)
        var hit = lastHitLimit
        if (md.isEmpty() || hit || SummaryChecks.looksTruncated(md)) { md = ask(prompt, 0.2f, tokens * 3 / 2).ifEmpty { md }; hit = lastHitLimit }
        md = finish(md, hit)
        val words = wordCount(md)
        if (words > target * TOO_LONG) {
            val again = finish(ask(prompt + tr("\n\nWICHTIG: Der letzte Versuch hatte $words Wörter und war damit viel zu lang. Schreibe höchstens $target Wörter: lasse Nebensächliches und Wiederholungen weg.", "\n\nIMPORTANT: The last attempt had $words words and was far too long. Write at most $target words: leave out side issues and repetition."), 0.1f, tokens), lastHitLimit)
            if (again.isNotBlank() && kotlin.math.abs(wordCount(again) - target) < kotlin.math.abs(words - target)) md = again
        }
        return md
    }

    /**
     * Hierarchische Verdichtung: passen die Texte nicht in ein Budget, werden sie stapelweise zu Zwischenständen verdichtet
     * (höchstens 4 Ebenen). Gibt den zusammengeführten Text zurück, der in den letzten Schritt geht.
     */
    private suspend fun reduceToBudget(parts: List<Pair<String, String>>): String {
        var items = parts.map { (t, text) -> "### $t\n${text.trim()}" }
        var level = 0
        while (items.sumOf { it.length } > reduceBudget && level < 4) {
            val batches = mutableListOf<MutableList<String>>()
            for (it in items) {
                val last = batches.lastOrNull()
                if (last != null && last.sumOf { s -> s.length } + it.length <= reduceBudget) last += it else batches += mutableListOf(it)
            }
            if (batches.size == items.size) break // jedes Element allein schon zu groß: nicht weiter zerlegbar
            val wordsEach = (spec.targetWords * 2 / batches.size).coerceIn(60, 220)
            items = batches.map { b ->
                val joined = b.joinToString("\n\n")
                ask(SummaryPrompts.intermediate(spec, label, joined, wordsEach), 0.2f, tokensFor(wordsEach)).let { finish(it, lastHitLimit) }.ifBlank { joined.take(reduceBudget / 2) }
            }
            level++
        }
        return items.joinToString("\n\n").take(reduceBudget * 2)
    }

    /** Fließtext über das ganze Dokument aus den Abschnittsstichpunkten (Format [SummaryFormat.PROSE]). */
    suspend fun prose(parts: List<Pair<String, String>>): String? {
        if (parts.isEmpty()) return null
        val joined = reduceToBudget(parts)
        val md = askWithLength(SummaryPrompts.proseFinal(spec, label, joined), spec.targetWords)
        return md.takeIf { it.isNotBlank() && !SummaryChecks.isEmptySection(it) }
    }

    fun wrapProse(title: String, body: String, modelNote: String, heading: String = "Zusammenfassung"): String = "# $heading: $title\n\n${note(modelNote)}\n\n${body.trim()}\n"

    /**
     * Kürzt eine zu lange strukturierte Zusammenfassung: Abschnitte werden zu Gruppen zusammengefasst, jede Gruppe bekommt
     * anteilig ihre Wortzahl. Kleine Zusammenfassungen kommen unverändert zurück.
     */
    suspend fun condense(parts: List<Pair<String, String>>): List<Pair<String, String>> {
        val total = parts.sumOf { wordCount(it.second) }
        if (!spec.needsCondense(total)) return parts
        val groups = mutableListOf<MutableList<Pair<String, String>>>()
        for (p in parts) {
            val last = groups.lastOrNull()
            if (last != null && last.sumOf { it.second.length } + p.second.length <= reduceBudget) last += p else groups += mutableListOf(p)
        }
        return groups.map { g ->
            val words = g.sumOf { wordCount(it.second) }
            val goal = maxOf(MIN_GROUP_WORDS, (spec.targetWords.toLong() * words / total).toInt())
            val joined = g.joinToString("\n\n") { (t, x) -> "## $t\n${x.trim()}" }
            val out = ask(SummaryPrompts.condense(spec, label, joined, goal), 0.2f, tokensFor(goal, 1.8))
            val clean = finish(out, lastHitLimit)
            // Titel leer: Die verdichtete Gruppe bringt ihre Überschriften selbst mit. Misslingt das Verdichten, bleibt der Originaltext.
            if (clean.isBlank()) "" to joined else "" to clean
        }
    }

    /** Überblick über mehrere Quellen eines Fachs; [perDoc] sind (Titel, Zusammenfassung) je Quelle. */
    suspend fun overview(subject: String, perDoc: List<Pair<String, String>>, words: Int): String? {
        if (perDoc.isEmpty()) return null
        val joined = reduceToBudget(perDoc)
        return askWithLength(SummaryPrompts.overview(spec, subject, joined, words), words).takeIf { it.isNotBlank() }
    }

    companion object {
        const val MIN_GROUP_WORDS = 40
        /** Ab diesem Vielfachen der Zielwortzahl wird ein Fließtext neu angefragt. */
        const val TOO_LONG = 1.4
        fun wordCount(text: String) = text.split(Regex("""\s+""")).count { it.isNotBlank() }
    }
}

/** Glossarzeilen („- **Begriff:** Erklärung“) mehrerer Abschnitte zusammenführen. */
object GlossaryMerge {
    private val LINE = Regex("""^\s*[-*•]\s*\*\*(.+?)\*\*\s*[:–-]?\s*(.*)$""")

    /** @param maxEntries höchstens so viele Einträge; sind es mehr, werden gleichmäßig über das Dokument verteilte behalten. */
    fun merge(texts: List<String>, maxEntries: Int = Int.MAX_VALUE): List<String> {
        val best = LinkedHashMap<String, Pair<String, String>>()   // klein geschriebener Begriff -> (Begriff, Erklärung)
        for (t in texts) for (line in t.lines()) {
            val m = LINE.matchEntire(line.trimEnd()) ?: continue
            val term = m.groupValues[1].trim().trimEnd(':').trim()
            val def = m.groupValues[2].trim()
            if (term.isEmpty() || def.isEmpty()) continue
            val key = term.lowercase()
            val old = best[key]
            if (old == null || def.length > old.second.length) best[key] = term to def
        }
        val inOrder = best.values.toList()
        val kept = if (inOrder.size <= maxEntries) inOrder else (0 until maxEntries).map { inOrder[it * inOrder.size / maxEntries] }
        return kept.sortedBy { it.first.lowercase() }.map { (t, d) -> "- **$t:** $d" }
    }
}

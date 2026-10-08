package de.edgebird.lernsystem.core.cards

import de.edgebird.lernsystem.core.ai.Embedder
import de.edgebird.lernsystem.core.ai.GenerationParams
import de.edgebird.lernsystem.core.ai.LlmEngine
import kotlinx.coroutines.flow.fold

/** Eine fertig erzeugte, geprüfte Karte. [questionVector] ist die Frage-Einbettung (für spätere Dublettenprüfung). */
data class GeneratedCard(val question: String, val answer: String, val questionVector: FloatArray?, val kind: CardKind = CardKind.QA) {
    override fun equals(other: Any?) = other is GeneratedCard && question == other.question && answer == other.answer
    override fun hashCode() = 31 * question.hashCode() + answer.hashCode()
}

/** Statistik einer Erzeugung, damit die Oberfläche ehrlich berichten kann, was verworfen wurde. */
data class GenerationStats(var rejectedQuestions: Int = 0, var rejectedAnswers: Int = 0, var duplicates: Int = 0, var retries: Int = 0)

/**
 * Erzeugt Karteikarten aus einem Textabschnitt (Port der zweistufigen Pipeline der PC-App): erst Fragen als JSON,
 * dann je Frage eine Musterlösung. Mängel (Quellenbezug, fehlender Kontext, Dubletten …) führen zu Neuversuchen mit
 * gezieltem Hinweis; was danach noch Mängel hat, wird verworfen.
 */
class CardGenerator(
    private val llm: LlmEngine,
    private val embedder: Embedder? = null,
    private val retries: Int = 2,
    private val minChunkChars: Int = 120,
) {
    private suspend fun ask(prompt: String, system: String, temperature: Float, maxTokens: Int): String {
        llm.load()
        return llm.generate(prompt, GenerationParams(maxTokens = maxTokens, temperature = temperature, system = system))
            .fold(StringBuilder()) { sb, part -> sb.append(part) }.toString()
    }

    /**
     * @param existing bereits vorhandene Fragen als (Einbettung, Text) für die Dublettenprüfung; wird nicht verändert.
     * @return bis zu [n] neue Karten
     */
    suspend fun generate(chunk: String, n: Int = 2, existing: List<Pair<FloatArray?, String>> = emptyList(), stats: GenerationStats = GenerationStats()): List<GeneratedCard> {
        if (chunk.trim().length < minChunkChars || !CardChunkFilter.isStudyWorthy(chunk)) return emptyList()
        // Ohne geladenen Embedder gäbe es keine Vektoren und damit keine Dublettenprüfung (fiel vorher still aus)
        val vectorsAvailable = embedder != null && runCatching { embedder!!.load() }.isSuccess
        val accepted = mutableListOf<Pair<String, FloatArray?>>()
        val seen = HashSet<String>()
        var hint = ""
        for (attempt in 0..retries) {
            val want = n - accepted.size
            if (want <= 0) break
            val raw = try {
                ask(CardPrompts.questionPrompt(chunk, want) + hint, CardPrompts.QUESTION_SYSTEM, 0.3f + 0.15f * attempt, 300)
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                if (attempt == 0) throw e else break
            }
            val problemsSeen = mutableListOf<CardProblem>()
            for (q in CardPrompts.parseQuestions(raw)) {
                val key = q.lowercase()
                if (q.isEmpty() || !seen.add(key) || !CardPrompts.isQuestion(q) || CardPrompts.isHeadingEcho(q, chunk)) continue
                val problems = CardQuality.questionProblems(q)
                if (problems.isNotEmpty()) {
                    problemsSeen += problems
                    stats.rejectedQuestions++
                    continue
                }
                val vec = if (vectorsAvailable) runCatching { embedder!!.embed(listOf(q)).first() }.getOrNull() else null
                if (vec != null && CardQuality.isDuplicate(vec, q, existing + accepted.map { it.second to it.first })) {
                    stats.duplicates++
                    continue
                }
                accepted += q to vec
                if (accepted.size >= n) break
            }
            if (accepted.size >= n || problemsSeen.isEmpty()) break
            hint = CardQuality.retryHint(problemsSeen)
            if (attempt < retries) stats.retries++
        }

        val out = mutableListOf<GeneratedCard>()
        for ((q, vec) in accepted) {
            val answer = answer(chunk, q, stats) ?: continue
            out += GeneratedCard(q, answer, vec)
        }
        return out
    }

    /** Musterlösung mit Neuversuchen; `null`, wenn sie nicht im Text steht oder Mängel bleiben. */
    private suspend fun answer(chunk: String, question: String, stats: GenerationStats): String? {
        val base = CardPrompts.answerPrompt(question, chunk)
        var best = CardPrompts.cleanAnswer(ask(base, CardPrompts.ANSWER_SYSTEM, 0.2f, 350))
        if (best.isEmpty()) {
            stats.rejectedAnswers++
            return null
        }
        var problems = CardQuality.answerProblems(best, question)
        for (attempt in 0 until retries) {
            if (problems.isEmpty()) break
            val again = try {
                CardPrompts.cleanAnswer(ask(base + CardQuality.retryHint(problems), CardPrompts.ANSWER_SYSTEM, 0.3f + 0.1f * attempt, 350))
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                break
            }
            stats.retries++
            val againProblems = if (again.isEmpty()) problems else CardQuality.answerProblems(again, question)
            if (again.isNotEmpty() && againProblems.size < problems.size) {
                best = again
                problems = againProblems
            }
        }
        if (problems.isNotEmpty()) {
            stats.rejectedAnswers++
            return null
        }
        return best
    }

    /**
     * Lückentext-Karten aus einem Abschnitt: das Modell wählt Sätze und Begriffe, [Cloze.build] prüft sie gegen den Quelltext.
     * Es gibt keinen zweiten Modellaufruf (keine Antwortstufe), deshalb geht es deutlich schneller als bei Frage-Antwort-Karten.
     * @param existingFronts schon vorhandene Karten-Vorderseiten (Dubletten werden übersprungen)
     */
    suspend fun generateCloze(chunk: String, n: Int = 2, existingFronts: Collection<String> = emptyList(), stats: GenerationStats = GenerationStats()): List<GeneratedCard> {
        if (chunk.trim().length < minChunkChars || !CardChunkFilter.isStudyWorthy(chunk) || ContentKind.isCode(chunk)) return emptyList()
        val seenFronts = existingFronts.map { it.lowercase().replace(Regex("""\s+"""), " ") }.toMutableSet()
        val seenTerms = HashSet<String>()
        val seenSentences = HashSet<String>()   // höchstens eine Lücke je Satz
        val out = mutableListOf<GeneratedCard>()
        for (attempt in 0..1) {
            val want = n - out.size
            if (want <= 0) break
            val raw = try {
                ask(Cloze.prompt(chunk, want + attempt), CardPrompts.QUESTION_SYSTEM, 0.3f + 0.3f * attempt, 400)
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                if (attempt == 0) throw e else break
            }
            for (item in Cloze.parse(raw)) {
                if (out.size >= n) break
                val built = Cloze.build(item, chunk)
                if (built == null) { stats.rejectedQuestions++; continue }
                val key = built.front.lowercase().replace(Regex("""\s+"""), " ")
                if (!seenFronts.add(key) || !seenTerms.add(item.term.lowercase()) || !seenSentences.add(item.sentence.lowercase().replace(Regex("""\\s+"""), " "))) { stats.duplicates++; continue }
                out += GeneratedCard(built.front, built.answer, null, CardKind.CLOZE)
            }
            if (attempt == 0 && out.size < n) stats.retries++
        }
        return out
    }
}

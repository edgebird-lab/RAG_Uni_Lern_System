package de.edgebird.lernsystem.core.quiz

import com.google.gson.JsonParser
import de.edgebird.lernsystem.core.ai.GenerationParams
import de.edgebird.lernsystem.core.ai.LlmEngine
import de.edgebird.lernsystem.core.cards.CardPrompts
import de.edgebird.lernsystem.core.cards.CardQuality
import de.edgebird.lernsystem.core.i18n.Lang
import de.edgebird.lernsystem.core.i18n.tr
import kotlinx.coroutines.flow.toList
import kotlin.random.Random

/** Eine Mehrfachauswahl-Frage; [correctIndex] zeigt in [options] auf die richtige Antwort. */
data class McQuestion(val question: String, val options: List<String>, val correctIndex: Int, val explanation: String, val sourceText: String) {
    val correct get() = options[correctIndex]
}

/**
 * Mehrfachauswahl-Fragen aus einem Textabschnitt. Das Modell liefert Frage, richtige und drei falsche Antworten; der CODE prüft, dass die richtige Antwort
 * im Abschnitt belegt ist (kein Erfinden), die falschen verschieden und nicht verraten sind, und mischt die Reihenfolge.
 */
object MultipleChoice {
    fun system(lang: Lang = Lang.current) = tr(
        "Du bist ein erfahrener Prüfer an einer deutschen Hochschule. Du schreibst eindeutige Mehrfachauswahl-Fragen mit genau einer richtigen Antwort.",
        "You are an experienced university examiner. You write unambiguous multiple-choice questions with exactly one correct answer.", lang,
    )
    val SYSTEM get() = system()

    fun prompt(chunk: String, lang: Lang = Lang.current): String = if (lang == Lang.EN) promptEn(chunk) else """Lies den folgenden Abschnitt und schreibe EINE Mehrfachauswahl-Frage dazu. Regeln:
- Die Frage prüft einen wichtigen Begriff, eine Regel oder einen Zusammenhang und lässt sich allein aus dem Abschnitt beantworten.
- Genau EINE richtige Antwort, kurz (höchstens 15 Wörter), sinngemäß aus dem Abschnitt.
- Drei FALSCHE Antworten, die plausibel klingen, aber eindeutig falsch sind (typische Verwechslungen); ähnlich lang wie die richtige.
- Die Frage muss ohne den Abschnitt verständlich sein (kein „im Text“, keine Abbildungs- oder Seitenverweise).
- Eine Erklärung in einem Satz, warum die richtige Antwort stimmt.

Abschnitt:
${"\"\"\""}
${chunk.take(2500)}
${"\"\"\""}

Gib NUR gültiges JSON zurück:
{"frage": "...", "richtig": "...", "falsch": ["...", "...", "..."], "erklaerung": "..."}"""

    private fun promptEn(chunk: String): String = """Read the following passage and write ONE multiple-choice question about it. Rules:
- The question tests an important term, rule or relationship and can be answered from the passage alone.
- Exactly ONE correct answer, short (at most 15 words), faithful to the passage.
- Three WRONG answers that sound plausible but are clearly wrong (typical mix-ups); about as long as the correct one.
- The question must be understandable without the passage (no "in the text", no references to figures or pages).
- An explanation in one sentence of why the correct answer is right.
- Write question, answers and explanation in English.

Passage:
${"\"\"\""}
${chunk.take(2500)}
${"\"\"\""}

Return ONLY valid JSON (keep the German key names):
{"frage": "...", "richtig": "...", "falsch": ["...", "...", "..."], "erklaerung": "..."}"""

    data class Raw(val question: String, val correct: String, val wrong: List<String>, val explanation: String)

    fun parse(raw: String): Raw? {
        val start = raw.indexOf('{'); val end = raw.lastIndexOf('}')
        if (start < 0 || end <= start) return null
        return try {
            val o = JsonParser.parseString(raw.substring(start, end + 1)).asJsonObject
            fun str(k: String) = o.get(k)?.takeIf { it.isJsonPrimitive }?.asString?.trim().orEmpty()
            val wrong = o.getAsJsonArray("falsch")?.mapNotNull { e -> e.takeIf { it.isJsonPrimitive }?.asString?.trim()?.takeIf { it.isNotEmpty() } }.orEmpty()
            Raw(str("frage"), str("richtig"), wrong, str("erklaerung")).takeIf { it.question.isNotEmpty() && it.correct.isNotEmpty() }
        } catch (e: Exception) { null }
    }

    private fun norm(s: String) = s.lowercase().replace(Regex("""[^\p{L}\p{N} ]+"""), " ").trim().replace(Regex("""\s+"""), " ")
    private fun stems(s: String) = Regex("""\p{L}{4,}""").findAll(s.lowercase()).map { it.value.take(5) }.toSet()

    /** Anteil der Inhaltswörter (Stamm) von [answer], die im Abschnitt vorkommen. */
    internal fun grounded(answer: String, chunk: String): Double {
        val a = stems(answer); if (a.isEmpty()) return 1.0
        val c = stems(chunk)
        return a.count { it in c }.toDouble() / a.size
    }

    /** Fertige Frage oder `null`, wenn eine Prüfung scheitert. [rng] bestimmt die gemischte Reihenfolge. */
    fun build(raw: Raw, chunk: String, rng: Random): McQuestion? {
        if (!CardPrompts.isQuestion(raw.question) || CardQuality.questionProblems(raw.question).isNotEmpty()) return null
        if (raw.correct.length > 160 || grounded(raw.correct, chunk) < 0.6) return null          // Antwort muss im Text stehen
        val wrong = raw.wrong.distinctBy { norm(it) }.filter { norm(it).isNotEmpty() && norm(it) != norm(raw.correct) }.take(3)
        if (wrong.size < 3) return null
        val c = norm(raw.correct)
        if (wrong.any { val w = norm(it); w in c || c in w }) return null                         // „richtig“ steckt in einer falschen Antwort (oder umgekehrt)
        if (norm(raw.question).contains(c) && c.length > 6) return null                           // Frage verrät die Antwort
        if (wrong.any { it.length > 160 }) return null
        val longest = (wrong + raw.correct).maxOf { it.length }
        if (raw.correct.length == longest && raw.correct.length > 2.2 * wrong.maxOf { it.length }) return null   // richtige Antwort sticht deutlich heraus
        val options = (wrong + raw.correct).shuffled(rng)
        return McQuestion(raw.question.trim(), options, options.indexOf(raw.correct), raw.explanation.take(300), chunk.take(400))
    }

    /** Erzeugt eine Frage (bis zu [attempts] Versuche); `null`, wenn keiner brauchbar war. */
    suspend fun generate(llm: LlmEngine, chunk: String, rng: Random = Random.Default, attempts: Int = 3): McQuestion? {
        llm.load()
        for (i in 0 until attempts) {
            val raw = llm.generate(prompt(chunk), GenerationParams(maxTokens = 400, temperature = 0.3f + 0.2f * i, system = system())).toList().joinToString("")
            parse(raw)?.let { r -> build(r, chunk, rng)?.let { return it } }
        }
        return null
    }
}

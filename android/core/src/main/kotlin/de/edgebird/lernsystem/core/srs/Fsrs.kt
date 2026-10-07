package de.edgebird.lernsystem.core.srs

import kotlin.math.E
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.round

/** Bewertung einer Karte; Werte wie im Python-Paket `fsrs`. */
enum class Rating(val value: Int) { AGAIN(1), HARD(2), GOOD(3), EASY(4) }

/** Lernzustand; Werte wie im Python-Paket `fsrs` (und in der PC-App gespeichert). */
enum class CardState(val value: Int) {
    LEARNING(1), REVIEW(2), RELEARNING(3);

    companion object {
        fun of(value: Int) = entries.first { it.value == value }
    }
}

/** Planungsdaten einer Karte. Zeiten in Millisekunden seit 1970 (UTC). */
data class FsrsCard(
    val state: CardState = CardState.LEARNING,
    /** Aktueller Lern-/Wiederholungsschritt; `null` im Zustand REVIEW. */
    val step: Int? = 0,
    val stability: Double? = null,
    val difficulty: Double? = null,
    val dueMillis: Long,
    val lastReviewMillis: Long? = null,
)

data class FsrsConfig(
    val desiredRetention: Double = 0.9,
    val maximumIntervalDays: Int = 365,
    val learningStepsMinutes: List<Double> = listOf(1.0, 10.0),
    val relearningStepsMinutes: List<Double> = listOf(10.0),
    val parameters: List<Double> = DEFAULT_PARAMETERS,
) {
    companion object {
        const val DEFAULT_DECAY = 0.1542
        val DEFAULT_PARAMETERS = listOf(
            0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194, 0.001, 1.8722, 0.1666, 0.796,
            1.4835, 0.0614, 0.2629, 1.6483, 0.6014, 1.8729, 0.5425, 0.0912, 0.0658, DEFAULT_DECAY,
        )
    }
}

/**
 * FSRS-6-Planer, Port von `fsrs.Scheduler` (py-fsrs 6.3) ohne Fuzzing (die PC-App schaltet es ebenfalls ab).
 * Ein Paritätstest vergleicht zufällige Bewertungsfolgen mit dem Python-Original.
 */
class FsrsScheduler(private val config: FsrsConfig = FsrsConfig()) {
    private val p = config.parameters
    private val decay = -p[20]
    private val factor = 0.9.pow(1.0 / decay) - 1.0

    init {
        require(p.size == 21) { "FSRS-6 braucht 21 Parameter" }
    }

    /** Erinnerungswahrscheinlichkeit zum Zeitpunkt [nowMillis]. */
    fun retrievability(card: FsrsCard, nowMillis: Long): Double {
        val last = card.lastReviewMillis ?: return 0.0
        val stability = card.stability ?: return 0.0
        val elapsedDays = max(0L, Math.floorDiv(nowMillis - last, DAY_MS))
        return (1.0 + factor * elapsedDays / stability).pow(decay)
    }

    fun review(card: FsrsCard, rating: Rating, nowMillis: Long): FsrsCard {
        val daysSince = card.lastReviewMillis?.let { Math.floorDiv(nowMillis - it, DAY_MS) }
        var state = card.state
        var step = card.step
        var stability = card.stability
        var difficulty = card.difficulty
        val nextIntervalMs: Long

        when (card.state) {
            CardState.LEARNING -> {
                val s = step ?: 0
                if (stability == null || difficulty == null) {
                    stability = initialStability(rating)
                    difficulty = initialDifficulty(rating, clamp = true)
                } else if (daysSince != null && daysSince < 1) {
                    stability = shortTermStability(stability, rating)
                    difficulty = nextDifficulty(difficulty, rating)
                } else {
                    stability = nextStability(difficulty, stability, retrievability(card, nowMillis), rating)
                    difficulty = nextDifficulty(difficulty, rating)
                }
                val steps = config.learningStepsMinutes
                if (steps.isEmpty() || (s >= steps.size && rating != Rating.AGAIN)) {
                    state = CardState.REVIEW; step = null
                    nextIntervalMs = intervalMs(stability)
                } else {
                    val r = stepTransition(rating, s, steps)
                    state = if (r.graduates) CardState.REVIEW else CardState.LEARNING
                    step = if (r.graduates) null else r.step
                    nextIntervalMs = if (r.graduates) intervalMs(stability) else r.intervalMs
                }
            }

            CardState.REVIEW -> {
                val st = checkNotNull(stability); val d = checkNotNull(difficulty)
                stability = if (daysSince != null && daysSince < 1) shortTermStability(st, rating)
                else nextStability(d, st, retrievability(card, nowMillis), rating)
                difficulty = nextDifficulty(d, rating)
                if (rating == Rating.AGAIN && config.relearningStepsMinutes.isNotEmpty()) {
                    state = CardState.RELEARNING; step = 0
                    nextIntervalMs = minutesMs(config.relearningStepsMinutes[0])
                } else {
                    nextIntervalMs = intervalMs(stability)
                }
            }

            CardState.RELEARNING -> {
                val st = checkNotNull(stability); val d = checkNotNull(difficulty)
                val s = checkNotNull(step)
                if (daysSince != null && daysSince < 1) {
                    stability = shortTermStability(st, rating)
                    difficulty = nextDifficulty(d, rating)
                } else {
                    stability = nextStability(d, st, retrievability(card, nowMillis), rating)
                    difficulty = nextDifficulty(d, rating)
                }
                val steps = config.relearningStepsMinutes
                if (steps.isEmpty() || (s >= steps.size && rating != Rating.AGAIN)) {
                    state = CardState.REVIEW; step = null
                    nextIntervalMs = intervalMs(stability)
                } else {
                    val r = stepTransition(rating, s, steps)
                    state = if (r.graduates) CardState.REVIEW else CardState.RELEARNING
                    step = if (r.graduates) null else r.step
                    nextIntervalMs = if (r.graduates) intervalMs(stability) else r.intervalMs
                }
            }
        }
        return FsrsCard(state, step, stability, difficulty, nowMillis + nextIntervalMs, nowMillis)
    }

    private class StepResult(val step: Int, val intervalMs: Long, val graduates: Boolean)

    /** Schrittlogik für Lern- und Wiederholungsschritte (identisch aufgebaut im Original). */
    private fun stepTransition(rating: Rating, step: Int, steps: List<Double>): StepResult = when (rating) {
        Rating.AGAIN -> StepResult(0, minutesMs(steps[0]), false)
        Rating.HARD -> {
            val ms = when {
                step == 0 && steps.size == 1 -> minutesMs(steps[0] * 1.5)
                step == 0 && steps.size >= 2 -> minutesMs((steps[0] + steps[1]) / 2.0)
                else -> minutesMs(steps[step])
            }
            StepResult(step, ms, false)
        }
        Rating.GOOD -> if (step + 1 == steps.size) StepResult(step, 0, true) else StepResult(step + 1, minutesMs(steps[step + 1]), false)
        Rating.EASY -> StepResult(step, 0, true)
    }

    private fun minutesMs(minutes: Double): Long = (minutes * 60_000.0).toLong()

    private fun intervalMs(stability: Double): Long = nextIntervalDays(stability) * DAY_MS

    private fun nextIntervalDays(stability: Double): Long {
        val raw = (stability / factor) * (config.desiredRetention.pow(1.0 / decay) - 1.0)
        // Python rundet kaufmännisch-gerade ("banker's rounding"), kotlin.math.round macht dasselbe (IEEE, halb zu gerade)
        return min(max(round(raw).toLong(), 1L), config.maximumIntervalDays.toLong())
    }

    private fun clampStability(s: Double) = max(s, STABILITY_MIN)
    private fun clampDifficulty(d: Double) = min(max(d, 1.0), 10.0)

    private fun initialStability(rating: Rating) = clampStability(p[rating.value - 1])

    private fun initialDifficulty(rating: Rating, clamp: Boolean): Double {
        val d = p[4] - E.pow(p[5] * (rating.value - 1)) + 1
        return if (clamp) clampDifficulty(d) else d
    }

    private fun shortTermStability(stability: Double, rating: Rating): Double {
        var inc = E.pow(p[17] * (rating.value - 3 + p[18])) * stability.pow(-p[19])
        if (rating != Rating.AGAIN) inc = max(inc, 1.0)
        return clampStability(stability * inc)
    }

    private fun nextDifficulty(difficulty: Double, rating: Rating): Double {
        val arg1 = initialDifficulty(Rating.EASY, clamp = false)
        val delta = -(p[6] * (rating.value - 3))
        val arg2 = difficulty + (10.0 - difficulty) * delta / 9.0
        return clampDifficulty(p[7] * arg1 + (1 - p[7]) * arg2)
    }

    private fun nextStability(difficulty: Double, stability: Double, retrievability: Double, rating: Rating): Double {
        val next = if (rating == Rating.AGAIN) {
            val longTerm = p[11] * difficulty.pow(-p[12]) * ((stability + 1).pow(p[13]) - 1) * E.pow((1 - retrievability) * p[14])
            val shortTerm = stability / E.pow(p[17] * p[18])
            min(longTerm, shortTerm)
        } else {
            val hardPenalty = if (rating == Rating.HARD) p[15] else 1.0
            val easyBonus = if (rating == Rating.EASY) p[16] else 1.0
            stability * (1 + E.pow(p[8]) * (11 - difficulty) * stability.pow(-p[9]) * (E.pow((1 - retrievability) * p[10]) - 1) * hardPenalty * easyBonus)
        }
        return clampStability(next)
    }

    companion object {
        const val DAY_MS = 86_400_000L
        const val STABILITY_MIN = 0.001
    }
}

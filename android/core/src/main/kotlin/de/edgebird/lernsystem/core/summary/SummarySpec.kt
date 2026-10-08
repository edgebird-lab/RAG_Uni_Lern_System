package de.edgebird.lernsystem.core.summary

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.security.MessageDigest

/** Form der Zusammenfassung. */
enum class SummaryFormat(val label: String, val description: String) {
    OUTLINE("Gegliedert", "Je Abschnitt: Kernidee, Begriffe, Regeln"),
    BULLETS("Stichpunkte", "Je Abschnitt wenige Stichpunkte"),
    PROSE("Fließtext", "Zusammenhängender Text über das Ganze"),
    GLOSSARY("Glossar", "Fachbegriffe mit kurzer Erklärung, alphabetisch"),
}

/** Rolle der KI („Masterprompt“): bestimmt Ton und Schwerpunkt. Eine eigene Fassung ersetzt den Text, nicht die Regeln gegen Erfinden. */
enum class SummaryRole(val label: String, val prompt: String) {
    TUTOR("Hochschul-Tutor", "Du bist ein erfahrener Hochschul-Tutor und schreibst präzise, klausurtaugliche Lern-Zusammenfassungen."),
    EDITOR("Wissenschaftlicher Lektor", "Du bist ein wissenschaftlicher Lektor. Du verdichtest Fachtexte präzise, sachlich und in korrektem Wissenschaftsstil, ohne den Sinn zu verändern."),
    EXAM_COACH("Klausur-Coach", "Du bist ein Klausur-Coach. Du hebst heraus, was in Prüfungen abgefragt wird: Definitionen, Formeln, Verfahren und typische Fehler."),
    BEGINNER("Erklärer für Einsteiger", "Du erklärst Fachinhalte für Einsteiger in einfacher, klarer Sprache und erklärst Fachbegriffe kurz beim ersten Auftreten."),
    ESSENTIAL("Nur das Wesentliche", "Du fasst ausschließlich das Wesentliche zusammen: keine Nebensächlichkeiten, keine Wiederholungen, keine Ausschmückung."),
}

enum class SummaryLevel(val label: String, val hint: String) {
    BEGINNER("Einsteiger", "Schreibe für Einsteiger ohne Vorkenntnisse; vermeide unnötigen Fachjargon."),
    STANDARD("Standard", ""),
    ADVANCED("Fortgeschritten", "Schreibe für Fortgeschrittene; Fachbegriffe sind bekannt und müssen nicht erklärt werden."),
}

enum class SummaryLanguage(val label: String, val instruction: String) {
    DE("Deutsch", "Schreibe auf Deutsch."),
    EN("Englisch", "Write the summary in English (keep technical terms in their original form where sensible)."),
}

/**
 * Alle Einstellungen einer Zusammenfassung. [targetWords] ist die ungefähre Gesamtlänge; je Abschnitt ergibt sich daraus der Umfang
 * (siehe [wordsPerSection]). Der Fingerabdruck [partsFingerprint] steuert, ob zwischengespeicherte Abschnittsergebnisse noch passen.
 */
data class SummarySpec(
    val format: SummaryFormat = SummaryFormat.BULLETS,
    val targetWords: Int = 400,
    val role: SummaryRole = SummaryRole.TUTOR,
    /** Eigener Rollentext („Masterprompt“); ersetzt [role]. */
    val customRole: String = "",
    /** Zusätzliche Wünsche in freien Worten („Fasse nur das Wesentliche zusammen“). */
    val extra: String = "",
    val level: SummaryLevel = SummaryLevel.STANDARD,
    val language: SummaryLanguage = SummaryLanguage.DE,
    val keepFormulas: Boolean = true,
    val includeExamples: Boolean = false,
    val boldTerms: Boolean = true,
    /** Fundstelle (Seite, Folie) hinter jeden Stichpunkt. */
    val cite: Boolean = false,
    val examFocus: Boolean = false,
) {
    val roleText: String get() = customRole.trim().ifEmpty { role.prompt }

    /** Systemanweisung: Rolle plus feste Regeln gegen Erfinden (nicht abschaltbar). */
    val system: String get() = roleText + " " + FIXED_SYSTEM

    /** Wörter je Abschnitt bei [sections] nutzbaren Abschnitten. */
    fun wordsPerSection(sections: Int): Int = (targetWords / maxOf(1, sections)).coerceIn(MIN_SECTION_WORDS, MAX_SECTION_WORDS)

    /** Erwartete Gesamtlänge in Wörtern (für die Anzeige). */
    fun expectedWords(sections: Int): Int = when (format) {
        SummaryFormat.PROSE -> targetWords
        else -> (wordsPerSection(sections) * sections).coerceAtLeast(MIN_SECTION_WORDS)
    }

    /** Wird die strukturierte Zusammenfassung deutlich länger als gewünscht, verdichtet ein Zusatzschritt sie. */
    fun needsCondense(totalWords: Int): Boolean = format != SummaryFormat.PROSE && format != SummaryFormat.GLOSSARY && totalWords > targetWords * 1.5

    /** Teil des Fingerabdrucks, der den Text eines Abschnitts beeinflusst; passt er nicht, wird der Abschnitt neu erzeugt. */
    fun partsFingerprint(sections: Int): String {
        val perSection = if (format == SummaryFormat.PROSE) wordsPerSection(sections) / 10 * 10 else wordsPerSection(sections) / 10 * 10
        val s = listOf(partKind(), perSection, roleText, extra.trim(), level, language, keepFormulas, includeExamples, boldTerms, cite, examFocus).joinToString("|")
        return MessageDigest.getInstance("SHA-256").digest(s.toByteArray()).joinToString("") { "%02x".format(it) }.take(16)
    }

    fun partKind(): PartKind = when (format) {
        SummaryFormat.OUTLINE -> PartKind.OUTLINE
        SummaryFormat.GLOSSARY -> PartKind.GLOSSARY
        else -> PartKind.BULLETS
    }

    fun toJson(): String = JsonObject().apply {
        addProperty("format", format.name); addProperty("targetWords", targetWords); addProperty("role", role.name); addProperty("customRole", customRole)
        addProperty("extra", extra); addProperty("level", level.name); addProperty("language", language.name); addProperty("keepFormulas", keepFormulas)
        addProperty("includeExamples", includeExamples); addProperty("boldTerms", boldTerms); addProperty("cite", cite); addProperty("examFocus", examFocus)
    }.toString()

    companion object {
        const val MIN_SECTION_WORDS = 20
        const val MAX_SECTION_WORDS = 200
        const val MIN_TARGET = 50
        const val MAX_TARGET = 2000

        const val FIXED_SYSTEM = "Du bleibst strikt am gelieferten Quelltext und erfindest nichts hinzu."

        /** Tolerant: fehlende oder unbekannte Felder fallen auf die Standardwerte zurück (ältere gespeicherte Fassungen bleiben lesbar). */
        fun fromJson(json: String?): SummarySpec {
            val o = runCatching { JsonParser.parseString(json.orEmpty()).asJsonObject }.getOrNull() ?: return SummarySpec()
            fun str(k: String) = o.get(k)?.takeIf { it.isJsonPrimitive }?.asString
            fun bool(k: String, d: Boolean) = o.get(k)?.takeIf { it.isJsonPrimitive }?.runCatching { asBoolean }?.getOrNull() ?: d
            val d = SummarySpec()
            return SummarySpec(
                format = enumOr(str("format"), d.format), targetWords = (str("targetWords")?.toIntOrNull() ?: d.targetWords).coerceIn(MIN_TARGET, MAX_TARGET),
                role = enumOr(str("role"), d.role), customRole = str("customRole").orEmpty(), extra = str("extra").orEmpty(),
                level = enumOr(str("level"), d.level), language = enumOr(str("language"), d.language),
                keepFormulas = bool("keepFormulas", d.keepFormulas), includeExamples = bool("includeExamples", d.includeExamples),
                boldTerms = bool("boldTerms", d.boldTerms), cite = bool("cite", d.cite), examFocus = bool("examFocus", d.examFocus),
            )
        }

        private inline fun <reified E : Enum<E>> enumOr(name: String?, default: E): E = enumValues<E>().firstOrNull { it.name == name } ?: default

        /** Fertige Vorlagen (zusätzlich zu den eigenen). */
        val PRESETS: List<Pair<String, SummarySpec>> = listOf(
            "Schnellüberblick" to SummarySpec(format = SummaryFormat.PROSE, targetWords = 150, role = SummaryRole.ESSENTIAL),
            "Klausur-Spickzettel" to SummarySpec(format = SummaryFormat.BULLETS, targetWords = 500, role = SummaryRole.EXAM_COACH, examFocus = true, keepFormulas = true),
            "Lektor: Stichpunkte" to SummarySpec(format = SummaryFormat.BULLETS, targetWords = 400, role = SummaryRole.EDITOR),
            "Einsteiger-Erklärung" to SummarySpec(format = SummaryFormat.PROSE, targetWords = 500, role = SummaryRole.BEGINNER, level = SummaryLevel.BEGINNER, includeExamples = true),
            "Begriffe lernen" to SummarySpec(format = SummaryFormat.GLOSSARY, role = SummaryRole.TUTOR),
        )
    }
}

/** Welche Teilergebnisse (Abschnittszusammenfassungen) ein Format braucht. */
enum class PartKind { OUTLINE, BULLETS, GLOSSARY }

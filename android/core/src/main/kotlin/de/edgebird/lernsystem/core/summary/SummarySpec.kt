// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.summary

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import de.edgebird.lernsystem.core.i18n.Lang
import de.edgebird.lernsystem.core.i18n.tr
import java.security.MessageDigest

/** Form der Zusammenfassung. */
enum class SummaryFormat {
    OUTLINE, BULLETS, PROSE, GLOSSARY;

    val label: String get() = when (this) {
        OUTLINE -> tr("Gegliedert", "Structured"); BULLETS -> tr("Stichpunkte", "Bullet points"); PROSE -> tr("Fließtext", "Running text"); GLOSSARY -> tr("Glossar", "Glossary")
    }
    val description: String get() = when (this) {
        OUTLINE -> tr("Je Abschnitt: Kernidee, Begriffe, Regeln", "Per section: core idea, terms, rules")
        BULLETS -> tr("Je Abschnitt wenige Stichpunkte", "A few bullet points per section")
        PROSE -> tr("Zusammenhängender Text über das Ganze", "Continuous text about the whole")
        GLOSSARY -> tr("Fachbegriffe mit kurzer Erklärung, alphabetisch", "Technical terms with a short explanation, alphabetical")
    }
}

/** Rolle der KI („Masterprompt“): bestimmt Ton und Schwerpunkt. Eine eigene Fassung ersetzt den Text, nicht die Regeln gegen Erfinden. */
enum class SummaryRole {
    TUTOR, EDITOR, EXAM_COACH, BEGINNER, ESSENTIAL;

    val label: String get() = when (this) {
        TUTOR -> tr("Hochschul-Tutor", "University tutor"); EDITOR -> tr("Wissenschaftlicher Lektor", "Academic editor"); EXAM_COACH -> tr("Klausur-Coach", "Exam coach")
        BEGINNER -> tr("Erklärer für Einsteiger", "Explainer for beginners"); ESSENTIAL -> tr("Nur das Wesentliche", "Essentials only")
    }
    val prompt: String get() = when (this) {
        TUTOR -> tr("Du bist ein erfahrener Hochschul-Tutor und schreibst präzise, klausurtaugliche Lern-Zusammenfassungen.", "You are an experienced university tutor and write precise study summaries suited for exams.")
        EDITOR -> tr("Du bist ein wissenschaftlicher Lektor. Du verdichtest Fachtexte präzise, sachlich und in korrektem Wissenschaftsstil, ohne den Sinn zu verändern.", "You are an academic editor. You condense technical texts precisely, objectively and in correct scientific style without changing the meaning.")
        EXAM_COACH -> tr("Du bist ein Klausur-Coach. Du hebst heraus, was in Prüfungen abgefragt wird: Definitionen, Formeln, Verfahren und typische Fehler.", "You are an exam coach. You highlight what is asked in exams: definitions, formulas, procedures and typical mistakes.")
        BEGINNER -> tr("Du erklärst Fachinhalte für Einsteiger in einfacher, klarer Sprache und erklärst Fachbegriffe kurz beim ersten Auftreten.", "You explain technical content to beginners in simple, clear language and briefly explain technical terms when they first appear.")
        ESSENTIAL -> tr("Du fasst ausschließlich das Wesentliche zusammen: keine Nebensächlichkeiten, keine Wiederholungen, keine Ausschmückung.", "You summarise only the essentials: no side issues, no repetition, no embellishment.")
    }
}

enum class SummaryLevel {
    BEGINNER, STANDARD, ADVANCED;

    val label: String get() = when (this) { BEGINNER -> tr("Einsteiger", "Beginner"); STANDARD -> tr("Standard", "Standard"); ADVANCED -> tr("Fortgeschritten", "Advanced") }
    val hint: String get() = when (this) {
        BEGINNER -> tr("Schreibe für Einsteiger ohne Vorkenntnisse; vermeide unnötigen Fachjargon.", "Write for beginners without prior knowledge; avoid unnecessary jargon.")
        STANDARD -> ""
        ADVANCED -> tr("Schreibe für Fortgeschrittene; Fachbegriffe sind bekannt und müssen nicht erklärt werden.", "Write for advanced readers; technical terms are known and need not be explained.")
    }
}

enum class SummaryLanguage {
    DE, EN;

    val label: String get() = when (this) { DE -> tr("Deutsch", "German"); EN -> tr("Englisch", "English") }
    val lang: de.edgebird.lernsystem.core.i18n.Lang get() = if (this == EN) de.edgebird.lernsystem.core.i18n.Lang.EN else de.edgebird.lernsystem.core.i18n.Lang.DE
    val instruction: String get() = when (this) {
        DE -> "Schreibe die gesamte Zusammenfassung ausschließlich auf Deutsch, auch wenn der Quelltext in einer anderen Sprache ist (Fachbegriffe dürfen in der Originalform stehen)."
        EN -> "Write the entire summary exclusively in English, even if the source text is in another language: translate the content (technical terms may stay in their original form)."
    }

    companion object { fun forApp(lang: Lang = Lang.current) = if (lang == Lang.EN) EN else DE }
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
    val language: SummaryLanguage = SummaryLanguage.forApp(),
    val keepFormulas: Boolean = true,
    val includeExamples: Boolean = false,
    val boldTerms: Boolean = true,
    /** Fundstelle (Seite, Folie) hinter jeden Stichpunkt. */
    val cite: Boolean = false,
    val examFocus: Boolean = false,
) {
    val roleText: String get() = customRole.trim().ifEmpty { role.prompt }

    /** Systemanweisung: Rolle plus feste Regeln gegen Erfinden (nicht abschaltbar). */
    val system: String get() = de.edgebird.lernsystem.core.i18n.Lang.using(language.lang) { roleText + " " + FIXED_SYSTEM }

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

        val FIXED_SYSTEM get() = tr("Du bleibst strikt am gelieferten Quelltext und erfindest nichts hinzu.", "You stay strictly with the supplied source text and add nothing of your own.")

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
        val PRESETS: List<Pair<String, SummarySpec>> get() = listOf(
            tr("Schnellüberblick", "Quick overview") to SummarySpec(format = SummaryFormat.PROSE, targetWords = 150, role = SummaryRole.ESSENTIAL),
            tr("Klausur-Spickzettel", "Exam cheat sheet") to SummarySpec(format = SummaryFormat.BULLETS, targetWords = 500, role = SummaryRole.EXAM_COACH, examFocus = true, keepFormulas = true),
            tr("Lektor: Stichpunkte", "Editor: bullet points") to SummarySpec(format = SummaryFormat.BULLETS, targetWords = 400, role = SummaryRole.EDITOR),
            tr("Einsteiger-Erklärung", "Beginner explanation") to SummarySpec(format = SummaryFormat.PROSE, targetWords = 500, role = SummaryRole.BEGINNER, level = SummaryLevel.BEGINNER, includeExamples = true),
            tr("Begriffe lernen", "Learn terms") to SummarySpec(format = SummaryFormat.GLOSSARY, role = SummaryRole.TUTOR),
        )
    }
}

/** Welche Teilergebnisse (Abschnittszusammenfassungen) ein Format braucht. */
enum class PartKind { OUTLINE, BULLETS, GLOSSARY }

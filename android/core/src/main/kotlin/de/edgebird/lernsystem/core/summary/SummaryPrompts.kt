package de.edgebird.lernsystem.core.summary

import de.edgebird.lernsystem.core.i18n.tr

/** Prompts der Zusammenfassung; alle Einstellungen aus [SummarySpec] fließen hier ein. */
object SummaryPrompts {
    private const val Q = "\"\"\""

    private fun grounding() = tr(
        """- Verwende AUSSCHLIESSLICH Informationen aus dem Quelltext oben. Erfinde nichts, ergänze kein Fremdwissen, rate keine Zahlen.
- Übernimm Zahlen, Fristen und Fachbegriffe exakt wie im Quelltext.""",
        """- Use EXCLUSIVELY information from the source text above. Invent nothing, add no outside knowledge, do not guess numbers.
- Take over numbers, deadlines and technical terms exactly as in the source text.""",
    )

    /** Regelzeilen aus den Einstellungen (ohne Länge und Form, die je Format anders sind). */
    fun rules(spec: SummarySpec): String = buildList {
        add(grounding())
        spec.level.hint.takeIf { it.isNotEmpty() }?.let { add("- $it") }
        add("- " + spec.language.instruction)
        add(if (spec.keepFormulas) tr("- Formeln und Regeln exakt aus dem Quelltext übernehmen, LaTeX beibehalten (einfacher Backslash, in \$...\$).", "- Take formulas and rules exactly from the source text, keep LaTeX (single backslash, in \$...\$).") else tr("- Formeln nur in Worten beschreiben, keine LaTeX-Formeln ausgeben.", "- Describe formulas in words only, output no LaTeX formulas."))
        add(if (spec.includeExamples) tr("- Nenne ein kurzes Beispiel aus dem Quelltext, wenn es das Verständnis stützt.", "- Give a short example from the source text if it supports understanding.") else tr("- Lasse Beispiele weg, außer sie sind zum Verständnis unverzichtbar.", "- Leave out examples unless they are indispensable for understanding."))
        if (spec.boldTerms) add(if (spec.format == SummaryFormat.PROSE) tr("- Markiere höchstens 5 zentrale Begriffe **fett**, nicht mehr.", "- Mark at most 5 key terms in **bold**, no more.") else tr("- Wichtige Begriffe **fett** markieren.", "- Mark important terms in **bold**."))
        if (spec.cite) add(tr("- Setze hinter jede Aussage die Fundstelle in Klammern, genau wie oben angegeben (z. B. „(Seite 4)“).", "- Put the location in parentheses after each statement, exactly as given above (e.g. \"(Page 4)\")."))
        if (spec.examFocus) add(tr("- Stelle heraus, was in einer Prüfung abgefragt werden könnte (Definitionen, Formeln, Verfahren, typische Fehler).", "- Highlight what could be asked in an exam (definitions, formulas, procedures, typical mistakes)."))
    }.joinToString("\n")

    private fun extra(spec: SummarySpec): String =
        spec.extra.trim().takeIf { it.isNotEmpty() }?.let { tr("\nZusätzlicher Wunsch der Nutzerin/des Nutzers (gilt nur im Rahmen der Regeln oben, nie gegen sie): ${it.take(400)}", "\nAdditional wish of the user (applies only within the rules above, never against them): ${it.take(400)}") }.orEmpty()

    private fun bulletCount(words: Int) = when { words <= 40 -> tr("2 bis 3", "2 to 3"); words <= 80 -> tr("3 bis 6", "3 to 6"); words <= 130 -> tr("5 bis 8", "5 to 8"); else -> tr("7 bis 10", "7 to 10") }

    private fun emptyRule() = tr("Wenn der Abschnitt keine prüfungsrelevante Substanz enthält, gib exakt \"${SummaryChecks.EMPTY_MARKER}\" aus.", "If the section contains no exam-relevant substance, output exactly \"${SummaryChecks.EMPTY_MARKER}\".")

    /**
     * Das Modell überschreitet Längenangaben bei Stichpunkten und Gliederung im Mittel um 50 bis 80 Prozent (auf dem Gerät gemessen). Darum wird im
     * Prompt ein kleinerer Wert genannt und als Obergrenze formuliert.
     */
    const val LENGTH_CALIBRATION = 0.7

    /** Zusammenfassung EINES Abschnitts im gewählten Format; [words] = Zielumfang dieses Abschnitts. */
    fun section(spec: SummarySpec, label: String, title: String, text: String, words: Int): String {
        val ask = maxOf(15, (words * LENGTH_CALIBRATION).toInt())
        val head = tr(
            """Abschnitt der Quelle "$label" (Thema: $title).
Nur der folgende Quelltext ist erlaubte Wissensgrundlage:
$Q
$text
$Q
""",
            """Section of the source "$label" (topic: $title).
Only the following source text is an allowed basis of knowledge:
$Q
$text
$Q
""",
        )
        val body = when (spec.format) {
            SummaryFormat.OUTLINE -> tr(
                """Schreibe eine prägnante, klausurtaugliche Zusammenfassung DIESES Abschnitts als Markdown, höchstens $ask Wörter. Regeln:
${rules(spec)}
- Struktur (nur die zutreffenden Punkte, in dieser Reihenfolge):
  - **Kernidee:** 1-2 Sätze, worum es geht.
  - **Definitionen & Begriffe:** als Stichpunkte.
  - **Formeln / Regeln:** exakt aus dem Quelltext.
  - **Vorgehen / Merksätze:** knappe Merk-Punkte.
  - **Typische Stolperfallen:** nur falls im Quelltext genannt.
- Kurz und dicht, keine Wiederholung des Rohtexts.
- Beginne NICHT mit einer eigenen Überschrift; gib nur den Inhalt aus.""",
                """Write a concise summary of THIS section suited for exams, as Markdown, at most $ask words. Rules:
${rules(spec)}
- Structure (only the applicable points, in this order):
  - **Core idea:** 1-2 sentences on what it is about.
  - **Definitions & terms:** as bullet points.
  - **Formulas / rules:** exactly from the source text.
  - **Procedure / key takeaways:** short memory points.
  - **Typical pitfalls:** only if mentioned in the source text.
- Short and dense, no repetition of the raw text.
- Do NOT start with a heading of your own; output only the content.""",
            )
            SummaryFormat.BULLETS, SummaryFormat.PROSE -> tr(
                """Fasse DIESEN Abschnitt in ${bulletCount(words)} Stichpunkten zusammen (Markdown-Liste mit "- "), zusammen höchstens $ask Wörter. Regeln:
${rules(spec)}
- Jeder Stichpunkt ist ein vollständiger, verständlicher Satz oder eine klare Aussage.
- Keine Überschrift, keine Einleitung, nur die Liste.""",
                """Summarise THIS section in ${bulletCount(words)} bullet points (Markdown list with "- "), together at most $ask words. Rules:
${rules(spec)}
- Each bullet point is a complete, understandable sentence or a clear statement.
- No heading, no introduction, only the list.""",
            )
            SummaryFormat.GLOSSARY -> tr(
                """Erstelle ein Glossar der wichtigsten Fachbegriffe DIESES Abschnitts. Regeln:
${rules(spec)}
- Je Begriff genau eine Zeile im Format "- **Begriff:** Erklärung in einem Satz".
- Nur Begriffe, die der Quelltext definiert oder erklärt; höchstens ${maxOf(2, words / 20)} Begriffe.
- Keine Überschrift, keine Einleitung, nur die Liste.""",
                """Create a glossary of the most important technical terms of THIS section. Rules:
${rules(spec)}
- Exactly one line per term in the format "- **Term:** explanation in one sentence".
- Only terms that the source text defines or explains; at most ${maxOf(2, words / 20)} terms.
- No heading, no introduction, only the list.""",
            )
        }
        return head + "\n" + body + extra(spec) + "\n" + emptyRule()
    }

    /** Letzter Schritt des Formats Fließtext: aus allen Abschnittsstichpunkten ein zusammenhängender Text. */
    fun proseFinal(spec: SummarySpec, label: String, parts: String): String = tr(
        """Dies sind Stichpunkte zu den einzelnen Abschnitten der Quelle "$label":
$Q
$parts
$Q

Schreibe daraus eine zusammenhängende Zusammenfassung des GANZEN Dokuments als Fließtext in ${paragraphs(spec.targetWords)}, etwa ${spec.targetWords} Wörter. Regeln:
${rules(spec)}
- Kein Aufzählungs-Layout, sondern ganze Sätze in logischer Reihenfolge; verbinde zusammengehörige Aussagen.
- Keine eigene Überschrift, keine Wiederholung gleicher Aussagen.${extra(spec)}""",
        """These are bullet points on the individual sections of the source "$label":
$Q
$parts
$Q

Write from them a coherent summary of the WHOLE document as running text in ${paragraphs(spec.targetWords)}, about ${spec.targetWords} words. Rules:
${rules(spec)}
- No list layout, but whole sentences in logical order; connect related statements.
- No heading of your own, no repetition of the same statements.${extra(spec)}""",
    )

    private fun paragraphs(words: Int) = when {
        words <= 120 -> tr("einem Absatz", "one paragraph")
        words <= 450 -> tr("2 bis 4 Absätzen", "2 to 4 paragraphs")
        else -> tr("mehreren Absätzen mit kurzen Zwischenüberschriften (## )", "several paragraphs with short subheadings (## )")
    }

    /** Zwischenschritt, wenn die Stichpunkte nicht in einen Aufruf passen. */
    fun intermediate(spec: SummarySpec, label: String, parts: String, words: Int): String = tr(
        """Dies sind Stichpunkte zu aufeinanderfolgenden Abschnitten der Quelle "$label":
$Q
$parts
$Q

Verdichte sie zu Stichpunkten ("- "), insgesamt etwa $words Wörter, die alle wichtigen Begriffe, Regeln und Zahlen enthalten.
${rules(spec)}
- Keine Überschrift, keine Einleitung, nur die Liste.""",
        """These are bullet points on consecutive sections of the source "$label":
$Q
$parts
$Q

Condense them into bullet points ("- "), about $words words in total, containing all important terms, rules and numbers.
${rules(spec)}
- No heading, no introduction, only the list.""",
    )

    /** Kürzt eine fertige strukturierte Zusammenfassung (Gruppe von Abschnitten) auf [words] Wörter. */
    fun condense(spec: SummarySpec, label: String, text: String, words: Int): String = tr(
        """Dies ist ein Teil einer Zusammenfassung der Quelle "$label":
$Q
$text
$Q

Kürze ihn auf etwa $words Wörter. Behalte die Struktur (Überschriften mit "## ", Stichpunkte mit "- ") und das Wichtigste bei, streiche Nebensächliches und Wiederholungen.
${rules(spec)}
- Keine neue Einleitung.${extra(spec)}""",
        """This is part of a summary of the source "$label":
$Q
$text
$Q

Shorten it to about $words words. Keep the structure (headings with "## ", bullet points with "- ") and the most important content, drop side issues and repetition.
${rules(spec)}
- No new introduction.${extra(spec)}""",
    )

    /** Überblicksabsatz über mehrere Dokumente (Fach-Zusammenfassung). */
    fun overview(spec: SummarySpec, subject: String, perDoc: String, words: Int): String = tr(
        """Dies sind Zusammenfassungen mehrerer Quellen zum Fach "$subject":
$Q
$perDoc
$Q

Schreibe einen Überblick über das ganze Fach als Fließtext in etwa $words Wörtern: Worum geht es insgesamt, wie hängen die Quellen zusammen, was sind die wichtigsten Punkte?
${rules(spec)}
- Keine Überschrift, keine Aufzählung.${extra(spec)}""",
        """These are summaries of several sources on the subject "$subject":
$Q
$perDoc
$Q

Write an overview of the whole subject as running text of about $words words: what is it about overall, how do the sources relate, what are the most important points?
${rules(spec)}
- No heading, no list.${extra(spec)}""",
    )

    val RETRY_NUMBERS get() = tr("\n\nWICHTIG: Der letzte Versuch enthielt Zahlen, die im Quelltext nicht stehen. Verwende nur Zahlen aus dem Quelltext oder gar keine.", "\n\nIMPORTANT: The last attempt contained numbers that are not in the source text. Use only numbers from the source text or none at all.")
}

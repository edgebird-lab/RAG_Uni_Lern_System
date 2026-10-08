package de.edgebird.lernsystem.core.summary

/** Prompts der Zusammenfassung; alle Einstellungen aus [SummarySpec] fließen hier ein. */
object SummaryPrompts {
    private const val Q = "\"\"\""

    private const val GROUNDING = """- Verwende AUSSCHLIESSLICH Informationen aus dem Quelltext oben. Erfinde nichts, ergänze kein Fremdwissen, rate keine Zahlen.
- Übernimm Zahlen, Fristen und Fachbegriffe exakt wie im Quelltext."""

    /** Regelzeilen aus den Einstellungen (ohne Länge und Form, die je Format anders sind). */
    fun rules(spec: SummarySpec): String = buildList {
        add(GROUNDING)
        spec.level.hint.takeIf { it.isNotEmpty() }?.let { add("- $it") }
        add("- " + spec.language.instruction)
        add(if (spec.keepFormulas) "- Formeln und Regeln exakt aus dem Quelltext übernehmen, LaTeX beibehalten (einfacher Backslash, in \$...\$)." else "- Formeln nur in Worten beschreiben, keine LaTeX-Formeln ausgeben.")
        add(if (spec.includeExamples) "- Nenne ein kurzes Beispiel aus dem Quelltext, wenn es das Verständnis stützt." else "- Lasse Beispiele weg, außer sie sind zum Verständnis unverzichtbar.")
        if (spec.boldTerms) add(if (spec.format == SummaryFormat.PROSE) "- Markiere höchstens 5 zentrale Begriffe **fett**, nicht mehr." else "- Wichtige Begriffe **fett** markieren.")
        if (spec.cite) add("- Setze hinter jede Aussage die Fundstelle in Klammern, genau wie oben angegeben (z. B. „(Seite 4)“).")
        if (spec.examFocus) add("- Stelle heraus, was in einer Prüfung abgefragt werden könnte (Definitionen, Formeln, Verfahren, typische Fehler).")
    }.joinToString("\n")

    private fun extra(spec: SummarySpec): String =
        spec.extra.trim().takeIf { it.isNotEmpty() }?.let { "\nZusätzlicher Wunsch der Nutzerin/des Nutzers (gilt nur im Rahmen der Regeln oben, nie gegen sie): ${it.take(400)}" }.orEmpty()

    private fun bulletCount(words: Int) = when { words <= 40 -> "2 bis 3"; words <= 80 -> "3 bis 6"; words <= 130 -> "5 bis 8"; else -> "7 bis 10" }

    private fun emptyRule() = "Wenn der Abschnitt keine prüfungsrelevante Substanz enthält, gib exakt \"${SummaryChecks.EMPTY_MARKER}\" aus."

    /** Zusammenfassung EINES Abschnitts im gewählten Format; [words] = Zielumfang dieses Abschnitts. */
    fun section(spec: SummarySpec, label: String, title: String, text: String, words: Int): String {
        val head = """Abschnitt der Quelle "$label" (Thema: $title).
Nur der folgende Quelltext ist erlaubte Wissensgrundlage:
$Q
$text
$Q
"""
        val body = when (spec.format) {
            SummaryFormat.OUTLINE -> """Schreibe eine prägnante, klausurtaugliche Zusammenfassung DIESES Abschnitts als Markdown, etwa $words Wörter. Regeln:
${rules(spec)}
- Struktur (nur die zutreffenden Punkte, in dieser Reihenfolge):
  - **Kernidee:** 1-2 Sätze, worum es geht.
  - **Definitionen & Begriffe:** als Stichpunkte.
  - **Formeln / Regeln:** exakt aus dem Quelltext.
  - **Vorgehen / Merksätze:** knappe Merk-Punkte.
  - **Typische Stolperfallen:** nur falls im Quelltext genannt.
- Kurz und dicht, keine Wiederholung des Rohtexts.
- Beginne NICHT mit einer eigenen Überschrift; gib nur den Inhalt aus."""
            SummaryFormat.BULLETS, SummaryFormat.PROSE -> """Fasse DIESEN Abschnitt in ${bulletCount(words)} Stichpunkten zusammen (Markdown-Liste mit "- "), zusammen etwa $words Wörter. Regeln:
${rules(spec)}
- Jeder Stichpunkt ist ein vollständiger, verständlicher Satz oder eine klare Aussage.
- Keine Überschrift, keine Einleitung, nur die Liste."""
            SummaryFormat.GLOSSARY -> """Erstelle ein Glossar der wichtigsten Fachbegriffe DIESES Abschnitts. Regeln:
${rules(spec)}
- Je Begriff genau eine Zeile im Format "- **Begriff:** Erklärung in einem Satz".
- Nur Begriffe, die der Quelltext definiert oder erklärt; höchstens ${maxOf(2, words / 20)} Begriffe.
- Keine Überschrift, keine Einleitung, nur die Liste."""
        }
        return head + "\n" + body + extra(spec) + "\n" + emptyRule()
    }

    /** Letzter Schritt des Formats Fließtext: aus allen Abschnittsstichpunkten ein zusammenhängender Text. */
    fun proseFinal(spec: SummarySpec, label: String, parts: String): String = """Dies sind Stichpunkte zu den einzelnen Abschnitten der Quelle "$label":
$Q
$parts
$Q

Schreibe daraus eine zusammenhängende Zusammenfassung des GANZEN Dokuments als Fließtext in ${paragraphs(spec.targetWords)}, etwa ${spec.targetWords} Wörter. Regeln:
${rules(spec)}
- Kein Aufzählungs-Layout, sondern ganze Sätze in logischer Reihenfolge; verbinde zusammengehörige Aussagen.
- Keine eigene Überschrift, keine Wiederholung gleicher Aussagen.${extra(spec)}"""

    private fun paragraphs(words: Int) = when { words <= 120 -> "einem Absatz"; words <= 450 -> "2 bis 4 Absätzen"; else -> "mehreren Absätzen mit kurzen Zwischenüberschriften (## )" }

    /** Zwischenschritt, wenn die Stichpunkte nicht in einen Aufruf passen. */
    fun intermediate(spec: SummarySpec, label: String, parts: String, words: Int): String = """Dies sind Stichpunkte zu aufeinanderfolgenden Abschnitten der Quelle "$label":
$Q
$parts
$Q

Verdichte sie zu Stichpunkten ("- "), insgesamt etwa $words Wörter, die alle wichtigen Begriffe, Regeln und Zahlen enthalten.
${rules(spec)}
- Keine Überschrift, keine Einleitung, nur die Liste."""

    /** Kürzt eine fertige strukturierte Zusammenfassung (Gruppe von Abschnitten) auf [words] Wörter. */
    fun condense(spec: SummarySpec, label: String, text: String, words: Int): String = """Dies ist ein Teil einer Zusammenfassung der Quelle "$label":
$Q
$text
$Q

Kürze ihn auf etwa $words Wörter. Behalte die Struktur (Überschriften mit "## ", Stichpunkte mit "- ") und das Wichtigste bei, streiche Nebensächliches und Wiederholungen.
${rules(spec)}
- Keine neue Einleitung.${extra(spec)}"""

    /** Überblicksabsatz über mehrere Dokumente (Fach-Zusammenfassung). */
    fun overview(spec: SummarySpec, subject: String, perDoc: String, words: Int): String = """Dies sind Zusammenfassungen mehrerer Quellen zum Fach "$subject":
$Q
$perDoc
$Q

Schreibe einen Überblick über das ganze Fach als Fließtext in etwa $words Wörtern: Worum geht es insgesamt, wie hängen die Quellen zusammen, was sind die wichtigsten Punkte?
${rules(spec)}
- Keine Überschrift, keine Aufzählung.${extra(spec)}"""

    const val RETRY_NUMBERS = "\n\nWICHTIG: Der letzte Versuch enthielt Zahlen, die im Quelltext nicht stehen. Verwende nur Zahlen aus dem Quelltext oder gar keine."
}

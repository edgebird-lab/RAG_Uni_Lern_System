package de.edgebird.lernsystem.core.summary

/**
 * Stile der Zusammenfassung.
 * - OUTLINE: je Abschnitt gegliedert (Kernidee, Begriffe, Regeln …), wie in der PC-App
 * - BULLETS: je Abschnitt 3 bis 6 Stichpunkte
 * - SHORT: Kurzfassung des ganzen Dokuments (aus den Stichpunkten, Map-Reduce)
 */
enum class SummaryStyle(val label: String, val description: String) {
    OUTLINE("Gegliedert", "Je Abschnitt: Kernidee, Begriffe, Regeln"),
    BULLETS("Stichpunkte", "Je Abschnitt wenige Stichpunkte"),
    SHORT("Kurzfassung", "Das Wichtigste des ganzen Dokuments auf einer Seite"),
}

/** Welche Teilergebnisse (Abschnittszusammenfassungen) ein Stil braucht. */
enum class PartKind { OUTLINE, BULLETS }

object SummaryPrompts {
    const val SYSTEM = "Du bist ein erfahrener Hochschul-Tutor und schreibst präzise, klausurtaugliche Lern-Zusammenfassungen. Du bleibst strikt am gelieferten Quelltext und erfindest nichts hinzu."

    private const val GROUNDING = """- Verwende AUSSCHLIESSLICH Informationen aus dem Quelltext oben. Erfinde nichts, ergänze kein Fremdwissen, rate keine Zahlen.
- Übernimm Zahlen, Fristen und Fachbegriffe exakt wie im Quelltext."""

    fun outline(label: String, title: String, section: String): String = """Abschnitt der Quelle "$label" (Thema: $title).
Nur der folgende Quelltext ist erlaubte Wissensgrundlage:
${"\"\"\""}
$section
${"\"\"\""}

Schreibe eine prägnante, klausurtaugliche Zusammenfassung DIESES Abschnitts als Markdown. Regeln:
$GROUNDING
- Struktur (nur die zutreffenden Punkte, in dieser Reihenfolge):
  - **Kernidee:** 1-2 Sätze, worum es geht.
  - **Definitionen & Begriffe:** als Stichpunkte.
  - **Formeln / Regeln:** exakt aus dem Quelltext übernehmen, LaTeX beibehalten (einfacher Backslash, in ${'$'}...${'$'}).
  - **Vorgehen / Merksätze:** knappe Merk-Punkte.
  - **Typische Stolperfallen:** nur falls im Quelltext genannt.
- Kurz und dicht (Stichpunkte bevorzugt), keine Wiederholung des Rohtexts.
- Beginne NICHT mit einer eigenen Überschrift; gib nur den Inhalt aus.
Wenn der Abschnitt keine prüfungsrelevante Substanz enthält, gib exakt "${SummaryChecks.EMPTY_MARKER}" aus."""

    fun bullets(label: String, title: String, section: String): String = """Abschnitt der Quelle "$label" (Thema: $title).
Nur der folgende Quelltext ist erlaubte Wissensgrundlage:
${"\"\"\""}
$section
${"\"\"\""}

Fasse DIESEN Abschnitt in 3 bis 6 Stichpunkten zusammen (Markdown-Liste mit "- "). Regeln:
$GROUNDING
- Jeder Stichpunkt ist ein vollständiger, verständlicher Satz oder eine klare Aussage.
- Wichtige Begriffe **fett** markieren.
- Keine Überschrift, keine Einleitung, nur die Liste.
Wenn der Abschnitt keine prüfungsrelevante Substanz enthält, gib exakt "${SummaryChecks.EMPTY_MARKER}" aus."""

    /** Letzter Schritt der Kurzfassung: aus allen Abschnittsstichpunkten eine Übersicht. */
    fun shortFinal(label: String, parts: String): String = """Dies sind Stichpunkte zu den einzelnen Abschnitten der Quelle "$label":
${"\"\"\""}
$parts
${"\"\"\""}

Schreibe daraus eine Kurzfassung des GANZEN Dokuments als Markdown:
- Zuerst ein kurzer Absatz (3 bis 5 Sätze) mit der Kernaussage und dem Aufbau.
- Danach die Zeile "**Das Wichtigste:**" und 4 bis 8 Stichpunkte ("- ") mit den wichtigsten Begriffen, Regeln und Zahlen.
$GROUNDING
- Keine eigene Überschrift.
- Keine Wiederholung gleicher Aussagen."""

    /** Zwischenschritt, wenn die Stichpunkte aller Abschnitte nicht in einen Aufruf passen. */
    fun shortIntermediate(label: String, parts: String): String = """Dies sind Stichpunkte zu aufeinanderfolgenden Abschnitten der Quelle "$label":
${"\"\"\""}
$parts
${"\"\"\""}

Verdichte sie zu 5 bis 8 Stichpunkten ("- "), die alle wichtigen Begriffe, Regeln und Zahlen enthalten.
$GROUNDING
- Keine Überschrift, keine Einleitung, nur die Liste."""

    const val RETRY_NUMBERS = "\n\nWICHTIG: Der letzte Versuch enthielt Zahlen, die im Quelltext nicht stehen. Verwende nur Zahlen aus dem Quelltext oder gar keine."
}

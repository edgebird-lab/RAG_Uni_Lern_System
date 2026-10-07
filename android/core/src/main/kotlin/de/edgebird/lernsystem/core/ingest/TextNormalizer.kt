package de.edgebird.lernsystem.core.ingest

import java.text.Normalizer

/** Vereinheitlicht Unicode und Whitespace, wichtig für stabile Hashes und Dedup (Port von `normalize_text`). */
object TextNormalizer {
    // Nur echte Silbentrennung am Zeilenende zusammenfügen: Buchstabe + '-' + Zeilenumbruch + Kleinbuchstabe.
    private val HYPHEN = Regex("([A-Za-zÄÖÜäöüß])-\n([a-zäöüß])")
    private val SPACES = Regex("[ \t]+")
    private val BLANK_LINES = Regex("\n{3,}")

    fun normalize(text: String): String {
        if (text.isEmpty()) return ""
        var t = Normalizer.normalize(text, Normalizer.Form.NFC)
        t = t.replace("\r\n", "\n").replace("\r", "\n")
        t = HYPHEN.replace(t, "$1$2")
        t = SPACES.replace(t, " ")
        t = BLANK_LINES.replace(t, "\n\n")
        return t.trim()
    }
}

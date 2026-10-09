// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.i18n

/**
 * Sprache der App: bestimmt Oberfläche, Anweisungen an die KI (und damit ihre Antworten), Sprachausgabe und Suchhilfen.
 * [current] wird beim Start aus den Einstellungen gesetzt; beim Wechsel startet die Oberfläche neu. Vorgabe ist Deutsch, damit
 * die Tests der Kernlogik unabhängig von Einstellungen laufen.
 */
enum class Lang(val tag: String, val nativeName: String) {
    DE("de", "Deutsch"),
    EN("en", "English");

    /** Gebietsschema für Datums- und Zahlenformate. */
    val locale: java.util.Locale get() = if (this == EN) java.util.Locale.ENGLISH else java.util.Locale.GERMAN

    companion object {
        @Volatile var current: Lang = DE

        private val forced = ThreadLocal<Lang?>()

        /** Sprache für [tr]: die erzwungene des laufenden (synchronen) Blocks, sonst [current]. */
        val effective: Lang get() = forced.get() ?: current

        /**
         * Führt [block] mit einer anderen Textsprache aus, z. B. für KI-Anweisungen, die in der Sprache der Zusammenfassung statt der
         * der Oberfläche stehen müssen. Gilt nur für den aktuellen Thread und den Block; in suspend-Code nicht über Unterbrechungen hinweg.
         */
        fun <T> using(lang: Lang, block: () -> T): T {
            val before = forced.get()
            forced.set(lang)
            try { return block() } finally { forced.set(before) }
        }

        fun fromTag(tag: String?): Lang? = entries.firstOrNull { it.tag.equals(tag?.take(2), ignoreCase = true) }

        /** Ohne gespeicherte Wahl: Systemsprache Englisch gibt Englisch, alles andere Deutsch. */
        fun default(systemTag: String?): Lang = fromTag(systemTag) ?: DE
    }
}

/** Text je nach Sprache; im Kern und in der Oberfläche gleichermaßen nutzbar. */
fun tr(de: String, en: String, lang: Lang = Lang.effective): String = if (lang == Lang.EN) en else de

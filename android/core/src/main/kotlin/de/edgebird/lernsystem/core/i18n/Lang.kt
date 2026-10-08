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

        fun fromTag(tag: String?): Lang? = entries.firstOrNull { it.tag.equals(tag?.take(2), ignoreCase = true) }

        /** Ohne gespeicherte Wahl: Systemsprache Englisch gibt Englisch, alles andere Deutsch. */
        fun default(systemTag: String?): Lang = fromTag(systemTag) ?: DE
    }
}

/** Text je nach Sprache; im Kern und in der Oberfläche gleichermaßen nutzbar. */
fun tr(de: String, en: String, lang: Lang = Lang.current): String = if (lang == Lang.EN) en else de

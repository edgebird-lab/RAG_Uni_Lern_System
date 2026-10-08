package de.edgebird.lernsystem.voice

import android.content.SharedPreferences
import org.json.JSONObject
import de.edgebird.lernsystem.ai.PiperVoice
import de.edgebird.lernsystem.core.i18n.Lang
import java.io.File

/** Eine installierte Stimme aus dem Katalog (Download aus dem Modell-Repo). */
data class VoiceEntry(val id: String, val name: String, val lang: Lang, val dir: File)

/**
 * Verwaltet die Offline-Stimmen auf dem Gerät. Sie liegen in `models/tts-<sprache>[-name]/` (Ordner = Kennung).
 * Je Sprache der App wird eine Stimme gewählt; ohne Wahl gilt die erste passende installierte Stimme.
 */
class VoiceLibrary(private val modelsDir: File, private val prefs: SharedPreferences) {
    private fun read(dir: File): VoiceEntry? {
        if (!PiperVoice.hasModel(dir)) return null
        val meta = runCatching { JSONObject(File(dir, "voice.json").readText()) }.getOrNull()
        val lang = Lang.fromTag(meta?.optString("lang")) ?: Lang.fromTag(Regex("^tts-([a-z]{2})").find(dir.name)?.groupValues?.get(1)) ?: return null
        val name = meta?.optString("name")?.takeIf { it.isNotBlank() }
            ?: if (dir.name == "tts-de") "Thorsten (Deutsch)" else dir.name.removePrefix("tts-")
        return VoiceEntry(id = dir.name, name = name, lang = lang, dir = dir)
    }

    /** Alle nutzbaren Stimmen. Eine Stimme ohne eigene espeak-ng-Daten braucht die einer anderen. */
    fun installed(): List<VoiceEntry> {
        val all = modelsDir.listFiles().orEmpty().filter { it.isDirectory && it.name.startsWith("tts-") && !it.name.endsWith(".new") }.sortedBy { it.name }.mapNotNull { read(it) }
        return all.filter { hasData(it, all) }
    }

    private fun hasData(e: VoiceEntry, all: List<VoiceEntry>) = PiperVoice.hasData(File(e.dir, "espeak-ng-data")) || all.any { it !== e && PiperVoice.hasData(File(it.dir, "espeak-ng-data")) }

    /** Ordner mit den espeak-ng-Daten für [e]: die eigenen oder die einer anderen installierten Stimme. */
    fun dataDirFor(e: VoiceEntry): File {
        val own = File(e.dir, "espeak-ng-data")
        if (PiperVoice.hasData(own)) return own
        return installed().firstNotNullOfOrNull { File(it.dir, "espeak-ng-data").takeIf { d -> PiperVoice.hasData(d) } } ?: own
    }

    fun forLang(lang: Lang) = installed().filter { it.lang == lang }

    fun selected(lang: Lang = Lang.current): VoiceEntry? {
        val list = forLang(lang)
        val id = prefs.getString(prefKey(lang), null)
        return list.firstOrNull { it.id == id } ?: list.firstOrNull()
    }

    fun select(e: VoiceEntry) { prefs.edit().putString(prefKey(e.lang), e.id).apply() }

    fun delete(e: VoiceEntry) {
        e.dir.deleteRecursively()
        if (prefs.getString(prefKey(e.lang), null) == e.id) prefs.edit().remove(prefKey(e.lang)).apply()
    }

    private fun prefKey(lang: Lang) = "voice_${lang.tag}"

}

package de.edgebird.lernsystem.voice

import android.content.SharedPreferences
import org.json.JSONObject
import de.edgebird.lernsystem.ai.PiperVoice
import de.edgebird.lernsystem.core.i18n.Lang
import de.edgebird.lernsystem.core.i18n.tr
import java.io.File
import java.io.InputStream

/** Eine installierte Stimme: aus dem Katalog (Download) oder vom Nutzer importiert. */
data class VoiceEntry(val id: String, val name: String, val lang: Lang, val dir: File, val custom: Boolean)

/**
 * Verwaltet die Offline-Stimmen auf dem Gerät. Katalogstimmen liegen in `models/tts-<sprache>[-name]/` (Ordner = Kennung), eigene in `models/voices-custom/<name>/`.
 * Je Sprache der App wird eine Stimme gewählt; ohne Wahl gilt die erste passende installierte Stimme.
 */
class VoiceLibrary(private val modelsDir: File, private val prefs: SharedPreferences) {
    private val customDir = File(modelsDir, "voices-custom")

    private fun read(dir: File, custom: Boolean): VoiceEntry? {
        if (!PiperVoice.hasModel(dir)) return null
        val meta = runCatching { JSONObject(File(dir, "voice.json").readText()) }.getOrNull()
        val lang = Lang.fromTag(meta?.optString("lang")) ?: Lang.fromTag(Regex("^tts-([a-z]{2})").find(dir.name)?.groupValues?.get(1)) ?: return null
        val name = meta?.optString("name")?.takeIf { it.isNotBlank() }
            ?: if (dir.name == "tts-de") "Thorsten (Deutsch)" else dir.name.removePrefix("tts-")
        return VoiceEntry(id = if (custom) "custom-${dir.name}" else dir.name, name = name, lang = lang, dir = dir, custom = custom)
    }

    /** Alle nutzbaren Stimmen (Katalog zuerst, dann eigene). Eine Stimme ohne eigene espeak-ng-Daten braucht die einer anderen. */
    fun installed(): List<VoiceEntry> {
        val catalog = modelsDir.listFiles().orEmpty().filter { it.isDirectory && it.name.startsWith("tts-") && !it.name.endsWith(".new") }.sortedBy { it.name }.mapNotNull { read(it, false) }
        val custom = customDir.listFiles().orEmpty().filter { it.isDirectory && !it.name.endsWith(".new") }.sortedBy { it.name }.mapNotNull { read(it, true) }
        val all = catalog + custom
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

    /**
     * Importiert ein Stimmenpaket (ZIP mit `model.onnx`, `tokens.txt`, optional `espeak-ng-data/` und `voice.json`) als eigene Stimme.
     * @return die neue Stimme; wirft [IllegalArgumentException] mit verständlicher Meldung, wenn das Paket nicht taugt.
     */
    fun importZip(input: InputStream, displayName: String, lang: Lang): VoiceEntry {
        val slug = displayName.substringBeforeLast('.').lowercase().replace(Regex("[^a-z0-9]+"), "-").trim('-').ifEmpty { "stimme" }.take(40)
        customDir.mkdirs()
        val tmp = File(customDir, "$slug.new").also { it.deleteRecursively(); it.mkdirs() }
        try {
            var total = 0L
            java.util.zip.ZipInputStream(input.buffered()).use { zin ->
                while (true) {
                    val e = zin.nextEntry ?: break
                    val out = File(tmp, e.name)
                    require(out.canonicalPath.startsWith(tmp.canonicalPath + File.separator)) { tr("Ungültiges Paket (Pfad außerhalb des Ordners)", "Invalid package (path outside the folder)") }
                    if (e.isDirectory) { out.mkdirs(); continue }
                    out.parentFile?.mkdirs()
                    out.outputStream().use { o ->
                        val buf = ByteArray(64 * 1024)
                        while (true) {
                            val n = zin.read(buf); if (n < 0) break
                            total += n; require(total <= MAX_IMPORT_BYTES) { tr("Das Paket ist größer als erlaubt (400 MB).", "The package is larger than allowed (400 MB).") }
                            o.write(buf, 0, n)
                        }
                    }
                }
            }
            // Liegt alles in einem einzigen Unterordner, eine Ebene hochholen
            val kids = tmp.listFiles().orEmpty()
            if (!PiperVoice.hasModel(tmp) && kids.size == 1 && kids[0].isDirectory) kids[0].listFiles().orEmpty().forEach { it.renameTo(File(tmp, it.name)) }
            require(PiperVoice.hasModel(tmp)) { tr("Im Paket fehlen model.onnx und tokens.txt. Erwartet wird ein Stimmenpaket im Format der App (siehe Anleitung im Modell-Repo).", "The package lacks model.onnx and tokens.txt. A voice pack in the app’s format is expected (see the instructions in the model repo).") }
            val meta = runCatching { JSONObject(File(tmp, "voice.json").readText()) }.getOrNull()
            val finalLang = Lang.fromTag(meta?.optString("lang")) ?: lang
            val name = meta?.optString("name")?.takeIf { it.isNotBlank() } ?: displayName.substringBeforeLast('.')
            File(tmp, "voice.json").writeText(JSONObject().put("name", name).put("lang", finalLang.tag).toString())
            val target = File(customDir, slug).also { it.deleteRecursively() }
            require(tmp.renameTo(target)) { tr("Die Stimme konnte nicht abgelegt werden.", "The voice could not be stored.") }
            val entry = read(target, true) ?: throw IllegalArgumentException(tr("Die Stimme ist unvollständig.", "The voice is incomplete."))
            if (!hasData(entry, installed() + entry)) {
                target.deleteRecursively()
                throw IllegalArgumentException(tr("Dem Paket fehlen die espeak-ng-Daten (Ordner espeak-ng-data), und keine geladene Stimme liefert sie. Lade zuerst eine Stimme aus dem Katalog.", "The package lacks the espeak-ng data (folder espeak-ng-data) and no downloaded voice provides it. Download a voice from the catalogue first."))
            }
            return entry
        } finally {
            tmp.deleteRecursively()
        }
    }

    private fun prefKey(lang: Lang) = "voice_${lang.tag}"

    companion object { const val MAX_IMPORT_BYTES = 400L * 1024 * 1024 }
}

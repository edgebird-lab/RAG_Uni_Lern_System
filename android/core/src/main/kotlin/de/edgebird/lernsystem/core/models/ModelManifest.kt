package de.edgebird.lernsystem.core.models

import de.edgebird.lernsystem.core.i18n.tr

import com.google.gson.Gson

/** Ein Teil einer Modelldatei; [urls] sind gleichwertige Quellen (Primär zuerst, danach Fallbacks). */
data class ModelPart(val name: String, val size: Long, val sha256: String, val urls: List<String>)

data class ModelInfo(
    val id: String,
    val role: String,
    val title: String,
    val source: String = "",
    val minRamMb: Int = 0,
    val version: String,
    val fileName: String,
    val size: Long,
    val sha256: String,
    val license: String = "",
    val parts: List<ModelPart>,
    /** Wird nur auf Wunsch geladen (z. B. die Stimme für die Sprachausgabe). */
    val optional: Boolean = false,
    /** Nicht leer: Die geladene ZIP-Datei wird nach `models/<unpack>/` entpackt (die ZIP selbst wird danach gelöscht). */
    val unpack: String = "",
    /** Sprache einer Stimme (`de`, `en`); `null` bei Modellen ohne Sprache. */
    val lang: String? = null,
    val titleEn: String? = null,
    /** Kurzbeschreibung (Stimmen: Klang, Qualität) in beiden Sprachen. */
    val description: String? = null,
    val descriptionEn: String? = null,
) {
    fun displayTitle(): String = tr(title, titleEn ?: title)
    fun displayDescription(): String = tr(description.orEmpty(), (descriptionEn ?: description).orEmpty())
}

/** `manifest.json` aus dem Modell-Repo (Schema 1). */
data class ModelManifest(val schemaVersion: Int, val release: String, val minAppVersion: Int = 1, val licenseUrl: String = "", val models: List<ModelInfo>) {
    companion object {
        const val SUPPORTED_SCHEMA = 1

        fun parse(json: String): ModelManifest {
            val m = try { Gson().fromJson(json, ModelManifest::class.java) } catch (e: Exception) { throw ModelException(tr("Manifest unlesbar: ${e.message}", "Manifest unreadable: ${e.message}")) }
                ?: throw ModelException(tr("Manifest ist leer", "Manifest is empty"))
            if (m.schemaVersion != SUPPORTED_SCHEMA) throw ModelException(tr("Manifest-Schema ${m.schemaVersion} wird von dieser App-Version nicht unterstützt", "Manifest schema ${m.schemaVersion} is not supported by this app version"))
            m.models.forEach { mod ->
                if (mod.parts.isEmpty() || mod.parts.any { it.urls.isEmpty() }) throw ModelException(tr("Manifest unvollständig: ${mod.id}", "Manifest incomplete: ${mod.id}"))
                if (mod.parts.sumOf { it.size } != mod.size) throw ModelException(tr("Manifest widersprüchlich (Teilgrößen): ${mod.id}", "Manifest inconsistent (part sizes): ${mod.id}"))
            }
            return m
        }
    }
}

class ModelException(message: String, cause: Throwable? = null) : Exception(message, cause)

/** Dateien neben dem Modell, die den Einbau-Stand festhalten (für Updates). */
object ModelPlan {
    /** Welche Modelle müssen geladen werden? [installed]: Dateiname → (Größe, Version aus der Markierung oder null bei manuell abgelegten). */
    fun pending(manifest: ModelManifest, installed: Map<String, InstalledModel>, includeOptional: Boolean = false, optionalIds: Set<String> = emptySet()): List<ModelInfo> = manifest.models.filter { m ->
        if (m.optional && !includeOptional && m.id !in optionalIds && installed[m.fileName] == null) return@filter false
        val have = installed[m.fileName]
        have == null || have.size != m.size || (have.version != null && have.version != m.version)
    }

    /** Empfehlung nach Arbeitsspeicher: reicht er für das Modell? */
    fun fitsRam(model: ModelInfo, totalRamMb: Long): Boolean = totalRamMb >= model.minRamMb

    /** Für Update-Prüfung: gibt es überhaupt Neues? */
    fun updatesAvailable(manifest: ModelManifest, installed: Map<String, InstalledModel>): List<ModelInfo> =
        manifest.models.filter { m -> installed[m.fileName]?.let { it.version != null && it.version != m.version } == true }
}

data class InstalledModel(val size: Long, val version: String?)

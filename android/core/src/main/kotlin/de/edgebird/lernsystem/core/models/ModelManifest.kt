package de.edgebird.lernsystem.core.models

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
)

/** `manifest.json` aus dem Modell-Repo (Schema 1). */
data class ModelManifest(val schemaVersion: Int, val release: String, val minAppVersion: Int = 1, val licenseUrl: String = "", val models: List<ModelInfo>) {
    companion object {
        const val SUPPORTED_SCHEMA = 1

        fun parse(json: String): ModelManifest {
            val m = try { Gson().fromJson(json, ModelManifest::class.java) } catch (e: Exception) { throw ModelException("Manifest unlesbar: ${e.message}") }
                ?: throw ModelException("Manifest ist leer")
            if (m.schemaVersion != SUPPORTED_SCHEMA) throw ModelException("Manifest-Schema ${m.schemaVersion} wird von dieser App-Version nicht unterstützt")
            m.models.forEach { mod ->
                if (mod.parts.isEmpty() || mod.parts.any { it.urls.isEmpty() }) throw ModelException("Manifest unvollständig: ${mod.id}")
                if (mod.parts.sumOf { it.size } != mod.size) throw ModelException("Manifest widersprüchlich (Teilgrößen): ${mod.id}")
            }
            return m
        }
    }
}

class ModelException(message: String, cause: Throwable? = null) : Exception(message, cause)

/** Dateien neben dem Modell, die den Einbau-Stand festhalten (für Updates). */
object ModelPlan {
    /** Welche Modelle müssen geladen werden? [installed]: Dateiname → (Größe, Version aus der Markierung oder null bei manuell abgelegten). */
    fun pending(manifest: ModelManifest, installed: Map<String, InstalledModel>): List<ModelInfo> = manifest.models.filter { m ->
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

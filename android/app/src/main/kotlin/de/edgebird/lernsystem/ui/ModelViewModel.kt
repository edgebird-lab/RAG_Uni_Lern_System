// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ui

import de.edgebird.lernsystem.core.i18n.tr

import android.app.ActivityManager
import android.app.Application
import java.io.File
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.WorkInfo
import androidx.work.WorkManager
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.i18n.Lang
import de.edgebird.lernsystem.core.models.ModelDownloader
import de.edgebird.lernsystem.core.models.ModelInfo
import de.edgebird.lernsystem.core.models.ModelManifest
import de.edgebird.lernsystem.core.models.ModelPlan
import de.edgebird.lernsystem.voice.VoiceEntry
import de.edgebird.lernsystem.work.ModelDownloadWorker
import de.edgebird.lernsystem.work.ModelWork
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

sealed interface ModelCheck {
    data object Loading : ModelCheck
    /** Alles Nötige ist da; [updates] sind neuere Versionen. */
    data class Ready(val manifest: ModelManifest?, val updates: List<ModelInfo>) : ModelCheck
    data class Needed(val manifest: ModelManifest, val pending: List<ModelInfo>, val ramMb: Long, val freeMb: Long) : ModelCheck
    data class Failed(val message: String) : ModelCheck
}

/** Stimmen für die Sprachausgabe: Katalog aus dem Manifest, installierte Stimmen und die Wahl je Sprache. */
data class VoicesState(val catalog: List<ModelInfo> = emptyList(), val installed: List<VoiceEntry> = emptyList(), val selected: Map<Lang, String> = emptyMap()) {
    /** Empfohlene Stimme für die App-Sprache (erste passende im Katalog). */
    fun recommended(lang: Lang = Lang.current) = catalog.firstOrNull { it.lang == lang.tag }
    fun entryFor(model: ModelInfo) = installed.firstOrNull { it.dir.name == model.unpack }
    fun hasVoiceFor(lang: Lang = Lang.current) = installed.any { it.lang == lang }
}

/** Wählbare Sprachmodelle: Katalog, aktives Modell (Dateiname), schon geladene Dateien und ob ein Neustart nach einem Wechsel nötig ist. */
data class LlmState(
    val choices: List<ModelInfo> = emptyList(), val active: String = ModelPlan.DEFAULT_LLM_FILE, val present: Set<String> = emptySet(), val restartNeeded: Boolean = false,
    /** Selbst hinzugefügte Modelldateien (Dateiname → Größe in Byte), die nicht im Katalog stehen. */
    val custom: Map<String, Long> = emptyMap(), val importing: Boolean = false, val message: String? = null,
)

data class DownloadState(val running: Boolean, val queued: Boolean, val done: Long, val total: Long, val name: String, val error: String?)

class ModelViewModel(app: Application) : AndroidViewModel(app) {
    private val graph = (app as LernsystemApp).graph
    private val work = WorkManager.getInstance(app)
    private val downloader = ModelDownloader(graph.modelsDir)

    private val _wifiOnly = MutableStateFlow(graph.prefs.getBoolean(PREF_WIFI_ONLY, true))
    val wifiOnly: StateFlow<Boolean> = _wifiOnly

    private val _withVoice = MutableStateFlow(false)
    /** Beim Erststart: Stimmen-Zusatzpaket mitladen? (Standard aus, weil es einen GPL-Teil enthält.) */
    val withVoice: StateFlow<Boolean> = _withVoice
    fun setWithVoice(v: Boolean) { _withVoice.value = v }

    private val _voices = MutableStateFlow(VoicesState(installed = graph.voices.installed(), selected = selectedMap()))
    val voices: StateFlow<VoicesState> = _voices

    private fun selectedMap(): Map<Lang, String> = Lang.entries.mapNotNull { l -> graph.voices.selected(l)?.let { l to it.id } }.toMap()
    private fun reloadVoices(manifest: ModelManifest? = null) {
        val catalog = manifest?.models?.filter { it.optional && it.role == "tts" } ?: _voices.value.catalog
        _voices.value = VoicesState(catalog, graph.voices.installed(), selectedMap())
    }

    private val _llm = MutableStateFlow(LlmState(active = graph.activeLlmFile))
    val llm: StateFlow<LlmState> = _llm

    private fun reloadLlm(manifest: ModelManifest? = null, installed: Map<String, de.edgebird.lernsystem.core.models.InstalledModel> = emptyMap(), restart: Boolean = _llm.value.restartNeeded) {
        val choices = manifest?.let { ModelPlan.llmChoices(it) } ?: _llm.value.choices
        val present = choices.filter { m -> installed[m.fileName]?.size == m.size }.map { it.fileName }.toSet()
        _llm.value = LlmState(choices, graph.activeLlmFile, present, restart, customFiles(), _llm.value.importing, _llm.value.message)
    }

    private fun customFiles(): Map<String, Long> = graph.modelsDir.listFiles().orEmpty()
        .filter { it.isFile && it.name.startsWith(CUSTOM_PREFIX) && it.name.endsWith(MODEL_EXT) }.sortedBy { it.name }.associate { it.name to it.length() }

    /**
     * Übernimmt eine selbst heruntergeladene Modelldatei (LiteRT-LM, `.litertlm`) als Sprachmodell. Die Datei wird in den App-Speicher kopiert
     * und sofort zum aktiven Modell; ob sie wirklich läuft, zeigt sich beim ersten Laden (Neustart der App nötig).
     */
    fun importLlm(uri: android.net.Uri) {
        val app = getApplication<Application>()
        viewModelScope.launch {
            val had = filesPresent()   // nur dann läuft schon ein Modell und ein Neustart ist nötig
            _llm.value = _llm.value.copy(importing = true, message = null)
            val msg = withContext(Dispatchers.IO) {
                runCatching {
                    val (rawName, size) = app.contentResolver.query(uri, arrayOf(android.provider.OpenableColumns.DISPLAY_NAME, android.provider.OpenableColumns.SIZE), null, null, null)?.use { c ->
                        if (c.moveToFirst()) c.getString(0).orEmpty() to (if (c.isNull(1)) -1L else c.getLong(1)) else null
                    } ?: ("" to -1L)
                    if (!rawName.endsWith(MODEL_EXT, ignoreCase = true)) return@runCatching tr("Das ist keine .litertlm-Datei. Die App kann nur Modelle im LiteRT-LM-Format laden.", "That is not a .litertlm file. The app can only load models in the LiteRT-LM format.")
                    val safe = CUSTOM_PREFIX + rawName.dropLast(MODEL_EXT.length).replace(Regex("[^A-Za-z0-9._-]"), "_").take(60) + MODEL_EXT
                    graph.modelsDir.mkdirs()
                    if (size > 0 && graph.modelsDir.usableSpace < size + 300L * 1_048_576) return@runCatching tr("Zu wenig freier Speicher für diese Datei.", "Not enough free storage for this file.")
                    val tmp = File(graph.modelsDir, "$safe.partial")
                    app.contentResolver.openInputStream(uri)!!.use { input -> tmp.outputStream().use { input.copyTo(it, 1 shl 20) } }
                    val target = File(graph.modelsDir, safe)
                    target.delete()
                    check(tmp.renameTo(target)) { "rename" }
                    graph.activeLlmFile = safe
                    graph.pendingLlmFile = null
                    null
                }.getOrElse { tr("Die Datei konnte nicht übernommen werden: ${it.message}", "The file could not be imported: ${it.message}") }
            }
            _llm.value = _llm.value.copy(importing = false, message = msg ?: tr("Eigenes Modell übernommen.", "Custom model imported."), restartNeeded = _llm.value.restartNeeded || (msg == null && had))
            refresh()
        }
    }

    /** Eine selbst hinzugefügte Modelldatei löschen; war sie aktiv, gilt wieder das Standardmodell. */
    fun deleteCustom(name: String) {
        viewModelScope.launch {
            withContext(Dispatchers.IO) { File(graph.modelsDir, name).delete() }
            if (graph.activeLlmFile == name) graph.activeLlmFile = ModelPlan.DEFAULT_LLM_FILE
            _llm.value = _llm.value.copy(restartNeeded = true)
            refresh()
        }
    }

    /** Eine schon vorhandene eigene Datei wieder als aktives Modell verwenden. */
    fun useCustom(name: String) { graph.activeLlmFile = name; graph.pendingLlmFile = null; reloadLlm(restart = true) }

    /** Wählt ein Sprachmodell. Im Erststart zählt die Wahl sofort; später wird ein noch nicht geladenes Modell erst nach dem Download aktiv. */
    fun chooseLlm(m: ModelInfo) {
        if (!filesPresent()) { graph.activeLlmFile = m.fileName; graph.pendingLlmFile = null; refresh(); return }
        if (m.fileName in _llm.value.present) { graph.activeLlmFile = m.fileName; graph.pendingLlmFile = null; reloadLlm(restart = true); return }
        graph.pendingLlmFile = m.fileName
        ModelWork.enqueue(getApplication(), _wifiOnly.value)
    }

    /** Ein nicht aktives Sprachmodell löschen (gibt Speicher frei). */
    fun deleteLlm(m: ModelInfo) {
        if (m.fileName == graph.activeLlmFile) return
        viewModelScope.launch {
            withContext(Dispatchers.IO) { File(graph.modelsDir, m.fileName).delete(); File(graph.modelsDir, m.fileName + ".version").delete() }
            refresh()
        }
    }

    private val _check = MutableStateFlow<ModelCheck>(ModelCheck.Loading)
    val check: StateFlow<ModelCheck> = _check

    val download: StateFlow<DownloadState?> = work.getWorkInfosForUniqueWorkFlow(ModelWork.UNIQUE).map { infos ->
        val i = infos.firstOrNull() ?: return@map null
        DownloadState(
            running = i.state == WorkInfo.State.RUNNING, queued = i.state == WorkInfo.State.ENQUEUED || i.state == WorkInfo.State.BLOCKED,
            done = i.progress.getLong(ModelDownloadWorker.DONE, 0), total = i.progress.getLong(ModelDownloadWorker.TOTAL, 0), name = i.progress.getString(ModelDownloadWorker.NAME) ?: "",
            error = if (i.state == WorkInfo.State.FAILED) i.outputData.getString(ModelDownloadWorker.ERROR) ?: tr("Download fehlgeschlagen", "Download failed") else null,
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    /** Zählt das Ende eines Downloads: danach wird neu geprüft. */
    private val succeeded = work.getWorkInfosForUniqueWorkFlow(ModelWork.UNIQUE).map { l -> l.any { it.state == WorkInfo.State.SUCCEEDED } }
        .stateIn(viewModelScope, SharingStarted.Eagerly, false)

    init {
        refresh()
        viewModelScope.launch { succeeded.collect { if (it) refresh() } }
    }

    private fun filesPresent() = graph.llmModelFile.exists() && graph.embeddingModelFile.exists()

    fun refresh() {
        viewModelScope.launch {
            val installed = withContext(Dispatchers.IO) { downloader.installed() }
            val present = filesPresent()
            val res = withContext(Dispatchers.IO) { runCatching { downloader.fetchManifest(ModelWork.MANIFEST_URLS) } }
            val manifest = res.getOrNull()
            withContext(Dispatchers.IO) { graph.voice.release() }   // nach einem Download oder Löschen neu laden
            reloadVoices(manifest)
            // Ein nachträglich gewähltes Sprachmodell wird aktiv, sobald es vollständig da ist
            var restart = _llm.value.restartNeeded
            graph.pendingLlmFile?.let { p ->
                val m = manifest?.models?.firstOrNull { it.fileName == p }
                if (m != null && installed[p]?.size == m.size) { graph.activeLlmFile = p; graph.pendingLlmFile = null; restart = true }
            }
            reloadLlm(manifest, installed, restart)
            _check.value = when {
                manifest != null -> {
                    val pending = ModelPlan.pending(manifest, installed, llmFile = graph.pendingLlmFile ?: graph.activeLlmFile)
                    if (!present) ModelCheck.Needed(manifest, pending, totalRamMb(), graph.modelsDir.apply { mkdirs() }.usableSpace / 1_048_576)
                    else ModelCheck.Ready(manifest, pending)   // alles da; offene Einträge sind neuere Versionen
                }
                present -> ModelCheck.Ready(null, emptyList())   // offline, aber Modelle sind da
                else -> ModelCheck.Failed(res.exceptionOrNull()?.message ?: tr("Manifest nicht erreichbar", "Manifest not reachable"))
            }
        }
    }

    fun setWifiOnly(v: Boolean) { graph.prefs.edit().putBoolean(PREF_WIFI_ONLY, v).apply(); _wifiOnly.value = v }
    fun start() {
        val v = _voices.value
        val rec = v.recommended()?.takeIf { _withVoice.value && !v.hasVoiceFor() }
        ModelWork.enqueue(getApplication(), _wifiOnly.value, voiceIds = setOfNotNull(rec?.id))
    }

    /** Eine Stimme aus dem Katalog (nachträglich) laden. */
    fun downloadVoice(model: ModelInfo) = ModelWork.enqueue(getApplication(), _wifiOnly.value, voiceIds = setOf(model.id))

    fun selectVoice(e: VoiceEntry) { graph.voices.select(e); viewModelScope.launch { graph.voice.release() }; reloadVoices() }

    fun deleteVoice(e: VoiceEntry) {
        viewModelScope.launch {
            withContext(Dispatchers.IO) { graph.voice.release(); graph.voices.delete(e) }
            // Katalogstimmen: Marker mit entfernt (Ordner gelöscht), der Download kann erneut starten
            reloadVoices()
        }
    }

    fun cancel() = ModelWork.cancel(getApplication())

    /** Beschädigte oder falsche Modelldateien entfernen, damit der Assistent sie neu lädt. */
    fun reinstall() {
        cancel()
        viewModelScope.launch {
            withContext(Dispatchers.IO) { graph.voice.release(); graph.modelsDir.listFiles().orEmpty().forEach { it.deleteRecursively() } }
            refresh()
        }
    }

    fun filesReady(): Boolean = filesPresent()

    fun ramMb(): Long = totalRamMb()

    private fun totalRamMb(): Long = ActivityManager.MemoryInfo().also { getApplication<Application>().getSystemService(ActivityManager::class.java).getMemoryInfo(it) }.totalMem / 1_048_576

    companion object {
        const val CUSTOM_PREFIX = "custom-"
        const val MODEL_EXT = ".litertlm"
        const val PREF_WIFI_ONLY = "models_wifi_only" }
}

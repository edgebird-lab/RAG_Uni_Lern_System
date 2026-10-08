package de.edgebird.lernsystem.ui

import android.app.ActivityManager
import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.WorkInfo
import androidx.work.WorkManager
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.models.ModelDownloader
import de.edgebird.lernsystem.core.models.ModelInfo
import de.edgebird.lernsystem.core.models.ModelManifest
import de.edgebird.lernsystem.core.models.ModelPlan
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

data class DownloadState(val running: Boolean, val queued: Boolean, val done: Long, val total: Long, val name: String, val error: String?)

class ModelViewModel(app: Application) : AndroidViewModel(app) {
    private val graph = (app as LernsystemApp).graph
    private val work = WorkManager.getInstance(app)
    private val downloader = ModelDownloader(graph.modelsDir)

    private val _wifiOnly = MutableStateFlow(graph.prefs.getBoolean(PREF_WIFI_ONLY, true))
    val wifiOnly: StateFlow<Boolean> = _wifiOnly

    private val _check = MutableStateFlow<ModelCheck>(ModelCheck.Loading)
    val check: StateFlow<ModelCheck> = _check

    val download: StateFlow<DownloadState?> = work.getWorkInfosForUniqueWorkFlow(ModelWork.UNIQUE).map { infos ->
        val i = infos.firstOrNull() ?: return@map null
        DownloadState(
            running = i.state == WorkInfo.State.RUNNING, queued = i.state == WorkInfo.State.ENQUEUED || i.state == WorkInfo.State.BLOCKED,
            done = i.progress.getLong(ModelDownloadWorker.DONE, 0), total = i.progress.getLong(ModelDownloadWorker.TOTAL, 0), name = i.progress.getString(ModelDownloadWorker.NAME) ?: "",
            error = if (i.state == WorkInfo.State.FAILED) i.outputData.getString(ModelDownloadWorker.ERROR) ?: "Download fehlgeschlagen" else null,
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
            _check.value = when {
                manifest != null -> {
                    val pending = ModelPlan.pending(manifest, installed)
                    if (!present) ModelCheck.Needed(manifest, pending, totalRamMb(), graph.modelsDir.apply { mkdirs() }.usableSpace / 1_048_576)
                    else ModelCheck.Ready(manifest, pending)   // alles da; offene Einträge sind neuere Versionen
                }
                present -> ModelCheck.Ready(null, emptyList())   // offline, aber Modelle sind da
                else -> ModelCheck.Failed(res.exceptionOrNull()?.message ?: "Manifest nicht erreichbar")
            }
        }
    }

    fun setWifiOnly(v: Boolean) { graph.prefs.edit().putBoolean(PREF_WIFI_ONLY, v).apply(); _wifiOnly.value = v }
    fun start() = ModelWork.enqueue(getApplication(), _wifiOnly.value)
    fun cancel() = ModelWork.cancel(getApplication())

    fun filesReady(): Boolean = filesPresent()

    private fun totalRamMb(): Long = ActivityManager.MemoryInfo().also { getApplication<Application>().getSystemService(ActivityManager::class.java).getMemoryInfo(it) }.totalMem / 1_048_576

    companion object { const val PREF_WIFI_ONLY = "models_wifi_only" }
}

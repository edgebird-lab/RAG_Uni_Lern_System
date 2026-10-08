package de.edgebird.lernsystem.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.data.chat.ChatEvent
import de.edgebird.lernsystem.data.chat.ChatTurn
import de.edgebird.lernsystem.data.chat.Source
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ChatMessage(
    val id: Long,
    val fromUser: Boolean,
    val text: String,
    val sources: List<Source> = emptyList(),
    val cited: Set<Int> = emptySet(),
    val notFound: Boolean = false,
    val streaming: Boolean = false,
    val failed: Boolean = false,
    /** Antwort stammt aus dem zweiten, toleranteren Versuch (weniger sicher). */
    val retried: Boolean = false,
)

enum class ModelState { MISSING, LOADING, OPTIMIZING, READY, ERROR }

class ChatViewModel(app: Application) : AndroidViewModel(app) {
    private val graph = (app as LernsystemApp).graph
    private var nextId = 0L
    private var job: Job? = null

    private val _messages = MutableStateFlow<List<ChatMessage>>(emptyList())
    val messages: StateFlow<List<ChatMessage>> = _messages

    private fun initialState() = when {
        !graph.llmModelFile.exists() -> ModelState.MISSING
        graph.llmCacheWarm() -> ModelState.LOADING
        else -> ModelState.OPTIMIZING // erster Start: GPU-Kerne werden kompiliert
    }

    private val _modelState = MutableStateFlow(initialState())
    val modelState: StateFlow<ModelState> = _modelState

    /** Grund, falls das Sprachmodell nicht geladen werden konnte (für die Anzeige). */
    private val _loadError = MutableStateFlow<String?>(null)
    val loadError: StateFlow<String?> = _loadError

    /** Quellen, in denen gesucht wird (angehakte Dokumente des Fachs); `null` = noch nicht gesetzt. */
    @Volatile private var scope: Set<Long>? = null
    fun setScope(ids: Set<Long>) { scope = ids }

    val busy: Boolean get() = job?.isActive == true

    init { loadModel() }

    private fun loadModel() {
        if (_modelState.value != ModelState.LOADING && _modelState.value != ModelState.OPTIMIZING) return
        _loadError.value = null
        viewModelScope.launch(Dispatchers.Default) {
            _modelState.value = try {
                graph.llm.load()
                ModelState.READY
            } catch (e: CancellationException) {
                throw e
            } catch (t: Throwable) {
                // Auch OutOfMemoryError und native Fehler: die App soll erklären statt abstürzen
                _loadError.value = if (t is OutOfMemoryError) "Zu wenig Arbeitsspeicher. Schließe andere Apps und versuche es erneut." else t.message
                ModelState.ERROR
            }
        }
    }

    /** Erneut laden, z. B. nach einem Fehler oder nachdem die Modelle heruntergeladen wurden. */
    fun retryLoad() {
        if (_modelState.value == ModelState.READY) return
        _modelState.value = initialState()
        loadModel()
    }

    fun send(question: String) {
        val q = question.trim()
        if (q.isEmpty() || busy || _modelState.value != ModelState.READY) return
        start(q, retry = false)
    }

    /** Nach „Nicht im Material gefunden“: dieselbe Frage mit mehr Abschnitten und toleranterem Prompt erneut stellen. */
    fun retryWithMoreSources(answerId: Long) {
        if (busy || _modelState.value != ModelState.READY) return
        val list = _messages.value
        val idx = list.indexOfFirst { it.id == answerId }
        val question = list.getOrNull(idx - 1)?.takeIf { it.fromUser }?.text ?: return
        _messages.update { l -> l.filterNot { it.id == answerId } }
        start(question, retry = true, dropLastPair = false)
    }

    private fun start(q: String, retry: Boolean, dropLastPair: Boolean = false) {
        val history = _messages.value.chunked(2).mapNotNull { pair ->
            val u = pair.firstOrNull()?.takeIf { it.fromUser }
            val a = pair.getOrNull(1)?.takeIf { !it.fromUser && !it.failed && !it.notFound && it.text.isNotBlank() }
            if (u != null && a != null) ChatTurn(u.text, a.text) else null
        }
        val answerId = nextId + 1
        _messages.update { (if (retry) it else it + ChatMessage(nextId, true, q)) + ChatMessage(answerId, false, "", streaming = true, retried = retry) }
        nextId += 2
        job = viewModelScope.launch(Dispatchers.Default) {
            try {
                (if (retry) graph.chat.ask(q, history, topKOverride = 6, styleOverride = de.edgebird.lernsystem.core.rag.PromptStyle.LENIENT, documentIds = scope) else graph.chat.ask(q, history, documentIds = scope)).collect { event ->
                    when (event) {
                        is ChatEvent.Sources -> patch(answerId) { it.copy(sources = event.sources) }
                        is ChatEvent.Token -> patch(answerId) { it.copy(text = it.text + event.text) }
                        is ChatEvent.Done -> patch(answerId) {
                            it.copy(text = event.answer, cited = event.cited, notFound = event.notFound, streaming = false)
                        }
                    }
                }
            } catch (e: CancellationException) {
                patch(answerId) { it.copy(streaming = false) }
                throw e
            } catch (e: Exception) {
                patch(answerId) { it.copy(text = "Die Antwort konnte nicht erstellt werden: ${e.message}", streaming = false, failed = true) }
            }
        }
    }

    fun stop() {
        job?.cancel()
    }

    fun newChat() {
        job?.cancel()
        _messages.value = emptyList()
    }

    private fun patch(id: Long, change: (ChatMessage) -> ChatMessage) {
        _messages.update { list -> list.map { if (it.id == id) change(it) else it } }
    }
}

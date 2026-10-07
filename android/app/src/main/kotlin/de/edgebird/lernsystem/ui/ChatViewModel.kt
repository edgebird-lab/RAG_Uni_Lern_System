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
import kotlinx.coroutines.flow.StateFlow
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
)

enum class ModelState { MISSING, LOADING, READY, ERROR }

class ChatViewModel(app: Application) : AndroidViewModel(app) {
    private val graph = (app as LernsystemApp).graph
    private var nextId = 0L
    private var job: Job? = null

    private val _messages = MutableStateFlow<List<ChatMessage>>(emptyList())
    val messages: StateFlow<List<ChatMessage>> = _messages

    private val _modelState = MutableStateFlow(if (graph.llmModelFile.exists()) ModelState.LOADING else ModelState.MISSING)
    val modelState: StateFlow<ModelState> = _modelState

    val busy: Boolean get() = job?.isActive == true

    init {
        if (_modelState.value == ModelState.LOADING) {
            viewModelScope.launch(Dispatchers.Default) {
                _modelState.value = try {
                    graph.llm.load()
                    ModelState.READY
                } catch (e: Exception) {
                    ModelState.ERROR
                }
            }
        }
    }

    fun send(question: String) {
        val q = question.trim()
        if (q.isEmpty() || busy || _modelState.value != ModelState.READY) return
        val history = _messages.value.chunked(2).mapNotNull { pair ->
            val u = pair.firstOrNull()?.takeIf { it.fromUser }
            val a = pair.getOrNull(1)?.takeIf { !it.fromUser && !it.failed && !it.notFound && it.text.isNotBlank() }
            if (u != null && a != null) ChatTurn(u.text, a.text) else null
        }
        val answerId = nextId + 1
        _messages.update { it + ChatMessage(nextId, true, q) + ChatMessage(answerId, false, "", streaming = true) }
        nextId += 2
        job = viewModelScope.launch(Dispatchers.Default) {
            try {
                graph.chat.ask(q, history).collect { event ->
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

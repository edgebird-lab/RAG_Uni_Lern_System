package de.edgebird.lernsystem.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.socratic.Phase
import de.edgebird.lernsystem.data.socratic.Action
import de.edgebird.lernsystem.data.socratic.SocraticSession
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class DialogMessage(val fromUser: Boolean, val text: String, val fallback: Boolean = false)

data class SocraticUi(
    val running: Boolean = false,
    val busy: Boolean = false,
    val phase: Phase = Phase.START,
    val topic: String = "",
    val messages: List<DialogMessage> = emptyList(),
    val error: String? = null,
)

/** Sokratischer Dialog („Abfragen“) eines Fachs. */
class SocraticViewModel(app: Application) : AndroidViewModel(app) {
    private val graph = (app as LernsystemApp).graph
    private var session: SocraticSession? = null
    private var job: Job? = null

    private val _ui = MutableStateFlow(SocraticUi())
    val ui: StateFlow<SocraticUi> = _ui

    fun start(topic: String, documentIds: Set<Long>) {
        if (documentIds.isEmpty() || _ui.value.busy) return
        val s = SocraticSession(graph.retriever, graph.llm, documentIds, topic, randomChunks = { ids, n ->
            ids.shuffled().firstOrNull()?.let { graph.db.chunks().byDocument(it).shuffled().take(n) }.orEmpty()
        })
        session = s
        _ui.value = SocraticUi(running = true, busy = true, topic = topic)
        job = viewModelScope.launch {
            try {
                graph.llm.load()
                val out = s.start()
                _ui.value = _ui.value.copy(busy = false, phase = out.phase, topic = s.topic, messages = listOf(DialogMessage(false, out.text, out.fallback)))
            } catch (e: CancellationException) { throw e
            } catch (e: Throwable) { fail(e) }
        }
    }

    fun act(action: Action) {
        val s = session ?: return
        if (_ui.value.busy) return
        val label = when (action) {
            Action.Hint -> "Hinweis"; Action.Partial -> "Ich weiß nur einen Teil"; Action.Resolve -> "Auflösen"; Action.Next -> "Nächster Aspekt"
            is Action.Answer -> action.text.trim()
        }
        if (label.isEmpty()) return
        _ui.value = _ui.value.copy(busy = true, error = null, messages = _ui.value.messages + DialogMessage(true, label))
        job = viewModelScope.launch {
            try {
                val out = s.act(action)
                _ui.value = _ui.value.copy(busy = false, phase = out.phase, messages = _ui.value.messages + DialogMessage(false, out.text, out.fallback))
            } catch (e: CancellationException) { throw e
            } catch (e: Throwable) { fail(e) }
        }
    }

    private fun fail(e: Throwable) {
        _ui.value = _ui.value.copy(busy = false, error = if (e is OutOfMemoryError) "Zu wenig Arbeitsspeicher. Schließe andere Apps und versuche es erneut." else "Die KI konnte nicht antworten: ${e.message}")
    }

    fun end() {
        job?.cancel()
        session = null
        _ui.value = SocraticUi()
    }
}

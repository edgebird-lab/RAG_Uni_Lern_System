// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ui

import de.edgebird.lernsystem.core.i18n.tr

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.socratic.Phase
import de.edgebird.lernsystem.core.socratic.Verdict
import de.edgebird.lernsystem.data.QuizResultEntity
import de.edgebird.lernsystem.data.TopicStat
import de.edgebird.lernsystem.data.socratic.Evaluation
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.stateIn
import de.edgebird.lernsystem.data.socratic.Action
import de.edgebird.lernsystem.data.socratic.SocraticSession
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class DialogMessage(val fromUser: Boolean, val text: String, val fallback: Boolean = false, val verdict: Verdict? = null)

/** Ergebnis einer beendeten Abfrage. */
data class QuizSummary(val topic: String, val evaluations: List<Evaluation>, val cardsSaved: Int? = null, val saving: Boolean = false) {
    val correct get() = evaluations.count { it.verdict == Verdict.CORRECT }
    val partial get() = evaluations.count { it.verdict == Verdict.PARTIAL }
    val wrong get() = evaluations.count { it.verdict == Verdict.WRONG }
    val weak get() = evaluations.filter { it.verdict != Verdict.CORRECT }
}

data class SocraticUi(
    val running: Boolean = false,
    val busy: Boolean = false,
    val phase: Phase = Phase.START,
    val topic: String = "",
    val messages: List<DialogMessage> = emptyList(),
    val error: String? = null,
)

/** Sokratischer Dialog („Abfragen“) eines Fachs. */
@OptIn(ExperimentalCoroutinesApi::class)
class SocraticViewModel(app: Application) : AndroidViewModel(app) {
    private val graph = (app as LernsystemApp).graph
    private var session: SocraticSession? = null
    private var job: Job? = null

    private val subject = MutableStateFlow<Long?>(null)
    fun bind(id: Long) { subject.value = id }

    /** Stand je Thema (schwächste zuerst). */
    val topics: StateFlow<List<TopicStat>> = subject.flatMapLatest { if (it == null) flowOf(emptyList()) else graph.db.quiz().observeTopics(it) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    private val _summary = MutableStateFlow<QuizSummary?>(null)
    val summary: StateFlow<QuizSummary?> = _summary

    private val _ui = MutableStateFlow(SocraticUi())
    val ui: StateFlow<SocraticUi> = _ui

    fun start(topic: String, documentIds: Set<Long>) {
        if (documentIds.isEmpty() || _ui.value.busy) return
        val s = SocraticSession(
            graph.retriever, graph.llm, documentIds, topic,
            randomChunks = { ids, n -> ids.shuffled().firstOrNull()?.let { graph.db.chunks().byDocument(it).shuffled().take(n) }.orEmpty() },
            // Überschriften wie „Dokument“ oder „Seite 3“ sagen nichts: dann zählt der Name der Quelle als Thema
            topicFor = { c -> de.edgebird.lernsystem.core.quiz.Topics.of(c.location, graph.db.documents().byId(c.documentId)?.title.orEmpty()) },
        )
        session = s
        s.onEvaluated = { e -> subject.value?.let { sid -> graph.db.quiz().insert(QuizResultEntity(subjectId = sid, topic = s.topic.ifBlank { tr("Allgemein", "General") }, question = e.question, answer = e.answer, verdict = e.verdict.name, at = System.currentTimeMillis())) } }
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
            Action.Hint -> tr("Hinweis", "Hint"); Action.Partial -> tr("Ich weiß nur einen Teil", "I only know part of it"); Action.Resolve -> tr("Auflösen", "Resolve"); Action.Next -> tr("Nächster Aspekt", "Next aspect")
            is Action.Answer -> action.text.trim()
        }
        if (label.isEmpty()) return
        _ui.value = _ui.value.copy(busy = true, error = null, messages = _ui.value.messages + DialogMessage(true, label))
        job = viewModelScope.launch {
            try {
                val out = s.act(action)
                val msgs = _ui.value.messages.toMutableList()
                if (out.verdict != null) { val i = msgs.indexOfLast { it.fromUser }; if (i >= 0) msgs[i] = msgs[i].copy(verdict = out.verdict) }
                _ui.value = _ui.value.copy(busy = false, phase = out.phase, messages = msgs + DialogMessage(false, out.text, out.fallback))
            } catch (e: CancellationException) { throw e
            } catch (e: Throwable) { fail(e) }
        }
    }

    private fun fail(e: Throwable) {
        _ui.value = _ui.value.copy(busy = false, error = if (e is OutOfMemoryError) tr("Zu wenig Arbeitsspeicher. Schließe andere Apps und versuche es erneut.", "Not enough memory. Close other apps and try again.") else tr("Die KI konnte nicht antworten: ${e.message}", "The AI could not answer: ${e.message}"))
    }

    /** Beendet die Abfrage; gab es bewertete Antworten, erscheint zuerst das Ergebnis. */
    fun end() {
        job?.cancel()
        val evals = session?.evaluations.orEmpty()
        if (evals.isNotEmpty()) _summary.value = QuizSummary(session?.topic.orEmpty(), evals) else closeSession()
    }

    private fun closeSession() { session = null; _ui.value = SocraticUi() }

    fun closeSummary() { _summary.value = null; closeSession() }

    /** Schwache Fragen (teilweise oder falsch beantwortet) als Karten ins Fach übernehmen. */
    fun saveWeakAsCards() {
        val s = session ?: return
        val sum = _summary.value ?: return
        val sid = subject.value ?: return
        if (sum.saving || sum.cardsSaved != null) return
        _summary.value = sum.copy(saving = true)
        viewModelScope.launch {
            var n = 0
            for (e in sum.weak.distinctBy { it.question }) {
                try {
                    val answer = s.modelAnswer(e.question) ?: continue
                    graph.study.addManual(e.question, answer, sid)
                    n++
                } catch (c: CancellationException) { throw c } catch (_: Throwable) { /* nächste Frage */ }
            }
            _summary.value = _summary.value?.copy(saving = false, cardsSaved = n)
        }
    }
}

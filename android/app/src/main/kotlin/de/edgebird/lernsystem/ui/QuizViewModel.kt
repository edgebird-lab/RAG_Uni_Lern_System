// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ui

import de.edgebird.lernsystem.core.i18n.tr

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.data.quiz.McQuizRunner
import de.edgebird.lernsystem.data.quiz.QuizItem
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** Zustände von Quiz und Probeklausur. */
sealed interface QuizState {
    data object Setup : QuizState
    data class Generating(val done: Int, val total: Int) : QuizState
    /** @param endAt Ende der Zeit (nur Probeklausur mit Zeitlimit), [revealed]: Rückmeldung zur aktuellen Frage sichtbar (nur Quiz) */
    data class Running(val items: List<QuizItem>, val index: Int, val answers: Map<Int, Int>, val revealed: Boolean, val exam: Boolean, val endAt: Long?) : QuizState
    data class Finished(val items: List<QuizItem>, val answers: Map<Int, Int>, val exam: Boolean, val timedOut: Boolean, val cardsSaved: Int? = null) : QuizState {
        val correct get() = items.indices.count { answers[it] == items[it].question.correctIndex }
    }
    data class Failed(val message: String) : QuizState
}

data class QuizOptions(val count: Int = 5, val exam: Boolean = false, val minutes: Int = 10, val preferWeak: Boolean = true)

class QuizViewModel(app: Application) : AndroidViewModel(app) {
    private val graph = (app as LernsystemApp).graph
    private var subjectId: Long = -1
    private var job: Job? = null
    private var options = QuizOptions()

    private val _state = MutableStateFlow<QuizState>(QuizState.Setup)
    val state: StateFlow<QuizState> = _state

    private val _options = MutableStateFlow(QuizOptions())
    val optionsFlow: StateFlow<QuizOptions> = _options
    fun setOptions(o: QuizOptions) { _options.value = o }

    fun bind(id: Long) { subjectId = id }

    /** Erzeugt die Fragen aus den angehakten Quellen; das dauert etwa 5 bis 10 Sekunden je Frage. */
    fun start(documentIds: Set<Long>) {
        if (documentIds.isEmpty() || _state.value is QuizState.Generating) return
        options = _options.value
        _state.value = QuizState.Generating(0, options.count)
        job = viewModelScope.launch {
            try {
                graph.llm.load()
                val runner = McQuizRunner(graph.db, graph.llm)
                val items = runner.prepare(subjectId, documentIds, options.count, options.preferWeak, onProgress = { d, t -> _state.value = QuizState.Generating(d, t) })
                _state.value = if (items.isEmpty()) QuizState.Failed(tr("Aus den gewählten Quellen konnten keine Fragen erzeugt werden. Wähle längere Quellen mit Fließtext.", "No questions could be created from the chosen sources. Choose longer sources with running text."))
                else QuizState.Running(items, 0, emptyMap(), revealed = false, exam = options.exam, endAt = if (options.exam) System.currentTimeMillis() + options.minutes * 60_000L else null)
                if (options.exam) watchTimer()
            } catch (e: CancellationException) { throw e
            } catch (t: Throwable) { _state.value = QuizState.Failed(if (t is OutOfMemoryError) tr("Zu wenig Arbeitsspeicher. Schließe andere Apps.", "Not enough memory. Close other apps.") else tr("Die Fragen konnten nicht erzeugt werden: ${t.message}", "The questions could not be created: ${t.message}")) }
        }
    }

    private fun watchTimer() {
        viewModelScope.launch {
            while (true) {
                delay(500)
                val s = _state.value as? QuizState.Running ?: return@launch
                val end = s.endAt ?: return@launch
                if (System.currentTimeMillis() >= end) { finish(timedOut = true); return@launch }
            }
        }
    }

    fun choose(option: Int) {
        val s = _state.value as? QuizState.Running ?: return
        if (s.revealed && !s.exam) return
        _state.value = s.copy(answers = s.answers + (s.index to option), revealed = !s.exam)
    }

    fun next() {
        val s = _state.value as? QuizState.Running ?: return
        if (s.index + 1 >= s.items.size) finish(false) else _state.value = s.copy(index = s.index + 1, revealed = false)
    }

    fun previous() {
        val s = _state.value as? QuizState.Running ?: return
        if (s.exam && s.index > 0) _state.value = s.copy(index = s.index - 1)
    }

    fun finish(timedOut: Boolean = false) {
        val s = _state.value as? QuizState.Running ?: return
        val fin = QuizState.Finished(s.items, s.answers, s.exam, timedOut)
        _state.value = fin
        viewModelScope.launch {
            val runner = McQuizRunner(graph.db, graph.llm)
            s.items.forEachIndexed { i, item -> runner.record(subjectId, item, s.answers[i]) }
        }
    }

    /** Falsch oder nicht beantwortete Fragen als Karten ins Fach übernehmen. */
    fun saveWrongAsCards() {
        val f = _state.value as? QuizState.Finished ?: return
        if (f.cardsSaved != null) return
        viewModelScope.launch {
            var n = 0
            f.items.forEachIndexed { i, item ->
                if (f.answers[i] != item.question.correctIndex) {
                    graph.study.addManual(item.question.question, item.question.correct + if (item.question.explanation.isNotBlank()) "\n\n" + item.question.explanation else "", subjectId)
                    n++
                }
            }
            _state.value = f.copy(cardsSaved = n)
        }
    }

    fun cancelGeneration() { job?.cancel(); _state.value = QuizState.Setup }
    fun reset() { job?.cancel(); _state.value = QuizState.Setup }
}

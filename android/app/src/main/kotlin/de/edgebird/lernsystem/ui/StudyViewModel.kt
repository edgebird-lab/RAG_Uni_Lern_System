// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.data.CardEntity
import de.edgebird.lernsystem.data.study.Grade
import de.edgebird.lernsystem.data.study.StudySettings
import de.edgebird.lernsystem.data.study.StudySummary
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class SessionState(
    val card: CardEntity? = null,
    val showAnswer: Boolean = false,
    val previews: Map<Grade, String> = emptyMap(),
    val remaining: Int = 0,
    val reviewed: Int = 0,
    val finished: Boolean = false,
)

class StudyViewModel(app: Application) : AndroidViewModel(app) {
    private val graph = (app as LernsystemApp).graph
    private val repo = graph.study

    private val _summary = MutableStateFlow<StudySummary?>(null)
    val summary: StateFlow<StudySummary?> = _summary

    private val _session = MutableStateFlow<SessionState?>(null)
    val session: StateFlow<SessionState?> = _session

    private val _settings = MutableStateFlow(graph.studySettings())
    val settings: StateFlow<StudySettings> = _settings

    private val queue = ArrayDeque<Long>()
    private var shownAt = 0L

    private var subjectId: Long? = null

    /** Lernstoff auf ein Fach begrenzen (idempotent). */
    fun bind(id: Long?) {
        if (id == subjectId && _summary.value != null) return
        subjectId = id
        refresh()
    }

    fun refresh() {
        viewModelScope.launch { _summary.value = repo.summary(subjectId) }
    }

    fun start() {
        viewModelScope.launch {
            queue.clear()
            queue.addAll(repo.buildQueue(subjectId))
            _session.value = SessionState(remaining = queue.size, finished = queue.isEmpty())
            if (queue.isNotEmpty()) showNext(reviewed = 0)
        }
    }

    private suspend fun showNext(reviewed: Int) {
        val id = queue.removeFirstOrNull()
        val card = id?.let { repo.card(it) }
        if (card == null) {
            _session.value = SessionState(reviewed = reviewed, finished = true)
            refresh()
            return
        }
        shownAt = System.currentTimeMillis()
        _session.value = SessionState(card = card, previews = repo.previews(card), remaining = queue.size + 1, reviewed = reviewed)
    }

    fun reveal() {
        _session.update { it?.copy(showAnswer = true) }
    }

    fun grade(g: Grade) {
        val s = _session.value ?: return
        val card = s.card ?: return
        viewModelScope.launch {
            val result = repo.review(card.id, g, System.currentTimeMillis() - shownAt)
            if (result.requeueInSession) queue.addLast(card.id)
            showNext(s.reviewed + 1)
        }
    }

    fun endSession() {
        _session.value = null
        refresh()
        de.edgebird.lernsystem.work.StudyWidgetProvider.refreshAll(getApplication())
    }

    fun saveSettings(s: StudySettings) {
        graph.saveStudySettings(s)
        _settings.value = s
        refresh()
    }
}

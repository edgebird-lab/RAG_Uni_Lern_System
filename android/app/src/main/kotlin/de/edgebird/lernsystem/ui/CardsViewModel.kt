package de.edgebird.lernsystem.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.data.CardEntity
import de.edgebird.lernsystem.data.CardWithSource
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class CardsViewModel(app: Application) : AndroidViewModel(app) {
    private val graph = (app as LernsystemApp).graph

    val cards: StateFlow<List<CardWithSource>> =
        graph.db.cards().observeAll().stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    fun add(front: String, answer: String) {
        if (front.isBlank() || answer.isBlank()) return
        viewModelScope.launch { graph.study.addManual(front, answer) }
    }

    fun edit(card: CardEntity, front: String, answer: String) {
        if (front.isBlank() || answer.isBlank()) return
        viewModelScope.launch { graph.study.edit(card, front, answer) }
    }

    /** Schreibt alle Karten als Tab-getrennte Datei (Anki-Import) an die gewählte Stelle. */
    fun export(uri: android.net.Uri) {
        viewModelScope.launch(kotlinx.coroutines.Dispatchers.IO) {
            val rows = cards.value.map { de.edgebird.lernsystem.core.cards.AnkiExport.Row(it.card.front, it.card.answer, it.documentTitle) }
            getApplication<Application>().contentResolver.openOutputStream(uri)?.use { it.write(de.edgebird.lernsystem.core.cards.AnkiExport.toTsv(rows).toByteArray()) }
        }
    }

    fun delete(card: CardEntity) {
        viewModelScope.launch { graph.study.delete(card.id) }
    }
}

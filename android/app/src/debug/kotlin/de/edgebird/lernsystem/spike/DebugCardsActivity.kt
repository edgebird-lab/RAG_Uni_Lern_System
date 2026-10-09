// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.spike

import android.app.Activity
import android.os.Bundle
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.work.CardGenWork
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Nur Debug. Kartenerzeugung per adb anstoßen und Ergebnis ausgeben:
 *   --es action gen --es doc <Titel> --ei n 10     startet die Erzeugung für das Dokument mit diesem Titel
 *   --es action dump                                schreibt alle Karten nach files/spike/cards.json
 */
class DebugCardsActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val graph = (application as LernsystemApp).graph
        if (savedInstanceState == null) when (intent.getStringExtra("action")) {
            "gen" -> runBlocking(Dispatchers.IO) {
                val doc = graph.db.documents().getAll().firstOrNull { it.title == intent.getStringExtra("doc") }
                if (doc != null) CardGenWork.enqueue(this@DebugCardsActivity, doc.id, intent.getIntExtra("n", 10))
            }
            "clear" -> runBlocking(Dispatchers.IO) { graph.db.cards().deleteAll() }
            "dump" -> runBlocking(Dispatchers.IO) {
                val arr = JSONArray()
                val db = graph.db
                val docs = db.documents().getAll().associate { it.id to it.title }
                db.cards().observeAll().first().forEach {
                    arr.put(JSONObject().put("front", it.card.front).put("answer", it.card.answer).put("doc", docs[it.card.documentId]).put("chunk", it.card.chunkId))
                }
                File(filesDir, "spike").apply { mkdirs() }.let { File(it, "cards.json").writeText(arr.toString(1)) }
            }
        }
        finish()
    }
}

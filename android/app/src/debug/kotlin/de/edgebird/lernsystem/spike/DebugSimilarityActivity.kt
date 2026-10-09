// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.spike

import android.app.Activity
import android.os.Bundle
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.ai.VectorCodec
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** Nur Debug: paarweise Kosinus-Ähnlichkeit der Kartenfragen aus files/spike/cards.json (Schwellen-Kalibrierung für Dubletten). */
class DebugSimilarityActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val graph = (application as LernsystemApp).graph
        if (savedInstanceState == null) runBlocking(Dispatchers.Default) {
            val cards = JSONArray(File(filesDir, "spike/cards.json").readText())
            val fronts = (0 until cards.length()).map { cards.getJSONObject(it).getString("front") }
            val emb = graph.sharedEmbedder.also { it.load() }
            val vecs = emb.embed(fronts).map { VectorCodec.normalize(it) }
            val out = JSONArray()
            for (i in fronts.indices) for (j in i + 1 until fronts.size) {
                out.put(JSONObject().put("i", i).put("j", j).put("sim", VectorCodec.dot(vecs[i], vecs[j]).toDouble()))
            }
            File(filesDir, "spike/sim.json").writeText(out.toString())
        }
        finish()
    }
}

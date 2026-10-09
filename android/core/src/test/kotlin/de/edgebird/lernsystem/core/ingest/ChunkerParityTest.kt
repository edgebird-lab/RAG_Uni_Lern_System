// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.ingest

import com.google.gson.JsonArray
import com.google.gson.JsonParser
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

/**
 * Paritaet mit dem PC-Chunker (`ragapp/ingestion/chunker.py`), Referenzdaten aus
 * `eval/tools/make_chunker_fixture.py`. Gleiche Einstellungen: size 1000, overlap 150, min 120.
 */
class ChunkerParityTest {
    private val cases: JsonArray by lazy {
        val stream = checkNotNull(javaClass.getResourceAsStream("/chunker/fixture.json")) { "fixture.json fehlt" }
        JsonParser.parseReader(stream.reader(Charsets.UTF_8)).asJsonArray
    }

    @Test
    fun `Kotlin-Chunker liefert dieselben Chunks wie der Python-Chunker`() {
        val cfg = ChunkerConfig(size = 1000, overlap = 150, minChars = 120)
        for (c in cases.map { it.asJsonObject }) {
            val blocks = c.getAsJsonArray("blocks").map { it.asJsonObject }.map { Block(it["text"].asString, it["page"].asInt) }
            val doc = LoadedDoc(c["text"].asString, blocks, isMarkdown = c["markdown"].asBoolean)
            val actual = Chunker.chunk(doc, cfg)
            val expected = c.getAsJsonArray("chunks").map { it.asJsonArray }
            val name = c["name"].asString
            assertEquals(expected.size, actual.size, "$name: Anzahl Chunks")
            expected.forEachIndexed { i, e ->
                assertEquals(e[0].asString, actual[i].text, "$name: Text von Chunk $i")
                assertEquals(e[1].asString, actual[i].location, "$name: Ort von Chunk $i")
            }
        }
    }
}

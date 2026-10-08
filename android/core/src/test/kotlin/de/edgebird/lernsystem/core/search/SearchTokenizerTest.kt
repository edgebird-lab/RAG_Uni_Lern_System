package de.edgebird.lernsystem.core.search

import com.google.gson.JsonParser
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class SearchTokenizerTest {
    @Test
    fun `Stoppwoerter und kurze Tokens fliegen raus, Rest wird gestemmt`() {
        assertEquals(listOf("bundesprasident", "gegenzeichn"), SearchTokenizer.tokenize("Der Bundespräsident und die Gegenzeichnung"))
        assertEquals(emptyList<String>(), SearchTokenizer.tokenize("Wie ist das? Es ist so."))
    }

    @Test
    fun `Paritaet mit der Tokenisierung der PC-App`() {
        val stream = checkNotNull(javaClass.getResourceAsStream("/search/tokens.json"))
        val cases = JsonParser.parseReader(stream.reader(Charsets.UTF_8)).asJsonArray
        val diffs = cases.map { it.asJsonObject }.mapNotNull { c ->
            val expected = c.getAsJsonArray("tokens").map { it.asString }
            val actual = SearchTokenizer.tokenize(c["text"].asString)
            if (expected != actual) "'${c["text"].asString.take(60)}': erwartet ${expected.take(8)}, war ${actual.take(8)}" else null
        }
        assertTrue(diffs.isEmpty(), "${diffs.size} Abweichungen:\n" + diffs.take(5).joinToString("\n"))
    }

    @Test
    fun `FTS-Abfrage verknuepft die Staemme mit ODER`() {
        // zuerst die deutschen Stämme, danach (nur wenn abweichend) die englischen für englische Quellen
        val q = FtsQuery.fromQuestion("Wer braucht die Gegenzeichnung des Bundespräsidenten? Gegenzeichnung!")!!
        assertEquals(true, q.startsWith("\"braucht\" OR \"gegenzeichn\" OR \"bundesprasident\""), q)
        assertNull(FtsQuery.fromQuestion("Wie ist das?"))
    }
}

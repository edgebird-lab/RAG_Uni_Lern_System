package de.edgebird.lernsystem.ingest

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import de.edgebird.lernsystem.core.ingest.ChunkerConfig
import de.edgebird.lernsystem.data.AppDatabase
import de.edgebird.lernsystem.data.search.HybridRetriever
import de.edgebird.lernsystem.data.search.KeywordSearch
import de.edgebird.lernsystem.data.search.SearchMode
import de.edgebird.lernsystem.data.search.VectorIndex
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class RetrieverTest {
    private lateinit var db: AppDatabase
    private val model = "bow-64"
    private val embedder = BagOfWordsEmbedder()

    private val docs = mapOf(
        "praesident.md" to "# Bundespräsident\n\nAnordnungen und Verfügungen des Bundespräsidenten bedürfen zu ihrer Gültigkeit der Gegenzeichnung durch den Bundeskanzler oder den zuständigen Bundesminister. ".repeat(2) +
            "\n\n# Wahl\n\nDer Bundespräsident wird von der Bundesversammlung ohne Aussprache gewählt. Wählbar ist jeder Deutsche, der das Wahlrecht zum Bundestag besitzt. ".repeat(2),
        "photo.md" to "# Photosynthese\n\nBei der Photosynthese wandeln Pflanzen Lichtenergie in chemische Energie um. Dabei entstehen Sauerstoff und Glucose aus Kohlenstoffdioxid und Wasser. ".repeat(3),
        "kosten.md" to "# Kostenrechnung\n\nDie Herstellkosten je Stück ergeben sich aus den Gesamtkosten geteilt durch die produzierte Menge. Verwaltungskosten werden zusätzlich berücksichtigt. ".repeat(3),
    )

    @Before
    fun setUp() = runBlocking {
        val ctx = InstrumentationRegistry.getInstrumentation().targetContext
        db = AppDatabase.inMemory(ctx)
        val pipeline = ImportPipeline(db, Loaders.default(ctx), ChunkerConfig(size = 400, overlap = 40, minChars = 60))
        docs.forEach { (name, text) -> pipeline.import(textSource(name, name, text)) }
        Unit
    }

    @After
    fun tearDown() = db.close()

    private fun retriever(withEmbedder: Boolean = true) =
        HybridRetriever(db, KeywordSearch(db), VectorIndex(db, model), if (withEmbedder) embedder else null)

    private suspend fun embedAll() = EmbeddingIndexer(db, embedder, model).run()

    @Test
    fun stichwortsuche_findetGestemmteFormen() = runBlocking {
        // „Gegenzeichnungen“ (Plural) muss „Gegenzeichnung“ finden, „Bundespräsidenten“ -> „Bundespräsident“
        val hits = retriever().retrieve("Welche Gegenzeichnungen braucht der Bundespräsidenten?", mode = SearchMode.KEYWORD)
        assertTrue(hits.isNotEmpty())
        assertEquals("praesident", hits.first().documentTitle)
        assertTrue("Gegenzeichnung" in hits.first().chunk.text)
        assertNotNull(hits.first().keywordRank)
    }

    @Test
    fun stichwortsuche_ordnetNachRelevanz() = runBlocking {
        val hits = retriever().retrieve("Lichtenergie Sauerstoff Pflanzen", mode = SearchMode.KEYWORD)
        assertEquals("photo", hits.first().documentTitle)
    }

    @Test
    fun vektorsuche_findetAehnlichenChunk() = runBlocking {
        embedAll()
        val hits = retriever().retrieve("Wie berechnet man die Herstellkosten pro Stück?", mode = SearchMode.DENSE)
        assertEquals("kosten", hits.first().documentTitle)
        assertNotNull(hits.first().denseRank)
    }

    @Test
    fun hybrid_kombiniertBeideListen() = runBlocking {
        embedAll()
        val hits = retriever().retrieve("Von wem wird der Bundespräsident gewählt?", topK = 3)
        val top = hits.first()
        assertEquals("praesident", top.documentTitle)
        assertTrue("falscher Chunk: ${top.chunk.text.take(80)}", "gewählt" in top.chunk.text)
        assertTrue("Rang Stichwort=${top.keywordRank}, Vektor=${top.denseRank}", top.keywordRank != null && top.denseRank != null)
    }

    @Test
    fun ohneEmbeddings_faelltHybridAufStichwortZurueck() = runBlocking {
        val hits = retriever().retrieve("Photosynthese Glucose", topK = 2)
        assertEquals("photo", hits.first().documentTitle)
        assertEquals(null, hits.first().denseRank)
    }

    @Test
    fun ohneEmbedder_funktioniertStichwortsuche() = runBlocking {
        val hits = retriever(withEmbedder = false).retrieve("Herstellkosten", topK = 2)
        assertEquals("kosten", hits.first().documentTitle)
    }

    @Test
    fun sonderzeichenInDerFrage_brechenDieAbfrageNicht() = runBlocking {
        val hits = retriever().retrieve("\"Herstellkosten\" AND (NEAR/3 * OR) ' ; -- ?", mode = SearchMode.KEYWORD)
        assertEquals("kosten", hits.first().documentTitle)
    }

    @Test
    fun frageOhneSuchbareWoerter_liefertNichts() = runBlocking {
        assertTrue(retriever().retrieve("Wie ist das?", mode = SearchMode.KEYWORD).isEmpty())
    }

    @Test
    fun vektorIndex_ladetNeu_wennEmbeddingsHinzukommen() = runBlocking {
        val index = VectorIndex(db, model)
        assertEquals(0, index.search(embedder.embed(listOf("Herstellkosten")).first(), 3).size)
        embedAll()
        assertTrue(index.search(embedder.embed(listOf("Herstellkosten")).first(), 3).isNotEmpty())
    }
}

package de.edgebird.lernsystem.ingest

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import de.edgebird.lernsystem.core.ai.VectorCodec
import de.edgebird.lernsystem.data.AppDatabase
import de.edgebird.lernsystem.data.DocumentStatus
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class EmbeddingIndexerTest {
    private lateinit var db: AppDatabase
    private val model = "fake-8"

    @Before
    fun setUp() {
        val ctx = InstrumentationRegistry.getInstrumentation().targetContext
        db = AppDatabase.inMemory(ctx)
        val pipeline = ImportPipeline(db, Loaders.default(ctx), de.edgebird.lernsystem.core.ingest.ChunkerConfig(size = 200, overlap = 20, minChars = 50))
        val text = (1..40).joinToString("\n\n") { "Absatz $it: " + "Inhalt zu Thema $it wird hier ausführlich beschrieben. ".repeat(2) }
        runBlocking { pipeline.import(textSource("k", "viel.txt", text)) }
    }

    @After
    fun tearDown() = db.close()

    @Test
    fun berechnetEmbeddingsFuerAlleChunks_undMarkiertDokumentAlsIndexiert() = runBlocking {
        val total = db.chunks().count()
        assertTrue(total > 20)
        val emb = FakeEmbedder()
        val progress = mutableListOf<Pair<Int, Int>>()
        val done = EmbeddingIndexer(db, emb, model, batchSize = 8).run { d, t -> progress += d to t }
        assertEquals(total, done)
        assertEquals(total, db.embeddings().countForModel(model))
        assertEquals(0, db.chunks().countWithoutEmbedding(model))
        assertEquals(DocumentStatus.INDEXED, db.documents().getAll().single().status)
        assertEquals(total to total, progress.last())
        val v = VectorCodec.decode(db.embeddings().allForModel(model).first().vector)
        assertEquals(8, v.size)
    }

    @Test
    fun abbruch_kannFortgesetztWerden_ohneDoppelteArbeit() = runBlocking {
        val total = db.chunks().count()
        try {
            EmbeddingIndexer(db, FakeEmbedder(failAfterBatches = 2), model, batchSize = 8).run()
            fail("Abbruch erwartet")
        } catch (e: IllegalStateException) {
            // erwartet
        }
        assertEquals(16, db.embeddings().countForModel(model))
        assertEquals(DocumentStatus.PENDING, db.documents().getAll().single().status)

        val resumed = FakeEmbedder()
        val done = EmbeddingIndexer(db, resumed, model, batchSize = 8).run()
        assertEquals(total - 16, done)
        assertEquals(total, db.embeddings().countForModel(model))
        assertEquals(DocumentStatus.INDEXED, db.documents().getAll().single().status)
    }

    @Test
    fun nichtsZuTun_ladetDasModellNicht() = runBlocking {
        val emb = FakeEmbedder()
        EmbeddingIndexer(db, emb, model).run()
        val second = FakeEmbedder()
        assertEquals(0, EmbeddingIndexer(db, second, model).run())
        assertTrue(!second.loaded)
    }
}

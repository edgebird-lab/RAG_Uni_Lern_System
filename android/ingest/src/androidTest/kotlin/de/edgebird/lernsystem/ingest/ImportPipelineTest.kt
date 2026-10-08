package de.edgebird.lernsystem.ingest

import androidx.room.useReaderConnection
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import de.edgebird.lernsystem.data.AppDatabase
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ImportPipelineTest {
    private lateinit var db: AppDatabase
    private lateinit var pipeline: ImportPipeline

    @Before
    fun setUp() {
        val ctx = InstrumentationRegistry.getInstrumentation().targetContext
        db = AppDatabase.inMemory(ctx)
        pipeline = ImportPipeline(db, Loaders.default(ctx))
    }

    @After
    fun tearDown() = db.close()

    /** Der Index enthält gestemmte Tokens: der Suchbegriff wird genauso aufbereitet. */
    private fun ftsHits(term: String): Int = runBlocking {
        val stem = de.edgebird.lernsystem.core.search.SearchTokenizer.tokenize(term).first()
        db.useReaderConnection { c ->
            c.usePrepared("SELECT COUNT(*) FROM chunk_fts WHERE chunk_fts MATCH ?") { st ->
                st.bindText(1, stem)
                st.step()
                st.getLong(0).toInt()
            }
        }
    }

    private val md = "# Kosten\n\n" + "Kosten sind bewertete Güter, die für die Erstellung von Leistungen verbraucht werden. ".repeat(3) +
        "\n\n# Erlöse\n\n" + "Erlöse sind die Einnahmen aus dem Verkauf von Waren und Dienstleistungen an Kunden. ".repeat(3)

    @Test
    fun markdown_wirdEingelesen_undIstPerStichwortFindbar() = runBlocking {
        val r = pipeline.import(textSource("k1", "kosten.md", md))
        assertTrue(r is ImportResult.Imported)
        r as ImportResult.Imported
        assertEquals(2, r.chunks)
        assertEquals(2, db.chunks().countForDocument(r.documentId))
        assertEquals(1, ftsHits("erlöse"))
        assertEquals(1, ftsHits("kosten"))
        assertEquals(0, ftsHits("photosynthese"))
        assertEquals("kosten", db.documents().byPath("k1")?.title)
    }

    @Test
    fun pdf_wirdSeitenweiseEingelesen_mitSeitenangabe() = runBlocking {
        val r = pipeline.import(assetSource("test.pdf")) as ImportResult.Imported
        assertEquals(1, r.emptyPages)
        val locations = db.chunks().byDocument(r.documentId).map { it.location }
        assertEquals(listOf("Seite 1", "Seite 2", "Seite 4"), locations)
        assertEquals(1, ftsHits("würde"))
    }

    @Test
    fun gleicheDateiNochmal_wirdUebersprungen() = runBlocking {
        pipeline.import(textSource("k1", "kosten.md", md))
        assertTrue(pipeline.import(textSource("k1", "kosten.md", md)) is ImportResult.SkippedUnchanged)
        assertEquals(1, db.documents().getAll().size)
    }

    @Test
    fun gleicherInhaltUnterAnderemPfad_istDuplikat() = runBlocking {
        pipeline.import(textSource("k1", "kosten.md", md))
        val r = pipeline.import(textSource("k2", "kopie.md", md))
        assertTrue(r is ImportResult.SkippedDuplicate)
        assertEquals(1, db.documents().getAll().size)
    }

    @Test
    fun geaenderterInhalt_ersetztAlteChunks_undAktualisiertDenIndex() = runBlocking {
        pipeline.import(textSource("k1", "kosten.md", md))
        val neu = "# Neu\n\n" + "Photosynthese wandelt Lichtenergie in chemische Energie um und erzeugt dabei Sauerstoff. ".repeat(3)
        val r = pipeline.import(textSource("k1", "kosten.md", neu)) as ImportResult.Imported
        assertTrue(r.replaced)
        assertEquals(1, db.documents().getAll().size)
        assertEquals(0, ftsHits("erlöse"))
        assertEquals(1, ftsHits("photosynthese"))
        assertEquals(r.chunks, db.chunks().count())
    }

    @Test
    fun dokumentLoeschen_entferntChunksUndIndex() = runBlocking {
        val r = pipeline.import(textSource("k1", "kosten.md", md)) as ImportResult.Imported
        db.documents().delete(r.documentId)
        assertEquals(0, db.chunks().count())
        assertEquals(0, ftsHits("kosten"))
    }

    @Test
    fun unbekannterDateityp_wirdAbgelehnt() = runBlocking {
        val r = pipeline.import(textSource("x", "tabelle.xyz", "a"))
        assertTrue(r is ImportResult.Failed)
        assertTrue((r as ImportResult.Failed).reason.contains(".xyz"))
    }

    @Test
    fun gescanntesPdf_ohneText_wirdMitHinweisAbgelehnt() = runBlocking {
        val r = pipeline.import(assetSource("leer.pdf")) as ImportResult.Failed
        assertTrue(r.reason, "Kein Text erkannt" in r.reason)
        assertEquals(0, db.documents().getAll().size)
    }

    @Test
    fun latin1Datei_wirdLesbarEingelesen() = runBlocking {
        val bytes = "# Titel\n\nÄpfel und Birnen sind Früchte, die in Gärten wachsen. ".repeat(4).toByteArray(Charsets.ISO_8859_1)
        val r = pipeline.import(DocumentSource("l", "alt.md") { bytes.inputStream() }) as ImportResult.Imported
        assertEquals(1, ftsHits("früchte"))
        assertTrue(r.chunks >= 1)
    }
}

package de.edgebird.lernsystem.ingest

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PdfDocumentLoaderTest {
    private val loader = PdfDocumentLoader(InstrumentationRegistry.getInstrumentation().targetContext)

    @Test
    fun extrahiertText_seitenweise_mitUmlauten() {
        val doc = loader.load(assetSource("test.pdf"))
        assertEquals(listOf(1, 2, 4), doc.blocks.map { it.page })
        assertEquals(1, doc.emptyPages)
        assertTrue("Umlaute fehlen: ${doc.blocks[0].text}", "Die Würde des Menschen ist unantastbar" in doc.blocks[0].text)
        assertTrue("unveräußerlichen" in doc.blocks[0].text)
    }

    @Test
    fun silbentrennung_wirdZusammengefuegt() {
        val doc = loader.load(assetSource("test.pdf"))
        val t = doc.blocks[1].text
        val i = t.indexOf("Divisions")
        assertTrue("um Divisions: " + t.substring(i, minOf(t.length, i + 24)).map { it.code.toString(16) }.joinToString(" "), "Divisionskalkulation" in t)
    }

    @Test
    fun reinesScan_ergibtKeineBloecke() {
        val doc = loader.load(assetSource("leer.pdf"))
        assertTrue(doc.blocks.isEmpty())
        assertEquals(2, doc.emptyPages)
    }

    @Test(expected = LoadException::class)
    fun kaputtePdf_wirftLoadException() {
        loader.load(DocumentSource("x", "kaputt.pdf") { "das ist kein pdf".byteInputStream() })
    }
}

// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ingest

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.pdf.PdfDocument
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import de.edgebird.lernsystem.core.ingest.OcrText
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream

@RunWith(AndroidJUnit4::class)
class OcrTest {
    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext
    private lateinit var recognizer: TesseractTextRecognizer

    @Before fun setUp() { recognizer = TesseractTextRecognizer({ Tessdata.ensure(ctx) }) }
    @After fun tearDown() = recognizer.close()

    /** Eine weiße „Seite“ mit schwarzem Text (so, wie ein Scan aussieht). */
    private fun page(vararg lines: String): Bitmap {
        val bmp = Bitmap.createBitmap(1400, 500 + 90 * lines.size, Bitmap.Config.ARGB_8888)
        val c = Canvas(bmp)
        c.drawColor(Color.WHITE)
        val p = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.BLACK; textSize = 56f; typeface = android.graphics.Typeface.SANS_SERIF }
        lines.forEachIndexed { i, l -> c.drawText(l, 60f, 120f + i * 90f, p) }
        return bmp
    }

    private fun png(b: Bitmap) = ByteArrayOutputStream().also { b.compress(Bitmap.CompressFormat.PNG, 100, it) }.toByteArray()

    @Test
    fun foto_wirdZuText() {
        val bytes = png(page("Die Photosynthese wandelt", "Lichtenergie in chemische", "Energie um."))
        val doc = ImageDocumentLoader(recognizer).load(DocumentSource("k", "scan.png") { bytes.inputStream() })
        assertTrue(doc.text, "Photosynthese" in doc.text && "Lichtenergie" in doc.text)
        assertEquals(1, doc.blocks.single().page)
    }

    @Test
    fun leeresBild_hatKeinenText_undWirdAlsLeereSeiteGezaehlt() {
        val bytes = png(Bitmap.createBitmap(800, 600, Bitmap.Config.ARGB_8888).also { Canvas(it).drawColor(Color.WHITE) })
        val doc = ImageDocumentLoader(recognizer).load(DocumentSource("k", "leer.jpg") { bytes.inputStream() })
        assertTrue(doc.text.isBlank())
        assertEquals(1, doc.emptyPages)
    }

    @Test
    fun gescanntesPdf_wirdPerOcrGelesen_ohneRecognizerBleibtEsLeer() {
        val pdf = PdfDocument()
        val bmp = page("Quicksort teilt das Feld rekursiv", "am Pivotelement in zwei Teile.")
        val info = PdfDocument.PageInfo.Builder(bmp.width, bmp.height, 1).create()
        val pg = pdf.startPage(info)
        pg.canvas.drawBitmap(bmp, 0f, 0f, null)        // nur ein Bild, keine Text-Ebene
        pdf.finishPage(pg)
        val out = ByteArrayOutputStream().also { pdf.writeTo(it) }.toByteArray()
        pdf.close()

        val src = DocumentSource("k", "scan.pdf") { out.inputStream() }
        val ohne = PdfDocumentLoader(ctx).load(src)
        assertEquals(1, ohne.emptyPages); assertTrue(ohne.text.isBlank())

        val mit = PdfDocumentLoader(ctx, recognizer).load(src)
        assertEquals(0, mit.emptyPages)
        assertTrue(mit.text, "Quicksort" in mit.text && "Pivotelement" in mit.text)
        assertEquals(1, mit.blocks.single().page)
    }

    @Test
    fun textMitSeitenwechsel_wirdZuSeiten() {
        val text = OcrText.joinPages(listOf("Erste Seite mit Inhalt.", "", "Dritte Seite mit Inhalt."))
        val doc = TextDocumentLoader().load(DocumentSource("k", "foto.txt") { text.toByteArray().inputStream() })
        assertEquals(listOf(1, 3), doc.blocks.map { it.page })
        assertEquals(1, doc.emptyPages)
    }

    @Test
    fun standardLoader_kennenBilder() {
        val loaders = Loaders.default(ctx)
        assertTrue(loaders.any { "jpg" in it.extensions && "png" in it.extensions })
    }
}

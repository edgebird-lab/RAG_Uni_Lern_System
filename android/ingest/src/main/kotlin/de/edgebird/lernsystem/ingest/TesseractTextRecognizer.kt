// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ingest

import android.graphics.Bitmap
import com.googlecode.leptonica.android.AdaptiveMap
import com.googlecode.leptonica.android.Binarize
import com.googlecode.leptonica.android.Convert
import com.googlecode.leptonica.android.Pix
import com.googlecode.leptonica.android.ReadFile
import com.googlecode.leptonica.android.Scale
import com.googlecode.leptonica.android.Skew
import com.googlecode.tesseract.android.TessBaseAPI
import de.edgebird.lernsystem.core.ingest.OcrText
import java.io.File

/** Wie ein Bild vor der Erkennung aufbereitet wird (Leptonica). */
enum class OcrPreprocess {
    /** Bild unverändert. */
    NONE,
    /** Graustufen, Hintergrund und Schatten ausgleichen, kleine Bilder vergrößern. */
    NORMALIZE,
    /** Wie [NORMALIZE], zusätzlich schiefe Zeilen begradigen. */
    NORMALIZE_DESKEW,
    /** Wie [NORMALIZE_DESKEW], zusätzlich lokal schwarz-weiß wandeln (Sauvola). */
    BINARIZE,
    /** Standard: erst [NORMALIZE_DESKEW]; ist die Erkennung unsicher (Schatten, Rauschen, Unschärfe), zusätzlich [BINARIZE] und das sicherere Ergebnis nehmen. */
    AUTO,
}

/**
 * Texterkennung mit Tesseract (Apache-2.0, läuft komplett auf dem Gerät). [dataRoot] enthält den Ordner `tessdata/` mit den Sprachdateien
 * (`deu.traineddata`, `eng.traineddata`); [languages] z. B. `deu+eng`. Nicht für gleichzeitige Aufrufe gedacht: Aufrufe werden nacheinander abgearbeitet.
 */
class TesseractTextRecognizer(
    private val dataRoot: () -> File,
    private val languages: String = "deu+eng",
    private val preprocess: OcrPreprocess = OcrPreprocess.AUTO,
) : TextRecognizer, AutoCloseable {
    constructor(dataRoot: File, languages: String = "deu+eng", preprocess: OcrPreprocess = OcrPreprocess.AUTO) : this({ dataRoot }, languages, preprocess)

    private var api: TessBaseAPI? = null

    private fun engine(): TessBaseAPI = api ?: TessBaseAPI().also {
        val root = dataRoot()
        check(it.init(root.path, languages, TessBaseAPI.OEM_LSTM_ONLY)) { "Tesseract konnte nicht gestartet werden (Sprachdaten in ${File(root, "tessdata")} prüfen)" }
        it.pageSegMode = TessBaseAPI.PageSegMode.PSM_AUTO
        api = it
    }

    /** Ein Durchgang mit einer festen Aufbereitung: erkannter Text und mittlere Sicherheit (0 bis 100). */
    private fun pass(tess: TessBaseAPI, bitmap: Bitmap, mode: OcrPreprocess): Pair<String, Int> {
        val pix = prepare(bitmap, mode)
        return try {
            tess.setImage(pix)
            // Tesseract trennt Absätze (Textblöcke) durch Leerzeilen
            val text = OcrText.joinBlocks(tess.utF8Text.orEmpty().split(Regex("\\n\\s*\\n")).map { it.lines() })
            text to tess.meanConfidence()
        } finally {
            pix.recycle(); tess.clear()
        }
    }

    @Synchronized
    override fun recognize(bitmap: Bitmap): String {
        val tess = engine()
        if (preprocess != OcrPreprocess.AUTO) return pass(tess, bitmap, preprocess).first
        val first = pass(tess, bitmap, OcrPreprocess.NORMALIZE_DESKEW)
        if (first.second >= CONFIDENT || first.first.isBlank()) return first.first
        val second = pass(tess, bitmap, OcrPreprocess.BINARIZE)
        return if (second.second > first.second) second.first else first.first
    }

    /** Das aufbereitete Bild (Aufrufer ruft `recycle()`). */
    internal fun prepare(bitmap: Bitmap, preprocess: OcrPreprocess = this.preprocess): Pix {
        var pix = ReadFile.readBitmap(bitmap) ?: error("Bild konnte nicht übernommen werden")
        if (preprocess == OcrPreprocess.NONE) return pix
        fun step(next: Pix?) { if (next != null && next !== pix) { pix.recycle(); pix = next } }
        step(Convert.convertTo8(pix))
        // Zu kleine Bilder (Screenshots, Vorschaubilder) für die Zeichenerkennung vergrößern: Tesseract erwartet Zeilenhöhen ab etwa 20 Pixeln
        val w = pix.width
        if (w in 1..1400) step(Scale.scale(pix, (1800f / w).coerceAtMost(3f)))
        step(AdaptiveMap.backgroundNormMorph(pix))
        if (preprocess != OcrPreprocess.NORMALIZE) step(Skew.deskew(pix, null))
        if (preprocess == OcrPreprocess.BINARIZE) step(Binarize.sauvolaBinarizeTiled(pix))
        return pix
    }

    /** Gibt den Arbeitsspeicher der Sprachmodelle frei; der nächste Aufruf lädt sie wieder. */
    @Synchronized
    fun release() { api?.recycle(); api = null }

    override fun close() = release()

    private companion object { const val CONFIDENT = 90 }
}

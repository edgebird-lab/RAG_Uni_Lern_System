// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.spike

import android.app.Activity
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Shader
import android.graphics.Typeface
import android.os.Bundle
import android.view.WindowManager
import de.edgebird.lernsystem.ingest.OcrPreprocess
import de.edgebird.lernsystem.ingest.TesseractTextRecognizer
import de.edgebird.lernsystem.ingest.TextRecognizer
import java.io.ByteArrayOutputStream
import java.io.File
import kotlin.random.Random

/**
 * Nur Debug: vergleicht Texterkennungen an künstlichen Seiten (sauber, „Foto“ mit Schatten, Rauschen, Drehung, JPEG) mit bekanntem Text.
 * Erwartet `files/ocr-eval/fast/tessdata/ und files/ocr-eval/best/tessdata/` (jeweils deu.traineddata und eng.traineddata); Ausgabe: `files/debug-out/ocr.txt`.
 */
class DebugOcrEvalActivity : Activity() {
    private val de = "Die Photosynthese ist ein biochemischer Prozess, bei dem Pflanzen, Algen und manche Bakterien Lichtenergie in chemische Energie umwandeln. In den Chloroplasten wird dabei Kohlenstoffdioxid mithilfe von Wasser zu Glucose reduziert, und es entsteht Sauerstoff als Nebenprodukt. Der Wirkungsgrad beträgt je nach Pflanze etwa 1 bis 3 Prozent der eingestrahlten Energie. Wichtige Größen sind außerdem die Temperatur (z. B. 25 °C), die Lichtintensität und die Konzentration von CO2 in der Luft. Der Calvin-Zyklus findet im Stroma statt; die Lichtreaktionen laufen an den Thylakoidmembranen ab."
    private val en = "A binary heap is a complete binary tree in which the key of every node is greater than or equal to the keys of its children. Inserting an element costs O(log n) because the element is moved upwards by swapping it with its parent. Heapsort first builds a max-heap and then repeatedly swaps the root with the last element of the heap region. It sorts in place, but it is not stable. Priority queues, Dijkstra's algorithm and operating system schedulers all rely on this data structure."

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContentView(android.widget.TextView(this).apply { text = "OCR-Vergleich läuft …"; textSize = 24f; setPadding(48, 200, 48, 48) })
        if (savedInstanceState != null) return
        val out = File(filesDir, "debug-out").apply { mkdirs() }.resolve("ocr.txt").also { it.writeText("") }
        Thread {
            try {
                val base = File(filesDir, "ocr-eval")
                val engines = linkedMapOf<String, TextRecognizer>(
                    "fast/ohne" to TesseractTextRecognizer(File(base, "fast"), "deu+eng", OcrPreprocess.NONE),
                    "fast/norm" to TesseractTextRecognizer(File(base, "fast"), "deu+eng", OcrPreprocess.NORMALIZE),
                    "fast/norm+schief" to TesseractTextRecognizer(File(base, "fast"), "deu+eng", OcrPreprocess.NORMALIZE_DESKEW),
                    "best/ohne" to TesseractTextRecognizer(File(base, "best"), "deu+eng", OcrPreprocess.NONE),
                    "best/norm+schief" to TesseractTextRecognizer(File(base, "best"), "deu+eng", OcrPreprocess.NORMALIZE_DESKEW),
                    "best/sauvola" to TesseractTextRecognizer(File(base, "best"), "deu+eng", OcrPreprocess.BINARIZE),
                    "best/auto" to TesseractTextRecognizer(File(base, "best"), "deu+eng", OcrPreprocess.AUTO),
                )
                val cases = listOf("de" to de, "en" to en).flatMap { (lang, text) ->
                    listOf("sauber" to page(text, 0), "Foto leicht" to page(text, 1), "Foto schwer" to page(text, 2)).map { (kind, bmp) -> Triple("$lang $kind", text, bmp) }
                }
                // Warm-up, damit die erste Messung nicht das Laden der Modelle enthält
                engines.values.forEach { runCatching { it.recognize(cases[0].third) } }
                out.appendText("Fall | Verfahren | Zeichenfehlerrate | Wortfehlerrate | Zeit\n")
                val totals = linkedMapOf<String, DoubleArray>()
                for ((name, ref, bmp) in cases) for ((en, rec) in engines) {
                    val t0 = System.currentTimeMillis()
                    val hyp = runCatching { rec.recognize(bmp) }.getOrElse { "FEHLER ${it.message}" }
                    val ms = System.currentTimeMillis() - t0
                    val cer = cer(ref, hyp); val wer = wer(ref, hyp)
                    out.appendText("$name | $en | ${"%.1f".format(cer * 100)} % | ${"%.1f".format(wer * 100)} % | $ms ms\n")
                    totals.getOrPut(en) { DoubleArray(3) }.also { it[0] += cer; it[1] += wer; it[2] += ms.toDouble() }
                }
                out.appendText("\nMittel über ${cases.size} Fälle:\n")
                totals.forEach { (k, v) -> out.appendText("$k: Zeichenfehler ${"%.1f".format(v[0] / cases.size * 100)} %, Wortfehler ${"%.1f".format(v[1] / cases.size * 100)} %, ${(v[2] / cases.size).toInt()} ms je Seite\n") }
                // Beispielausgabe zum Ansehen
                out.appendText("\nBeispiel de Foto schwer (best/norm+schief):\n" + engines.getValue("best/norm+schief").recognize(cases[2].third) + "\n")
                File(filesDir, "debug-out/ocr-schwer.jpg").outputStream().use { cases[2].third.compress(Bitmap.CompressFormat.JPEG, 80, it) }
                engines.values.forEach { (it as? AutoCloseable)?.close() }
                out.appendText("FERTIG\n")
            } catch (e: Throwable) { out.appendText("FEHLER: $e\n${e.stackTraceToString().take(800)}\n") }
            runOnUiThread { finish() }
        }.start()
    }

    // ---- Testbilder ----------------------------------------------------------------------------------------------------

    /** Seite mit [text]; [level] 0 = sauberer Scan, 1 = Foto leicht verschlechtert, 2 = Foto schwer (Schatten, Rauschen, Unschärfe, Drehung, JPEG). */
    private fun page(text: String, level: Int): Bitmap {
        val w = 1240; val h = 760
        val page = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        val c = Canvas(page); c.drawColor(Color.WHITE)
        val p = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(20, 20, 20); textSize = 30f; typeface = Typeface.SERIF }
        var y = 80f
        val words = text.split(' ')
        val line = StringBuilder()
        for (word in words) {
            if (p.measureText("$line $word") > w - 160) { c.drawText(line.toString().trim(), 80f, y, p); y += 44f; line.clear() }
            line.append(' ').append(word)
        }
        c.drawText(line.toString().trim(), 80f, y, p)
        if (level == 0) return page
        val rnd = Random(level * 31 + text.length)
        // Verkleinern und wieder vergrößern = weiche Kanten wie bei einer Handykamera
        val soft = if (level == 1) 0.8f else 0.55f
        var b = Bitmap.createScaledBitmap(Bitmap.createScaledBitmap(page, (w * soft).toInt(), (h * soft).toInt(), true), w, h, true)
        // Drehung und leichte Perspektive
        val m = Matrix().apply { postRotate(if (level == 1) 1.2f else 2.6f, w / 2f, h / 2f) }
        val rotated = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        Canvas(rotated).apply { drawColor(Color.rgb(205, 200, 190)); drawBitmap(b, m, Paint(Paint.FILTER_BITMAP_FLAG)) }
        b = rotated
        // Beleuchtung: Schatten von links, Helligkeitsverlauf
        val shade = Paint().apply { shader = LinearGradient(0f, 0f, w.toFloat(), 0f, Color.argb(if (level == 1) 70 else 150, 0, 0, 0), Color.argb(0, 0, 0, 0), Shader.TileMode.CLAMP) }
        Canvas(b).drawRect(0f, 0f, w.toFloat(), h.toFloat(), shade)
        // Rauschen
        val px = IntArray(w * h); b.getPixels(px, 0, w, 0, 0, w, h)
        val amp = if (level == 1) 10 else 26
        for (i in px.indices) { val d = rnd.nextInt(-amp, amp + 1); val c0 = px[i]; px[i] = Color.rgb((Color.red(c0) + d).coerceIn(0, 255), (Color.green(c0) + d).coerceIn(0, 255), (Color.blue(c0) + d).coerceIn(0, 255)) }
        b.setPixels(px, 0, w, 0, 0, w, h)
        // JPEG-Umweg
        val bo = ByteArrayOutputStream(); b.compress(Bitmap.CompressFormat.JPEG, if (level == 1) 70 else 40, bo)
        return android.graphics.BitmapFactory.decodeByteArray(bo.toByteArray(), 0, bo.size())
    }

    // ---- Fehlermaße ----------------------------------------------------------------------------------------------------

    private fun norm(s: String) = s.replace(Regex("\\s+"), " ").trim()
    private fun lev(a: List<String>, b: List<String>): Int {
        var prev = IntArray(b.size + 1) { it }; var cur = IntArray(b.size + 1)
        for (i in 1..a.size) { cur[0] = i; for (j in 1..b.size) cur[j] = minOf(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + if (a[i - 1] == b[j - 1]) 0 else 1); val t = prev; prev = cur; cur = t }
        return prev[b.size]
    }
    private fun cer(ref: String, hyp: String): Double { val r = norm(ref).map { it.toString() }; return lev(r, norm(hyp).map { it.toString() }).toDouble() / r.size }
    private fun wer(ref: String, hyp: String): Double { val r = norm(ref).split(' '); return lev(r, norm(hyp).split(' ')).toDouble() / r.size }
}

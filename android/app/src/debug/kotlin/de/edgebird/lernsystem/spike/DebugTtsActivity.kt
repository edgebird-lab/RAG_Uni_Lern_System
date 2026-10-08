package de.edgebird.lernsystem.spike

import android.app.Activity
import android.os.Bundle
import android.view.WindowManager
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.ai.PiperVoice
import de.edgebird.lernsystem.core.audio.SpeechText
import de.edgebird.lernsystem.core.audio.Wav
import java.io.File

/** Nur Debug: prüft die Offline-Stimme (files/models/tts-de): Laden, Geschwindigkeit, erzeugte Audiodatei (files/debug-out/tts.wav und tts.txt). */
class DebugTtsActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContentView(android.widget.TextView(this).apply { text = "Stimmen-Test läuft …"; textSize = 24f; setPadding(48, 200, 48, 48) })
        if (savedInstanceState != null) return
        val dir = File(filesDir, "debug-out").apply { mkdirs() }
        val log = File(dir, "tts.txt").also { it.writeText("") }
        Thread {
            try {
                val graph = (application as LernsystemApp).graph
                val old = de.edgebird.lernsystem.core.i18n.Lang.current
                for (lang in de.edgebird.lernsystem.core.i18n.Lang.entries) {
                    de.edgebird.lernsystem.core.i18n.Lang.current = lang
                    val entry = graph.voices.selected(lang)
                    log.appendText("== ${lang.tag}: Stimme ${entry?.name} (${entry?.id}), installiert: ${graph.voices.installed().map { it.id }}\n")
                    if (entry == null) continue
                    val t0 = System.currentTimeMillis()
                    val voice = PiperVoice(entry.dir, dataDir = graph.voices.dataDirFor(entry))
                    log.appendText("laden: ${System.currentTimeMillis() - t0} ms, Abtastrate ${voice.sampleRate}\n")
                    val md = if (lang == de.edgebird.lernsystem.core.i18n.Lang.EN) "## Photosynthesis\n\n- Plants convert **light energy** into chemical energy, e.g. into glucose.\n- The efficiency is approx. 29 % at 25 °C, i.e. rather low.\n\nThe cell is the smallest living unit of all organisms, and the Calvin cycle takes place in the stroma of the chloroplasts. See Fig. 3, e.g. the Dr. says so."
                    else "## Photosynthese\n\n- Pflanzen wandeln **Lichtenergie** in chemische Energie um, z. B. in Glucose.\n- Der Wirkungsgrad beträgt ca. 29 % bei 25 °C.\n\nDie Zelle ist die kleinste lebende Einheit aller Organismen, und der Calvin-Zyklus findet im Stroma der Chloroplasten statt."
                    val chunks = SpeechText.chunks(SpeechText.prepare(md))
                    log.appendText("Text: ${chunks.joinToString(" | ") { it.first }}\n")
                    val pcm = java.io.ByteArrayOutputStream()
                    var audioSec = 0.0
                    val t1 = System.currentTimeMillis()
                    for ((text, pauseMs) in chunks) {
                        val smp = voice.synthesize(text)
                        audioSec += smp.size / voice.sampleRate.toDouble()
                        pcm.write(SpeechText.toPcm16(smp)); pcm.write(ByteArray(voice.sampleRate * pauseMs / 1000 * 2))
                    }
                    val took = (System.currentTimeMillis() - t1) / 1000.0
                    val bytes = pcm.toByteArray()
                    File(dir, "tts-${lang.tag}.wav").writeBytes(Wav.build(Wav.Format(1, voice.sampleRate, 16), bytes))
                    val sh = java.nio.ByteBuffer.wrap(bytes).order(java.nio.ByteOrder.LITTLE_ENDIAN).asShortBuffer()
                    var peak = 0; var sum = 0.0
                    while (sh.hasRemaining()) { val v = sh.get().toInt(); peak = maxOf(peak, Math.abs(v)); sum += v.toDouble() * v }
                    val n = bytes.size / 2
                    log.appendText("Audio ${"%.1f".format(audioSec)} s Sprache in ${"%.1f".format(took)} s Rechenzeit (Echtzeitfaktor ${"%.2f".format(took / audioSec)}), Spitze $peak, Effektivwert ${"%.0f".format(Math.sqrt(sum / n))}\n")
                    voice.close()
                }
                de.edgebird.lernsystem.core.i18n.Lang.current = old
                log.appendText("FERTIG\n")
            } catch (e: Throwable) { log.appendText("FEHLER: $e\n") }
            runOnUiThread { finish() }
        }.start()
    }
}

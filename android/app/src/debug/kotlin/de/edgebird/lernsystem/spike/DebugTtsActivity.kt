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
                val voiceDir = File(graph.modelsDir, "tts-de")
                log.appendText("installiert: ${PiperVoice.isInstalled(voiceDir)}\n")
                val t0 = System.currentTimeMillis()
                val voice = PiperVoice(voiceDir)
                log.appendText("laden: ${System.currentTimeMillis() - t0} ms, Abtastrate ${voice.sampleRate}\n")
                val md = "## Photosynthese\n\n- Pflanzen wandeln **Lichtenergie** in chemische Energie um, z. B. in Glucose.\n- Der Wirkungsgrad beträgt ca. 29 % bei 25 °C.\n\nDie Zelle ist die kleinste lebende Einheit aller Organismen, und der Calvin-Zyklus findet im Stroma der Chloroplasten statt."
                val chunks = SpeechText.chunks(SpeechText.prepare(md))
                log.appendText("Text: ${chunks.joinToString(" | ") { it.first }}\n")
                val pcm = java.io.ByteArrayOutputStream()
                var audioSec = 0.0
                val t1 = System.currentTimeMillis()
                for ((text, pauseMs) in chunks) {
                    val s = voice.synthesize(text)
                    audioSec += s.size / voice.sampleRate.toDouble()
                    pcm.write(SpeechText.toPcm16(s)); pcm.write(ByteArray(voice.sampleRate * pauseMs / 1000 * 2))
                }
                val took = (System.currentTimeMillis() - t1) / 1000.0
                val bytes = pcm.toByteArray()
                File(dir, "tts.wav").writeBytes(Wav.build(Wav.Format(1, voice.sampleRate, 16), bytes))
                val sh = java.nio.ByteBuffer.wrap(bytes).order(java.nio.ByteOrder.LITTLE_ENDIAN).asShortBuffer()
                var peak = 0; var sum = 0.0
                while (sh.hasRemaining()) { val v = sh.get().toInt(); peak = maxOf(peak, Math.abs(v)); sum += v.toDouble() * v }
                val n = bytes.size / 2
                log.appendText("Audio ${"%.1f".format(audioSec)} s Sprache in ${"%.1f".format(took)} s Rechenzeit (Echtzeitfaktor ${"%.2f".format(took / audioSec)}), Spitze $peak, Effektivwert ${"%.0f".format(Math.sqrt(sum / n))}\nFERTIG\n")
                voice.close()
            } catch (e: Throwable) { log.appendText("FEHLER: $e\n") }
            runOnUiThread { finish() }
        }.start()
    }
}

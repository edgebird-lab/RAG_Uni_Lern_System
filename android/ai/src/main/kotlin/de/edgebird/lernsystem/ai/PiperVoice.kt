// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ai

import com.k2fsa.sherpa.onnx.OfflineTts
import com.k2fsa.sherpa.onnx.OfflineTtsConfig
import com.k2fsa.sherpa.onnx.OfflineTtsModelConfig
import com.k2fsa.sherpa.onnx.OfflineTtsVitsModelConfig
import java.io.File

/**
 * Offline-Stimme (Piper VITS über sherpa-onnx). Läuft komplett auf dem Gerät und ohne Netz; die Dateien liegen im entpackten Stimmenpaket
 * (`model.onnx`, `tokens.txt`, `espeak-ng-data/`).
 */
class PiperVoice(dir: File, threads: Int = 3, dataDir: File = File(dir, "espeak-ng-data")) : AutoCloseable {
    private val tts = OfflineTts(
        null,
        OfflineTtsConfig(
            model = OfflineTtsModelConfig(
                vits = OfflineTtsVitsModelConfig(
                    model = File(dir, "model.onnx").path, tokens = File(dir, "tokens.txt").path, dataDir = dataDir.path,
                    // etwas ruhiger und gleichmäßiger als die Voreinstellung; Lernstoff soll klar zu verstehen sein
                    noiseScale = 0.6f, noiseScaleW = 0.7f, lengthScale = 1.0f,
                ),
                numThreads = threads, provider = "cpu",
            ),
            silenceScale = 0.2f,
        ),
    )

    val sampleRate: Int get() = tts.sampleRate()

    /** Spricht einen kurzen Text (ein bis zwei Sätze); blockiert, bis das Ergebnis da ist. [speed] 1,0 = normal. */
    fun synthesize(text: String, speed: Float = 1.0f): FloatArray = tts.generate(text, 0, speed).samples

    override fun close() = tts.release()

    companion object {
        /** Ist ein vollständiges Stimmenpaket in [dir] entpackt? */
        fun isInstalled(dir: File) = hasModel(dir) && hasData(File(dir, "espeak-ng-data"))

        /** Modell und Zeichentabelle liegen in [dir] (die espeak-ng-Daten können auch von einer anderen Stimme kommen). */
        fun hasModel(dir: File) = File(dir, "model.onnx").isFile && File(dir, "tokens.txt").isFile
        fun hasData(dataDir: File) = File(dataDir, "phondata").isFile
    }
}

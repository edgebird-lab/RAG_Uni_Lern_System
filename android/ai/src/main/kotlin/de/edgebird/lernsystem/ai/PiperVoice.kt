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
class PiperVoice(dir: File, threads: Int = 3) : AutoCloseable {
    private val tts = OfflineTts(
        null,
        OfflineTtsConfig(
            model = OfflineTtsModelConfig(
                vits = OfflineTtsVitsModelConfig(
                    model = File(dir, "model.onnx").path, tokens = File(dir, "tokens.txt").path, dataDir = File(dir, "espeak-ng-data").path,
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
        fun isInstalled(dir: File) = File(dir, "model.onnx").isFile && File(dir, "tokens.txt").isFile && File(dir, "espeak-ng-data/phondata").isFile
    }
}

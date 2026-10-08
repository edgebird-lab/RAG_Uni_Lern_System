package de.edgebird.lernsystem.ui

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.ai.PiperVoice
import de.edgebird.lernsystem.core.audio.SpeechText
import de.edgebird.lernsystem.core.audio.Wav
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.produce
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.io.File

/** Hält die geladene Offline-Stimme (Piper, ca. 100 MB Arbeitsspeicher) und serialisiert die Zugriffe. */
class VoiceHolder(private val dir: File) {
    private val mutex = Mutex()
    private var voice: PiperVoice? = null

    fun installed() = PiperVoice.isInstalled(dir)

    suspend fun <T> use(block: (PiperVoice) -> T): T = mutex.withLock {
        val v = voice ?: PiperVoice(dir).also { voice = it }
        withContext(Dispatchers.Default) { block(v) }
    }

    /** Gibt die Stimme frei (z. B. nach dem Löschen oder Aktualisieren des Pakets). */
    suspend fun release() = mutex.withLock { voice?.close(); voice = null }
}

/** Öffnet die Seite „KI-Modelle“, wo die Stimme geladen werden kann (von der Navigation gesetzt). */
val LocalOpenModels = compositionLocalOf<() -> Unit> { {} }

/**
 * Vorlesen mit der **Offline-Stimme** der App (Piper über sherpa-onnx): Nichts verlässt das Gerät, es gibt keinen Rückgriff auf Online-Stimmen der
 * System-Sprachausgabe. Fehlt das Stimmenpaket, ist [missingVoice] wahr und die Oberfläche bietet das Laden an.
 */
@Stable
class SpeechOutput internal constructor(private val holder: VoiceHolder, private val scope: CoroutineScope) {
    var speaking by mutableStateOf(false); private set
    var error by mutableStateOf<String?>(null); private set
    var missingVoice by mutableStateOf(false); private set
    private var job: Job? = null
    @Volatile private var track: AudioTrack? = null

    private fun checkVoice(): Boolean {
        error = null
        missingVoice = !holder.installed()
        if (missingVoice) error = "Zum Vorlesen fehlt die Offline-Stimme (ca. 59 MB). Sie wird einmalig unter „KI-Modelle“ geladen und läuft danach ohne Internet."
        return !missingVoice
    }

    /** Liest [markdown] vor (Formatierung wird entfernt, Absätze werden mit Pausen gesprochen). */
    fun speak(markdown: String) {
        stop()
        if (!checkVoice()) return
        val chunks = SpeechText.chunks(SpeechText.prepare(markdown))
        if (chunks.isEmpty()) return
        speaking = true
        job = scope.launch(Dispatchers.Default) {
            try {
                // Der nächste Satz wird schon berechnet, während der vorige spricht
                val ready = produce(capacity = 2) {
                    for ((text, pauseMs) in chunks) { val (pcm, rate) = holder.use { v -> SpeechText.toPcm16(v.synthesize(text)) to v.sampleRate }; send(Triple(pcm, rate, pauseMs)) }
                }
                var frames = 0L
                for ((pcm, rate, pauseMs) in ready) {
                    val t = track ?: newTrack(rate).also { track = it; it.play() }
                    t.write(pcm, 0, pcm.size); frames += pcm.size / 2
                    val silence = ByteArray(rate * pauseMs / 1000 * 2)
                    t.write(silence, 0, silence.size); frames += silence.size / 2
                }
                val t = track
                while (t != null && t.playbackHeadPosition < frames && speaking) delay(100)
            } catch (e: CancellationException) {
                throw e
            } catch (t: Throwable) {
                error = if (t is OutOfMemoryError) "Zu wenig Arbeitsspeicher für die Sprachausgabe. Schließe andere Apps und versuche es erneut." else "Vorlesen ist fehlgeschlagen: ${t.message}"
            } finally {
                releaseTrack(); speaking = false
            }
        }
    }

    private fun newTrack(rate: Int): AudioTrack {
        val min = AudioTrack.getMinBufferSize(rate, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
        return AudioTrack.Builder()
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
            .setAudioFormat(AudioFormat.Builder().setSampleRate(rate).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
            .setBufferSizeInBytes(maxOf(min, rate * 2)).setTransferMode(AudioTrack.MODE_STREAM).build()
    }

    private fun releaseTrack() {
        val t = track ?: return
        track = null
        runCatching { t.pause(); t.flush(); t.release() }
    }

    fun stop() {
        job?.cancel(); job = null
        speaking = false
        releaseTrack()
    }

    /** Erzeugt die Sprachausgabe als WAV (alle Teile mit Pausen). `null`, wenn die Stimme fehlt oder das Erzeugen scheitert. [onProgress]: (erledigt, gesamt). */
    suspend fun renderWav(markdown: String, onProgress: (Int, Int) -> Unit = { _, _ -> }): ByteArray? {
        if (!checkVoice()) return null
        val chunks = SpeechText.chunks(SpeechText.prepare(markdown))
        if (chunks.isEmpty()) return null
        return try {
            val pcm = ByteArrayOutputStream()
            var rate = 22050
            for ((i, c) in chunks.withIndex()) {
                val (data, r) = holder.use { v -> SpeechText.toPcm16(v.synthesize(c.first)) to v.sampleRate }
                rate = r
                pcm.write(data); pcm.write(ByteArray(rate * c.second / 1000 * 2))
                onProgress(i + 1, chunks.size)
            }
            Wav.build(Wav.Format(1, rate, 16), pcm.toByteArray())
        } catch (e: CancellationException) {
            throw e
        } catch (t: Throwable) {
            error = "Das Audio konnte nicht erstellt werden: ${t.message}"; null
        }
    }
}

@Composable
fun rememberSpeechOutput(): SpeechOutput {
    val context: Context = LocalContext.current
    val scope = rememberCoroutineScope()
    val holder = remember { (context.applicationContext as LernsystemApp).graph.voice }
    val s = remember { SpeechOutput(holder, scope) }
    DisposableEffect(s) { onDispose { s.stop() } }
    return s
}

/** Hinweis mit Knopf, wenn die Offline-Stimme noch fehlt. */
@Composable
fun VoiceMissingHint(speaker: SpeechOutput) {
    if (!speaker.missingVoice) return
    val open = LocalOpenModels.current
    androidx.compose.foundation.layout.Column {
        androidx.compose.material3.Text(speaker.error.orEmpty(), style = androidx.compose.material3.MaterialTheme.typography.bodySmall, color = androidx.compose.material3.MaterialTheme.colorScheme.error)
        androidx.compose.material3.TextButton(onClick = open) { androidx.compose.material3.Text("Stimme laden") }
    }
}

package de.edgebird.lernsystem.ui

import de.edgebird.lernsystem.core.i18n.tr

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
import de.edgebird.lernsystem.core.i18n.Lang
import de.edgebird.lernsystem.voice.VoiceEntry
import de.edgebird.lernsystem.voice.VoiceLibrary
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

/** Hält die geladene Offline-Stimme (Piper, ca. 100 MB Arbeitsspeicher) und serialisiert die Zugriffe. Es wird die Stimme der App-Sprache genutzt. */
class VoiceHolder(private val library: VoiceLibrary) {
    private val mutex = Mutex()
    private var voice: PiperVoice? = null
    private var loaded: File? = null

    /** Gibt es eine installierte Stimme für die aktuelle Sprache? */
    fun installed(lang: Lang = Lang.current) = library.selected(lang) != null

    /** Aktuell gewählte Stimme für [lang]. */
    fun selected(lang: Lang = Lang.current) = library.selected(lang)

    /** Führt [block] mit der gewählten Stimme der App-Sprache aus (oder mit [entry], etwa für die Hörprobe). */
    suspend fun <T> use(entry: VoiceEntry? = null, block: (PiperVoice) -> T): T = mutex.withLock {
        val e = entry ?: library.selected() ?: throw IllegalStateException(tr("Keine Stimme installiert", "No voice installed"))
        if (loaded != e.dir) { voice?.close(); voice = null; loaded = null }
        val v = voice ?: PiperVoice(e.dir, dataDir = library.dataDirFor(e)).also { voice = it; loaded = e.dir }
        withContext(Dispatchers.Default) { block(v) }
    }

    /** Gibt die Stimme frei (z. B. nach dem Löschen, Wechseln oder Aktualisieren des Pakets). */
    suspend fun release() = mutex.withLock { voice?.close(); voice = null; loaded = null }
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

    private fun checkVoice(entry: VoiceEntry? = null): Boolean {
        error = null
        missingVoice = entry == null && !holder.installed()
        if (missingVoice) error = tr("Zum Vorlesen fehlt eine deutsche Offline-Stimme (ca. 59 MB). Sie wird einmalig unter „KI-Modelle“ geladen und läuft danach ohne Internet.", "An English offline voice (about 59 MB) is missing for reading aloud. It is downloaded once under “AI models” and then works without internet.")
        return !missingVoice
    }

    /** Liest [markdown] vor (Formatierung wird entfernt, Absätze werden mit Pausen gesprochen). */
    fun speak(markdown: String, entry: VoiceEntry? = null) {
        stop()
        if (!checkVoice(entry)) return
        val chunks = SpeechText.chunks(SpeechText.prepare(markdown))
        if (chunks.isEmpty()) return
        speaking = true
        job = scope.launch(Dispatchers.Default) {
            try {
                // Der nächste Satz wird schon berechnet, während der vorige spricht
                val ready = produce(capacity = 2) {
                    for ((text, pauseMs) in chunks) { val (pcm, rate) = holder.use(entry) { v -> SpeechText.toPcm16(v.synthesize(text)) to v.sampleRate }; send(Triple(pcm, rate, pauseMs)) }
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
                error = if (t is OutOfMemoryError) tr("Zu wenig Arbeitsspeicher für die Sprachausgabe. Schließe andere Apps und versuche es erneut.", "Not enough memory for speech output. Close other apps and try again.") else tr("Vorlesen ist fehlgeschlagen: ${t.message}", "Reading aloud failed: ${t.message}")
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

    /** Hörprobe einer bestimmten Stimme (auch einer anderen Sprache als der der App). */
    fun preview(entry: VoiceEntry) {
        speak(if (entry.lang == Lang.EN) "Hello! This is how I sound when I read your study notes aloud." else "Hallo! So klinge ich, wenn ich dir deine Lernunterlagen vorlese.", entry)
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
            error = tr("Das Audio konnte nicht erstellt werden: ${t.message}", "The audio could not be created: ${t.message}"); null
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
        androidx.compose.material3.TextButton(onClick = open) { androidx.compose.material3.Text(tr("Stimme laden", "Download voice")) }
    }
}

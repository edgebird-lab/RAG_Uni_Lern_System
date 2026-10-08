package de.edgebird.lernsystem.ui

import android.content.Context
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import de.edgebird.lernsystem.core.cards.LatexLite
import de.edgebird.lernsystem.core.summary.MarkdownLite
import java.util.Locale

/** Vorlesen mit der Sprachausgabe des Geräts (deutsche Stimme, bevorzugt ohne Netz). */
@Stable
class SpeechOutput internal constructor(context: Context) {
    var speaking by mutableStateOf(false); private set
    var error by mutableStateOf<String?>(null); private set
    /** Braucht die gewählte Stimme das Internet? Dann geht der vorzulesende Text an den Sprachdienst des Geräteherstellers. */
    var networkVoice by mutableStateOf(false); private set
    private var ready = false
    private var pending: List<String>? = null
    private var remaining = 0
    private val files = java.util.concurrent.ConcurrentHashMap<String, kotlinx.coroutines.CompletableDeferred<Boolean>>()

    private val tts: TextToSpeech = TextToSpeech(context.applicationContext) { status ->
        if (status != TextToSpeech.SUCCESS) { error = "Die Sprachausgabe ist nicht verfügbar."; return@TextToSpeech }
        val r = tts.setLanguage(Locale.GERMAN)
        if (r == TextToSpeech.LANG_MISSING_DATA || r == TextToSpeech.LANG_NOT_SUPPORTED) { error = "Die deutsche Stimme fehlt. Installiere sie in den Android-Einstellungen unter Sprachausgabe."; return@TextToSpeech }
        // lieber eine Stimme, die ohne Internet auskommt
        // Nur Stimmen nehmen, die wirklich installiert sind (sonst bricht das Sprechen sofort ab) und ohne Netz auskommen; sonst bleibt die Standardstimme
        tts.voices?.filter { it.locale.language == "de" && !it.isNetworkConnectionRequired && TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED !in it.features }?.maxByOrNull { it.quality }?.let { tts.voice = it }
        ready = true
        pending?.let { pending = null; start(it) }
    }.also {
        it.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) { speaking = true }
            override fun onDone(utteranceId: String?) { if (utteranceId != null && files.remove(utteranceId)?.complete(true) != null) return; if (--remaining <= 0) speaking = false }
            @Deprecated("Deprecated in Java") override fun onError(utteranceId: String?) { if (utteranceId != null && files.remove(utteranceId)?.complete(false) != null) return; remaining = 0; speaking = false; error = "Vorlesen ist fehlgeschlagen. Ist die deutsche Stimme in den Android-Einstellungen unter Sprachausgabe installiert?" }
        })
    }

    /** Liest [markdown] vor (Formatierung wird entfernt, lange Texte werden in Stücke geteilt). */
    fun speak(markdown: String) {
        error = null
        val plain = LatexLite.toPlain(MarkdownLite.toPlain(markdown)).replace(Regex("""\*+"""), "")
        val chunks = split(plain)
        if (chunks.isEmpty()) return
        if (!ready) { pending = chunks; return }
        start(chunks)
    }

    private fun start(chunks: List<String>) {
        networkVoice = tts.voice?.isNetworkConnectionRequired == true
        tts.stop()
        remaining = chunks.size
        chunks.forEachIndexed { i, c -> tts.speak(c, if (i == 0) TextToSpeech.QUEUE_FLUSH else TextToSpeech.QUEUE_ADD, null, "u$i") }
        speaking = true
    }

    /**
     * Erzeugt die Sprachausgabe als WAV-Datei (alle Teile hintereinander, mit kurzen Pausen). `null`, wenn die Stimme fehlt oder das Erzeugen scheitert.
     * Läuft im Hintergrund der Sprachausgabe; [onProgress] meldet (erledigt, gesamt).
     */
    suspend fun renderWav(markdown: String, cacheDir: java.io.File, onProgress: (Int, Int) -> Unit = { _, _ -> }): ByteArray? {
        var waited = 0
        while (!ready && error == null && waited < 8000) { kotlinx.coroutines.delay(100); waited += 100 }
        if (!ready) return null
        val chunks = split(LatexLite.toPlain(MarkdownLite.toPlain(markdown)).replace(Regex("""\*+"""), ""))
        val parts = mutableListOf<ByteArray>()
        for ((i, c) in chunks.withIndex()) {
            val f = java.io.File.createTempFile("tts", ".wav", cacheDir)
            val id = "f$i-${System.nanoTime()}"
            val done = kotlinx.coroutines.CompletableDeferred<Boolean>().also { files[id] = it }
            if (tts.synthesizeToFile(c, null, f, id) != TextToSpeech.SUCCESS) { files.remove(id); f.delete(); return null }
            val ok = kotlinx.coroutines.withTimeoutOrNull(120_000) { done.await() } ?: false
            if (ok) parts += f.readBytes()
            f.delete()
            onProgress(i + 1, chunks.size)
        }
        return de.edgebird.lernsystem.core.audio.Wav.merge(parts)
    }

    fun stop() { pending = null; tts.stop(); remaining = 0; speaking = false }
    internal fun release() { tts.stop(); tts.shutdown() }

    companion object {
        /** Teilt an Absatz- und Satzgrenzen in Stücke, die in eine Äußerung passen. */
        fun split(text: String, max: Int = 3500): List<String> {
            val out = mutableListOf<String>()
            val cur = StringBuilder()
            for (para in text.split(Regex("""\n\s*\n|\n""")).map { it.trim() }.filter { it.isNotEmpty() }) {
                for (piece in if (para.length <= max) listOf(para) else para.split(Regex("""(?<=[.!?])\s+""")).flatMap { it.chunked(max) }) {
                    if (cur.isNotEmpty() && cur.length + piece.length + 1 > max) { out += cur.toString(); cur.clear() }
                    if (cur.isNotEmpty()) cur.append('\n')
                    cur.append(piece)
                }
            }
            if (cur.isNotEmpty()) out += cur.toString()
            return out
        }
    }
}

@Composable
fun rememberSpeechOutput(): SpeechOutput {
    val context = LocalContext.current
    val s = remember { SpeechOutput(context) }
    DisposableEffect(s) { onDispose { s.release() } }
    return s
}

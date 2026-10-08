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
    private var ready = false
    private var pending: List<String>? = null
    private var remaining = 0

    private val tts: TextToSpeech = TextToSpeech(context.applicationContext) { status ->
        if (status != TextToSpeech.SUCCESS) { error = "Die Sprachausgabe ist nicht verfügbar."; return@TextToSpeech }
        val r = tts.setLanguage(Locale.GERMAN)
        if (r == TextToSpeech.LANG_MISSING_DATA || r == TextToSpeech.LANG_NOT_SUPPORTED) { error = "Die deutsche Stimme fehlt. Installiere sie in den Android-Einstellungen unter Sprachausgabe."; return@TextToSpeech }
        // lieber eine Stimme, die ohne Internet auskommt
        tts.voices?.filter { it.locale.language == "de" && !it.isNetworkConnectionRequired }?.maxByOrNull { it.quality }?.let { tts.voice = it }
        ready = true
        pending?.let { pending = null; start(it) }
    }.also {
        it.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) { speaking = true }
            override fun onDone(utteranceId: String?) { if (--remaining <= 0) speaking = false }
            @Deprecated("Deprecated in Java") override fun onError(utteranceId: String?) { remaining = 0; speaking = false; error = "Vorlesen ist fehlgeschlagen." }
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
        tts.stop()
        remaining = chunks.size
        chunks.forEachIndexed { i, c -> tts.speak(c, if (i == 0) TextToSpeech.QUEUE_FLUSH else TextToSpeech.QUEUE_ADD, null, "u$i") }
        speaking = true
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

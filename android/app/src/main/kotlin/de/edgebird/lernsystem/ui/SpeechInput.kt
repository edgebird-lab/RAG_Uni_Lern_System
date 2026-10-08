package de.edgebird.lernsystem.ui

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat

/**
 * Spracheingabe mit der Erkennung **auf dem Gerät** (kein Audio verlässt das Handy). Steht sie nicht zur Verfügung
 * (kein deutsches Sprachpaket), ist [available] falsch und die Oberfläche blendet das Mikrofon aus.
 */
@Stable
class SpeechController internal constructor(private val context: Context, private val requestPermission: () -> Unit) {
    var listening by mutableStateOf(false); private set
    var error by mutableStateOf<String?>(null); private set
    val available: Boolean = SpeechRecognizer.isOnDeviceRecognitionAvailable(context)

    private var recognizer: SpeechRecognizer? = null
    internal var onPartial: (String) -> Unit = {}
    internal var onFinal: (String) -> Unit = {}

    fun toggle() {
        if (listening) { stop(); return }
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) { requestPermission(); return }
        start()
    }

    internal fun start() {
        if (!available) return
        error = null
        val r = recognizer ?: SpeechRecognizer.createOnDeviceSpeechRecognizer(context).also { recognizer = it }
        r.setRecognitionListener(object : RecognitionListener {
            override fun onResults(results: Bundle?) { listening = false; text(results)?.let(onFinal) }
            override fun onPartialResults(partialResults: Bundle?) { text(partialResults)?.let(onPartial) }
            override fun onError(code: Int) {
                listening = false
                error = when (code) {
                    SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "Nichts verstanden. Tippe auf das Mikrofon und sprich noch einmal."
                    SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED, SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE -> "Das deutsche Sprachpaket fehlt. Lade es in den Android-Einstellungen unter Sprachen und Spracheingabe herunter."
                    SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "Ohne Mikrofon-Erlaubnis geht keine Spracheingabe."
                    else -> "Spracheingabe nicht möglich (Fehler $code)."
                }
            }
            override fun onReadyForSpeech(params: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onEvent(eventType: Int, params: Bundle?) {}
        })
        listening = true
        r.startListening(
            Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "de-DE")
                .putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                .putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true),
        )
    }

    fun stop() { recognizer?.stopListening(); listening = false }

    internal fun release() { recognizer?.destroy(); recognizer = null; listening = false }

    private fun text(b: Bundle?) = b?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.takeIf { it.isNotBlank() }
}

/** [onPartial] liefert den Zwischenstand während des Sprechens, [onFinal] das Ergebnis. */
@Composable
fun rememberSpeech(onPartial: (String) -> Unit, onFinal: (String) -> Unit): SpeechController {
    val context = LocalContext.current
    var controller: SpeechController? = null
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted -> if (granted) controller?.start() }
    val c = remember { SpeechController(context) { launcher.launch(Manifest.permission.RECORD_AUDIO) }.also { controller = it } }
    val partial by rememberUpdatedState(onPartial)
    val final by rememberUpdatedState(onFinal)
    c.onPartial = { partial(it) }
    c.onFinal = { final(it) }
    DisposableEffect(c) { onDispose { c.release() } }
    return c
}

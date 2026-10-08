package de.edgebird.lernsystem.spike

import android.app.Activity
import android.content.Intent
import android.media.MediaPlayer
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognitionSupport
import android.speech.RecognitionSupportCallback
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.view.WindowManager
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Nur Debug: prüft die Spracheingabe Ende zu Ende. Spielt die erzeugten Sprachdateien (files/debug-out/tts-de.wav, tts-en.wav, siehe DebugTtsActivity)
 * über den Lautsprecher ab, während die Erkennung auf dem Gerät mithört. Protokoll: files/debug-out/speech.txt. Braucht die Mikrofon-Berechtigung (adb shell pm grant).
 */
@android.annotation.SuppressLint("NewApi")
class DebugSpeechActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContentView(android.widget.TextView(this).apply { text = "Sprach-Test läuft …"; textSize = 24f; setPadding(48, 200, 48, 48) })
        if (savedInstanceState != null) return
        val log = File(filesDir, "debug-out").apply { mkdirs() }.resolve("speech.txt").also { it.writeText("") }
        log.appendText("onDevice verfügbar: ${SpeechRecognizer.isOnDeviceRecognitionAvailable(this)}, allgemein: ${SpeechRecognizer.isRecognitionAvailable(this)}\n")
        val main = android.os.Handler(mainLooper)
        fun runLang(tag: String, wav: String, done: () -> Unit) {
            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE, tag).putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true).putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
            val r = SpeechRecognizer.createOnDeviceSpeechRecognizer(this)
            r.checkRecognitionSupport(intent, mainExecutor, object : RecognitionSupportCallback {
                override fun onSupportResult(s: RecognitionSupport) {
                    log.appendText("[$tag] installiert=${s.installedOnDeviceLanguages} unterstützt=${s.supportedOnDeviceLanguages} online=${s.onlineLanguages.size}\n")
                    val t0 = System.currentTimeMillis()
                    r.setRecognitionListener(object : RecognitionListener {
                        override fun onResults(b: Bundle?) { log.appendText("[$tag] ERGEBNIS (${System.currentTimeMillis() - t0} ms): ${b?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)}\n"); r.destroy(); done() }
                        override fun onPartialResults(b: Bundle?) { log.appendText("[$tag] teilweise: ${b?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()}\n") }
                        override fun onError(code: Int) { log.appendText("[$tag] FEHLER $code\n"); r.destroy(); done() }
                        override fun onReadyForSpeech(p: Bundle?) {
                            // erst jetzt abspielen, damit der Anfang nicht verloren geht
                            val mp = MediaPlayer().apply { setDataSource(File(filesDir, "debug-out/$wav").path); prepare(); start() }
                            main.postDelayed({ r.stopListening() }, mp.duration.toLong() + 2500)
                        }
                        override fun onBeginningOfSpeech() {}
                        override fun onRmsChanged(rmsdB: Float) {}
                        override fun onBufferReceived(buffer: ByteArray?) {}
                        override fun onEndOfSpeech() {}
                        override fun onEvent(eventType: Int, params: Bundle?) {}
                    })
                    r.startListening(intent)
                }
                override fun onError(error: Int) { log.appendText("[$tag] Unterstützung prüfen FEHLER $error\n"); r.destroy(); done() }
            })
        }
        runLang("en-US", "tts-en.wav") { runLang("de-DE", "tts-de.wav") { log.appendText("FERTIG\n"); finish() } }
    }
}

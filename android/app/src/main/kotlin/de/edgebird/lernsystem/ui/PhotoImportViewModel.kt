package de.edgebird.lernsystem.ui

import de.edgebird.lernsystem.core.i18n.tr

import android.app.Application
import android.net.Uri
import androidx.core.content.FileProvider
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.ingest.OcrText
import de.edgebird.lernsystem.ingest.ImageDecoder
import de.edgebird.lernsystem.ingest.MlKitTextRecognizer
import de.edgebird.lernsystem.ingest.PageScanner
import de.edgebird.lernsystem.work.ImportItem
import de.edgebird.lernsystem.work.ImportWork
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID

/** Schritte beim Import von Fotos: aufnehmen, Text erkennen, prüfen und speichern. */
enum class PhotoStep { CAPTURE, RECOGNIZING, REVIEW }

data class PhotoState(
    val step: PhotoStep = PhotoStep.CAPTURE,
    val pages: List<File> = emptyList(),
    val texts: List<String> = emptyList(),
    val name: String = "",
    val progress: Int = 0,
    val error: String? = null,
    val version: Int = 0,
)

/** Foto-Dokument: mehrere Bilder (Kamera oder Galerie), Texterkennung auf dem Gerät, Korrektur, Import als Quelle. */
class PhotoImportViewModel(app: Application) : AndroidViewModel(app) {
    private val graph = (app as LernsystemApp).graph
    private val dir = File(app.cacheDir, "photos").apply { mkdirs() }
    private var pendingCapture: File? = null
    private var subject: Long? = null
    private var folder: Long? = null

    private val _state = MutableStateFlow(PhotoState(name = defaultName()))
    val state: StateFlow<PhotoState> = _state

    private fun defaultName() = tr("Foto-Notizen ", "Photo notes ") + SimpleDateFormat(tr("d. MMM HH:mm", "MMM d, HH:mm"), de.edgebird.lernsystem.core.i18n.Lang.current.locale).format(Date())

    fun bind(subjectId: Long, folderId: Long? = null) { subject = subjectId; folder = folderId }

    /** Zieldatei für die Kamera-App; sie schreibt das Foto dort hinein. */
    fun newCaptureUri(): Uri {
        val f = File(dir, "p-${UUID.randomUUID()}.jpg").also { pendingCapture = it }
        return FileProvider.getUriForFile(getApplication(), "${getApplication<Application>().packageName}.files", f)
    }

    fun captureDone(ok: Boolean) {
        val f = pendingCapture ?: return
        pendingCapture = null
        if (ok && f.exists() && f.length() > 0) _state.value = _state.value.copy(pages = _state.value.pages + f, error = null) else f.delete()
    }

    fun addFromGallery(uris: List<Uri>) {
        viewModelScope.launch {
            val files = withContext(Dispatchers.IO) {
                uris.mapNotNull { u -> runCatching { File(dir, "p-${UUID.randomUUID()}.jpg").also { f -> getApplication<Application>().contentResolver.openInputStream(u)!!.use { i -> f.outputStream().use { o -> i.copyTo(o) } } } }.getOrNull() }
            }
            _state.value = _state.value.copy(pages = _state.value.pages + files, error = null)
        }
    }

    fun remove(i: Int) {
        val s = _state.value
        s.pages.getOrNull(i)?.delete()
        _state.value = s.copy(pages = s.pages.filterIndexed { idx, _ -> idx != i })
    }

    fun move(i: Int, delta: Int) {
        val s = _state.value
        val j = i + delta
        if (i !in s.pages.indices || j !in s.pages.indices) return
        _state.value = s.copy(pages = s.pages.toMutableList().also { val t = it[i]; it[i] = it[j]; it[j] = t })
    }

    /** Schneidet Seite [i] auf das gewählte Viereck zu und begradigt sie. */
    fun crop(i: Int, corners: List<de.edgebird.lernsystem.core.scan.Pt>) {
        val f = _state.value.pages.getOrNull(i) ?: return
        viewModelScope.launch {
            val ok = withContext(Dispatchers.Default) { PageScanner.crop(f, corners) }
            // neue Version erzwingen, damit die Vorschau neu geladen wird
            _state.value = _state.value.copy(version = _state.value.version + 1, error = if (ok) null else tr("Der Zuschnitt ist fehlgeschlagen.", "Cropping failed."))
        }
    }

    fun setName(n: String) { _state.value = _state.value.copy(name = n.take(80)) }
    fun editText(i: Int, t: String) { _state.value = _state.value.copy(texts = _state.value.texts.toMutableList().also { if (i in it.indices) it[i] = t }) }

    /** Erkennt den Text aller Seiten nacheinander (Modell ist in der App, kein Netz). */
    fun recognize() {
        val pages = _state.value.pages
        if (pages.isEmpty()) return
        _state.value = _state.value.copy(step = PhotoStep.RECOGNIZING, progress = 0, error = null)
        viewModelScope.launch {
            try {
                val texts = withContext(Dispatchers.IO) {
                    MlKitTextRecognizer().use { rec ->
                        pages.mapIndexed { i, f ->
                            val bmp = ImageDecoder.decode({ f.inputStream() })
                            val t = try { de.edgebird.lernsystem.core.ingest.TextNormalizer.normalize(rec.recognize(bmp)) } finally { bmp.recycle() }
                            _state.value = _state.value.copy(progress = i + 1)
                            t
                        }
                    }
                }
                _state.value = _state.value.copy(step = PhotoStep.REVIEW, texts = texts)
            } catch (e: CancellationException) { throw e
            } catch (e: Throwable) {
                _state.value = _state.value.copy(step = PhotoStep.CAPTURE, error = tr("Die Texterkennung ist fehlgeschlagen: ${e.message}", "Text recognition failed: ${e.message}"))
            }
        }
    }

    fun backToCapture() { _state.value = _state.value.copy(step = PhotoStep.CAPTURE) }

    /** Speichert den (korrigierten) Text als Quelle im Fach. Seiten bleiben als Seiten erhalten. */
    fun save(onDone: () -> Unit) {
        val s = _state.value
        val sid = subject ?: return
        if (s.texts.all { it.isBlank() }) { _state.value = s.copy(error = tr("Auf den Fotos wurde kein Text erkannt. Bitte gerader, schärfer und heller aufnehmen.", "No text was recognised in the photos. Please shoot straighter, sharper and brighter.")) ; return }
        viewModelScope.launch {
            val name = s.name.trim().ifEmpty { defaultName() }.let { if (it.endsWith(".txt")) it else "$it.txt" }
            val item = withContext(Dispatchers.IO) {
                val f = File(graph.inboxDir, UUID.randomUUID().toString())
                f.writeText(OcrText.joinPages(s.texts), Charsets.UTF_8)
                // Die Seitenbilder bleiben als PDF erhalten (Ansicht, Teilen, Drucken)
                val pdf = File(graph.inboxDir, "${UUID.randomUUID()}.pdf")
                val ok = runCatching { de.edgebird.lernsystem.ingest.PagesPdf.build(s.pages, pdf) > 0 }.getOrDefault(false)
                ImportItem("photo:${UUID.randomUUID()}", name, f, original = pdf.takeIf { ok })
            }
            ImportWork.enqueue(getApplication(), listOf(item), graph.prefs.getBoolean("embed_only_when_charging", false), sid, folder)
            discard()
            onDone()
        }
    }

    /** Alles verwerfen und die Zwischenbilder löschen. */
    fun discard() {
        _state.value.pages.forEach { it.delete() }
        dir.listFiles()?.forEach { it.delete() }
        _state.value = PhotoState(name = defaultName())
    }
}

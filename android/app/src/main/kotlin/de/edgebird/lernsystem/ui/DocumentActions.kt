package de.edgebird.lernsystem.ui

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.CancellationSignal
import android.os.ParcelFileDescriptor
import android.print.PageRange
import android.print.PrintAttributes
import android.print.PrintDocumentAdapter
import android.print.PrintDocumentInfo
import android.print.PrintManager
import android.util.Base64
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.core.content.FileProvider
import de.edgebird.lernsystem.core.i18n.tr
import de.edgebird.lernsystem.core.summary.MarkdownHtml
import de.edgebird.lernsystem.source.SourceStore
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream

/** Eine Quelle zum Weitergeben: Original (falls vorhanden) und erkannter Text. */
data class SourceFile(val title: String, val ext: String, val original: File?, val text: () -> String)

/** Teilen, Öffnen in anderen Apps, Drucken und Speichern von Quellen. Nichts davon sendet etwas an einen Server; der Nutzer wählt die Ziel-App. */
object DocumentActions {
    private fun uriFor(ctx: Context, f: File): Uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", f)

    private fun safeName(title: String) = title.replace(Regex("[\\\\/:*?\"<>|\\n]"), " ").trim().take(80).ifEmpty { "Quelle" }

    private fun exportDir(ctx: Context) = File(ctx.cacheDir, "export").apply { mkdirs(); listFiles()?.filter { System.currentTimeMillis() - it.lastModified() > 24 * 3600_000L }?.forEach { it.delete() } }

    /** Datei für den Versand: das Original unter dem Titel der Quelle (Kopie im Cache, damit der Empfänger einen sprechenden Dateinamen sieht). */
    private fun exportable(ctx: Context, s: SourceFile, asText: Boolean): File {
        val dir = exportDir(ctx)
        return if (!asText && s.original != null) File(dir, "${safeName(s.title)}.${s.original.extension.ifEmpty { s.ext }}").also { s.original.copyTo(it, overwrite = true) }
        else File(dir, "${safeName(s.title)}.${if (s.ext == "md") "md" else "txt"}").also { it.writeText(s.text(), Charsets.UTF_8) }
    }

    private fun mime(f: File) = SourceStore.mimeFor(f.extension)

    /** Teilen/Weiterleiten: Original als Datei oder (Standard bei Quellen ohne Original) als Textdatei. */
    fun share(ctx: Context, s: SourceFile, asText: Boolean = false) {
        val f = exportable(ctx, s, asText)
        val i = Intent(Intent.ACTION_SEND).setType(mime(f)).putExtra(Intent.EXTRA_STREAM, uriFor(ctx, f)).putExtra(Intent.EXTRA_SUBJECT, s.title).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        ctx.startActivity(Intent.createChooser(i, s.title).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    fun shareMany(ctx: Context, list: List<SourceFile>) {
        if (list.isEmpty()) return
        if (list.size == 1) return share(ctx, list[0])
        val uris = ArrayList(list.map { uriFor(ctx, exportable(ctx, it, false)) })
        val i = Intent(Intent.ACTION_SEND_MULTIPLE).setType("*/*").putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        ctx.startActivity(Intent.createChooser(i, tr("Quellen teilen", "Share sources")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    /** Den Text einer Quelle als reinen Text teilen (zum Einfügen in Nachrichten oder Notizen). */
    fun shareTextOnly(ctx: Context, title: String, text: String) {
        val i = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_SUBJECT, title).putExtra(Intent.EXTRA_TEXT, text.take(200_000))
        ctx.startActivity(Intent.createChooser(i, title).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    /** Öffnen in einer anderen App (PDF-Betrachter, Bildbetrachter). Gibt `false` zurück, wenn keine App das kann. */
    fun openWith(ctx: Context, s: SourceFile): Boolean {
        val f = exportable(ctx, s, false)
        val i = Intent(Intent.ACTION_VIEW).setDataAndType(uriFor(ctx, f), mime(f)).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        return try { ctx.startActivity(i); true } catch (e: android.content.ActivityNotFoundException) { false }
    }

    /** Schreibt Original (oder Text) in die vom Nutzer gewählte Zieldatei („Speichern unter“, auch Download-Ordner). */
    fun saveTo(ctx: Context, uri: Uri, s: SourceFile, asText: Boolean = false): Boolean = runCatching {
        ctx.contentResolver.openOutputStream(uri, "wt")!!.use { out ->
            if (!asText && s.original != null) s.original.inputStream().use { it.copyTo(out) } else out.write(s.text().toByteArray(Charsets.UTF_8))
        }
        true
    }.getOrDefault(false)

    /** Vorgeschlagener Dateiname und Typ für „Speichern unter“. */
    fun suggestedName(s: SourceFile, asText: Boolean = false): String = safeName(s.title) + "." + (if (!asText && s.original != null) s.original.extension.ifEmpty { s.ext } else if (s.ext == "md") "md" else "txt")
    fun suggestedMime(s: SourceFile, asText: Boolean = false): String = if (!asText && s.original != null) SourceStore.mimeFor(s.original.extension) else if (s.ext == "md") "text/markdown" else "text/plain"

    // ---- Drucken --------------------------------------------------------------------------------------------------------

    /** PDF-Datei an den Druckdienst reichen (der Systemdialog bietet auch „Als PDF speichern“). */
    private class PdfFileAdapter(private val file: File, private val name: String) : PrintDocumentAdapter() {
        override fun onLayout(old: PrintAttributes?, new: PrintAttributes?, cancel: CancellationSignal?, callback: LayoutResultCallback, extras: android.os.Bundle?) {
            if (cancel?.isCanceled == true) { callback.onLayoutCancelled(); return }
            callback.onLayoutFinished(PrintDocumentInfo.Builder(name).setContentType(PrintDocumentInfo.CONTENT_TYPE_DOCUMENT).setPageCount(PrintDocumentInfo.PAGE_COUNT_UNKNOWN).build(), true)
        }
        override fun onWrite(pages: Array<out PageRange>?, dest: ParcelFileDescriptor, cancel: CancellationSignal?, callback: WriteResultCallback) {
            try {
                FileInputStream(file).use { i -> FileOutputStream(dest.fileDescriptor).use { o -> i.copyTo(o) } }
                callback.onWriteFinished(arrayOf(PageRange.ALL_PAGES))
            } catch (e: Exception) { callback.onWriteFailed(e.message) }
        }
    }

    // Verhindert, dass die WebView vor dem Ende des Druckauftrags eingesammelt wird
    private var printView: WebView? = null

    /** Druckt die Quelle: PDF direkt, Bilder und Text/Markdown über eine WebView (Zusammenfassungen mit Formatierung). */
    fun print(activity: Activity, s: SourceFile, markdown: Boolean) {
        val pm = activity.getSystemService(Context.PRINT_SERVICE) as PrintManager
        val job = safeName(s.title)
        val o = s.original
        if (o != null && o.extension.equals("pdf", true)) { pm.print(job, PdfFileAdapter(o, job), PrintAttributes.Builder().build()); return }
        val html = if (o != null && o.extension.lowercase() in setOf("jpg", "jpeg", "png", "webp")) {
            "<html><body style=\"margin:0\"><img style=\"max-width:100%\" src=\"data:${mime(o)};base64,${Base64.encodeToString(o.readBytes(), Base64.NO_WRAP)}\"></body></html>"
        } else if (markdown || s.ext == "md") MarkdownHtml.toHtml(s.text(), s.title) else MarkdownHtml.fromPlainText(s.text(), s.title)
        val web = WebView(activity)
        printView = web
        web.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView, url: String?) {
                pm.print(job, view.createPrintDocumentAdapter(job), PrintAttributes.Builder().build())
            }
        }
        web.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
    }
}

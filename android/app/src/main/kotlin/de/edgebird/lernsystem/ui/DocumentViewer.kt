// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ui

import android.app.Activity
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import android.util.LruCache
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import de.edgebird.lernsystem.core.i18n.Lang
import de.edgebird.lernsystem.core.i18n.tr
import de.edgebird.lernsystem.data.ChunkEntity
import de.edgebird.lernsystem.data.DocumentEntity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File
import java.text.DateFormat
import java.util.Date

/** PDF-Datei seitenweise als Bitmaps; Seitenformate werden beim Öffnen gelesen, damit die Liste nicht springt. */
private class PdfDoc(file: File) : AutoCloseable {
    private val pfd = ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
    private val renderer = PdfRenderer(pfd)
    private val lock = Mutex()
    val pageCount = renderer.pageCount
    val ratios: List<Float> = (0 until pageCount).map { i -> renderer.openPage(i).use { it.width.toFloat() / it.height.coerceAtLeast(1) } }

    suspend fun render(index: Int, widthPx: Int): Bitmap = lock.withLock {
        withContext(Dispatchers.IO) {
            renderer.openPage(index).use { p ->
                val w = widthPx.coerceIn(200, 3000); val h = (w / (p.width.toFloat() / p.height)).toInt().coerceAtLeast(1)
                Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888).also { it.eraseColor(android.graphics.Color.WHITE); p.render(it, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY) }
            }
        }
    }

    override fun close() { runCatching { renderer.close(); pfd.close() } }
}

private val HEADER_PREFIX = Regex("^\\[[^\\]]{0,160}]\\n")

/**
 * Ansicht einer Quelle: Original (PDF seitenweise mit Zoom, Bilder) und erkannter Text mit Suche; Zusammenfassungen und Notizen als formatierter Text.
 * Menü: Teilen, Öffnen in anderer App, Drucken, Speichern unter, Info.
 */
@Composable
fun DocumentViewer(documentId: Long, onClose: () -> Unit, startChunk: Int? = null, vm: DocumentViewerViewModel = viewModel(key = "docview$documentId")) {
    LaunchedEffect(documentId) { vm.load(documentId) }
    val data by vm.data.collectAsStateWithLifecycle()
    val context = LocalContext.current
    BackHandler { onClose() }
    val d = data
    if (d == null) { Column(Modifier.padding(16.dp)) { Text(tr("Wird geladen …", "Loading …")); TextButton(onClick = onClose) { Text(tr("Zurück", "Back")) } }; return }

    val doc = d.doc
    val orig = d.original
    val isPdf = orig?.extension.equals("pdf", true)
    val isImage = orig?.extension?.lowercase() in setOf("jpg", "jpeg", "png", "webp")
    val markdownText = d.markdown
    var mode by remember(documentId) { mutableStateOf(if ((isPdf || isImage) && startChunk == null) 0 else 1) }   // 0 Original, 1 Text; ein Sprung zu einer Stelle zeigt den Text
    var menu by remember { mutableStateOf(false) }
    var info by remember { mutableStateOf(false) }
    var notice by remember { mutableStateOf<String?>(null) }
    var saveAsText by remember { mutableStateOf(false) }
    val source = SourceFile(doc.title, if (markdownText != null) "md" else doc.filetype, orig) { d.fullText }
    val saver = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("*/*")) { uri ->
        if (uri != null) notice = if (DocumentActions.saveTo(context, uri, source, saveAsText)) tr("Gespeichert.", "Saved.") else tr("Speichern fehlgeschlagen.", "Saving failed.")
    }
    val activity = context as? Activity

    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp, vertical = 6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onClose) { Text(tr("Zurück", "Back")) }
            Text(doc.title, Modifier.weight(1f), style = MaterialTheme.typography.titleMedium, maxLines = 2)
            androidx.compose.foundation.layout.Box {
                TextButton(onClick = { menu = true }) { Text(tr("Aktionen", "Actions")) }
                DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                    DropdownMenuItem(text = { Text(if (orig != null) tr("Teilen / Weiterleiten …", "Share / forward …") else tr("Als Textdatei teilen …", "Share as text file …")) }, onClick = { menu = false; DocumentActions.share(context, source, asText = orig == null) })
                    if (orig != null) DropdownMenuItem(text = { Text(tr("Text teilen …", "Share text …")) }, onClick = { menu = false; DocumentActions.shareTextOnly(context, doc.title, d.fullText) })
                    if (orig != null && !isNoteLike(doc, orig)) DropdownMenuItem(text = { Text(tr("In anderer App öffnen …", "Open in another app …")) }, onClick = { menu = false; if (!DocumentActions.openWith(context, source)) notice = tr("Keine App zum Öffnen gefunden.", "No app found to open it.") })
                    DropdownMenuItem(text = { Text(tr("Drucken …", "Print …")) }, onClick = { menu = false; activity?.let { DocumentActions.print(it, source, markdown = markdownText != null) } })
                    DropdownMenuItem(text = { Text(if (orig != null) tr("Speichern unter … (Download)", "Save as … (download)") else tr("Als Textdatei speichern …", "Save as text file …")) }, onClick = { menu = false; saveAsText = orig == null; saver.launch(DocumentActions.suggestedName(source, saveAsText)) })
                    if (orig != null) DropdownMenuItem(text = { Text(tr("Text speichern unter …", "Save text as …")) }, onClick = { menu = false; saveAsText = true; saver.launch(DocumentActions.suggestedName(source, true)) })
                    DropdownMenuItem(text = { Text(tr("Info", "Info")) }, onClick = { menu = false; info = true })
                }
            }
        }
        notice?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary) }
        if ((isPdf || isImage) && markdownText == null) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(selected = mode == 0, onClick = { mode = 0 }, label = { Text(tr("Original", "Original")) })
            FilterChip(selected = mode == 1, onClick = { mode = 1 }, label = { Text(tr("Erkannter Text", "Recognised text")) })
        }
        when {
            mode == 0 && isPdf && orig != null -> PdfView(orig)
            mode == 0 && isImage && orig != null -> ImageView(orig)
            markdownText != null -> Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) { MarkdownView(markdownText) }
            else -> TextView(d.chunks, startChunk, doc.status == de.edgebird.lernsystem.data.DocumentStatus.INDEXED)
        }
    }

    if (info) AlertDialog(
        onDismissRequest = { info = false }, title = { Text(tr("Info", "Info")) },
        text = {
            val fmt = DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT, Lang.current.locale)
            val kind = when (doc.kind) { "SUMMARY" -> tr("Zusammenfassung", "Summary"); "NOTE" -> tr("Notiz", "Note"); "PHOTO" -> tr("Foto-Dokument", "Photo document"); else -> doc.filetype.uppercase() }
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(tr("Art: $kind", "Type: $kind"))
                Text(tr("Hinzugefügt: ${fmt.format(Date(doc.addedAt))}", "Added: ${fmt.format(Date(doc.addedAt))}"))
                Text(tr("${d.chunks.size} Abschnitte · ${doc.charCount} Zeichen", "${d.chunks.size} sections · ${doc.charCount} characters"))
                orig?.let { Text(tr("Original: ${it.length() / 1024} KB", "Original: ${it.length() / 1024} KB")) } ?: Text(tr("Kein Original gespeichert (älter importierte Quelle); es gibt den erkannten Text.", "No original stored (source imported earlier); the recognised text is available."))
                d.folderName?.let { Text(tr("Kapitel: $it", "Chapter: $it")) }
            }
        },
        confirmButton = { TextButton(onClick = { info = false }) { Text(tr("Schließen", "Close")) } },
    )
}

private fun isNoteLike(doc: DocumentEntity, orig: File) = doc.kind == "SUMMARY" || doc.kind == "NOTE" || orig.extension.lowercase() in setOf("md", "txt")

@Composable
private fun ColumnScopeFill(content: @Composable () -> Unit) = content()

@Composable
private fun androidx.compose.foundation.layout.ColumnScope.PdfView(file: File) {
    var doc by remember(file) { mutableStateOf<PdfDoc?>(null) }
    var error by remember(file) { mutableStateOf(false) }
    var zoom by remember(file) { mutableStateOf(1f) }
    LaunchedEffect(file) { withContext(Dispatchers.IO) { runCatching { PdfDoc(file) }.onSuccess { doc = it }.onFailure { error = true } } }
    DisposableEffect(file) { onDispose { doc?.close() } }
    if (error) { Text(tr("Das PDF lässt sich nicht anzeigen. Du kannst es in einer anderen App öffnen.", "The PDF cannot be displayed. You can open it in another app."), color = MaterialTheme.colorScheme.error); return }
    val pdf = doc ?: run { Text(tr("Wird geladen …", "Loading …")); return }
    val cache = remember(pdf) { LruCache<String, Bitmap>(6) }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(tr("${pdf.pageCount} S.", "${pdf.pageCount} p."), style = MaterialTheme.typography.bodySmall, maxLines = 1, softWrap = false, modifier = Modifier.weight(1f))
        listOf(1f, 1.5f, 2f, 3f).forEach { z -> FilterChip(selected = zoom == z, onClick = { zoom = z }, label = { Text(if (z == z.toInt().toFloat()) "${z.toInt()}×" else "$z×") }) }
    }
    BoxWithConstraints(Modifier.weight(1f).fillMaxWidth()) {
        val widthDp = maxWidth * zoom
        val widthPx = with(LocalDensity.current) { widthDp.roundToPx() }
        Box2(Modifier.fillMaxSize().then(if (zoom > 1f) Modifier.horizontalScroll(rememberScrollState()) else Modifier)) {
            LazyColumn(Modifier.width(widthDp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                itemsIndexed(List(pdf.pageCount) { it }) { i, _ ->
                    val key = "$i@$widthPx"
                    var bmp by remember(key) { mutableStateOf(cache.get(key)) }
                    LaunchedEffect(key) { if (bmp == null) bmp = runCatching { pdf.render(i, widthPx) }.getOrNull()?.also { cache.put(key, it) } }
                    val b = bmp
                    if (b != null) Image(b.asImageBitmap(), contentDescription = tr("Seite ${i + 1}", "Page ${i + 1}"), contentScale = ContentScale.FillWidth, modifier = Modifier.fillMaxWidth())
                    else androidx.compose.foundation.layout.Box(Modifier.fillMaxWidth().aspectRatio(pdf.ratios[i]).background(Color.White.copy(alpha = 0.9f)))
                }
            }
        }
    }
}

@Composable
private fun Box2(modifier: Modifier, content: @Composable () -> Unit) = androidx.compose.foundation.layout.Box(modifier) { content() }

@Composable
private fun androidx.compose.foundation.layout.ColumnScope.ImageView(file: File) {
    val bmp = remember(file) { runCatching { de.edgebird.lernsystem.ingest.ImageDecoder.decode({ file.inputStream() }) }.getOrNull() }
    if (bmp == null) { Text(tr("Das Bild lässt sich nicht anzeigen.", "The image cannot be displayed."), color = MaterialTheme.colorScheme.error); return }
    Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) { Image(bmp.asImageBitmap(), contentDescription = null, contentScale = ContentScale.FillWidth, modifier = Modifier.fillMaxWidth()) }
}

@Composable
private fun androidx.compose.foundation.layout.ColumnScope.TextView(chunks: List<ChunkEntity>, startChunk: Int?, indexed: Boolean) {
    var query by remember { mutableStateOf("") }
    val state = rememberLazyListState()
    val q = query.trim()
    val shown = remember(chunks, q) { chunks.filter { q.isEmpty() || it.text.contains(q, ignoreCase = true) } }
    LaunchedEffect(startChunk, chunks.size) { if (startChunk != null && q.isEmpty()) chunks.indexOfFirst { it.idx == startChunk }.takeIf { it >= 0 }?.let { state.scrollToItem(it + 1) } }
    OutlinedTextField(value = query, onValueChange = { query = it }, singleLine = true, label = { Text(tr("Im Text suchen", "Search in text")) }, modifier = Modifier.fillMaxWidth())
    if (q.isNotEmpty()) Text(tr("${shown.size} Abschnitte mit „$q“", "${shown.size} sections containing “$q”"), style = MaterialTheme.typography.bodySmall)
    if (chunks.isEmpty()) Text(if (indexed) tr("Kein Text.", "No text.") else tr("Wird noch indexiert …", "Still being indexed …"), style = MaterialTheme.typography.bodyMedium)
    LazyColumn(Modifier.weight(1f), state = state, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { androidx.compose.foundation.layout.Spacer(Modifier.padding(0.dp)) }
        itemsIndexed(shown, key = { _, c -> c.id }) { _, c ->
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(c.location, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
                val body = HEADER_PREFIX.replace(c.text, "")
                Text(highlight(body, q), style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

private fun highlight(text: String, q: String): androidx.compose.ui.text.AnnotatedString = buildAnnotatedString {
    if (q.isEmpty()) { append(text); return@buildAnnotatedString }
    var pos = 0
    while (true) {
        val i = text.indexOf(q, pos, ignoreCase = true)
        if (i < 0) { append(text.substring(pos)); break }
        append(text.substring(pos, i))
        withStyle(SpanStyle(background = Color(0xFFFFE082), color = Color.Black)) { append(text.substring(i, i + q.length)) }
        pos = i + q.length
    }
}

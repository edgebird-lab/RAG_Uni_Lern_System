package de.edgebird.lernsystem.ui

import android.content.Intent
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import de.edgebird.lernsystem.core.summary.MarkdownLite
import de.edgebird.lernsystem.core.summary.SummaryStyle
import java.text.DateFormat
import java.util.Date

@Composable
fun SummaryScreen(documentId: Long, onBack: () -> Unit, vm: SummaryViewModel = viewModel()) {
    val title by vm.title.collectAsStateWithLifecycle()
    val style by vm.style.collectAsStateWithLifecycle()
    val summary by vm.summary.collectAsStateWithLifecycle()
    val job by vm.job.collectAsStateWithLifecycle()
    val sections by vm.sectionCount.collectAsStateWithLifecycle()
    val context = LocalContext.current
    LaunchedEffect(documentId) { vm.open(documentId) }
    BackHandler(onBack = onBack)

    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            TextButton(onClick = onBack) { Text("Zurück") }
            Text(title, Modifier.weight(1f), style = MaterialTheme.typography.titleLarge, maxLines = 1)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            SummaryStyle.entries.forEach { s -> FilterChip(selected = s == style, onClick = { vm.select(s) }, label = { Text(s.label) }) }
        }
        Text(style.description, style = MaterialTheme.typography.bodySmall)

        if (job.running) {
            Column {
                Text(if (job.total > 0) "Abschnitt ${job.done} von ${job.total}" else "Wird gestartet …")
                if (job.total > 0) LinearProgressIndicator(progress = { job.done.toFloat() / job.total }, modifier = Modifier.fillMaxWidth())
                Text("Das Display sollte dabei an bleiben. Du kannst die App wechseln, die Erzeugung läuft weiter.", style = MaterialTheme.typography.bodySmall)
            }
        }
        job.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }

        val s = summary
        if (s == null) {
            if (!job.running) {
                // Gemessen auf dem Pixel 9 Pro XL: ca. 12 s je Abschnitt (Stichpunkte, Kurzfassung) bzw. 23 s (Gegliedert), Kurzfassung +1 Minute
                val minutes = (sections * (if (style == SummaryStyle.OUTLINE) 23 else 12) + (if (style == SummaryStyle.SHORT) 60 else 0)) / 60.0
                Text(
                    if (sections > 0) "Dein Dokument hat etwa $sections Abschnitte. Die Erstellung dauert ungefähr ${"%.0f".format(minutes.coerceAtLeast(1.0))} Minute(n)." else "Das Dokument hat keinen Text.",
                    style = MaterialTheme.typography.bodyMedium,
                )
                Button(onClick = { vm.create(restart = false) }, enabled = sections > 0, modifier = Modifier.fillMaxWidth()) { Text("Zusammenfassung erstellen") }
                job.message?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
            }
        } else {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = {
                    val send = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, MarkdownLite.toPlain(s.text))
                    context.startActivity(Intent.createChooser(send, "Zusammenfassung teilen"))
                }) { Text("Teilen") }
                OutlinedButton(onClick = { vm.create(restart = true) }, enabled = !job.running) { Text("Neu erstellen") }
            }
            val date = DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT).format(Date(s.createdAt))
            Text(
                "Erstellt am $date mit ${s.model}: ${s.sectionsUsed} Abschnitte" + if (s.sectionsSkipped > 0) ", ${s.sectionsSkipped} übersprungen" else "",
                style = MaterialTheme.typography.labelSmall,
            )
            if (s.warnings > 0) {
                Text(
                    "Hinweis: In ${s.warnings} Abschnitt(en) stehen Zahlen, die im Dokument nicht gefunden wurden. Bitte mit dem Original abgleichen.",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error,
                )
            }
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                MarkdownView(s.text)
            }
        }
    }
}

/** Zeigt den kleinen Markdown-Ausschnitt der Zusammenfassungen (Überschriften, Listen, fett). */
@Composable
fun MarkdownView(markdown: String) {
    val blocks = MarkdownLite.parse(markdown)
    blocks.forEach { b ->
        when (b) {
            is MarkdownLite.Block.Heading -> Text(
                inline(b.text), modifier = Modifier.padding(top = if (b.level <= 2) 8.dp else 4.dp),
                style = when (b.level) { 1 -> MaterialTheme.typography.titleLarge; 2 -> MaterialTheme.typography.titleMedium; else -> MaterialTheme.typography.titleSmall },
            )
            is MarkdownLite.Block.Bullet -> Text(inline("•  ${b.text}"), Modifier.padding(start = (8 + 16 * b.indent).dp), style = MaterialTheme.typography.bodyMedium)
            is MarkdownLite.Block.Paragraph -> Text(inline(b.text), style = MaterialTheme.typography.bodyMedium)
        }
    }
}

private fun inline(text: String): AnnotatedString = buildAnnotatedString {
    MarkdownLite.spans(de.edgebird.lernsystem.core.cards.LatexLite.toPlain(text)).forEach { span ->
        when {
            span.bold -> withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(span.text) }
            span.italic -> withStyle(SpanStyle(fontStyle = androidx.compose.ui.text.font.FontStyle.Italic)) { append(span.text) }
            else -> append(span.text)
        }
    }
}

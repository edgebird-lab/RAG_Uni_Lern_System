package de.edgebird.lernsystem.ui

import de.edgebird.lernsystem.core.i18n.tr

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import de.edgebird.lernsystem.core.summary.MarkdownLite
import de.edgebird.lernsystem.core.summary.SummaryFormat
import de.edgebird.lernsystem.core.summary.SummaryLanguage
import de.edgebird.lernsystem.core.summary.SummaryLevel
import de.edgebird.lernsystem.core.summary.SummaryRole
import de.edgebird.lernsystem.core.summary.SummarySpec
import de.edgebird.lernsystem.data.DocumentStatus
import de.edgebird.lernsystem.data.GeneratedSummaryEntity
import de.edgebird.lernsystem.data.SummaryScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.DateFormat
import java.util.Date

/** Bereich „Studio“: Zusammenfassungen eines Dokuments, mehrerer Quellen (ganzes Fach) oder eines Themas, mit allen Einstellungen. */
@Composable
fun StudioScreen(subjectId: Long, vm: StudioViewModel = viewModel(key = "studio$subjectId"), docsVm: DocumentsViewModel = viewModel(key = "docs$subjectId")) {
    LaunchedEffect(subjectId) { vm.bind(subjectId); docsVm.bind(subjectId) }
    var openId by rememberSaveable { mutableStateOf<Long?>(null) }
    openId?.let { id ->
        BackHandler { openId = null }
        SummaryViewer(id, vm, onBack = { openId = null })
        return
    }
    val results by vm.results.collectAsStateWithLifecycle()
    val stale by vm.stale.collectAsStateWithLifecycle()
    val jobs by vm.jobs.collectAsStateWithLifecycle()
    val docs by docsVm.documents.collectAsStateWithLifecycle()
    val selected by docsVm.selectedIds.collectAsStateWithLifecycle()

    LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { Text(tr("Studio", "Studio"), style = MaterialTheme.typography.headlineMedium) }
        item { Composer(vm, docs.filter { it.document.status == DocumentStatus.INDEXED }, selected) }
        if (jobs.running.isNotEmpty() || jobs.failed.isNotEmpty()) item { JobsCard(jobs, vm) }
        item { Text(tr("Meine Zusammenfassungen", "My summaries"), style = MaterialTheme.typography.titleMedium) }
        if (results.isEmpty()) item { Text(tr("Noch keine. Wähle oben Umfang, Format und Länge und tippe auf „Zusammenfassung erstellen“.", "None yet. Choose scope, format and length above and tap “Create summary”."), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        items(results, key = { it.id }) { r -> ResultCard(r, r.id in stale) { openId = r.id } }
    }
}

@OptIn(ExperimentalLayoutApi::class, androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
private fun Composer(vm: StudioViewModel, docs: List<de.edgebird.lernsystem.data.DocumentSummary>, selected: Set<Long>) {
    val spec by vm.spec.collectAsStateWithLifecycle()
    val templates by vm.templates.collectAsStateWithLifecycle()
    var scope by rememberSaveable { mutableStateOf(SummaryScope.DOC) }
    var docId by rememberSaveable { mutableStateOf<Long?>(null) }
    var topic by rememberSaveable { mutableStateOf("") }
    var advanced by rememberSaveable { mutableStateOf(false) }
    var saving by remember { mutableStateOf(false) }
    var docMenu by remember { mutableStateOf(false) }
    var tplMenu by remember { mutableStateOf(false) }

    val currentDoc = docs.firstOrNull { it.document.id == docId } ?: docs.firstOrNull()
    val docIds: List<Long> = when (scope) {
        SummaryScope.DOC -> listOfNotNull(currentDoc?.document?.id)
        else -> docs.map { it.document.id }.filter { it in selected }
    }
    val estimate by produceState<Estimate?>(null, scope, docIds, topic, spec) { value = vm.estimate(scope, docIds, topic, spec) }
    val canStart = docIds.isNotEmpty() && (scope != SummaryScope.TOPIC || topic.isNotBlank())

    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(tr("Neue Zusammenfassung", "New summary"), style = MaterialTheme.typography.titleMedium)

            // 1. Umfang
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                listOf(SummaryScope.DOC to tr("Quelle", "Source"), SummaryScope.SUBJECT to tr("Fach", "Subject"), SummaryScope.TOPIC to tr("Thema", "Topic")).forEachIndexed { i, (s, label) ->
                    SegmentedButton(selected = scope == s, onClick = { scope = s }, shape = SegmentedButtonDefaults.itemShape(i, 3), icon = {}) { Text(label, maxLines = 1, softWrap = false, style = MaterialTheme.typography.labelLarge) }
                }
            }
            when (scope) {
                SummaryScope.DOC -> Column {
                    OutlinedButton(onClick = { docMenu = true }, modifier = Modifier.fillMaxWidth(), enabled = docs.isNotEmpty()) { Text(currentDoc?.document?.title ?: tr("Keine fertige Quelle", "No finished source")) }
                    DropdownMenu(expanded = docMenu, onDismissRequest = { docMenu = false }) {
                        docs.forEach { d -> DropdownMenuItem(text = { Text(d.document.title) }, onClick = { docId = d.document.id; docMenu = false }) }
                    }
                }
                SummaryScope.SUBJECT -> Text(tr("Alle angehakten Quellen (${docIds.size}). Unter „Quellen“ kannst du die Auswahl ändern.", "All checked sources (${docIds.size}). You can change the selection under “Sources”."), style = MaterialTheme.typography.bodySmall)
                SummaryScope.TOPIC -> {
                    OutlinedTextField(value = topic, onValueChange = { topic = it.take(100) }, label = { Text(tr("Thema oder Unterpunkt", "Topic or subtopic")) }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    Text(tr("Es werden nur die dazu passenden Stellen der angehakten Quellen (${docIds.size}) zusammengefasst.", "Only the matching passages of the checked sources (${docIds.size}) are summarised."), style = MaterialTheme.typography.bodySmall)
                }
            }

            // 2. Format
            Text(tr("Form", "Format"), style = MaterialTheme.typography.labelLarge)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SummaryFormat.entries.forEach { f -> FilterChip(selected = spec.format == f, onClick = { vm.edit { it.copy(format = f) } }, label = { Text(f.label) }) }
            }
            Text(spec.format.description, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)

            // 3. Länge
            var slider by remember(spec.targetWords) { mutableStateOf(spec.targetWords.toFloat()) }
            Text(tr("Länge: ca. ${(slider / 25).toInt() * 25} Wörter", "Length: about ${(slider / 25).toInt() * 25} words"), style = MaterialTheme.typography.labelLarge)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(tr("Kurz", "Short") to 150, tr("Mittel", "Medium") to 400, tr("Ausführlich", "Detailed") to 900).forEach { (l, w) -> FilterChip(selected = spec.targetWords == w, onClick = { vm.edit { it.copy(targetWords = w) } }, label = { Text(l) }) }
            }
            // Erst beim Loslassen übernehmen: Der Aufwand wird neu berechnet und die Einstellung gespeichert
            Slider(value = slider, onValueChange = { slider = it }, onValueChangeFinished = { vm.edit { it.copy(targetWords = (slider / 25).toInt() * 25) } }, valueRange = SummarySpec.MIN_TARGET.toFloat()..SummarySpec.MAX_TARGET.toFloat())
            if (spec.format != SummaryFormat.PROSE && scope != SummaryScope.TOPIC) Text(tr("Bei strukturierten Formen verteilt sich die Länge auf die Abschnitte der Quelle.", "With structured formats the length is spread over the sections of the source."), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)

            // 4. Weitere Einstellungen
            TextButton(onClick = { advanced = !advanced }) { Text(if (advanced) tr("Weniger Einstellungen ▲", "Fewer settings ▲") else tr("Weitere Einstellungen ▼", "More settings ▼")) }
            if (advanced) Advanced(spec, vm)

            // 5. Vorlagen
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Column {
                    OutlinedButton(onClick = { tplMenu = true }) { Text(tr("Vorlage laden", "Load template")) }
                    DropdownMenu(expanded = tplMenu, onDismissRequest = { tplMenu = false }) {
                        SummarySpec.PRESETS.forEach { (n, s) -> DropdownMenuItem(text = { Text(n) }, onClick = { vm.edit { s }; tplMenu = false }) }
                        templates.forEach { (n, s) ->
                            DropdownMenuItem(text = { Text(tr("$n  (eigene)", "$n  (own)")) }, onClick = { vm.edit { s }; tplMenu = false }, trailingIcon = { TextButton(onClick = { vm.deleteTemplate(n) }) { Text(tr("Löschen", "Delete")) } })
                        }
                    }
                }
                OutlinedButton(onClick = { saving = true }) { Text(tr("Als Vorlage speichern", "Save as template"), maxLines = 1) }
            }

            // 6. Start
            estimate?.let {
                Text(tr("Etwa ${it.words} Wörter, ${it.steps} Schritte, ungefähr ${it.minutes} Minute(n) auf diesem Gerät. Das Display sollte dabei an bleiben.", "About ${it.words} words, ${it.steps} steps, roughly ${it.minutes} minute(s) on this device. The display should stay on."), style = MaterialTheme.typography.bodySmall)
                if (it.words > spec.targetWords * 1.3) Text(tr("Die Quelle ist so groß, dass jeder Abschnitt mindestens ein paar Zeilen braucht. Für ein kürzeres Ergebnis wähle „Fließtext“.", "The source is so large that every section needs at least a few lines. For a shorter result choose “Running text”."), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.secondary)
            }
            if (docIds.isEmpty()) Text(if (scope == SummaryScope.DOC) tr("Diese Quelle ist noch nicht fertig indexiert.", "This source has not finished indexing yet.") else tr("Keine Quelle angehakt. Hake unter „Quellen“ mindestens eine an.", "No source checked. Check at least one under “Sources”."), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
            Button(
                onClick = {
                    val label = when (scope) { SummaryScope.DOC -> currentDoc?.document?.title.orEmpty(); SummaryScope.SUBJECT -> tr("Ganzes Fach", "Whole subject"); SummaryScope.TOPIC -> tr("Thema: ${topic.trim()}", "Topic: ${topic.trim()}") } + " · " + spec.format.label
                    vm.create(scope, docIds, topic, label)
                },
                enabled = canStart, modifier = Modifier.fillMaxWidth(),
            ) { Text(tr("Zusammenfassung erstellen", "Create summary")) }
        }
    }
    if (saving) {
        var name by remember { mutableStateOf("") }
        AlertDialog(
            onDismissRequest = { saving = false }, title = { Text(tr("Vorlage speichern", "Save template")) },
            text = { OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text(tr("Name der Vorlage", "Name of the template")) }, singleLine = true) },
            confirmButton = { TextButton(onClick = { vm.saveTemplate(name); saving = false }, enabled = name.isNotBlank()) { Text(tr("Speichern", "Save")) } },
            dismissButton = { TextButton(onClick = { saving = false }) { Text(tr("Abbrechen", "Cancel")) } },
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Advanced(spec: SummarySpec, vm: StudioViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(tr("Rolle der KI", "Role of the AI"), style = MaterialTheme.typography.labelLarge)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            SummaryRole.entries.forEach { r -> FilterChip(selected = spec.role == r && spec.customRole.isBlank(), onClick = { vm.edit { it.copy(role = r, customRole = "") } }, label = { Text(r.label) }) }
        }
        OutlinedTextField(
            value = spec.roleText, onValueChange = { t -> vm.edit { it.copy(customRole = if (t == it.role.prompt) "" else t) } },
            label = { Text(tr("Masterprompt (Rolle und Ton)", "Master prompt (role and tone)")) }, minLines = 2, maxLines = 6, modifier = Modifier.fillMaxWidth(),
            supportingText = { Text(tr("Hier kannst du die Rolle selbst formulieren. Die Regel „nichts erfinden, nur den Quelltext nutzen“ gilt immer zusätzlich.", "Here you can word the role yourself. The rule “invent nothing, use only the source text” always applies in addition.")) },
        )
        if (spec.customRole.isNotBlank()) TextButton(onClick = { vm.edit { it.copy(customRole = "") } }) { Text(tr("Masterprompt zurücksetzen", "Reset master prompt")) }
        OutlinedTextField(
            value = spec.extra, onValueChange = { t -> vm.edit { it.copy(extra = t.take(400)) } },
            label = { Text(tr("Zusätzliche Wünsche", "Additional wishes")) }, placeholder = { Text(tr("z. B. „Fasse nur das Wesentliche zusammen“ oder „Mit Merksätzen“", "e.g. “Summarise only the essentials” or “With key takeaways”")) },
            minLines = 2, maxLines = 4, modifier = Modifier.fillMaxWidth(),
        )
        Text(tr("Niveau", "Level"), style = MaterialTheme.typography.labelLarge)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) { SummaryLevel.entries.forEach { l -> FilterChip(selected = spec.level == l, onClick = { vm.edit { it.copy(level = l) } }, label = { Text(l.label) }) } }
        Text(tr("Sprache der Zusammenfassung", "Language of the summary"), style = MaterialTheme.typography.labelLarge)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) { SummaryLanguage.entries.forEach { l -> FilterChip(selected = spec.language == l, onClick = { vm.edit { it.copy(language = l) } }, label = { Text(l.label) }) } }
        Toggle(tr("Formeln und Regeln übernehmen", "Keep formulas and rules"), spec.keepFormulas) { v -> vm.edit { it.copy(keepFormulas = v) } }
        Toggle(tr("Beispiele einbeziehen", "Include examples"), spec.includeExamples) { v -> vm.edit { it.copy(includeExamples = v) } }
        Toggle(tr("Wichtige Begriffe fett", "Important terms in bold"), spec.boldTerms) { v -> vm.edit { it.copy(boldTerms = v) } }
        Toggle(tr("Fundstellen angeben (Seite, Folie)", "Give locations (page, slide)"), spec.cite) { v -> vm.edit { it.copy(cite = v) } }
        Toggle(tr("Prüfungsfokus (was wird abgefragt?)", "Exam focus (what is asked?)"), spec.examFocus) { v -> vm.edit { it.copy(examFocus = v) } }
    }
}

@Composable
private fun Toggle(label: String, checked: Boolean, onChange: (Boolean) -> Unit) = Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
    Text(label, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
    Switch(checked = checked, onCheckedChange = onChange)
}

@Composable
private fun JobsCard(jobs: JobsState, vm: StudioViewModel) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            jobs.running.forEach { j ->
                Column {
                    Text(j.label, style = MaterialTheme.typography.titleSmall)
                    if (j.queued) Text(tr("Wartet …", "Waiting …"), style = MaterialTheme.typography.bodySmall)
                    else {
                        Text(if (j.total > 0) tr("Schritt ${j.done} von ${j.total}", "Step ${j.done} of ${j.total}") else tr("Startet …", "Starting …"), style = MaterialTheme.typography.bodySmall)
                        if (j.total > 0) LinearProgressIndicator(progress = { j.done.toFloat() / j.total }, modifier = Modifier.fillMaxWidth())
                    }
                }
            }
            if (jobs.running.isNotEmpty()) Text(tr("Du kannst die App wechseln, die Erstellung läuft weiter. Das Display sollte an bleiben.", "You can switch apps; the creation continues. The display should stay on."), style = MaterialTheme.typography.bodySmall)
            if (jobs.running.isNotEmpty()) TextButton(onClick = vm::cancelAll) { Text(tr("Abbrechen (Fortschritt bleibt erhalten)", "Cancel (progress is kept)")) }
            jobs.failed.forEach { f -> Text(tr("${f.label}: ${f.message}", "${f.label}: ${f.message}"), color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
            if (jobs.failed.isNotEmpty()) TextButton(onClick = vm::dismissFailed) { Text(tr("Meldung schließen", "Dismiss message")) }
        }
    }
}

@Composable
private fun ResultCard(r: GeneratedSummaryEntity, stale: Boolean, onOpen: () -> Unit) {
    val spec = SummarySpec.fromJson(r.specJson)
    val date = DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT, de.edgebird.lernsystem.core.i18n.Lang.current.locale).format(Date(r.createdAt))
    Card(onClick = onOpen, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(r.title, style = MaterialTheme.typography.titleMedium)
            val scopeText = when (SummaryScope.valueOf(r.scope)) { SummaryScope.DOC -> tr("Eine Quelle", "One source"); SummaryScope.SUBJECT -> tr("${r.docIdList.size} Quellen", "${r.docIdList.size} sources"); SummaryScope.TOPIC -> tr("Thema", "Topic") }
            Text("$scopeText · ${spec.format.label} · " + tr("ca. ${MarkdownLite.toPlain(r.text).split(Regex("\\s+")).size} Wörter", "about ${MarkdownLite.toPlain(r.text).split(Regex("\\s+")).size} words") + " · $date", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (stale) Text(tr("Veraltet: Eine Quelle hat sich geändert. Öffne die Zusammenfassung und erstelle sie neu.", "Outdated: a source has changed. Open the summary and recreate it."), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
        }
    }
}

/** Anzeige einer Zusammenfassung mit Teilen, Kopieren, Vorlesen, Neu erstellen, Umbenennen und Löschen. */
@Composable
private fun SummaryViewer(id: Long, vm: StudioViewModel, onBack: () -> Unit) {
    val s by remember(id) { vm.observe(id) }.collectAsStateWithLifecycle(null)
    val stale by vm.stale.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val speaker = rememberSpeechOutput()
    var renaming by remember { mutableStateOf(false) }
    var deleting by remember { mutableStateOf(false) }
    var audioStatus by remember { mutableStateOf<String?>(null) }
    val scope = androidx.compose.runtime.rememberCoroutineScope()
    val saveAudio = androidx.activity.compose.rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.CreateDocument("audio/x-wav")) { uri ->
        val text = s?.text
        if (uri != null && text != null) scope.launch {
            audioStatus = tr("Audio wird erstellt …", "Creating audio …")
            val bytes = speaker.renderWav(text) { d, t -> audioStatus = tr("Audio wird erstellt: $d von $t", "Creating audio: $d of $t") }
            audioStatus = if (bytes == null) tr("Das Audio konnte nicht erstellt werden.", "The audio could not be created.") else {
                withContext(kotlinx.coroutines.Dispatchers.IO) { context.contentResolver.openOutputStream(uri)?.use { it.write(bytes) } }
                tr("Audio gespeichert (${maxOf(1, bytes.size / 1_048_576)} MB)", "Audio saved (${maxOf(1, bytes.size / 1_048_576)} MB)")
            }
        }
    }
    val r = s
    if (r == null) { Column(Modifier.padding(16.dp)) { Text(tr("Wird geladen …", "Loading …")); TextButton(onClick = onBack) { Text(tr("Zurück", "Back")) } }; return }

    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack) { Text(tr("Zurück", "Back")) }
            Text(r.title, Modifier.weight(1f), style = MaterialTheme.typography.titleMedium, maxLines = 2)
        }
        val spec = SummarySpec.fromJson(r.specJson)
        FlowRow2 {
            OutlinedButton(onClick = {
                context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, MarkdownLite.toPlain(r.text)), tr("Zusammenfassung teilen", "Share summary")))
            }) { Text(tr("Teilen", "Share")) }
            OutlinedButton(onClick = { (context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText(tr("Zusammenfassung", "Summary"), MarkdownLite.toPlain(r.text))) }) { Text(tr("Kopieren", "Copy")) }
            OutlinedButton(onClick = { if (speaker.speaking) speaker.stop() else speaker.speak(r.text) }) { Text(if (speaker.speaking) tr("Stopp", "Stop") else tr("Vorlesen", "Read aloud")) }
            OutlinedButton(onClick = { saveAudio.launch(r.title.take(40).replace(Regex("[^A-Za-z0-9äöüÄÖÜß _-]"), "") + ".wav") }, enabled = audioStatus?.startsWith(tr("Audio wird", "Creating audio")) != true) { Text(tr("Als Audio speichern", "Save as audio")) }
            OutlinedButton(onClick = { vm.rerun(r, r.title); onBack() }) { Text(tr("Neu erstellen", "Recreate")) }
            OutlinedButton(onClick = { vm.adopt(r) }) { Text(tr("Einstellungen übernehmen", "Apply settings")) }
            OutlinedButton(onClick = { vm.saveAsSource(r); android.widget.Toast.makeText(context, tr("Als Quelle gespeichert (unter „Quellen“)", "Saved as a source (under “Sources”)"), android.widget.Toast.LENGTH_SHORT).show() }) { Text(tr("Als Quelle speichern", "Save as source")) }
            OutlinedButton(onClick = { renaming = true }) { Text(tr("Umbenennen", "Rename")) }
            OutlinedButton(onClick = { deleting = true }) { Text(tr("Löschen", "Delete")) }
        }
        VoiceMissingHint(speaker)
        if (!speaker.missingVoice) speaker.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
        audioStatus?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
        val date = DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT, de.edgebird.lernsystem.core.i18n.Lang.current.locale).format(Date(r.createdAt))
        Text(tr("Erstellt am $date mit ${r.model}: ${r.sectionsUsed} Abschnitte", "Created on $date with ${r.model}: ${r.sectionsUsed} sections") + (if (r.sectionsSkipped > 0) tr(", ${r.sectionsSkipped} übersprungen", ", ${r.sectionsSkipped} skipped") else "") + " · ${spec.role.label}${if (spec.customRole.isNotBlank()) tr(" (eigener Prompt)", " (own prompt)") else ""}", style = MaterialTheme.typography.labelSmall)
        if (id in stale) Text(tr("Veraltet: Eine Quelle hat sich seit der Erstellung geändert. Mit „Neu erstellen“ aktualisieren.", "Outdated: a source has changed since creation. Update with “Recreate”."), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
        if (r.warnings > 0) Text(tr("Hinweis: In ${r.warnings} Abschnitt(en) stehen Zahlen, die im Dokument nicht gefunden wurden. Bitte mit dem Original abgleichen.", "Note: in ${r.warnings} section(s) there are numbers that were not found in the document. Please compare with the original."), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) { MarkdownView(r.text) }
    }
    if (renaming) {
        var name by remember { mutableStateOf(r.title) }
        AlertDialog(
            onDismissRequest = { renaming = false }, title = { Text(tr("Umbenennen", "Rename")) },
            text = { OutlinedTextField(value = name, onValueChange = { name = it.take(120) }, singleLine = true, modifier = Modifier.fillMaxWidth()) },
            confirmButton = { TextButton(onClick = { vm.rename(r.id, name); renaming = false }, enabled = name.isNotBlank()) { Text(tr("Speichern", "Save")) } },
            dismissButton = { TextButton(onClick = { renaming = false }) { Text(tr("Abbrechen", "Cancel")) } },
        )
    }
    if (deleting) AlertDialog(
        onDismissRequest = { deleting = false }, title = { Text(tr("Zusammenfassung löschen?", "Delete summary?")) }, text = { Text(tr("„${r.title}“ wird gelöscht. Die Quellen bleiben unberührt.", "“${r.title}” will be deleted. The sources are not affected.")) },
        confirmButton = { TextButton(onClick = { vm.delete(r.id); deleting = false; onBack() }) { Text(tr("Löschen", "Delete")) } },
        dismissButton = { TextButton(onClick = { deleting = false }) { Text(tr("Abbrechen", "Cancel")) } },
    )
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun FlowRow2(content: @Composable () -> Unit) = FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) { content() }

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

internal fun inline(text: String): androidx.compose.ui.text.AnnotatedString = androidx.compose.ui.text.buildAnnotatedString {
    MarkdownLite.spans(de.edgebird.lernsystem.core.cards.LatexLite.toPlain(text)).forEach { span ->
        when {
            span.bold -> withStyle(androidx.compose.ui.text.SpanStyle(fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)) { append(span.text) }
            span.italic -> withStyle(androidx.compose.ui.text.SpanStyle(fontStyle = androidx.compose.ui.text.font.FontStyle.Italic)) { append(span.text) }
            else -> append(span.text)
        }
    }
}

private fun androidx.compose.ui.text.AnnotatedString.Builder.withStyle(style: androidx.compose.ui.text.SpanStyle, block: androidx.compose.ui.text.AnnotatedString.Builder.() -> Unit) {
    val start = length; block(); addStyle(style, start, length)
}

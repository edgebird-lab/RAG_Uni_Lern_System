package de.edgebird.lernsystem.ui

import android.graphics.BitmapFactory
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel

/** Fotos von Unterlagen aufnehmen (oder aus der Galerie wählen), Text auf dem Gerät erkennen, korrigieren und als Quelle speichern. */
@Composable
fun PhotoImportScreen(subjectId: Long, onClose: () -> Unit, vm: PhotoImportViewModel = viewModel()) {
    LaunchedEffect(subjectId) { vm.bind(subjectId) }
    val s by vm.state.collectAsStateWithLifecycle()
    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok -> vm.captureDone(ok) }
    val gallery = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(20)) { uris -> vm.addFromGallery(uris) }
    var cropping by remember { androidx.compose.runtime.mutableStateOf<Int?>(null) }
    cropping?.let { i -> s.pages.getOrNull(i)?.let { f -> CropDialog(f, onApply = { vm.crop(i, it); cropping = null }, onDismiss = { cropping = null }) } }
    BackHandler {
        when (s.step) {
            PhotoStep.REVIEW -> vm.backToCapture()
            PhotoStep.RECOGNIZING -> Unit
            PhotoStep.CAPTURE -> { vm.discard(); onClose() }
        }
    }

    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Foto zu Text", style = MaterialTheme.typography.headlineMedium)
        when (s.step) {
            PhotoStep.CAPTURE -> {
                Text("Fotografiere Seiten deiner Unterlagen oder wähle Bilder aus der Galerie. Die Texterkennung läuft komplett auf dem Gerät. Tipp: Seite gerade von oben, scharf und gut beleuchtet, ohne Schatten.", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { camera.launch(vm.newCaptureUri()) }, modifier = Modifier.weight(1f)) { Text("Fotografieren") }
                    OutlinedButton(onClick = { gallery.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) }, modifier = Modifier.weight(1f)) { Text("Aus Galerie") }
                }
                s.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    itemsIndexed(s.pages, key = { _, f -> f.absolutePath }) { i, f ->
                        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                            Row(Modifier.padding(8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                val thumb = remember(f.absolutePath, s.version) { BitmapFactory.decodeFile(f.absolutePath, BitmapFactory.Options().apply { inSampleSize = 8 })?.asImageBitmap() }
                                if (thumb != null) Image(thumb, contentDescription = "Seite ${i + 1}", contentScale = ContentScale.Crop, modifier = Modifier.size(64.dp))
                                Text("Seite ${i + 1}", Modifier.weight(1f), style = MaterialTheme.typography.titleSmall)
                                TextButton(onClick = { cropping = i }) { Text("Zuschneiden") }
                                TextButton(onClick = { vm.move(i, -1) }, enabled = i > 0) { Text("↑") }
                                TextButton(onClick = { vm.move(i, 1) }, enabled = i < s.pages.lastIndex) { Text("↓") }
                                TextButton(onClick = { vm.remove(i) }) { Text("Entfernen") }
                            }
                        }
                    }
                }
                Button(onClick = vm::recognize, enabled = s.pages.isNotEmpty(), modifier = Modifier.fillMaxWidth()) { Text(if (s.pages.isEmpty()) "Zuerst Seiten hinzufügen" else "Text erkennen (${s.pages.size} ${if (s.pages.size == 1) "Seite" else "Seiten"})") }
                TextButton(onClick = { vm.discard(); onClose() }) { Text("Abbrechen") }
            }
            PhotoStep.RECOGNIZING -> {
                Text("Text wird erkannt: Seite ${s.progress} von ${s.pages.size}", style = MaterialTheme.typography.bodyLarge)
                LinearProgressIndicator(progress = { s.progress.toFloat() / s.pages.size.coerceAtLeast(1) }, modifier = Modifier.fillMaxWidth())
            }
            PhotoStep.REVIEW -> {
                Text("Prüfe den erkannten Text und korrigiere Fehler, bevor du ihn als Quelle speicherst.", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                OutlinedTextField(value = s.name, onValueChange = vm::setName, label = { Text("Name der Quelle") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                s.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    itemsIndexed(s.texts) { i, t ->
                        OutlinedTextField(
                            value = t, onValueChange = { vm.editText(i, it) }, label = { Text("Seite ${i + 1}") }, modifier = Modifier.fillMaxWidth().height(220.dp),
                            supportingText = { if (t.isBlank()) Text("Kein Text erkannt. Diese Seite wird übersprungen.") },
                        )
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = vm::backToCapture, modifier = Modifier.weight(1f)) { Text("Zurück") }
                    Button(onClick = { vm.save(onClose) }, modifier = Modifier.weight(1f)) { Text("Als Quelle speichern") }
                }
            }
        }
    }
}

// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ui

import de.edgebird.lernsystem.core.i18n.tr

import android.graphics.Bitmap
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import de.edgebird.lernsystem.core.scan.Pt
import java.io.File
import de.edgebird.lernsystem.ingest.PageScanner

/** Vollbild-Zuschnitt: Ecken sind automatisch erkannt und lassen sich mit dem Finger ziehen. */
@Composable
fun CropDialog(file: File, onApply: (List<Pt>) -> Unit, onDismiss: () -> Unit) {
    var bmp by remember(file) { mutableStateOf<Bitmap?>(null) }
    var corners by remember(file) { mutableStateOf<List<Pt>>(emptyList()) }
    LaunchedEffect(file) {
        val b = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Default) { PageScanner.load(file) }
        if (b != null) { corners = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Default) { PageScanner.detect(b) }; bmp = b }
    }
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxSize()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(tr("Seite zuschneiden", "Crop page"), style = MaterialTheme.typography.titleLarge)
                Text(tr("Ziehe die Ecken auf die Ränder des Blatts. Das Foto wird begradigt, das hilft der Texterkennung.", "Drag the corners onto the edges of the sheet. The photo is straightened, which helps text recognition."), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                val b = bmp
                if (b == null) Text(tr("Wird geladen …", "Loading …"), Modifier.weight(1f)) else {
                    val accent = MaterialTheme.colorScheme.primary
                    var box by remember { mutableStateOf(IntSize.Zero) }
                    var active by remember { mutableStateOf(-1) }
                    // Bild passend einpassen; Ecken in normierten Bildkoordinaten
                    Canvas(
                        Modifier.weight(1f).fillMaxWidth()
                            .pointerInput(b) {
                                detectDragGestures(
                                    onDragStart = { p ->
                                        val s = minOf(size.width / b.width.toFloat(), size.height / b.height.toFloat())
                                        val ox = (size.width - b.width * s) / 2; val oy = (size.height - b.height * s) / 2
                                        active = corners.indices.minByOrNull { i -> (Offset(ox + corners[i].x * b.width * s, oy + corners[i].y * b.height * s) - p).getDistance() }
                                            ?.takeIf { i -> (Offset(ox + corners[i].x * b.width * s, oy + corners[i].y * b.height * s) - p).getDistance() < 90.dp.toPx() } ?: -1
                                    },
                                    onDragEnd = { active = -1 }, onDragCancel = { active = -1 },
                                ) { change, drag ->
                                    change.consume()
                                    if (active >= 0) {
                                        val s = minOf(size.width / b.width.toFloat(), size.height / b.height.toFloat())
                                        val c = corners[active]
                                        val nx = (c.x + drag.x / (b.width * s)).coerceIn(0f, 1f)
                                        val ny = (c.y + drag.y / (b.height * s)).coerceIn(0f, 1f)
                                        corners = corners.toMutableList().also { it[active] = Pt(nx, ny) }
                                    }
                                }
                            },
                    ) {
                        box = IntSize(size.width.toInt(), size.height.toInt())
                        val s = minOf(size.width / b.width, size.height / b.height)
                        val ox = (size.width - b.width * s) / 2; val oy = (size.height - b.height * s) / 2
                        drawImage(b.asImageBitmap(), dstOffset = IntOffset(ox.toInt(), oy.toInt()), dstSize = IntSize((b.width * s).toInt(), (b.height * s).toInt()))
                        val pts = corners.map { Offset(ox + it.x * b.width * s, oy + it.y * b.height * s) }
                        if (pts.size == 4) {
                            val path = Path().apply { moveTo(pts[0].x, pts[0].y); pts.drop(1).forEach { lineTo(it.x, it.y) }; close() }
                            drawPath(path, accent, style = Stroke(width = 3.dp.toPx()))
                            pts.forEachIndexed { i, p ->
                                drawCircle(Color.White, 14.dp.toPx(), p)
                                drawCircle(accent, if (i == active) 12.dp.toPx() else 9.dp.toPx(), p)
                            }
                        }
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = onDismiss, Modifier.weight(1f)) { Text(tr("Abbrechen", "Cancel")) }
                    OutlinedButton(onClick = { bmp?.let { corners = PageScanner.detect(it) } }, Modifier.weight(1f), enabled = bmp != null) { Text(tr("Neu erkennen", "Detect again")) }
                    Button(onClick = { onApply(corners) }, Modifier.weight(1f), enabled = corners.size == 4) { Text(tr("Zuschneiden", "Crop")) }
                }
            }
        }
    }
}

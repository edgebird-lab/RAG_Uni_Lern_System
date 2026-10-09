// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.spike

import android.app.Activity
import android.os.Bundle
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.work.ImportItem
import de.edgebird.lernsystem.work.ImportWork
import java.io.File
import java.util.UUID

/**
 * Nur Debug: importiert alle Dateien aus `files/debug-in/` (per `adb shell run-as … cp` abgelegt), ohne Dateiauswahl.
 *   adb shell am start -n de.edgebird.lernsystem/.spike.DebugImportActivity
 */
class DebugImportActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val graph = (application as LernsystemApp).graph
        val files = File(filesDir, "debug-in").listFiles().orEmpty().filter { it.isFile }
        val items = files.map { f ->
            val copy = File(graph.inboxDir, UUID.randomUUID().toString()).also { f.copyTo(it, overwrite = true) }
            ImportItem("debug:${f.name}", f.name, copy)
        }
        if (items.isNotEmpty()) ImportWork.enqueue(this, items)
        finish()
    }
}

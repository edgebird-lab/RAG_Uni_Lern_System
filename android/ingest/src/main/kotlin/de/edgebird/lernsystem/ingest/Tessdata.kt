// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ingest

import android.content.Context
import java.io.File

/** Sprachdaten der Texterkennung: liegen als Assets in der App und werden einmal (nach jedem App-Update neu) in den privaten Speicher kopiert, weil Tesseract Dateien braucht. */
object Tessdata {
    /** Ordner, der `tessdata/` enthält. */
    @Synchronized
    fun ensure(context: Context): File {
        val root = File(context.filesDir, "ocr")
        val dir = File(root, "tessdata").apply { mkdirs() }
        val stamp = File(root, "tessdata.stamp")
        val version = runCatching { context.packageManager.getPackageInfo(context.packageName, 0).lastUpdateTime.toString() }.getOrDefault("0")
        val names = context.assets.list("tessdata").orEmpty().filter { it.endsWith(".traineddata") }
        val complete = names.isNotEmpty() && names.all { File(dir, it).length() > 0 }
        if (complete && stamp.takeIf { it.exists() }?.readText() == version) return root
        for (name in names) {
            val tmp = File(dir, "$name.tmp")
            context.assets.open("tessdata/$name").use { i -> tmp.outputStream().use { o -> i.copyTo(o) } }
            check(tmp.renameTo(File(dir, name))) { "Sprachdaten konnten nicht abgelegt werden" }
        }
        stamp.writeText(version)
        return root
    }
}

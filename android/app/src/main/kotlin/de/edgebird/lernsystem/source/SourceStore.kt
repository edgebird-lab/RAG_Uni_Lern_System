// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.source

import de.edgebird.lernsystem.data.DocumentEntity
import java.io.File

/**
 * Originale der Quellen (PDF, Bild, Text) im privaten App-Speicher: `files/sources/<dokument-id>.<endung>`. Aus ihnen entstehen Ansicht, Teilen,
 * Drucken und Speichern. Ältere Quellen ohne Original zeigen den erkannten Text.
 */
class SourceStore(filesDir: File) {
    val dir = File(filesDir, "sources").apply { mkdirs() }

    /** Das Original zu [doc] oder `null`. */
    fun original(doc: DocumentEntity): File? = if (doc.hasOriginal) find(doc.id) else null

    fun find(id: Long): File? = dir.listFiles { f -> f.isFile && f.name.startsWith("$id.") }?.firstOrNull()

    /** Legt [src] als Original von [docId] ab (ersetzt ein vorhandenes); [ext] ohne Punkt. */
    fun save(docId: Long, src: File, ext: String): File {
        delete(docId)
        val clean = ext.lowercase().filter { it.isLetterOrDigit() }.ifEmpty { "bin" }.take(8)
        return File(dir, "$docId.$clean").also { src.copyTo(it, overwrite = true) }
    }

    fun delete(id: Long) { dir.listFiles { f -> f.name.startsWith("$id.") }?.forEach { it.delete() } }

    fun deleteAll() { dir.listFiles()?.forEach { it.delete() } }

    /** Entfernt Originale von Quellen, die es nicht mehr gibt (gelöschtes Fach, ersetzte Fassung). */
    fun prune(validIds: Collection<Long>) {
        val keep = validIds.toSet()
        dir.listFiles()?.forEach { f -> val id = f.name.substringBefore('.').toLongOrNull(); if (id == null || id !in keep) f.delete() }
    }

    companion object {
        /** Endungen, die sich als Original anzeigen und weiterreichen lassen. */
        fun mimeFor(ext: String): String = when (ext.lowercase()) {
            "pdf" -> "application/pdf"; "docx" -> "application/vnd.openxmlformats-officedocument.wordprocessingml.document"; "pptx" -> "application/vnd.openxmlformats-officedocument.presentationml.presentation"; "odt" -> "application/vnd.oasis.opendocument.text"; "odp" -> "application/vnd.oasis.opendocument.presentation"; "png" -> "image/png"; "jpg", "jpeg" -> "image/jpeg"; "webp" -> "image/webp"
            "md", "markdown" -> "text/markdown"; "txt" -> "text/plain"; else -> "application/octet-stream"
        }
    }
}

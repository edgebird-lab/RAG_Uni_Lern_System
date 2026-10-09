// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.ingest

/**
 * @param size Zielgröße pro Chunk in Zeichen. Der Embedder verträgt höchstens 512 Token, in deutschem Text
 *   sind das im Worst Case (Paragrafen, Zahlen) etwa 2,9 Zeichen/Token, daher inklusive Überlappung unter ~1300 bleiben.
 */
data class ChunkerConfig(
    val size: Int = 1000,
    val overlap: Int = 150,
    val minChars: Int = 120,
    val respectMarkdownHeaders: Boolean = true,
)

/**
 * Struktur-bewusstes Chunking (Port von `ragapp/ingestion/chunker.py`).
 * Markdown wird an Überschriften geschnitten, Seiten/Folien rekursiv an natürlichen Grenzen.
 */
object Chunker {
    private val SEPARATORS = listOf("\n\n", "\n", ". ", "; ", ", ", " ", "")
    private val MD_TABLE_SEP = Regex("""^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$""")
    private val HEADER = Regex("""^(#{1,6})\s+(.*)$""")

    fun chunk(doc: LoadedDoc, config: ChunkerConfig = ChunkerConfig()): List<Chunk> {
        val out = mutableListOf<Chunk>()
        if (doc.isMarkdown && config.respectMarkdownHeaders) {
            for ((path, body) in splitMarkdownSections(doc.text)) {
                val prefix = if (path.isNotEmpty()) "[$path]\n" else ""
                for (piece in splitRecursive(body, config.size, config.overlap)) {
                    out += Chunk(text = (prefix + piece).trim(), location = path.ifEmpty { de.edgebird.lernsystem.core.i18n.tr("Dokument", "Document") }, headerPath = path)
                }
            }
        } else {
            for (block in doc.blocks) {
                for (piece in splitRecursive(block.text, config.size, config.overlap)) {
                    val page = block.page
                    val location = when {
                        page == null -> de.edgebird.lernsystem.core.i18n.tr("Dokument", "Document")
                        block.kind == BlockKind.SLIDE -> de.edgebird.lernsystem.core.i18n.tr("Folie", "Slide") + " $page"
                        else -> de.edgebird.lernsystem.core.i18n.tr("Seite", "Page") + " $page"
                    }
                    out += Chunk(text = piece, location = location, page = page)
                }
            }
        }
        return mergeSmall(out, config.minChars).mapIndexed { i, c -> c.copy(index = i) }
    }

    // ---- Tabellen ---------------------------------------------------------------------------------

    private fun looksLikeRow(line: String) = line.count { it == '|' } >= 2 || '\t' in line || MD_TABLE_SEP.matches(line)

    private fun isTableLike(text: String): Boolean {
        val lines = text.split("\n").filter { it.isNotBlank() }
        if (lines.size < 2) return false
        val rows = lines.count { looksLikeRow(it) }
        return rows >= 2 && rows.toDouble() / lines.size >= 0.5
    }

    private fun applyLineOverlap(chunks: List<String>, overlap: Int): List<String> {
        if (overlap <= 0 || chunks.size <= 1) return chunks
        val out = mutableListOf(chunks[0])
        for (i in 1 until chunks.size) {
            val tail = ArrayDeque<String>()
            var length = 0
            for (ln in chunks[i - 1].split("\n").asReversed()) {
                if (tail.isNotEmpty() && length + ln.length + 1 > overlap) break
                tail.addFirst(ln)
                length += ln.length + 1
            }
            val prefix = tail.joinToString("\n")
            out += if (prefix.isNotEmpty()) "$prefix\n${chunks[i]}" else chunks[i]
        }
        return out
    }

    private fun splitTable(text: String, size: Int, overlap: Int): List<String> {
        val chunks = mutableListOf<String>()
        var current = ""
        for (ln in text.split("\n")) {
            val candidate = if (current.isEmpty()) ln else "$current\n$ln"
            if (current.isNotEmpty() && candidate.length > size) {
                chunks += current
                current = ln
            } else {
                current = candidate
            }
        }
        if (current.isNotEmpty()) chunks += current
        return applyLineOverlap(chunks, overlap)
    }

    // ---- Rekursiver Splitter ----------------------------------------------------------------------

    internal fun splitRecursive(raw: String, size: Int, overlap: Int): List<String> {
        val text = raw.trim()
        if (text.length <= size) return if (text.isEmpty()) emptyList() else listOf(text)
        if (isTableLike(text)) return splitTable(text, size, overlap)

        for (sep in SEPARATORS) {
            if (sep.isEmpty()) {
                val step = maxOf(1, size - overlap)
                return (text.indices step step).map { text.substring(it, minOf(it + size, text.length)) }.filter { it.isNotBlank() }
            }
            val parts = text.split(sep)
            if (parts.size == 1) continue
            val chunks = mutableListOf<String>()
            var current = ""
            for (part in parts) {
                val candidate = if (current.isEmpty()) part else current + sep + part
                if (candidate.length <= size) {
                    current = candidate
                } else {
                    if (current.isNotEmpty()) chunks += current
                    if (part.length > size) {
                        chunks += splitRecursive(part, size, overlap)
                        current = ""
                    } else {
                        current = part
                    }
                }
            }
            if (current.isNotEmpty()) chunks += current
            return applyOverlap(chunks, overlap)
        }
        return listOf(text)
    }

    private fun applyOverlap(chunks: List<String>, overlap: Int): List<String> {
        if (overlap <= 0 || chunks.size <= 1) return chunks
        val out = mutableListOf(chunks[0])
        for (i in 1 until chunks.size) {
            out += (chunks[i - 1].takeLast(overlap) + " " + chunks[i]).trim()
        }
        return out
    }

    // ---- Markdown ---------------------------------------------------------------------------------

    /** Zerlegt Markdown in (Überschriften-Pfad, Abschnittstext). */
    internal fun splitMarkdownSections(text: String): List<Pair<String, String>> {
        val sections = mutableListOf<Pair<String, String>>()
        val stack = mutableListOf<Pair<Int, String>>()
        val buffer = mutableListOf<String>()

        fun path() = stack.joinToString(" › ") { it.second }
        fun flush() {
            val body = buffer.joinToString("\n").trim()
            if (body.isNotEmpty()) sections += path() to body
            buffer.clear()
        }

        for (line in text.split("\n")) {
            val m = HEADER.matchEntire(line.trim())
            if (m != null) {
                flush()
                val level = m.groupValues[1].length
                stack.removeAll { it.first >= level }
                stack += level to m.groupValues[2].trim()
            } else {
                buffer += line
            }
        }
        flush()
        return sections.ifEmpty { listOf("" to text.trim()) }
    }

    private fun mergeSmall(chunks: List<Chunk>, minChars: Int): List<Chunk> {
        val out = mutableListOf<Chunk>()
        for (c in chunks) {
            val last = out.lastOrNull()
            if (last != null && c.text.length < minChars && c.location == last.location) {
                out[out.lastIndex] = last.copy(text = (last.text + "\n" + c.text).trim())
            } else {
                out += c
            }
        }
        return out
    }
}

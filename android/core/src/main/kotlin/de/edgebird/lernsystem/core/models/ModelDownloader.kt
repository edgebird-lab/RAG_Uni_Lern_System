package de.edgebird.lernsystem.core.models

import java.io.File
import java.io.IOException
import java.io.RandomAccessFile
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * Lädt ein Modell aus seinen Teilen in eine einzige `.partial`-Datei (Teile nacheinander angehängt) und benennt sie nach
 * erfolgreicher SHA-256-Prüfung um. Ein Abbruch oder Absturz lässt die Datei stehen; der nächste Aufruf setzt an der Länge fort
 * (HTTP Range). Ein vorhandenes älteres Modell bleibt bis zum letzten Schritt unangetastet (Umbenennen ersetzt es atomar).
 */
class ModelDownloader(
    private val dir: File,
    private val freeSpace: () -> Long = { dir.usableSpace },
    private val connectTimeoutMs: Int = 15_000,
    private val readTimeoutMs: Int = 30_000,
    private val reserveBytes: Long = 200L * 1024 * 1024,
) {
    class Cancelled : Exception("Abgebrochen")

    /** Entpackt [zip] erst in einen Nebenordner und ersetzt dann [target]; so bleibt eine ältere Fassung bis zum Erfolg erhalten. Schutz vor Pfaden außerhalb des Ordners. */
    internal fun unzipAtomic(zip: File, target: File, marker: String, maxBytes: Long = 600L * 1024 * 1024) {
        val tmp = File(target.parentFile, target.name + ".new").also { it.deleteRecursively(); it.mkdirs() }
        try {
            var total = 0L
            java.util.zip.ZipInputStream(zip.inputStream().buffered()).use { zin ->
                while (true) {
                    val e = zin.nextEntry ?: break
                    val out = File(tmp, e.name)
                    if (!out.canonicalPath.startsWith(tmp.canonicalPath + File.separator)) throw ModelException("Ungültiges Paket (Pfad außerhalb des Ordners)")
                    if (e.isDirectory) { out.mkdirs(); continue }
                    out.parentFile?.mkdirs()
                    out.outputStream().use { o ->
                        val buf = ByteArray(64 * 1024)
                        while (true) { val n = zin.read(buf); if (n < 0) break; total += n; if (total > maxBytes) throw ModelException("Paket ist größer als erlaubt"); o.write(buf, 0, n) }
                    }
                }
            }
            File(tmp, MARKER).writeText(marker)
            target.deleteRecursively()
            if (!tmp.renameTo(target)) throw ModelException("Paket konnte nicht abgelegt werden")
        } catch (e: Exception) {
            tmp.deleteRecursively()
            throw if (e is ModelException) e else ModelException("Paket konnte nicht entpackt werden: ${e.message}", e)
        }
    }

    fun versionFile(model: ModelInfo) = File(dir, model.fileName + ".version")
    fun installed(): Map<String, InstalledModel> {
        val files = dir.listFiles().orEmpty()
        val plain = files.filter { it.isFile && !it.name.endsWith(".partial") && !it.name.endsWith(".version") }
            .associate { f -> f.name to InstalledModel(f.length(), File(dir, f.name + ".version").takeIf { it.exists() }?.readText()?.trim()) }
        // Entpackte Pakete (Stimme): Der Marker im Ordner nennt Dateiname, Größe und Version des geladenen Pakets
        val unpacked = files.filter { it.isDirectory }.mapNotNull { d ->
            File(d, MARKER).takeIf { it.isFile }?.readText()?.split('|')?.takeIf { it.size == 3 }?.let { (name, size, version) -> name to InstalledModel(size.toLongOrNull() ?: 0, version) }
        }.toMap()
        return plain + unpacked
    }

    /** Manifest von der ersten erreichbaren URL holen. */
    fun fetchManifest(urls: List<String>): ModelManifest {
        var last: Exception? = null
        for (u in urls) {
            try {
                val c = open(u, 0)
                try {
                    if (c.responseCode != 200) throw IOException("HTTP ${c.responseCode}")
                    return ModelManifest.parse(c.inputStream.bufferedReader().readText())
                } finally { c.disconnect() }
            } catch (e: Exception) { last = e }
        }
        throw ModelException("Manifest nicht erreichbar: ${last?.message}", last)
    }

    /** Speicher, der für [model] noch gebraucht wird (Teilstand wird angerechnet). */
    fun bytesNeeded(model: ModelInfo): Long = model.size - (File(dir, model.fileName + ".partial").takeIf { it.exists() }?.length() ?: 0L).coerceAtMost(model.size) + reserveBytes

    fun install(model: ModelInfo, onProgress: (done: Long, total: Long) -> Unit = { _, _ -> }, isCancelled: () -> Boolean = { false }) {
        dir.mkdirs()
        val partial = File(dir, model.fileName + ".partial")
        if (partial.exists() && partial.length() > model.size) partial.delete()
        val need = bytesNeeded(model)
        if (freeSpace() < need) throw ModelException("Zu wenig freier Speicher: ${need / 1_048_576} MB nötig, ${freeSpace() / 1_048_576} MB frei")
        try {
            RandomAccessFile(partial, "rw").use { raf ->
                var start = 0L
                for (part in model.parts) {
                    val end = start + part.size
                    if (raf.length() < end) {
                        if (raf.length() < start) raf.setLength(start)
                        downloadPart(raf, part, start, model.size, onProgress, isCancelled)
                    }
                    if (!verifyRange(raf, start, part.size, part.sha256)) {
                        raf.setLength(start)
                        throw ModelException("Prüfsumme von ${part.name} stimmt nicht, Teil wird beim nächsten Versuch neu geladen")
                    }
                    start = end
                }
                raf.setLength(model.size)
            }
            if (sha256(partial) != model.sha256) { partial.delete(); throw ModelException("Prüfsumme von ${model.fileName} stimmt nicht, Datei wurde verworfen") }
            if (model.unpack.isNotEmpty()) {
                unzipAtomic(partial, File(dir, model.unpack), "${model.fileName}|${model.size}|${model.version}")
                partial.delete()
            } else {
                val target = File(dir, model.fileName)
                if (!partial.renameTo(target)) throw ModelException("Modell konnte nicht abgelegt werden")
                versionFile(model).writeText(model.version)
            }
        } catch (e: Cancelled) { throw e }
    }

    private fun downloadPart(raf: RandomAccessFile, part: ModelPart, start: Long, total: Long, onProgress: (Long, Long) -> Unit, isCancelled: () -> Boolean) {
        var last: Exception? = null
        for (url in part.urls) {
            repeat(2) { attempt ->
                try {
                    fetchInto(raf, url, start, part.size, total, onProgress, isCancelled)
                    return
                } catch (e: Cancelled) { throw e
                } catch (e: Exception) {
                    last = e
                    if (attempt == 0) Thread.sleep(500)
                }
            }
        }
        throw ModelException("${part.name} konnte nicht geladen werden: ${last?.message}", last)
    }

    private fun fetchInto(raf: RandomAccessFile, url: String, start: Long, size: Long, total: Long, onProgress: (Long, Long) -> Unit, isCancelled: () -> Boolean) {
        val have = (raf.length() - start).coerceIn(0, size)
        raf.seek(start + have)
        val c = open(url, have)
        try {
            val code = c.responseCode
            var skip = 0L
            when {
                code == 206 -> Unit
                code == 200 -> { if (have > 0) skip = have }  // Server ignoriert Range: Anfang überspringen
                else -> throw IOException("HTTP $code")
            }
            val buf = ByteArray(64 * 1024)
            c.inputStream.use { input ->
                var toSkip = skip
                while (toSkip > 0) { val n = input.skip(toSkip); if (n <= 0) throw IOException("Überspringen fehlgeschlagen"); toSkip -= n }
                var written = have
                while (written < size) {
                    if (isCancelled()) throw Cancelled()
                    val n = input.read(buf, 0, minOf(buf.size.toLong(), size - written).toInt())
                    if (n < 0) throw IOException("Verbindung beendet nach ${written} von $size Bytes")
                    raf.write(buf, 0, n)
                    written += n
                    onProgress(start + written, total)
                }
            }
        } finally { c.disconnect() }
    }

    private fun open(url: String, from: Long): HttpURLConnection = (URL(url).openConnection() as HttpURLConnection).apply {
        connectTimeout = connectTimeoutMs; readTimeout = readTimeoutMs; instanceFollowRedirects = true
        setRequestProperty("User-Agent", "RAG-Lernsystem-Android")
        if (from > 0) setRequestProperty("Range", "bytes=$from-")
    }

    private fun verifyRange(raf: RandomAccessFile, start: Long, size: Long, expected: String): Boolean {
        val md = MessageDigest.getInstance("SHA-256")
        raf.seek(start)
        val buf = ByteArray(1 shl 20)
        var left = size
        while (left > 0) {
            val n = raf.read(buf, 0, minOf(buf.size.toLong(), left).toInt())
            if (n < 0) return false
            md.update(buf, 0, n); left -= n
        }
        return md.digest().toHex() == expected
    }

    companion object {
        /** Datei im entpackten Ordner, die Dateiname, Größe und Version des Pakets festhält. */
        const val MARKER = ".installed"

        fun sha256(f: File): String {
            val md = MessageDigest.getInstance("SHA-256")
            f.inputStream().use { i -> val b = ByteArray(1 shl 20); while (true) { val n = i.read(b); if (n < 0) break; md.update(b, 0, n) } }
            return md.digest().toHex()
        }
        private fun ByteArray.toHex() = joinToString("") { "%02x".format(it) }
    }
}

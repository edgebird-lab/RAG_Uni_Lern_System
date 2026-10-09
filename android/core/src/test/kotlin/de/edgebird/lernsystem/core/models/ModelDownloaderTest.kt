// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.models

import com.sun.net.httpserver.HttpServer
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File
import java.net.InetSocketAddress
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicInteger

class ModelDownloaderTest {
    @TempDir lateinit var dir: File
    private lateinit var server: HttpServer
    private val data = ByteArray(300_000) { (it * 31 + it / 7).toByte() }
    private val parts = listOf(0 to 120_000, 120_000 to 250_000, 250_000 to 300_000)
    private val hits = AtomicInteger()
    private var ignoreRange = false
    private var failFirst = 0
    private var corruptPart2 = false
    private val port get() = server.address.port

    private fun sha(b: ByteArray) = MessageDigest.getInstance("SHA-256").digest(b).joinToString("") { "%02x".format(it) }

    @BeforeEach fun start() {
        server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        server.createContext("/") { ex ->
            hits.incrementAndGet()
            val idx = ex.requestURI.path.removePrefix("/p").toIntOrNull()
            if (ex.requestURI.path == "/broken" || (failFirst > 0 && failFirst-- > 0)) { ex.sendResponseHeaders(503, -1); ex.close(); return@createContext }
            if (idx == null) { ex.sendResponseHeaders(404, -1); ex.close(); return@createContext }
            var body = data.copyOfRange(parts[idx].first, parts[idx].second)
            if (corruptPart2 && idx == 1) body = body.copyOf().also { it[5] = (it[5] + 1).toByte() }
            val range = ex.requestHeaders.getFirst("Range")?.removePrefix("bytes=")?.removeSuffix("-")?.toIntOrNull()
            if (range != null && !ignoreRange) {
                ex.responseHeaders.add("Content-Range", "bytes $range-${body.size - 1}/${body.size}")
                ex.sendResponseHeaders(206, (body.size - range).toLong()); ex.responseBody.use { it.write(body, range, body.size - range) }
            } else { ex.sendResponseHeaders(200, body.size.toLong()); ex.responseBody.use { it.write(body) } }
        }
        server.start()
    }

    @AfterEach fun stop() = server.stop(0)

    private fun model(urls: (Int) -> List<String> = { listOf("http://127.0.0.1:$port/p$it") }) = ModelInfo(
        id = "m", role = "embedding", title = "m", version = "v1", fileName = "m.bin", size = data.size.toLong(), sha256 = sha(data),
        parts = parts.mapIndexed { i, (a, b) -> ModelPart("m.bin.part${i + 1}", (b - a).toLong(), sha(data.copyOfRange(a, b)), urls(i)) },
    )

    private fun dl(space: Long = Long.MAX_VALUE) = ModelDownloader(dir, freeSpace = { space }, reserveBytes = 0)

    @Test fun `laedt alle Teile und setzt sie zusammen`() {
        dl().install(model())
        assertArrayEquals(data, File(dir, "m.bin").readBytes())
        assertEquals("v1", File(dir, "m.bin.version").readText())
        assertFalse(File(dir, "m.bin.partial").exists())
    }

    @Test fun `setzt nach Abbruch per Range fort`() {
        val m = model()
        var seen = 0L
        assertThrows(ModelDownloader.Cancelled::class.java) { dl().install(m, { d, _ -> seen = d }, { seen > 150_000 }) }
        val partial = File(dir, "m.bin.partial")
        assertTrue(partial.exists() && partial.length() in 150_000..260_000)
        hits.set(0)
        dl().install(m)
        assertArrayEquals(data, File(dir, "m.bin").readBytes())
        assertTrue(hits.get() <= 3)
    }

    @Test fun `Server ohne Range-Unterstuetzung wird beim Fortsetzen verkraftet`() {
        val m = model()
        var seen = 0L
        assertThrows(ModelDownloader.Cancelled::class.java) { dl().install(m, { d, _ -> seen = d }, { seen > 60_000 }) }
        ignoreRange = true
        dl().install(m)
        assertArrayEquals(data, File(dir, "m.bin").readBytes())
    }

    @Test fun `faellt auf zweite URL zurueck`() {
        dl().install(model { listOf("http://127.0.0.1:$port/broken", "http://127.0.0.1:$port/p$it") })
        assertArrayEquals(data, File(dir, "m.bin").readBytes())
    }

    @Test fun `ein kurzer Ausfall wird wiederholt`() {
        failFirst = 1
        dl().install(model())
        assertArrayEquals(data, File(dir, "m.bin").readBytes())
    }

    @Test fun `kaputtes Teil wird erkannt und nicht uebernommen`() {
        corruptPart2 = true
        val e = assertThrows(ModelException::class.java) { dl().install(model()) }
        assertTrue("Prüfsumme" in e.message!!)
        assertFalse(File(dir, "m.bin").exists())
        // nach Reparatur des Servers wird ab dem kaputten Teil neu geladen
        corruptPart2 = false
        dl().install(model())
        assertArrayEquals(data, File(dir, "m.bin").readBytes())
    }

    @Test fun `zu wenig Speicher bricht vor dem Laden ab`() {
        val e = assertThrows(ModelException::class.java) { dl(space = 1000).install(model()) }
        assertTrue("Speicher" in e.message!!)
        assertEquals(0, hits.get())
    }

    @Test fun `altes Modell bleibt bis zum Erfolg erhalten`() {
        File(dir, "m.bin").writeText("alt"); File(dir, "m.bin.version").writeText("v0")
        corruptPart2 = true
        assertThrows(ModelException::class.java) { dl().install(model()) }
        assertEquals("alt", File(dir, "m.bin").readText())
        corruptPart2 = false
        dl().install(model())
        assertEquals("v1", File(dir, "m.bin.version").readText())
    }

    @Test fun `alle URLs ausgefallen ergibt verstaendlichen Fehler`() {
        val e = assertThrows(ModelException::class.java) { dl().install(model { listOf("http://127.0.0.1:$port/broken") }) }
        assertTrue("konnte nicht geladen werden" in e.message!!)
    }

    @Test fun `Manifest wird geladen und geprueft`() {
        val json = com.google.gson.Gson().toJson(ModelManifest(1, "v1", 1, "", listOf(model())))
        server.createContext("/manifest.json") { ex -> ex.sendResponseHeaders(200, json.length.toLong()); ex.responseBody.use { it.write(json.toByteArray()) } }
        val m = dl().fetchManifest(listOf("http://127.0.0.1:$port/broken", "http://127.0.0.1:$port/manifest.json"))
        assertEquals("m.bin", m.models.single().fileName)
        assertThrows(ModelException::class.java) { ModelManifest.parse(json.replace("\"schemaVersion\":1", "\"schemaVersion\":2")) }
        assertThrows(ModelException::class.java) { ModelManifest.parse("{kaputt") }
    }

    @Test fun `Nur das gewaehlte Sprachmodell wird geplant`() {
        val e2b = model().copy(id = "e2b", role = "llm", fileName = ModelPlan.DEFAULT_LLM_FILE)
        val e4b = model().copy(id = "e4b", role = "llm", fileName = "gemma-4-E4B-it.litertlm", optional = true)
        val emb = model().copy(id = "emb", role = "embedding", fileName = "emb.bin")
        val man = ModelManifest(1, "v1", 1, "", listOf(e4b, emb, e2b))
        assertEquals(listOf("emb", "e2b"), ModelPlan.pending(man, emptyMap()).map { it.id })
        assertEquals(listOf("e4b", "emb"), ModelPlan.pending(man, emptyMap(), llmFile = e4b.fileName).map { it.id })
        assertEquals(listOf("e2b", "e4b"), ModelPlan.llmChoices(man).map { it.id }.let { listOf(it[0], it[1]) })
    }

    @Test fun `Plan erkennt fehlende und veraltete Modelle`() {
        val man = ModelManifest(1, "v2", 1, "", listOf(model().copy(version = "v2")))
        val name = "m.bin"; val size = data.size.toLong()
        assertEquals(1, ModelPlan.pending(man, emptyMap()).size)
        assertEquals(0, ModelPlan.pending(man, mapOf(name to InstalledModel(size, null))).size)   // manuell abgelegt, gleiche Größe
        assertEquals(1, ModelPlan.pending(man, mapOf(name to InstalledModel(size, "v1"))).size)  // älteres Release
        assertEquals(1, ModelPlan.pending(man, mapOf(name to InstalledModel(5, null))).size)     // falsche Größe
        assertEquals(1, ModelPlan.updatesAvailable(man, mapOf(name to InstalledModel(size, "v1"))).size)
        assertEquals(0, ModelPlan.updatesAvailable(man, mapOf(name to InstalledModel(size, null))).size)
    }

    @Test fun `echtes Manifest aus dem Repo ist gueltig`() {
        val f = File(System.getProperty("user.home"), "lernsystem-modelle-repo/manifest.json")
        org.junit.jupiter.api.Assumptions.assumeTrue(f.exists())
        val m = ModelManifest.parse(f.readText())
        assertEquals(2, m.models.count { !it.optional })
        assertTrue(m.models.filter { !it.optional }.all { it.license == "Apache-2.0" })
        val voices = m.models.filter { it.optional }
        assertTrue(voices.all { it.role == "tts" && it.unpack.startsWith("tts-") && it.license.contains("espeak-ng") && it.lang != null })
        assertEquals("tts-de", voices.first { it.id == "voice-de-thorsten" }.unpack)
        assertTrue(voices.any { it.lang == "en" } && voices.any { it.lang == "de" })
        assertEquals(voices.size, voices.map { it.unpack }.toSet().size)   // jede Stimme hat einen eigenen Ordner
    }

    @Test fun `Manifest ohne neuere Felder bekommt Standardwerte statt null`() {
        // Fassung des Manifests aus der Zeit vor Stimmenpaketen: ohne optional, unpack, lang, license, source
        val json = """{"schemaVersion":1,"release":"v1","models":[{"id":"a","role":"llm","title":"A","version":"v1","fileName":"a.bin","size":3,"sha256":"x","parts":[{"name":"a.part1","size":3,"sha256":"x","urls":["http://u"]}]}]}"""
        val m = ModelManifest.parse(json).models.single()
        assertEquals("", m.unpack); assertEquals(false, m.optional); assertEquals("", m.license); assertEquals("", m.source); assertEquals(0, m.minRamMb)
        assertEquals(null, m.lang); assertEquals("A", m.displayTitle())
        assertEquals("", ModelManifest.parse(json).licenseUrl)
    }

    // ---- Pakete (ZIP), z. B. die Stimme ------------------------------------------------------------------------------

    private fun zipOf(vararg entries: Pair<String, String>): ByteArray {
        val bo = java.io.ByteArrayOutputStream()
        java.util.zip.ZipOutputStream(bo).use { z -> entries.forEach { (n, c) -> z.putNextEntry(java.util.zip.ZipEntry(n)); z.write(c.toByteArray()); z.closeEntry() } }
        return bo.toByteArray()
    }

    @Test fun `ZIP-Paket wird entpackt, mit Marker versehen und gilt danach als installiert`() {
        val zip = zipOf("model.onnx" to "daten", "espeak-ng-data/de_dict" to "dict")
        val f = File(dir, "pack.zip.partial").also { it.writeBytes(zip) }
        ModelDownloader(dir).unzipAtomic(f, File(dir, "tts-de"), "voice.zip|${zip.size}|v1")
        assertEquals("daten", File(dir, "tts-de/model.onnx").readText())
        assertEquals("dict", File(dir, "tts-de/espeak-ng-data/de_dict").readText())
        val inst = ModelDownloader(dir).installed()
        assertEquals(InstalledModel(zip.size.toLong(), "v1"), inst["voice.zip"])
    }

    @Test fun `Paket mit Pfad ausserhalb des Ordners wird abgelehnt und hinterlaesst nichts`() {
        val f = File(dir, "bad.zip").also { it.writeBytes(zipOf("../boese.txt" to "x")) }
        assertThrows(ModelException::class.java) { ModelDownloader(dir).unzipAtomic(f, File(dir, "tts-de"), "a|1|v") }
        assertFalse(File(dir.parentFile, "boese.txt").exists())
        assertFalse(File(dir, "tts-de.new").exists())
    }

    @Test fun `ein aelteres Paket bleibt bei einem Fehler erhalten`() {
        File(dir, "tts-de").mkdirs(); File(dir, "tts-de/alt.txt").writeText("alt")
        val f = File(dir, "bad.zip").also { it.writeBytes(zipOf("../x.txt" to "x")) }
        assertThrows(ModelException::class.java) { ModelDownloader(dir).unzipAtomic(f, File(dir, "tts-de"), "a|1|v") }
        assertEquals("alt", File(dir, "tts-de/alt.txt").readText())
    }

    @Test fun `Paket ueber dem Groessenlimit wird abgelehnt`() {
        val f = File(dir, "big.zip").also { it.writeBytes(zipOf("a.bin" to "x".repeat(5000))) }
        assertThrows(ModelException::class.java) { ModelDownloader(dir).unzipAtomic(f, File(dir, "t"), "a|1|v", maxBytes = 1000) }
    }

    @Test fun `optionale Modelle werden nur auf Wunsch oder bei vorhandener Fassung eingeplant`() {
        val voice = model().copy(id = "voice", fileName = "voice.zip", optional = true, unpack = "tts-de", version = "v2")
        val man = ModelManifest(1, "v2", 1, "", listOf(model(), voice))
        assertEquals(listOf("m.bin"), ModelPlan.pending(man, emptyMap()).map { it.fileName })
        assertEquals(listOf("m.bin", "voice.zip"), ModelPlan.pending(man, emptyMap(), includeOptional = true).map { it.fileName })
        // schon installiert, aber ältere Version: gilt als Update, auch ohne Wunsch
        assertEquals(listOf("voice.zip"), ModelPlan.pending(man, mapOf("m.bin" to InstalledModel(data.size.toLong(), null), "voice.zip" to InstalledModel(voice.size, "v1"))).map { it.fileName })
    }
}

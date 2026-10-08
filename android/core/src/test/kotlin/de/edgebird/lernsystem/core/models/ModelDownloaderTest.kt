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
        id = "m", role = "llm", title = "m", version = "v1", fileName = "m.bin", size = data.size.toLong(), sha256 = sha(data),
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
        assertEquals(2, m.models.size)
        assertTrue(m.models.all { it.license == "Apache-2.0" })
    }
}

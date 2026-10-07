package de.edgebird.lernsystem.ingest

import androidx.test.platform.app.InstrumentationRegistry
import de.edgebird.lernsystem.core.ai.Embedder
import kotlin.math.abs

fun assetSource(name: String, key: String = "asset:$name"): DocumentSource {
    val assets = InstrumentationRegistry.getInstrumentation().context.assets
    return DocumentSource(key, name) { assets.open(name) }
}

fun textSource(key: String, name: String, content: String) = DocumentSource(key, name) { content.byteInputStream() }

/** Deterministischer Attrappen-Embedder: Vektor aus Zeichenhäufigkeiten, damit ähnliche Texte ähnliche Vektoren haben. */
class FakeEmbedder(override val dimensions: Int = 8, private val failAfterBatches: Int = Int.MAX_VALUE) : Embedder {
    var batches = 0
        private set
    var loaded = false
        private set

    override suspend fun load() { loaded = true }

    override suspend fun embed(texts: List<String>): List<FloatArray> {
        if (batches >= failAfterBatches) error("simulierter Abbruch")
        batches++
        return texts.map { t ->
            val v = FloatArray(dimensions)
            t.forEach { ch -> v[abs(ch.code) % dimensions] += 1f }
            val n = kotlin.math.sqrt(v.sumOf { (it * it).toDouble() }).toFloat()
            if (n > 0) FloatArray(dimensions) { v[it] / n } else v
        }
    }

    override fun close() = Unit
}

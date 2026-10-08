package de.edgebird.lernsystem.core.cards

import de.edgebird.lernsystem.core.ai.GenerationParams
import de.edgebird.lernsystem.core.ai.LlmEngine
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test

class ClozeTest {
    private val chunk = "Bei der Photosynthese wandeln Pflanzen Lichtenergie in chemische Energie um. Dabei entstehen Sauerstoff und Glucose aus Kohlenstoffdioxid und Wasser. " +
        "Die Lichtreaktion findet in den Thylakoidmembranen der Chloroplasten statt und liefert ATP und NADPH für den Calvin-Zyklus."

    private fun item(s: String, t: String) = Cloze.Item(s, t)

    @Test fun `Karte wird aus Satz und Begriff gebaut`() {
        val b = Cloze.build(item("Die Lichtreaktion findet in den Thylakoidmembranen der Chloroplasten statt und liefert ATP und NADPH für den Calvin-Zyklus.", "Thylakoidmembranen"), chunk)!!
        assertTrue(b.front.startsWith("Ergänze die Lücke:"))
        assertTrue("[…]" in b.front && "Thylakoidmembranen" !in b.front)
        assertTrue("**Thylakoidmembranen**" in b.answer && b.answer.contains("Calvin-Zyklus"))
    }

    @Test fun `Satz muss wirklich im Quelltext stehen`() {
        assertNull(Cloze.build(item("Die Photosynthese findet ausschließlich nachts in den Mitochondrien der Tiere statt, sagt man.", "Mitochondrien"), chunk))
    }

    @Test fun `Begriff muss im Satz stehen und darf kein Fuellwort oder zu lang sein`() {
        val s = "Dabei entstehen Sauerstoff und Glucose aus Kohlenstoffdioxid und Wasser."
        assertNull(Cloze.build(item(s, "Stickstoff"), chunk))
        assertNull(Cloze.build(item(s, "und"), chunk))
        assertNull(Cloze.build(item(s, "Sauerstoff und Glucose aus Kohlenstoffdioxid und Wasser"), chunk))
        assertNotNull(Cloze.build(item(s, "Glucose"), chunk))
    }

    @Test fun `alle Vorkommen des Begriffs werden verdeckt`() {
        val c = "Die Zelle ist die kleinste lebende Einheit, und jede Zelle besitzt eine Membran, die die Zelle nach außen abgrenzt."
        val b = Cloze.build(item(c, "Zelle"), c)!!
        assertFalse(b.front.lowercase().contains("zelle"))
        assertEquals(3, Regex("""\[…]""").findAll(b.front).count())
    }

    @Test fun `Quellenbezug im Satz wird abgelehnt`() {
        val c = "Wie in Abbildung 3 gezeigt, steigt die Rate der Photosynthese bei höherer Lichtintensität zunächst linear an und erreicht dann ein Plateau."
        assertNull(Cloze.build(item(c, "Plateau"), c))
    }

    @Test fun `Parser toleriert Text und Codefences drumherum`() {
        val raw = "Hier:\n```json\n{\"cloze\": [{\"satz\": \"A b c\", \"luecke\": \"b\"}, {\"satz\": \"\", \"luecke\": \"x\"}]}\n```"
        assertEquals(listOf(Cloze.Item("A b c", "b")), Cloze.parse(raw))
        assertTrue(Cloze.parse("kaputt").isEmpty())
    }

    private class Scripted(vararg val replies: String) : LlmEngine {
        var n = 0
        override suspend fun load() {}
        override fun generate(prompt: String, params: GenerationParams): Flow<String> = flowOf(replies[minOf(n++, replies.size - 1)])
        override fun close() {}
    }

    @Test fun `Generator erzeugt Karten, verwirft Erfundenes und Dubletten`() = runTest {
        val good = """{"cloze": [{"satz": "Dabei entstehen Sauerstoff und Glucose aus Kohlenstoffdioxid und Wasser.", "luecke": "Glucose"},
            {"satz": "Pflanzen betreiben nachts Photosynthese mit Hilfe des Mondlichts und der Sterne am Himmel.", "luecke": "Mondlichts"},
            {"satz": "Dabei entstehen Sauerstoff und Glucose aus Kohlenstoffdioxid und Wasser.", "luecke": "Wasser"}]}"""
        val stats = GenerationStats()
        val cards = CardGenerator(Scripted(good, good)).generateCloze(chunk, n = 3, stats = stats)
        assertEquals(1, cards.size)
        assertEquals(CardKind.CLOZE, cards.first().kind)
        assertTrue(stats.rejectedQuestions >= 1 && stats.duplicates >= 1)
    }

    @Test fun `schon vorhandene Luecken werden nicht doppelt erzeugt`() = runTest {
        val good = """{"cloze": [{"satz": "Dabei entstehen Sauerstoff und Glucose aus Kohlenstoffdioxid und Wasser.", "luecke": "Glucose"}]}"""
        val first = CardGenerator(Scripted(good)).generateCloze(chunk, n = 1)
        val again = CardGenerator(Scripted(good)).generateCloze(chunk, n = 1, existingFronts = first.map { it.question })
        assertTrue(again.isEmpty())
    }

    @Test fun `Code wird erkannt, normaler Text nicht`() {
        assertTrue(ContentKind.isCode("```java\nint x = 1;\n```"))
        assertTrue(ContentKind.isCode("def partition(a, lo, hi):\n    pivot = a[hi]\n    i = lo\n    for j in range(lo, hi):\n        if a[j] < pivot:\n            i += 1\n    return i"))
        assertTrue(ContentKind.isCode("void quicksort(int[] a, int l, int r) {\n  if (l < r) {\n    int p = partition(a, l, r);\n    quicksort(a, l, p - 1);\n  }\n}"))
        assertFalse(ContentKind.isCode(chunk))
    }

    @Test fun `Code-Abschnitte bekommen den Code-Prompt und gelten als lernenswert`() {
        val code = "void quicksort(int[] a, int l, int r) {\n  if (l < r) {\n    int p = partition(a, l, r);\n    quicksort(a, l, p - 1);\n    quicksort(a, p + 1, r);\n  }\n}\n// teilt das Feld rekursiv am Pivot"
        assertTrue("Programmcode" in CardPrompts.questionPrompt(code, 2))
        assertTrue("Programmcode" !in CardPrompts.questionPrompt(chunk, 2))
        assertTrue(CardChunkFilter.isStudyWorthy(code.repeat(2)))
    }

    @Test fun `Beinahe-Dubletten werden ueber Wortueberlappung gefangen`() {
        val a = "Was ist der zyklische Elektronentransport in der Lichtreaktion?"
        val b = "Wie läuft der zyklische Elektronentransport in der Lichtreaktion ab?"
        assertTrue(CardQuality.wordOverlap(a, b) >= CardQuality.TEXT_DUP_OVERLAP)
        val v = floatArrayOf(1f, 0f)
        val near = floatArrayOf(0.94f, 0.3412f)      // Kosinus ca. 0,94: unter der reinen Schwelle
        assertTrue(CardQuality.isDuplicate(near, b, listOf(v to a)))
        assertFalse(CardQuality.isDuplicate(near, "Welche Rolle spielt Chlorophyll bei der Absorption von Licht?", listOf(v to a)))
    }

    @Test fun `verwandte aber verschiedene Fragen bleiben bei hoher Aehnlichkeit erhalten, wenn die Woerter abweichen`() {
        // an EmbeddingGemma gemessen: Kosinus 0,9568 für „Best Case“ gegen „Worst Case“ bei Wortüberlappung 0,67 – nur knapp über der Schwelle
        val v = floatArrayOf(1f, 0f)
        val a = floatArrayOf(0.93f, 0.3676f)         // Kosinus 0,93
        assertFalse(CardQuality.isDuplicate(a, "Worin besteht der Worst Case von Quicksort?", listOf(v to "Worin besteht der Best Case von Quicksort?")))
        assertTrue(CardQuality.isDuplicate(floatArrayOf(0.97f, 0.2431f), "Wie hoch ist die durchschnittliche Laufzeit von Quicksort?", listOf(v to "Welche Laufzeit hat Quicksort im Durchschnitt?")))
    }
}

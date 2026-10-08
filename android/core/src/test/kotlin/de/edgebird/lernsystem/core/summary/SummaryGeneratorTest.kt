package de.edgebird.lernsystem.core.summary

import de.edgebird.lernsystem.core.ai.GenerationParams
import de.edgebird.lernsystem.core.ai.LlmEngine
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNotEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class SummaryGeneratorTest {
    /** Antwortet der Reihe nach mit den vorbereiteten Texten (der letzte wiederholt sich) und merkt sich die Prompts. */
    private class Scripted(vararg replies: String) : LlmEngine {
        private val queue = ArrayDeque(replies.toList())
        val prompts = mutableListOf<String>()
        val maxTokens = mutableListOf<Int>()
        override suspend fun load() = Unit
        override fun generate(prompt: String, params: GenerationParams): Flow<String> = flow {
            prompts += prompt; maxTokens += params.maxTokens
            emit(if (queue.size > 1) queue.removeFirst() else queue.first())
        }
        override fun close() = Unit
    }

    private val section = SummarySection("Kosten", "Kosten sind bewerteter Güterverbrauch. Die Frist beträgt 14 Tage und der Satz 3,5 Prozent. ".repeat(3))

    @Test
    fun `Abschnitt wird zusammengefasst`() = runTest {
        val r = SummaryGenerator(Scripted("- Kosten sind **bewerteter Güterverbrauch**.\n- Frist 14 Tage."), "Skript").summarizeSection(section, 60)
        assertNotNull(r.text)
        assertTrue(r.unsupportedNumbers.isEmpty())
    }

    @Test
    fun `zu kurzer Abschnitt wird uebersprungen, ohne das Modell zu fragen`() = runTest {
        val llm = Scripted("x")
        val r = SummaryGenerator(llm, "Skript").summarizeSection(SummarySection("A", "kurz"), 60)
        assertEquals(SkipReason.TOO_SHORT, r.reason)
        assertTrue(llm.prompts.isEmpty())
    }

    @Test
    fun `leerer Marker ergibt keine Zusammenfassung`() = runTest {
        val r = SummaryGenerator(Scripted("(kein prüfungsrelevanter Inhalt)"), "S", SummarySpec(format = SummaryFormat.OUTLINE)).summarizeSection(section, 60)
        assertEquals(SkipReason.NOT_RELEVANT, r.reason)
        assertNull(r.text)
    }

    @Test
    fun `abgeschnittene Antwort wird mit mehr Tokens neu angefragt`() = runTest {
        val llm = Scripted("- Erster Punkt ist hier ausführlich beschrieben und lang genug,", "- Erster Punkt vollständig.\n- Zweiter Punkt vollständig und lang genug beschrieben.")
        val r = SummaryGenerator(llm, "S").summarizeSection(section, 60)
        assertTrue(r.text!!.contains("Zweiter Punkt"))
        assertTrue(llm.maxTokens[1] > llm.maxTokens[0])
    }

    @Test
    fun `erfundene Zahlen loesen einen Neuversuch aus, der bessere Versuch gewinnt`() = runTest {
        val llm = Scripted("- Die Frist beträgt 99 Tage.", "- Die Frist beträgt 14 Tage.")
        val r = SummaryGenerator(llm, "S").summarizeSection(section, 60)
        assertEquals("- Die Frist beträgt 14 Tage.", r.text)
        assertTrue(r.unsupportedNumbers.isEmpty())
        assertTrue(llm.prompts[1].contains("Zahlen, die im Quelltext nicht stehen"))
    }

    @Test
    fun `bleiben Zahlen unbelegt, wird der Befund gemeldet`() = runTest {
        val r = SummaryGenerator(Scripted("- Die Frist beträgt 99 Tage."), "S").summarizeSection(section, 60)
        assertEquals(listOf("99"), r.unsupportedNumbers)
    }

    @Test
    fun `Fehler im Modell ergibt uebersprungenen Abschnitt`() = runTest {
        val broken = object : LlmEngine {
            override suspend fun load() = Unit
            override fun generate(prompt: String, params: GenerationParams): Flow<String> = flow { error("kaputt") }
            override fun close() = Unit
        }
        assertEquals(SkipReason.FAILED, SummaryGenerator(broken, "S").summarizeSection(section, 60).reason)
    }

    @Test
    fun `Kurzfassung in einem Schritt, wenn alles ins Budget passt`() = runTest {
        val llm = Scripted("Ein Absatz mit der Kernaussage.")
        val md = SummaryGenerator(llm, "Skript").prose(listOf("A" to "- a1", "B" to "- b1"))
        assertEquals(1, llm.prompts.size)
        assertTrue(md!!.contains("Kernaussage"))
        assertTrue(llm.prompts[0].contains("### A") && llm.prompts[0].contains("### B"))
    }

    @Test
    fun `Kurzfassung verdichtet grosse Mengen stapelweise`() = runTest {
        val llm = Scripted("- verdichtet", "- verdichtet", "- verdichtet", "Absatz mit dem Ende.")
        val parts = (1..9).map { "Abschnitt $it" to "- " + "Inhalt ".repeat(100) }
        val md = SummaryGenerator(llm, "Skript", reduceBudget = 2000).prose(parts)
        assertTrue(llm.prompts.size >= 3, "erwartet mehrere Verdichtungsschritte, war ${llm.prompts.size}")
        assertTrue(llm.prompts.dropLast(1).all { "Verdichte sie" in it })
        assertTrue(md!!.contains("Ende"))
    }

    @Test
    fun `ohne Teile keine Kurzfassung`() = runTest { assertNull(SummaryGenerator(Scripted("x"), "S").prose(emptyList())) }

    @Test
    fun `Zusammensetzen der Abschnitte`() {
        val md = SummaryGenerator(Scripted("x"), "S").assemble("Skript", listOf("Seite 1" to "- a", "Seite 2" to "- b"), "Gemma")
        assertTrue(md.startsWith("# Zusammenfassung: Skript"))
        assertTrue("## Seite 1\n\n- a" in md && "## Seite 2\n\n- b" in md)
    }

    // ---- Einstellungen wirken sich aus ---------------------------------------------------------------------------------

    @Test
    fun `Rolle, Wuensche und Schalter landen im Prompt, die Regeln gegen Erfinden bleiben immer`() = runTest {
        val llm = Scripted("- Kosten sind bewerteter Güterverbrauch.")
        val spec = SummarySpec(role = SummaryRole.EDITOR, extra = "Fasse nur das Wesentliche zusammen", level = SummaryLevel.BEGINNER, includeExamples = true, cite = true, examFocus = true, language = SummaryLanguage.EN)
        SummaryGenerator(llm, "Skript", spec).summarizeSection(section, 60)
        val p = llm.prompts[0]
        assertTrue("Fasse nur das Wesentliche zusammen" in p)
        assertTrue("Einsteiger" in p && "Beispiel" in p && "Fundstelle" in p && "Prüfung" in p && "in English" in p)
        assertTrue("Erfinde nichts" in p)
        assertTrue("wissenschaftlicher Lektor" in spec.system && "erfindest nichts" in spec.system)
    }

    @Test
    fun `eigener Masterprompt ersetzt die Rolle, nicht aber die festen Regeln`() {
        val spec = SummarySpec(customRole = "Du bist ein Pirat.")
        assertTrue(spec.system.startsWith("Du bist ein Pirat."))
        assertTrue(SummarySpec.FIXED_SYSTEM in spec.system)
        assertFalse("Hochschul-Tutor" in spec.system)
    }

    @Test
    fun `Laenge steuert Stichpunktzahl und Token-Budget`() = runTest {
        val kurz = Scripted("- a ist ein ausreichend langer Punkt."); val lang = Scripted("- b ist ein ausreichend langer Punkt.")
        SummaryGenerator(kurz, "S").summarizeSection(section, 30)
        SummaryGenerator(lang, "S").summarizeSection(section, 150)
        assertTrue("2 bis 3 Stichpunkten" in kurz.prompts[0] && "7 bis 10 Stichpunkten" in lang.prompts[0])
        assertTrue("höchstens 21 Wörter" in kurz.prompts[0].replace("höchstens 20", "höchstens 21") || "höchstens 21 Wörter" in kurz.prompts[0] || "höchstens 15 Wörter" in kurz.prompts[0])
        assertTrue("höchstens 105 Wörter" in lang.prompts[0])   // 150 Wörter, mit 0,7 kalibriert
        assertTrue(lang.maxTokens[0] > kurz.maxTokens[0])
    }

    @Test
    fun `Abschnittsumfang folgt der Gesamtlaenge und bleibt in Grenzen`() {
        val s = SummarySpec(targetWords = 400)
        assertEquals(100, s.wordsPerSection(4))
        assertEquals(20, s.wordsPerSection(100))          // nicht unter dem Minimum
        assertEquals(200, SummarySpec(targetWords = 2000).wordsPerSection(2))   // nicht ueber dem Maximum
    }

    @Test
    fun `Fliesstext-Prompt nennt die Zielwortzahl`() = runTest {
        val llm = Scripted("Ein Text.")
        SummaryGenerator(llm, "S", SummarySpec(format = SummaryFormat.PROSE, targetWords = 250)).prose(listOf("A" to "- a"))
        assertTrue("etwa 250 Wörter" in llm.prompts.last())
    }

    @Test
    fun `Verdichten kuerzt nur, wenn die Zusammenfassung deutlich laenger als gewuenscht ist`() = runTest {
        val llm = Scripted("- kurz gefasst")
        val parts = (1..6).map { "Seite $it" to "- " + "wort ".repeat(120) }
        val unchanged = SummaryGenerator(llm, "S", SummarySpec(targetWords = 2000)).condense(parts)
        assertEquals(parts, unchanged); assertTrue(llm.prompts.isEmpty())
        val cut = SummaryGenerator(llm, "S", SummarySpec(targetWords = 200), reduceBudget = 1500).condense(parts)
        assertTrue(llm.prompts.isNotEmpty() && cut.size < parts.size)
        assertTrue("Kürze ihn auf etwa" in llm.prompts[0])
    }

    @Test
    fun `Glossar wird sortiert und ohne Dubletten zusammengefuehrt, ohne das Modell`() {
        val merged = GlossaryMerge.merge(listOf(
            "- **Kosten:** Güterverbrauch.\n- **Abschreibung:** Wertminderung eines Anlageguts.",
            "- **kosten:** Bewerteter Güterverbrauch einer Periode.\nunsinn ohne format",
        ))
        assertEquals(listOf("- **Abschreibung:** Wertminderung eines Anlageguts.", "- **kosten:** Bewerteter Güterverbrauch einer Periode."), merged)
    }

    @Test
    fun `Spec wird als JSON gespeichert und tolerant gelesen`() {
        val spec = SummarySpec(format = SummaryFormat.PROSE, targetWords = 321, role = SummaryRole.EXAM_COACH, extra = "Nur Formeln", cite = true, language = SummaryLanguage.EN)
        assertEquals(spec, SummarySpec.fromJson(spec.toJson()))
        assertEquals(SummarySpec(), SummarySpec.fromJson("kaputt"))
        assertEquals(SummarySpec(), SummarySpec.fromJson(null))
        assertEquals(SummaryFormat.GLOSSARY, SummarySpec.fromJson("""{"format":"GLOSSARY","unbekannt":1}""").format)
        assertEquals(SummarySpec.MAX_TARGET, SummarySpec.fromJson("""{"targetWords":999999}""").targetWords)
    }

    @Test
    fun `Fingerabdruck aendert sich nur bei Einstellungen, die den Abschnittstext veraendern`() {
        val a = SummarySpec(format = SummaryFormat.BULLETS)
        assertEquals(a.partsFingerprint(10), a.copy(format = SummaryFormat.PROSE).partsFingerprint(10))    // gleiche Abschnittsform
        assertNotEquals(a.partsFingerprint(10), a.copy(role = SummaryRole.EDITOR).partsFingerprint(10))
        assertNotEquals(a.partsFingerprint(10), a.copy(extra = "kurz").partsFingerprint(10))
        assertNotEquals(a.partsFingerprint(10), a.copy(format = SummaryFormat.OUTLINE).partsFingerprint(10))
    }

    @Test
    fun `zu langer Fliesstext wird mit Hinweis auf die Wortzahl neu angefragt, der kuerzere gewinnt`() = runTest {
        val lang = (1..300).joinToString(" ") { "wort$it" } + "."
        val kurz = (1..110).joinToString(" ") { "wort$it" } + "."
        val llm = Scripted(lang, kurz)
        val md = SummaryGenerator(llm, "S", SummarySpec(format = SummaryFormat.PROSE, targetWords = 100)).prose(listOf("A" to "- a"))
        assertEquals(2, llm.prompts.size)
        assertTrue("hatte 300 Wörter" in llm.prompts[1] && "höchstens 100 Wörter" in llm.prompts[1])
        assertEquals(110, SummaryGenerator.wordCount(md!!))
    }

    @Test
    fun `passender Fliesstext braucht keinen zweiten Versuch`() = runTest {
        val llm = Scripted((1..90).joinToString(" ") { "wort$it" } + ".")
        SummaryGenerator(llm, "S", SummarySpec(format = SummaryFormat.PROSE, targetWords = 100)).prose(listOf("A" to "- a"))
        assertEquals(1, llm.prompts.size)
    }

    @Test
    fun `Fettdruck im Fliesstext ist begrenzt`() {
        assertTrue("höchstens 5" in SummaryPrompts.rules(SummarySpec(format = SummaryFormat.PROSE)))
        assertTrue("höchstens 5" !in SummaryPrompts.rules(SummarySpec(format = SummaryFormat.BULLETS)))
    }

    /** Streamt in einzelnen Stücken (wie ein echtes Modell) und bricht beim Token-Limit ab. */
    private class Streaming(private val full: String) : LlmEngine {
        override suspend fun load() = Unit
        override fun generate(prompt: String, params: GenerationParams): Flow<String> = flow {
            val pieces = full.split(" ")
            for ((i, p) in pieces.withIndex()) { if (i >= params.maxTokens) break; emit(if (i == 0) p else " $p") }
        }
        override fun close() = Unit
    }

    @Test
    fun `Token-Limit erreicht - der unvollstaendige letzte Stichpunkt faellt weg`() = runTest {
        val bullets = (1..40).joinToString("\n") { "- Punkt $it ist hier ein vollständiger Satz mit genug Inhalt." }
        val r = SummaryGenerator(Streaming(bullets), "S").summarizeSection(section, 20)   // Budget 160 Token ⇒ Antwort wird abgeschnitten
        val last = r.text!!.lines().last()
        assertTrue(last.endsWith("Inhalt."), "letzte Zeile muss vollständig sein: $last")
    }

    @Test
    fun `Reste wie leere Fettmarker werden bereinigt`() {
        assertEquals("beschrieben, die Energie.", SummaryChecks.tidy("beschrieben,**** die   Energie ."))
    }

    @Test
    fun `Ueberschrift ohne Inhalt und geoeffneter Fettdruck gelten als abgeschnitten`() {
        assertTrue(SummaryChecks.looksTruncated("- Ein vollständiger Punkt mit genug Zeichen für die Prüfung hier.\n### Regulation des Elektronentrans"))
        assertTrue(SummaryChecks.looksTruncated("- Ein vollständiger Punkt mit genug Zeichen für die Prüfung hier.\n- **Eukaryot"))
        assertFalse(SummaryChecks.looksTruncated("- Ein vollständiger Punkt mit genug Zeichen für die Prüfung hier.\n- **Eukaryoten** haben einen Kern."))
    }

    @Test
    fun `Stichpunkt ohne Satzende wird bei Stichpunkten gekappt, bei Gegliedert bleibt er`() = runTest {
        val ok = "- Eine vollständige Aussage über die Zelle als kleinste lebende Einheit."
        val md = "$ok\n- **Vakuolen** sind große, membr"
        assertTrue(SummaryChecks.endsWithUnterminatedBullet(md))
        assertFalse(SummaryChecks.endsWithUnterminatedBullet("$ok\n- Zweiter vollständiger Punkt zur Struktur der Zelle und ihrer Organellen."))
        assertEquals(ok, SummaryGenerator(Scripted(md), "S").summarizeSection(section, 60).text)
        val outline = SummaryGenerator(Scripted(md), "S", SummarySpec(format = SummaryFormat.OUTLINE)).summarizeSection(section, 60).text
        assertTrue("membr" in outline!!)      // Gegliedert: Punkte ohne Satzende sind üblich
    }

    @Test
    fun `Glossar mit Obergrenze behaelt gleichmaessig verteilte Eintraege`() {
        val lines = (1..40).joinToString("\n") { "- **Begriff${"%02d".format(it)}:** Erklärung $it." }
        val merged = GlossaryMerge.merge(listOf(lines), maxEntries = 10)
        assertEquals(10, merged.size)
        assertTrue(merged.first().contains("Begriff01") && merged.any { it.contains("Begriff21") })   // über das ganze Dokument verteilt
    }

    @Test
    fun `Eintrag, der auf ein haengendes Wort endet, gilt als abgebrochen`() {
        assertTrue(SummaryChecks.looksTruncated("- **Plasmide:** Diese sind extrachromosomale, in sich geschlossene oder"))
        assertTrue(SummaryChecks.looksTruncated("Ein vollständiger Satz steht hier.\n- Die Zelle ist die kleinste Einheit der"))
        assertFalse(SummaryChecks.looksTruncated("- **Plasmide:** Diese sind extrachromosomale, in sich geschlossene DNA-Ringe."))
        assertFalse(SummaryChecks.looksTruncated("- **Mehrzeller:** Lebewesen, die aus mehr als nur einer Zelle bestehen"))
    }
}

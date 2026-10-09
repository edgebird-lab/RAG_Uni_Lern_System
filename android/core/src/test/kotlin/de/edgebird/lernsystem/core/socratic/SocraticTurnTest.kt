// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.socratic

import de.edgebird.lernsystem.core.ai.GenerationParams
import de.edgebird.lernsystem.core.ai.LlmEngine
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test

class SocraticTurnTest {
    private class Fake(private val answers: List<String>) : LlmEngine {
        val prompts = mutableListOf<String>()
        val temps = mutableListOf<Float>()
        override suspend fun load() {}
        override fun generate(prompt: String, params: GenerationParams): Flow<String> {
            prompts += prompt; temps += params.temperature
            return flowOf(answers[minOf(prompts.size, answers.size) - 1])
        }
        override fun close() {}
    }

    private fun ai(t: String) = Turn(false, t)
    private fun me(t: String) = Turn(true, t)

    @Test fun `offene Frage wird am Ende erkannt, rhetorische mitten im Text nicht`() {
        assertEquals("Was ist ein Pfeil?", SocraticText.lastQuestion("Das ist gut. Was ist ein Pfeil?"))
        assertEquals("Warum ist das so?", SocraticText.lastQuestion("Warum ist das so? Konzentrieren wir uns auf den Pfeil."))
        assertEquals("", SocraticText.lastQuestion("Wer weiß das schon? Der Pfeil hat Länge und Richtung, das ist die Definition aus der Vorlesung und sie gilt in der Ebene ebenso wie im Raum und bleibt bei jeder Verschiebung des Pfeils unverändert gültig."))
        assertEquals("", SocraticText.lastQuestion("Eine Erklärung ohne Frage."))
        assertEquals("Was bedeutet z. B. das hier?", SocraticText.lastQuestion("Sehr gut. Was bedeutet z. B. das hier?"))
    }

    @Test fun `Phase und Gespraechsstand`() {
        assertEquals(Phase.START, SocraticDialog.phase(emptyList()))
        val open = listOf(ai("Was ist ein Vektor?"), me("Ein Pfeil."))
        assertEquals(Phase.OPEN, SocraticDialog.phase(open))
        val resolved = open + ai("Ein Vektor hat Betrag und Richtung. Damit ist das geklärt.")
        assertEquals(Phase.RESOLVED, SocraticDialog.phase(resolved))
        val s = SocraticDialog.buildState(open, "Vektoren") { it == "Hinweis" }
        assertEquals("Was ist ein Vektor?", s.goal)
        assertEquals(listOf("Ein Pfeil."), s.answers)
        // nach der Aufloesung zaehlen alte Antworten nicht mehr
        assertTrue(SocraticDialog.buildState(resolved, "Vektoren").answers.isEmpty())
    }

    @Test fun `Steuerimpulse zaehlen nicht als Antwort`() {
        val s = SocraticDialog.buildState(listOf(ai("Was ist ein Vektor?"), me("Hinweis")), "V") { it == "Hinweis" }
        assertTrue(s.answers.isEmpty())
    }

    @Test fun `Nachricht enthaelt keinen Verlauf als Chat-Turns, aber den Stand und die Aufgabe`() {
        val s = SocraticDialog.buildState(listOf(ai("Was ist ein Vektor?"), me("Ein Pfeil.")), "Vektoren")
        val msg = SocraticDialog.userMessage(s, Kind.HINT, null, "", "[Quelle 1] Text")
        assertTrue("Deine offene Frage" in msg && "„Was ist ein Vektor?“" in msg)
        assertTrue("Ein Pfeil." in msg)
        assertTrue("EINEN kurzen Denkanstoß" in msg)
        assertTrue(msg.trimEnd().endsWith("DIESELBE Frage noch einmal, einfacher oder in kleineren Schritten."))
    }

    @Test fun `Pruefung erkennt Wiederholung, Unterlagenbezug, dritte Person und fehlende Frage`() {
        val prev = "Das ist ein guter erster Schritt. Können Sie mir noch sagen, was ein Vektor ist?"
        val st = DialogState("V", Phase.OPEN, goal = "Was ist ein Vektor?", asked = listOf("Was ist ein Vektor?"), aiTexts = listOf(prev))
        assertTrue("wiederholung" in SocraticDialog.validate(prev, Kind.ANSWER, st))
        assertTrue("unterlagen_bezug" in SocraticDialog.validate("Schau dir Abbildung 2 an. Was siehst du dort genau?", Kind.ANSWER, st))
        assertTrue("dritte_person" in SocraticDialog.validate("Die Studierenden haben das richtig. Was ist der Betrag eines Vektors?", Kind.ANSWER, st))
        assertTrue("keine_frage" in SocraticDialog.validate("Das stimmt so, gut gemacht und weiter so.", Kind.ANSWER, st))
        assertTrue("nicht_aufgeloest" in SocraticDialog.validate("Das ist die Lösung, aber was meinst du dazu?", Kind.RESOLVE, st))
        assertTrue(SocraticDialog.validate("Genau, ein Vektor hat Betrag und Richtung. Wie berechnet man den Betrag?", Kind.ANSWER, st).isEmpty())
        assertTrue("frage_wiederholt" in SocraticDialog.validate("Gut. Was ist ein Vektor?", Kind.NEXT, st))
        assertEquals(listOf("leer"), SocraticDialog.validate("Ok", Kind.ANSWER, st))
    }

    @Test fun `Aufraeumen entfernt Labels und Quellenverweise ausser beim Aufloesen`() {
        assertEquals("Gut. Was ist der Betrag?", SocraticText.clean("Rückmeldung: Gut. Was ist der Betrag? [Quelle 2]", Kind.ANSWER))
        assertEquals("Das gilt [Quelle 1].", SocraticText.clean("Das gilt [Quelle 1].", Kind.RESOLVE))
        assertEquals("Wie war das gemeint?", SocraticText.clean("„Wie war das gemeint?“", Kind.START))
    }

    @Test fun `schlechte Antwort wird neu versucht, zweiter Versuch ist besser`() = runBlocking {
        val st = DialogState("V", Phase.OPEN, goal = "Was ist ein Vektor?", asked = listOf("Was ist ein Vektor?"))
        val llm = Fake(listOf("Schau in Abbildung 3 nach. Was siehst du?", "Genau, er hat Betrag und Richtung. Wie berechnet man den Betrag?"))
        val r = SocraticDialog.generateTurn(llm, Kind.ANSWER, null, st, "Ein Pfeil", "ctx")
        assertEquals(2, r.attempts); assertFalse(r.fallback); assertTrue(r.problems.isEmpty())
        assertTrue("KORREKTUR" in llm.prompts[1] && "Abbildungen, Quellen oder Nummern" in llm.prompts[1])
        assertTrue(llm.temps[1] > llm.temps[0])
    }

    @Test fun `bleibt es hart schlecht, kommt die ehrliche Rueckfallantwort`() = runBlocking {
        val prev = "Das ist ein guter erster Schritt. Können Sie mir noch sagen, was ein Vektor ist?"
        val st = DialogState("Vektoren", Phase.OPEN, goal = "Was ist ein Vektor?", asked = listOf("Was ist ein Vektor?"), aiTexts = listOf(prev))
        val r = SocraticDialog.generateTurn(Fake(listOf(prev)), Kind.HINT, null, st, "", "ctx")
        assertTrue(r.fallback)
        assertEquals(3, r.attempts)
        assertTrue(SocraticText.isOpenQuestion(r.text))
    }

    @Test fun `Rueckfall beim Aufloesen zeigt die Stelle aus den Unterlagen`() = runBlocking {
        val st = DialogState("V", Phase.OPEN, goal = "Was ist ein Vektor?", aiTexts = listOf("x".repeat(50) + "?"))
        val chunk = "Ein Vektor ist eine Größe mit Betrag und Richtung und wird durch einen Pfeil dargestellt, dessen Länge dem Betrag entspricht und dessen Spitze die Richtung zeigt."
        val r = SocraticDialog.generateTurn(Fake(listOf("kurz")), Kind.RESOLVE, null, st, "", "ctx", fallbackChunks = listOf(chunk))
        assertTrue(r.fallback)
        assertTrue("Ein Vektor ist eine Größe" in r.text)
    }

    @Test fun `Aehnlichkeit ignoriert Satzzeichen und Quellenmarker`() {
        assertTrue(SocraticText.similarity("Was ist ein Vektor? [Quelle 1]", "was ist ein vektor") > 0.99)
        assertTrue(SocraticText.similarity("Was ist ein Vektor?", "Wie berechnet man eine Determinante?") < 0.5)
    }

    @Test fun `beim Aufloesen wird eine angehaengte Frage gestrichen, eine reine Frage nicht`() {
        val erklaerung = "Bei der Photosynthese wandeln Pflanzen Lichtenergie in chemische Energie um und bilden dabei Glucose und Sauerstoff. Was denkst du dazu?"
        val cleaned = SocraticText.clean(erklaerung, Kind.RESOLVE)
        assertFalse(cleaned.endsWith("?"))
        assertTrue(cleaned.startsWith("Bei der Photosynthese"))
        assertEquals("Was denkst du, welche Schritte beteiligt sind?", SocraticText.clean("Was denkst du, welche Schritte beteiligt sind?", Kind.RESOLVE))
    }

    @Test fun `beim Aufloesen steht die Frage als zu erklaerende Frage im Stand`() {
        val st = DialogState("V", Phase.OPEN, goal = "Was ist ein Vektor?")
        val msg = SocraticDialog.userMessage(st, Kind.RESOLVE, null, "", "ctx")
        assertTrue("nicht erneut stellen" in msg)
        assertFalse("Deine offene Frage" in msg)
    }

    @Test fun `Urteil wird aus der Modellantwort gelesen`() {
        assertEquals(Verdict.CORRECT, SocraticGrader.parse("richtig"))
        assertEquals(Verdict.CORRECT, SocraticGrader.parse("Richtig."))
        assertEquals(Verdict.PARTIAL, SocraticGrader.parse("teilweise richtig"))
        assertEquals(Verdict.PARTIAL, SocraticGrader.parse("Die Antwort ist teilweise korrekt"))
        assertEquals(Verdict.WRONG, SocraticGrader.parse("Falsch!"))
        assertEquals(Verdict.WRONG, SocraticGrader.parse("Das ist nicht richtig."))
        assertNull(SocraticGrader.parse(""))
        assertNull(SocraticGrader.parse("Vielleicht"))
    }

    @Test fun `leere oder inhaltslose Antwort ist falsch, ohne das Modell zu fragen`() = runBlocking {
        val llm = Fake(listOf("richtig"))
        assertEquals(Verdict.WRONG, SocraticGrader.grade(llm, "Was ist ein Vektor?", " ", "ctx"))
        assertTrue(llm.prompts.isEmpty())
        assertEquals(Verdict.CORRECT, SocraticGrader.grade(llm, "Was ist ein Vektor?", "Eine Größe mit Betrag und Richtung", "ctx"))
        assertTrue("GENAU EINEM Wort" in llm.prompts[0] && "ANTWORT: Eine Größe" in llm.prompts[0])
    }

    @Test fun `die Bewertung wird dem Tutor verbindlich vorgegeben`() {
        val st = DialogState("V", Phase.OPEN, goal = "Was ist ein Vektor?")
        val msg = SocraticDialog.userMessage(st, Kind.ANSWER, null, "Eine Zahl", "ctx", verdict = Verdict.WRONG)
        assertTrue("verbindlich" in msg && "noch nicht richtig" in msg)
        assertFalse("verbindlich" in SocraticDialog.userMessage(st, Kind.ANSWER, null, "Eine Zahl", "ctx"))
    }

    @Test fun `Bewertungskriterien stehen im Pruefer-Prompt`() {
        val p = SocraticGrader.prompt("Was ist ein Vektor?", "Ein Pfeil", "ctx")
        assertTrue("teilweise: Sie enthält Zutreffendes" in p && "falsch: Sie widerspricht" in p)
    }
}

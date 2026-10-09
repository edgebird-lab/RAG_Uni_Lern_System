// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core

import de.edgebird.lernsystem.core.cards.CardPrompts
import de.edgebird.lernsystem.core.cards.CardProblem
import de.edgebird.lernsystem.core.cards.CardQuality
import de.edgebird.lernsystem.core.cards.Cloze
import de.edgebird.lernsystem.core.i18n.Lang
import de.edgebird.lernsystem.core.i18n.tr
import de.edgebird.lernsystem.core.quiz.MultipleChoice
import de.edgebird.lernsystem.core.rag.Citations
import de.edgebird.lernsystem.core.rag.Passage
import de.edgebird.lernsystem.core.rag.RagPromptBuilder
import de.edgebird.lernsystem.core.socratic.DialogState
import de.edgebird.lernsystem.core.socratic.Kind
import de.edgebird.lernsystem.core.socratic.Phase
import de.edgebird.lernsystem.core.socratic.SocraticDialog
import de.edgebird.lernsystem.core.socratic.SocraticGrader
import de.edgebird.lernsystem.core.socratic.SocraticPrompts
import de.edgebird.lernsystem.core.socratic.Verdict
import de.edgebird.lernsystem.core.summary.SummaryChecks
import de.edgebird.lernsystem.core.summary.SummaryFormat
import de.edgebird.lernsystem.core.summary.SummaryPrompts
import de.edgebird.lernsystem.core.summary.SummarySpec
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNotEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/** Englische Fassung: Anweisungen an die KI und Prüfregeln müssen vollständig auf Englisch vorliegen. */
class I18nEnglishTest {
    private inline fun <T> english(block: () -> T): T {
        val old = Lang.current
        Lang.current = Lang.EN
        try { return block() } finally { Lang.current = old }
    }

    /** Typische deutsche Funktionswörter und Umlaute: ein englischer Prompt darf sie nicht enthalten (Beispieltexte ausgenommen). */
    private val GERMAN = Regex("""[äöüß]|\b(und|oder|nicht|mit|der|die|das|ein|eine|Frage|Antwort|Abschnitt|Quelle|Wörter)\b""")

    private fun assertEnglish(label: String, text: String) {
        val hit = GERMAN.find(text)
        assertTrue(hit == null, "$label enthält Deutsch: „${hit?.value}“ in …${text.substring(maxOf(0, (hit?.range?.first ?: 0) - 40), minOf(text.length, (hit?.range?.last ?: 0) + 40))}…")
    }

    @Test fun trSwitchesWithLang() {
        assertEquals("Hallo", tr("Hallo", "Hello"))
        english { assertEquals("Hello", tr("Hallo", "Hello")) }
        assertEquals("Hello", tr("Hallo", "Hello", Lang.EN))
    }

    @Test fun langTags() {
        assertEquals(Lang.EN, Lang.fromTag("en-US")); assertEquals(Lang.DE, Lang.fromTag("de")); assertEquals(Lang.DE, Lang.default("fr")); assertEquals(Lang.EN, Lang.default("en"))
    }

    @Test fun ragPromptIsEnglish() = english {
        val p = RagPromptBuilder.build("What is a heap?", listOf(Passage("a.pdf, Page 1", "A heap is a tree.")))
        assertEnglish("RAG system", p.system); assertEnglish("RAG user", p.user.substringBefore("A heap"))
        assertTrue(RagPromptBuilder.NOT_FOUND in p.system)
        assertEquals("Not found in the material.", RagPromptBuilder.NOT_FOUND)
        assertTrue(Citations.isNotFound("Not found in the material."))
        assertTrue(RagPromptBuilder.isNotFound("Not found in the material"))
    }

    @Test fun summaryPromptsAreEnglish() = english {
        val spec = SummarySpec(language = de.edgebird.lernsystem.core.summary.SummaryLanguage.EN)
        for (f in SummaryFormat.entries) {
            val p = SummaryPrompts.section(spec.copy(format = f), "doc", "Heaps", "A heap is a tree.", 80)
            assertEnglish("section $f", p.replace("A heap is a tree.", "").replace("doc", ""))
        }
        assertEnglish("prose", SummaryPrompts.proseFinal(spec, "doc", "- x").replace("- x", ""))
        assertEnglish("overview", SummaryPrompts.overview(spec, "Subj", "text", 100).replace("Subj", ""))
        assertEnglish("system", spec.system)
        assertEquals("(no exam-relevant content)", SummaryChecks.EMPTY_MARKER)
        assertTrue(SummaryChecks.isEmptySection("(no exam-relevant content)"))
        assertTrue(SummaryChecks.isEmptySection("(kein prüfungsrelevanter Inhalt)"))
        assertTrue(SummaryChecks.looksTruncated("This summary of the chapter is cut off right in the middle of a sentence and"))
    }

    @Test fun cardPromptsAreEnglish() = english {
        assertEnglish("question", CardPrompts.questionPrompt("A heap is a complete binary tree with the heap property.", 2).substringBefore("Passage:"))
        assertEnglish("code", CardPrompts.codeQuestionPrompt("x", 2).substringBefore("Passage:"))
        assertEnglish("answer", CardPrompts.answerPrompt("What is a heap?", "x").substringBefore("Passage:").replace("What is a heap?", ""))
        assertEnglish("system", CardPrompts.questionSystem() + CardPrompts.answerSystem())
        assertEnglish("cloze", Cloze.prompt("x", 2).substringBefore("Passage:"))
        assertEnglish("mc", MultipleChoice.prompt("x").substringBefore("Passage:") + MultipleChoice.system())
    }

    @Test fun englishQuestionsAreRecognised() {
        assertTrue(CardPrompts.isQuestion("What is the time complexity of heapsort?"))
        assertTrue(CardPrompts.isQuestion("Explain how the partition step of quicksort works"))
        assertFalse(CardPrompts.isQuestion("Heapsort"))
        assertEquals("Heap sort", CardPrompts.cleanAnswer("Answer: Heap sort"))
    }

    @Test fun englishCardQualityRules() = english {
        assertTrue(CardProblem.SOURCE_REFERENCE in CardQuality.questionProblems("What does Figure 2 show about the heap?"))
        assertTrue(CardProblem.SOURCE_REFERENCE in CardQuality.questionProblems("According to the text, what is a heap?"))
        assertTrue(CardProblem.CONTEXT in CardQuality.questionProblems("Why is this step necessary?").plus(CardQuality.questionProblems("What happens in this context to the given figure?")))
        assertTrue(CardQuality.questionProblems("What is the worst-case running time of quicksort and why?").isEmpty())
        assertTrue(CardQuality.questionProblems("What?").isNotEmpty())
        assertTrue(CardQuality.retryHint(listOf(CardProblem.CONTEXT)).startsWith("\n\nIMPORTANT"))
        assertEquals("too vague", CardProblem.VAGUE.label)
    }

    @Test fun socraticPromptsAreEnglish() = english {
        val state = DialogState("Heaps", Phase.OPEN, goal = "What is a heap?", asked = listOf("What is a heap?"), answers = listOf("a tree"))
        for (k in Kind.entries) {
            val msg = SocraticDialog.userMessage(state, k, "hint_limit", "a tree", "[Source 1] A heap is a tree.", verdict = Verdict.PARTIAL)
            assertEnglish("socratic $k", msg.replace("a tree", "").replace("What is a heap?", "").replace("A heap is a tree.", ""))
        }
        assertEnglish("system", SocraticPrompts.system())
        assertEnglish("grader", SocraticGrader.prompt("What is a heap?", "a tree", "ctx").replace("What is a heap?", ""))
    }

    @Test fun socraticValidationUnderstandsEnglish() = english {
        val state = DialogState("Heaps", Phase.OPEN, goal = "What is a heap?")
        val bad = SocraticDialog.validate("Look at Figure 3 on the slide. What property holds there?", Kind.HINT, state)
        assertTrue("unterlagen_bezug" in bad, bad.toString())
        val third = SocraticDialog.validate("The student seems unsure. What do you think a heap is?", Kind.HINT, state)
        assertTrue("dritte_person" in third, third.toString())
        assertTrue(SocraticDialog.validate("Think about a tree where every parent is larger than its children. Which tree is that?", Kind.HINT, state).isEmpty())
    }

    @Test fun verdictParsingEnglishAndGerman() {
        assertEquals(Verdict.CORRECT, SocraticGrader.parse("correct")); assertEquals(Verdict.PARTIAL, SocraticGrader.parse("Partly.")); assertEquals(Verdict.WRONG, SocraticGrader.parse("wrong"))
        assertEquals(Verdict.CORRECT, SocraticGrader.parse("richtig")); assertEquals(Verdict.PARTIAL, SocraticGrader.parse("teilweise")); assertEquals(Verdict.WRONG, SocraticGrader.parse("falsch"))
        assertEquals(Verdict.WRONG, SocraticGrader.parse("That is not correct"))
        english { assertEquals("correct", Verdict.CORRECT.label) }
        assertEquals("richtig", Verdict.CORRECT.label)
    }

    @Test fun germanStaysUnchanged() {
        assertNotEquals(RagPromptBuilder.build("x", emptyList(), lang = Lang.EN).system, RagPromptBuilder.build("x", emptyList()).system)
        assertEquals("Nicht im Material gefunden.", RagPromptBuilder.NOT_FOUND)
        assertTrue(CardProblem.SOURCE_REFERENCE in CardQuality.questionProblems("Was zeigt Abbildung 2 über den Heap?"))
    }
}

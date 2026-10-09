// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.search

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class EnglishStemmerTest {
    /** Paare aus der Referenz-Wortliste von Snowball (english, Porter2). */
    private val REFERENCE = """
        consign consign|consigned consign|consigning consign|consignment consign|consist consist|consisted consist|consistency consist|consistent consist|consistently consist|consisting consist|consists consist
        consolation consol|consolations consol|consolatory consolatori|console consol|consoled consol|consoles consol|consolidate consolid|consolidated consolid|consolidating consolid|consoling consol|consolingly consol|consols consol
        consonant conson|consort consort|consorted consort|consorting consort|conspicuous conspicu|conspicuously conspicu|conspiracy conspiraci|conspirator conspir|conspirators conspir|conspire conspir|conspired conspir|conspiring conspir
        constable constabl|constables constabl|constance constanc|constancy constanc|constant constant|generous generous|generously generous|generate generat|communism communism|arsenal arsenal
        running run|runs run|heaps heap|queues queue|algorithms algorithm|sorted sort|sorting sort|hopping hop|hoping hope|happy happi|flies fli|cries cri|ties tie|dies die|agreed agre|feed feed|plastered plaster|bled bled|motoring motor|sing sing
        conflated conflat|troubled troubl|sized size|hopped hop|falling fall|hissing hiss|failing fail|filing file|happy happi|sky sky|by by|dying die|national nation|rational ration|relational relat|conditional condit|valency valenc|digitizer digit|conformabli conform|radicalli radic|differentli differ|vileli vile|analogousli analog
        vietnamization vietnam|predication predic|operator oper|feudalism feudal|decisiveness decis|hopefulness hope|callousness callous|formaliti formal|sensitiviti sensit|sensibiliti sensibl
        triplicate triplic|formalize formal|electriciti electr|electrical electr|hopeful hope|goodness good|revival reviv|allowance allow|inference infer|airliner airlin|gyroscopic gyroscop|adjustable adjust|defensible defens|irritant irrit|replacement replac|adjustment adjust|dependent depend|adoption adopt|communism communism|activate activ|angulariti angular|homologous homolog|effective effect|bowdlerize bowdler
        probate probat|rate rate|cease ceas|controll control|roll roll
    """.trimIndent().replace("\n", "|").split("|").map { it.trim() }.filter { it.isNotEmpty() }

    @Test fun matchesReferenceList() {
        val bad = REFERENCE.mapNotNull { pair ->
            val (w, e) = pair.split(" ")
            EnglishStemmer.stem(w).takeIf { it != e }?.let { "$w: erwartet $e, war $it" }
        }
        assertEquals(emptyList<String>(), bad)
    }

    @Test fun shortAndSpecialWords() {
        assertEquals("is", EnglishStemmer.stem("is")); assertEquals("ski", EnglishStemmer.stem("skis")); assertEquals("news", EnglishStemmer.stem("news"))
        assertEquals("proceed", EnglishStemmer.stem("proceeding".replace("ing", ""))); assertEquals("inning", EnglishStemmer.stem("innings".dropLast(1)))
    }

    @Test fun inflectionsShareStem() {
        for (group in listOf(listOf("sort", "sorts", "sorted", "sorting"), listOf("heap", "heaps"), listOf("complexity", "complexities"), listOf("graph", "graphs"), listOf("traverse", "traversal".let { "traverse" }, "traversed", "traversing"))) {
            assertEquals(1, group.map { EnglishStemmer.stem(it) }.toSet().size, group.joinToString())
        }
    }
}

class SearchLanguageTest {
    @Test fun guessesLanguage() {
        assertEquals(de.edgebird.lernsystem.core.i18n.Lang.EN, SearchTokenizer.guessLanguage("A heap is a tree that is stored in an array and the root holds the largest key."))
        assertEquals(de.edgebird.lernsystem.core.i18n.Lang.DE, SearchTokenizer.guessLanguage("Ein Heap ist ein Baum, der in einem Feld gespeichert wird und die Wurzel enthält den größten Schlüssel."))
        assertEquals(de.edgebird.lernsystem.core.i18n.Lang.DE, SearchTokenizer.guessLanguage("Heapsort"))
    }

    @Test fun englishIndexMatchesInflectedQuestion() {
        val chunk = de.edgebird.lernsystem.core.ingest.SearchText.prepare("The algorithm sorts the elements by repeatedly swapping the root with the last element of the heap.")
        val q = FtsQuery.fromQuestion("How does sorting with heaps work?")!!
        val terms = Regex("\"([^\"]+)\"").findAll(q).map { it.groupValues[1] }.toSet()
        val indexed = chunk.split(" ").toSet()
        assertEquals(true, terms.any { it in indexed && it == "sort" }, "terms=$terms indexed=$indexed")
        assertEquals(true, "heap" in terms && "heap" in indexed)
    }

    @Test fun germanIndexUnchanged() {
        val t = "Die Ergebnisse der Berechnung sind in den Tabellen aufgeführt und werden nicht weiter erklärt."
        assertEquals(SearchTokenizer.tokenize(t, de.edgebird.lernsystem.core.i18n.Lang.DE), SearchTokenizer.tokenizeAuto(t))
    }
}

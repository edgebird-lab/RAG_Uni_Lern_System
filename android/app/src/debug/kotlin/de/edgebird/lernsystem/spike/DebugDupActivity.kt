// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.spike

import android.app.Activity
import android.os.Bundle
import android.view.WindowManager
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.ai.VectorCodec
import de.edgebird.lernsystem.core.cards.CardQuality
import kotlinx.coroutines.runBlocking
import java.io.File

/** Nur Debug: Ähnlichkeit (EmbeddingGemma) und Wortüberlappung für handgelabelte Fragepaare, um die Dublettenschwellen zu kalibrieren. */
class DebugDupActivity : Activity() {
    private val dups = listOf(
        "Was versteht man unter oxygener Photosynthese?" to "Wie ist oxygene Photosynthese definiert?",
        "Welche Rolle spielt ATP bei der Photosynthese?" to "Welche Funktion hat ATP in der Photosynthese?",
        "Wie funktioniert der zyklische Elektronentransport?" to "Was ist der zyklische Elektronentransport und wie läuft er ab?",
        "Was ist der Calvin-Zyklus?" to "Erkläre den Calvin-Zyklus.",
        "Welche Laufzeit hat Quicksort im Durchschnitt?" to "Wie hoch ist die durchschnittliche Laufzeit von Quicksort?",
        "Was ist ein Pivotelement bei Quicksort?" to "Was versteht man bei Quicksort unter dem Pivotelement?",
        "Wie wird bei Quicksort das Feld partitioniert?" to "Wie läuft die Partitionierung bei Quicksort ab?",
        "Was ist der Unterschied zwischen Prokaryoten und Eukaryoten?" to "Wodurch unterscheiden sich Prokaryoten von Eukaryoten?",
        "Welche Aufgabe haben Ribosomen?" to "Wofür sind Ribosomen zuständig?",
        "Was ist ein Chloroplast?" to "Was versteht man unter einem Chloroplasten?",
        "Wie berechnet man den Wirkungsgrad der Photosynthese?" to "Wie wird der Wirkungsgrad bei der Photosynthese berechnet?",
        "Welche Funktion haben Mitochondrien?" to "Was leisten Mitochondrien in der Zelle?",
        "Was ist die Lichtreaktion der Photosynthese?" to "Wie läuft die Lichtreaktion bei der Photosynthese ab?",
        "Worin besteht der Worst Case von Quicksort?" to "Wann tritt bei Quicksort der schlechteste Fall auf?",
        "Was bewirkt die Photolyse des Wassers?" to "Welche Bedeutung hat die Photolyse von Wasser?",
    )
    private val distinct = listOf(
        "Was ist oxygene Photosynthese?" to "Was ist anoxygene Photosynthese?",
        "Welche Rolle spielt ATP bei der Photosynthese?" to "Welche Rolle spielt NADPH bei der Photosynthese?",
        "Wie funktioniert der zyklische Elektronentransport?" to "Wie funktioniert der pseudozyklische Elektronentransport?",
        "Was ist der Calvin-Zyklus?" to "Wo findet der Calvin-Zyklus statt?",
        "Welche Laufzeit hat Quicksort im Durchschnitt?" to "Welche Laufzeit hat Quicksort im schlechtesten Fall?",
        "Was ist ein Pivotelement bei Quicksort?" to "Wie wählt man das Pivotelement bei Quicksort?",
        "Wie wird bei Quicksort das Feld partitioniert?" to "Warum ist Quicksort nicht stabil?",
        "Was sind Prokaryoten?" to "Was sind Eukaryoten?",
        "Welche Aufgabe haben Ribosomen?" to "Welche Aufgabe haben Zentriolen?",
        "Was ist ein Chloroplast?" to "Was ist ein Mitochondrium?",
        "Wie berechnet man den Wirkungsgrad der Photosynthese?" to "Wovon hängt der Wirkungsgrad der Photosynthese ab?",
        "Welche Funktion haben Mitochondrien?" to "Wie sind Mitochondrien aufgebaut?",
        "Was ist die Lichtreaktion der Photosynthese?" to "Was ist die Dunkelreaktion der Photosynthese?",
        "Worin besteht der Best Case von Quicksort?" to "Worin besteht der Worst Case von Quicksort?",
        "Was bewirkt die Photolyse des Wassers?" to "Welche Produkte entstehen bei der Photolyse des Wassers?",
        "Was ist DNA?" to "Was ist RNA?",
        "Welche Aufgabe hat der Zellkern?" to "Wie ist die Kernhülle aufgebaut?",
        "Wie viele Chromosomen hat die menschliche Zelle?" to "Wie viele Chromosomen haben Bakterien?",
        "Was ist Quicksort?" to "Was ist Mergesort?",
        "Welche Bedeutung hat die Photosynthese für den Sauerstoffgehalt der Atmosphäre?" to "Welche Bedeutung hat die Photosynthese für den Kohlenstoffkreislauf?",
        "Was ist die Rolle des Cytochrom-b6f-Komplexes?" to "Was ist die Rolle des Photosystems II?",
        "Wie unterscheidet sich Quicksort von Bubblesort in der Laufzeit?" to "Wie unterscheidet sich Quicksort von Mergesort im Speicherbedarf?",
        "Was sind Vakuolen?" to "Welche Funktion haben Vakuolen in Pflanzenzellen?",
        "Was ist das Zellskelett?" to "Welche Filamente gehören zum Zellskelett?",
        "Was ist Zytologie?" to "Was ist ein Einzeller?",
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContentView(android.widget.TextView(this).apply { text = "Dubletten-Kalibrierung läuft …"; textSize = 24f; setPadding(48, 200, 48, 48) })
        if (savedInstanceState != null) return
        val out = File(filesDir, "debug-out").apply { mkdirs() }.resolve("dup.txt")
        Thread {
            val graph = (application as LernsystemApp).graph
            runBlocking {
                try {
                    val emb = graph.sharedEmbedder.also { it.load() }
                    val sb = StringBuilder()
                    for ((label, pairs) in listOf("DUP" to dups, "DIST" to distinct)) for ((a, b) in pairs) {
                        val v = emb.embed(listOf(a, b)).map { VectorCodec.normalize(it) }
                        sb.append("$label;${"%.4f".format(VectorCodec.dot(v[0], v[1]))};${"%.3f".format(CardQuality.wordOverlap(a, b))};$a;$b\n")
                    }
                    out.writeText(sb.toString() + "FERTIG\n")
                } catch (e: Throwable) { out.writeText("FEHLER $e\n") }
                runOnUiThread { finish() }
            }
        }.start()
    }
}

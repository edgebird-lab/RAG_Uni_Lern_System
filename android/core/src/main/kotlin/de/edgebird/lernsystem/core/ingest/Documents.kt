// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.ingest

enum class BlockKind { TEXT, SLIDE }

/** Ein zusammenhängender Textblock, z. B. eine PDF-Seite oder eine Folie. */
data class Block(val text: String, val page: Int? = null, val kind: BlockKind = BlockKind.TEXT)

/** Ergebnis des Ladens einer Datei: Volltext plus seiten-/blockweise Zerlegung. */
data class LoadedDoc(
    val text: String,
    val blocks: List<Block>,
    val isMarkdown: Boolean = false,
    /** Anzahl Seiten ohne extrahierbaren Text (z. B. gescannte Seiten). */
    val emptyPages: Int = 0,
)

/** Ein Textabschnitt für den Index mit Herkunftsangabe. */
data class Chunk(
    val text: String,
    /** Anzeigetext der Fundstelle, z. B. „Seite 12“ oder der Überschriften-Pfad. */
    val location: String,
    val page: Int? = null,
    val headerPath: String? = null,
    val index: Int = 0,
)

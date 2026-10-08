package de.edgebird.lernsystem.core.summary

import de.edgebird.lernsystem.core.summary.MarkdownLite.Block
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class MarkdownLiteTest {
    @Test
    fun `Ueberschriften, Listen und Absaetze`() {
        val blocks = MarkdownLite.parse("# Titel\n\nErste Zeile\nzweite Zeile.\n\n## Teil\n\n- Punkt eins\n  - eingerückt\n* Punkt zwei\n1. Nummer")
        assertEquals(
            listOf(
                Block.Heading(1, "Titel"), Block.Paragraph("Erste Zeile zweite Zeile."), Block.Heading(2, "Teil"),
                Block.Bullet("Punkt eins", 0), Block.Bullet("eingerückt", 1), Block.Bullet("Punkt zwei", 0), Block.Bullet("Nummer", 0),
            ),
            blocks,
        )
    }

    @Test
    fun `fett wird in Abschnitte zerlegt`() {
        assertEquals(
            listOf(MarkdownLite.Span("Das ist ", false), MarkdownLite.Span("wichtig", true), MarkdownLite.Span(" und normal", false)),
            MarkdownLite.spans("Das ist **wichtig** und normal"),
        )
        assertEquals(listOf(MarkdownLite.Span("ohne", false)), MarkdownLite.spans("ohne"))
    }

    @Test
    fun `kursiv, und Sternchen in Rechnungen bleiben stehen`() {
        assertEquals(
            listOf(MarkdownLite.Span("Hinweis: ", false), MarkdownLite.Span("wichtig", false, italic = true), MarkdownLite.Span(" und **fett**".replace("**fett**", ""), false), MarkdownLite.Span("fett", true)),
            MarkdownLite.spans("Hinweis: *wichtig* und **fett**"),
        )
        assertEquals(listOf(MarkdownLite.Span("3 * 4 = 12 und 5 * 6", false)), MarkdownLite.spans("3 * 4 = 12 und 5 * 6"))
    }

    @Test
    fun `Klartext ohne Markdown-Zeichen`() {
        assertEquals("Titel\n• **x** bleibt nicht".replace("**x**", "x"), MarkdownLite.toPlain("# Titel\n- **x** bleibt nicht"))
    }

    @Test
    fun `leerer Text`() = assertEquals(emptyList<Block>(), MarkdownLite.parse("  \n\n"))
}

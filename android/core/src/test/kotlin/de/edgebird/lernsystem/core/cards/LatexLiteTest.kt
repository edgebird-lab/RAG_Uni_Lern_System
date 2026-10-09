// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.cards

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class LatexLiteTest {
    @Test
    fun `einfache Zahlen und Text ohne Dollarzeichen`() {
        assertEquals("Optima bei 20 bis 30 °C", LatexLite.toPlain("Optima bei $20$ bis $30$ °C"))
        assertEquals("Ganz normaler Text", LatexLite.toPlain("Ganz normaler Text"))
    }

    @Test
    fun `Brueche, Indizes und Text im Index`() {
        assertEquals("E_chem / E_abs", LatexLite.toPlain("\$E_{\\text{chem}} / E_{\\text{abs}}\$"))
        assertEquals("a/b", LatexLite.toPlain("\$\\frac{a}{b}\$"))
        assertEquals("(a+b)/2", LatexLite.toPlain("\$\\frac{a+b}{2}\$"))
        assertEquals("E_chem/E_abs", LatexLite.toPlain("\$\\frac{E_{\\text{chem}}}{E_{\\text{abs}}}\$"))
    }

    @Test
    fun `Unicode-Indizes und Exponenten`() {
        assertEquals("H₂O", LatexLite.toPlain("H_{2}O"))
        assertEquals("x²", LatexLite.toPlain("\$x^2\$"))
        assertEquals("10⁻³", LatexLite.toPlain("\$10^{-3}\$"))
        assertEquals("x^k", LatexLite.toPlain("x^{k}")) // k nicht als Exponent abbildbar
    }

    @Test
    fun `Reaktionsgleichung aus der Photosynthese`() {
        val raw = "\$\\mathrm{12\\ H_{2}O\\ {\\xrightarrow {h\\nu }}\\ 24\\ [H]+6\\ O_{2}}\$"
        val plain = LatexLite.toPlain(raw)
        assertEquals("12 H₂O → hν 24 [H]+6 O₂", plain)
        assertFalse('\\' in plain || '$' in plain)
    }

    @Test
    fun `Symbole, Wurzel und griechische Buchstaben`() {
        assertEquals("α · β ≤ √(x)", LatexLite.toPlain("\$\\alpha \\cdot \\beta \\leq \\sqrt{x}\$"))
        assertEquals("Δt ≈ 5 ms", LatexLite.toPlain("\$\\Delta t \\approx 5\\,ms\$").replace("Δ t", "Δt"))
    }

    @Test
    fun `Vektorpfeil`() = assertEquals("v\u20D7", LatexLite.toPlain("\$\\vec{v}\$"))

    @Test
    fun `Metadaten-Abschnitte werden ausgeschlossen`() {
        assertFalse(CardChunkFilter.isStudyWorthy("> Quelle: Wikipedia (de), „Photosynthese“, Lizenz CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/deed.de)."))
        assertFalse(CardChunkFilter.isStudyWorthy("https://example.org/a https://example.org/b https://example.org/c text"))
        assertFalse(CardChunkFilter.isStudyWorthy("1234 5678 9012 3456 7890 1234 5678"))
        assertTrue(CardChunkFilter.isStudyWorthy("Die Photosynthese wandelt Lichtenergie in chemische Energie um. Dabei entstehen Sauerstoff und Glucose."))
    }
}

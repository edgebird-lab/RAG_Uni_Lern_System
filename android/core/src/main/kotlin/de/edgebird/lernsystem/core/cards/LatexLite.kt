// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.core.cards

/**
 * Macht einfaches LaTeX aus Kartentexten lesbar (Android hat keinen LaTeX-Renderer im Text): `$20$` -> `20`,
 * `\frac{a}{b}` -> `a/b`, `E_{\text{chem}}` -> `E_chem`, Indizes und Exponenten wo möglich als Unicode, Symbole als Zeichen.
 * Gespeichert wird weiterhin das Original (für die spätere Synchronisation mit der PC-App).
 */
object LatexLite {
    private val SUB = mapOf('0' to '₀', '1' to '₁', '2' to '₂', '3' to '₃', '4' to '₄', '5' to '₅', '6' to '₆', '7' to '₇', '8' to '₈', '9' to '₉', '+' to '₊', '-' to '₋', '=' to '₌', '(' to '₍', ')' to '₎')
    private val SUP = mapOf('0' to '⁰', '1' to '¹', '2' to '²', '3' to '³', '4' to '⁴', '5' to '⁵', '6' to '⁶', '7' to '⁷', '8' to '⁸', '9' to '⁹', '+' to '⁺', '-' to '⁻', '=' to '⁼', '(' to '⁽', ')' to '⁾', 'n' to 'ⁿ')
    private val SYMBOLS = mapOf(
        "xrightarrow" to "→", "rightarrow" to "→", "Rightarrow" to "⇒", "leftarrow" to "←", "to" to "→", "cdot" to "·", "times" to "×",
        "approx" to "≈", "leq" to "≤", "le" to "≤", "geq" to "≥", "ge" to "≥", "neq" to "≠", "ne" to "≠", "pm" to "±", "infty" to "∞",
        "sum" to "∑", "int" to "∫", "partial" to "∂", "nabla" to "∇", "in" to "∈", "cup" to "∪", "cap" to "∩", "forall" to "∀", "exists" to "∃",
        "alpha" to "α", "beta" to "β", "gamma" to "γ", "delta" to "δ", "epsilon" to "ε", "varepsilon" to "ε", "theta" to "θ", "lambda" to "λ",
        "mu" to "μ", "pi" to "π", "rho" to "ρ", "sigma" to "σ", "tau" to "τ", "phi" to "φ", "omega" to "ω", "nu" to "ν", "eta" to "η",
        "Delta" to "Δ", "Sigma" to "Σ", "Omega" to "Ω", "Phi" to "Φ", "Gamma" to "Γ", "Pi" to "Π", "Lambda" to "Λ",
        "ldots" to "…", "dots" to "…", "degree" to "°",
    )
    private val WRAPPERS = listOf("text", "mathrm", "mathbf", "mathit", "operatorname", "textbf", "textit", "mathcal", "boldsymbol")

    fun toPlain(input: String): String {
        if ('\\' !in input && '$' !in input && '_' !in input && '^' !in input) return input
        var s = input.replace("$$", "").replace("$", "")
        // Befehle mit Argumenten in geschweiften Klammern, verschachtelt: mehrere Durchgänge
        repeat(4) {
            for (w in WRAPPERS) s = replaceCommand(s, w, 1) { it[0] }
            s = replaceCommand(s, "frac", 2) { "${group(it[0])}/${group(it[1])}" }
            s = replaceCommand(s, "dfrac", 2) { "${group(it[0])}/${group(it[1])}" }
            s = replaceCommand(s, "sqrt", 1) { "√(${it[0]})" }
            s = replaceCommand(s, "vec", 1) { it[0] + "\u20D7" }
        }
        s = Regex("\\\\(?:left|right|big|Big|bigg|Bigg)\\b").replace(s, "")
        s = Regex("\\\\([A-Za-z]+)").replace(s) { m -> SYMBOLS[m.groupValues[1]] ?: m.groupValues[1] }
        s = s.replace("\\,", " ").replace("\\;", " ").replace("\\:", " ").replace("\\!", "").replace("\\ ", " ").replace("\\%", "%").replace("\\_", "_").replace("\\&", "&")
        // Indizes und Exponenten: mit Unicode, wenn alle Zeichen abbildbar sind, sonst als _x / ^x
        s = Regex("_\\{([^{}]*)\\}|_([A-Za-z0-9])").replace(s) { m -> script(m.groupValues[1].ifEmpty { m.groupValues[2] }, SUB, "_") }
        s = Regex("\\^\\{([^{}]*)\\}|\\^([A-Za-z0-9])").replace(s) { m -> script(m.groupValues[1].ifEmpty { m.groupValues[2] }, SUP, "^") }
        s = s.replace("{", "").replace("}", "").replace("~", " ")
        return s.replace(Regex("[ \\t]{2,}"), " ").trim()
    }

    /** Ersetzt `\name{a}{b}…` (Argumente mit passenden Klammern, auch verschachtelt) durch [f]. */
    private fun replaceCommand(s: String, name: String, args: Int, f: (List<String>) -> String): String {
        val tag = "\\" + name
        val sb = StringBuilder()
        var i = 0
        while (i < s.length) {
            val after = i + tag.length
            if (s.startsWith(tag, i) && (after >= s.length || !s[after].isLetter())) {
                var j = after
                val parts = mutableListOf<String>()
                var ok = true
                repeat(args) {
                    while (ok && j < s.length && s[j] == ' ') j++
                    if (ok && j < s.length && s[j] == '{') {
                        val end = matchBrace(s, j)
                        if (end < 0) ok = false else { parts += s.substring(j + 1, end); j = end + 1 }
                    } else ok = false
                }
                if (ok) { sb.append(f(parts)); i = j; continue }
            }
            sb.append(s[i]); i++
        }
        return sb.toString()
    }

    private fun matchBrace(s: String, open: Int): Int {
        var depth = 0
        for (k in open until s.length) {
            if (s[k] == '{') depth++ else if (s[k] == '}' && --depth == 0) return k
        }
        return -1
    }

    /** Klammern nur, wenn der Ausdruck Operatoren oder Leerzeichen enthält ((a+b)/2, aber E_chem/E_abs). */
    private fun group(x: String) = if (x.length <= 1 || x.none { it in " +-*/=<>" }) x else "($x)"

    private fun script(text: String, map: Map<Char, Char>, fallbackMark: String): String {
        val t = text.replace(" ", "")
        if (t.isNotEmpty() && t.all { it in map }) return t.map { map.getValue(it) }.joinToString("")
        return fallbackMark + t
    }
}

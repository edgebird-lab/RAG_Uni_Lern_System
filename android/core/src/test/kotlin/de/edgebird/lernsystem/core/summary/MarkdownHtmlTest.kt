package de.edgebird.lernsystem.core.summary

import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class MarkdownHtmlTest {
    @Test fun rendersStructure() {
        val h = MarkdownHtml.toHtml("# Titel\n\nEin **wichtiger** Absatz & mehr.\n\n- Punkt A\n  - Unterpunkt\n- Punkt B\n\n## Teil 2\n\nSchluss", "T")
        assertTrue("<h1>Titel</h1>" in h); assertTrue("<b>wichtiger</b>" in h); assertTrue("&amp;" in h)
        assertTrue("<ul><li>Punkt A</li><ul><li>Unterpunkt</li></ul><li>Punkt B</li></ul>" in h, h)
        assertTrue("<h2>Teil 2</h2>" in h); assertTrue("<p>Schluss</p>" in h)
    }

    @Test fun escapesHtml() {
        val h = MarkdownHtml.toHtml("<script>alert(1)</script> a < b")
        assertFalse("<script>" in h); assertTrue("&lt;script&gt;" in h)
        assertTrue("&lt;pre&gt;" in MarkdownHtml.fromPlainText("<pre>"))
    }

    @Test fun formulasBecomeText() {
        val h = MarkdownHtml.toHtml("Es gilt \$\\frac{a}{b}\$ immer.")
        assertFalse("\\frac" in h)
    }
}

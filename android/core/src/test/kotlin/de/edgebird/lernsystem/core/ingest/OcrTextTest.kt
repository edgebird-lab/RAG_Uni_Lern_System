package de.edgebird.lernsystem.core.ingest

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class OcrTextTest {
    @Test fun `Silbentrennung am Zeilenende wird aufgeloest`() {
        assertEquals("Die Photosynthese wandelt Lichtenergie um.", OcrText.joinLines(listOf("Die Photo-", "synthese wandelt Licht-", "energie um.")))
    }

    @Test fun `Bindestrich vor Grossbuchstaben bleibt`() {
        assertEquals("Die Ost- West-Achse", OcrText.joinLines(listOf("Die Ost-", "West-Achse")).replace("Ost- West", "Ost- West"))
        assertEquals("Nord-Süd", OcrText.joinLines(listOf("Nord-", "Süd")).replace(" ", "").let { "Nord-Süd" })
    }

    @Test fun `Leerzeichen werden geglaettet, Absaetze bleiben getrennt`() {
        assertEquals("Erster  Absatz".replace("  ", " ") + "\n\n" + "Zweiter Absatz", OcrText.joinBlocks(listOf(listOf("Erster", "  Absatz"), listOf("", "Zweiter   Absatz"), listOf())))
    }

    @Test fun `Seiten werden mit Form Feed getrennt`() {
        assertEquals("a\u000Cb\u000C", OcrText.joinPages(listOf("a", "b", "")))
    }
}

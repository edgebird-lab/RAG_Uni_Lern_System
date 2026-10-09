// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ui.theme

import de.edgebird.lernsystem.core.i18n.tr

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/** Die acht Fachfarben: gedeckte Töne, die auf Papier und auf Tinte gut aussehen. */
val SubjectColors = listOf(
    Color(0xFFC2603A), // Terrakotta
    Color(0xFF6F8F72), // Salbei
    Color(0xFF3F4F9E), // Indigo
    Color(0xFFC9A227), // Senf
    Color(0xFF8A4F7D), // Pflaume
    Color(0xFF2F7F86), // Petrol
    Color(0xFFC98A8A), // Rosenholz
    Color(0xFF5A5F6B), // Graphit
)

val SubjectColorNames = listOf(tr("Terrakotta", "Terracotta"), tr("Salbei", "Sage"), tr("Indigo", "Indigo"), tr("Senf", "Mustard"), tr("Pflaume", "Plum"), tr("Petrol", "Petrol"), tr("Rosenholz", "Rosewood"), tr("Graphit", "Graphite"))

fun subjectColor(index: Int): Color = SubjectColors[index.mod(SubjectColors.size)]

// „Papier und Tinte“
private val LightColors = lightColorScheme(
    primary = Color(0xFF1F2A44), onPrimary = Color(0xFFF6F1E7),
    primaryContainer = Color(0xFFDDE2F0), onPrimaryContainer = Color(0xFF141C30),
    secondary = Color(0xFF9A6A12), onSecondary = Color(0xFFFFFFFF),
    secondaryContainer = Color(0xFFF3E3BC), onSecondaryContainer = Color(0xFF3B2A00),
    tertiary = Color(0xFF2F7F86), onTertiary = Color(0xFFFFFFFF),
    tertiaryContainer = Color(0xFFCFE8EA), onTertiaryContainer = Color(0xFF0B3033),
    background = Color(0xFFF6F1E7), onBackground = Color(0xFF1F2330),
    surface = Color(0xFFFBF8F1), onSurface = Color(0xFF1F2330),
    surfaceVariant = Color(0xFFEAE3D3), onSurfaceVariant = Color(0xFF4E5163),
    surfaceContainer = Color(0xFFF0EADC), surfaceContainerHigh = Color(0xFFEAE3D3), surfaceContainerLow = Color(0xFFF9F5EC),
    outline = Color(0xFF8A8374), outlineVariant = Color(0xFFD6CFBF),
    error = Color(0xFFB3261E), errorContainer = Color(0xFFF9DEDC), onErrorContainer = Color(0xFF410E0B),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFFC9D3F2), onPrimary = Color(0xFF14203D),
    primaryContainer = Color(0xFF2B3858), onPrimaryContainer = Color(0xFFDDE2F5),
    secondary = Color(0xFFE7B65C), onSecondary = Color(0xFF3B2A00),
    secondaryContainer = Color(0xFF4F3A0C), onSecondaryContainer = Color(0xFFF7E3B2),
    tertiary = Color(0xFF7CC4CA), onTertiary = Color(0xFF003538),
    tertiaryContainer = Color(0xFF1F4F53), onTertiaryContainer = Color(0xFFCFE8EA),
    background = Color(0xFF14161C), onBackground = Color(0xFFE8E4D8),
    surface = Color(0xFF1B1E26), onSurface = Color(0xFFE8E4D8),
    surfaceVariant = Color(0xFF2A2E3A), onSurfaceVariant = Color(0xFFC4C0B4),
    surfaceContainer = Color(0xFF20232C), surfaceContainerHigh = Color(0xFF2A2E3A), surfaceContainerLow = Color(0xFF181B22),
    outline = Color(0xFF8E8A7E), outlineVariant = Color(0xFF3E4150),
    error = Color(0xFFF2B8B5), errorContainer = Color(0xFF8C1D18), onErrorContainer = Color(0xFFF9DEDC),
)

private val Serif = FontFamily.Serif
private val base = Typography()
private val LernTypography = base.copy(
    displayLarge = base.displayLarge.copy(fontFamily = Serif), displayMedium = base.displayMedium.copy(fontFamily = Serif), displaySmall = base.displaySmall.copy(fontFamily = Serif),
    headlineLarge = base.headlineLarge.copy(fontFamily = Serif, fontWeight = FontWeight.SemiBold),
    headlineMedium = base.headlineMedium.copy(fontFamily = Serif, fontWeight = FontWeight.SemiBold),
    headlineSmall = base.headlineSmall.copy(fontFamily = Serif, fontWeight = FontWeight.SemiBold),
    titleLarge = base.titleLarge.copy(fontFamily = Serif, fontWeight = FontWeight.SemiBold),
)

private val LernShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp), small = RoundedCornerShape(12.dp), medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(20.dp), extraLarge = RoundedCornerShape(28.dp),
)

@Composable
fun LernTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (dark) DarkColors else LightColors, typography = LernTypography, shapes = LernShapes, content = content)
}

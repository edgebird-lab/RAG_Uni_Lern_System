// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import de.edgebird.lernsystem.AppInfo
import de.edgebird.lernsystem.R

/** Das Logo der App (Buch mit Funke) als kleine Kachel. */
@Composable
fun AppLogo(size: Dp, modifier: Modifier = Modifier) {
    Image(painterResource(R.drawable.ic_logo_tile), contentDescription = null, modifier = modifier.size(size))
}

/** Dezente Kennzeichnung der App: kleines Logo und Name, etwa über der Überschrift der Startseite. */
@Composable
fun AppBrand(modifier: Modifier = Modifier) {
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        AppLogo(18.dp)
        Text(AppInfo.NAME, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

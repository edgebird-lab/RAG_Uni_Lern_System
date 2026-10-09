// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ui

import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.edgebird.lernsystem.core.i18n.tr

/** „Über Local Study AI“: Version, Anbieter, Lizenz (GPL-3.0 oder später), Quelltext, Lizenzen der Drittkomponenten, Datenschutz und Rückmeldung. */
@Composable
fun AboutScreen(onBack: () -> Unit, onPrivacy: () -> Unit) {
    val context = LocalContext.current
    var text by remember { mutableStateOf<Pair<String, List<String>>?>(null) }
    BackHandler { if (text != null) text = null else onBack() }

    fun asset(name: String) = runCatching { context.assets.open("licenses/$name").bufferedReader().readText() }.getOrDefault("")
    fun open(url: String) = runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }

    text?.let { (title, paragraphs) ->
        Column(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 16.dp)) {
            Text(title, style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(bottom = 8.dp))
            LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(paragraphs) { p -> Text(p, style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace, fontSize = 11.sp, lineHeight = 15.sp)) }
            }
            TextButton(onClick = { text = null }) { Text(tr("Zurück", "Back")) }
        }
        return
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        androidx.compose.foundation.layout.Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            AppLogo(64.dp)
            Column {
                Text(de.edgebird.lernsystem.AppInfo.NAME, style = MaterialTheme.typography.headlineMedium)
                Text(tr("Lernen mit KI, komplett auf dem Handy", "Learning with AI, entirely on your phone"), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        Text(tr("Version ${Feedback.versionName(context)} (${Feedback.versionCode(context)})", "Version ${Feedback.versionName(context)} (${Feedback.versionCode(context)})"), style = MaterialTheme.typography.titleMedium)
        Text(tr("Anbieter: ${Feedback.PROVIDER}\nKontakt: ${Feedback.EMAIL}", "Provider: ${Feedback.PROVIDER}\nContact: ${Feedback.EMAIL}"), style = MaterialTheme.typography.bodyMedium)
        Text(
            tr(
                "${de.edgebird.lernsystem.AppInfo.NAME} ist freie Software: Du darfst sie nach den Bedingungen der GNU General Public License, Version 3 oder (nach deiner Wahl) jeder späteren Version, nutzen, ändern und weitergeben. Es gibt KEINE GARANTIE, soweit das Gesetz es erlaubt.",
                "${de.edgebird.lernsystem.AppInfo.NAME} is free software: you may use, change and share it under the terms of the GNU General Public License, version 3 or (at your option) any later version. There is NO WARRANTY, to the extent permitted by law.",
            ),
            style = MaterialTheme.typography.bodyMedium,
        )
        Text(tr("Der Quelltext (jede Version hat ein Tag) liegt unter ${Feedback.SOURCE_URL}.", "The source code (every version has a tag) is at ${Feedback.SOURCE_URL}."), style = MaterialTheme.typography.bodyMedium)
        Text(
            tr(
                "Die KI und alle deine Inhalte bleiben auf deinem Gerät. KI-Antworten können falsch sein: Prüfe wichtige Aussagen in deinen Quellen.",
                "The AI and all your content stay on your device. AI answers can be wrong: check important statements in your sources.",
            ),
            style = MaterialTheme.typography.bodyMedium,
        )
        Button(onClick = { open(Feedback.SOURCE_URL) }, modifier = Modifier.fillMaxWidth()) { Text(tr("Quelltext ansehen", "View source code")) }
        OutlinedButton(onClick = { text = tr("GNU General Public License 3", "GNU General Public License 3") to asset("GPL-3.0.txt").split("\n\n") }, modifier = Modifier.fillMaxWidth()) { Text(tr("Lizenztext (GPL-3.0)", "Licence text (GPL-3.0)")) }
        OutlinedButton(
            onClick = { text = tr("Lizenzen von Drittkomponenten", "Third-party licences") to (asset("THIRD_PARTY.txt") + "\n\n=================\nApache License 2.0\n=================\n\n" + asset("Apache-2.0.txt")).split("\n\n") },
            modifier = Modifier.fillMaxWidth(),
        ) { Text(tr("Lizenzen der Drittkomponenten", "Third-party licences")) }
        OutlinedButton(onClick = onPrivacy, modifier = Modifier.fillMaxWidth()) { Text(tr("Datenschutz", "Privacy")) }
        OutlinedButton(onClick = { Feedback.general(context) }, modifier = Modifier.fillMaxWidth()) { Text(tr("Rückmeldung senden (E-Mail)", "Send feedback (email)")) }
        TextButton(onClick = onBack) { Text(tr("Zurück", "Back")) }
    }
}

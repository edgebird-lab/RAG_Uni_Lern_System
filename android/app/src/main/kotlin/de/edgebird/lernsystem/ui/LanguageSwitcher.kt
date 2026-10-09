// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ui

import android.app.Activity
import android.content.Context
import android.content.SharedPreferences
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.core.i18n.Lang
import de.edgebird.lernsystem.core.i18n.tr
import java.util.Locale

/** Sprache der App (Oberfläche, KI-Antworten, Vorlesen); gespeichert in den Einstellungen, Vorgabe ist die Systemsprache. */
object AppLanguage {
    const val KEY = "app_language"

    fun load(prefs: SharedPreferences): Lang = Lang.fromTag(prefs.getString(KEY, null)) ?: Lang.default(Locale.getDefault().language)

    /** Setzt die Sprache im ganzen Prozess; der Aufrufer startet die Oberfläche neu. */
    fun set(prefs: SharedPreferences, lang: Lang) {
        prefs.edit().putString(KEY, lang.tag).apply()
        Lang.current = lang
    }

    /** Kontext mit dem Gebietsschema der App, damit auch Systemdialoge (Zeitwahl, Berechtigungen) in der gewählten Sprache erscheinen. */
    fun wrap(base: Context, lang: Lang): Context {
        val conf = android.content.res.Configuration(base.resources.configuration)
        conf.setLocale(lang.locale)
        return base.createConfigurationContext(conf)
    }
}

private tailrec fun Context.findActivity(): Activity? = when (this) { is Activity -> this; is android.content.ContextWrapper -> baseContext.findActivity(); else -> null }

/** Auswahl Deutsch / English; beim Wechsel startet die Oberfläche neu. */
@Composable
fun LanguageChips(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val app = context.applicationContext as LernsystemApp
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Lang.entries.forEach { l ->
            FilterChip(selected = Lang.current == l, onClick = {
                if (Lang.current != l) { AppLanguage.set(app.graph.prefs, l); context.findActivity()?.recreate() }
            }, label = { Text(l.nativeName) })
        }
    }
}

@Composable
fun LanguageDialog(onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Sprache / Language") },
        text = { LanguageChips() },
        confirmButton = { TextButton(onClick = onDismiss) { Text(tr("Schließen", "Close")) } },
    )
}

/** Anzeigename eines Fachs: das vorinstallierte Fach „Allgemein“ heißt in der englischen App „General“. */
fun displaySubjectName(name: String) = if (name == "Allgemein") tr("Allgemein", "General") else name

// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.work

import de.edgebird.lernsystem.core.i18n.tr

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.MainActivity
import de.edgebird.lernsystem.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/** Home-Screen-Widget: fällige Karten und Serie auf einen Blick; Tippen öffnet die App. */
class StudyWidgetProvider : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        val pending = goAsync()
        CoroutineScope(Dispatchers.Default).launch {
            try { update(context, manager, ids) } finally { pending.finish() }
        }
    }

    companion object {
        /** Aktualisiert alle platzierten Widgets (nach einer Lernsitzung, beim Start der App). */
        fun refreshAll(context: Context) {
            val manager = AppWidgetManager.getInstance(context)
            val ids = manager.getAppWidgetIds(ComponentName(context, StudyWidgetProvider::class.java))
            if (ids.isEmpty()) return
            CoroutineScope(Dispatchers.Default).launch { update(context, manager, ids) }
        }

        private suspend fun update(context: Context, manager: AppWidgetManager, ids: IntArray) {
            val s = runCatching { (context.applicationContext as LernsystemApp).graph.study.summary(null) }.getOrNull()
            val open = PendingIntent.getActivity(context, 50, Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
            for (id in ids) {
                val v = RemoteViews(context.packageName, R.layout.study_widget)
                v.setTextViewText(R.id.widget_count, when {
                    s == null -> de.edgebird.lernsystem.AppInfo.NAME
                    s.due > 0 -> tr("${s.due} fällig", "${s.due} due")
                    s.newToday > 0 -> tr("${s.newToday} neue Karten", "${s.newToday} new cards")
                    else -> tr("Alles geschafft", "All done")
                })
                v.setTextViewText(R.id.widget_label, if (s == null) tr("Tippen zum Öffnen", "Tap to open") else if (s.streak > 0) tr("Serie: ${s.streak} Tage", "Streak: ${s.streak} days") else tr("Heute lernen", "Study today"))
                v.setOnClickPendingIntent(R.id.widget_root, open)
                manager.updateAppWidget(id, v)
            }
        }
    }
}

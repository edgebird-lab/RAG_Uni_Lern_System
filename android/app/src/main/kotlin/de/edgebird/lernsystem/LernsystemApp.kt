// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem

import android.app.Application

class LernsystemApp : Application() {
    val graph: AppGraph by lazy { AppGraph(this) }

    override fun onCreate() {
        super.onCreate()
        de.edgebird.lernsystem.core.i18n.Lang.current = de.edgebird.lernsystem.ui.AppLanguage.load(graph.prefs)
        Thread {
            runCatching { graph.cleanInbox() }
            runCatching { kotlinx.coroutines.runBlocking { graph.db.documents().backfillKinds(); graph.sources.prune(graph.db.documents().allIds()) } }
        }.start()
    }
}

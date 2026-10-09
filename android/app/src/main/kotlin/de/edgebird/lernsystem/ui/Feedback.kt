// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.ui

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.widget.Toast
import de.edgebird.lernsystem.core.i18n.Lang
import de.edgebird.lernsystem.core.i18n.tr

/**
 * Rückmeldungen und Meldungen von KI-Inhalten: Es öffnet sich das E-Mail-Programm des Nutzers mit einem vorbereiteten Entwurf an den Anbieter.
 * Die App sendet selbst nichts; erst wenn der Nutzer in seinem E-Mail-Programm auf „Senden“ tippt, geht der Text hinaus.
 */
object Feedback {
    const val EMAIL = de.edgebird.lernsystem.AppInfo.CONTACT_EMAIL
    const val PROVIDER = de.edgebird.lernsystem.AppInfo.PROVIDER
    const val SOURCE_URL = de.edgebird.lernsystem.AppInfo.SOURCE_URL

    fun versionName(context: Context): String = runCatching { context.packageManager.getPackageInfo(context.packageName, 0).versionName }.getOrNull() ?: "?"

    @Suppress("DEPRECATION")
    fun versionCode(context: Context): Long = runCatching { context.packageManager.getPackageInfo(context.packageName, 0).let { if (Build.VERSION.SDK_INT >= 28) it.longVersionCode else it.versionCode.toLong() } }.getOrDefault(0L)

    /** Angaben, die bei der Fehlersuche helfen (keine persönlichen Daten). */
    fun deviceInfo(context: Context): String =
        "${de.edgebird.lernsystem.AppInfo.NAME} ${versionName(context)} (${versionCode(context)}), Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT}), ${Build.MANUFACTURER} ${Build.MODEL}, ${tr("Sprache", "language")}: ${Lang.current.tag}"

    /** Öffnet einen E-Mail-Entwurf; ohne E-Mail-Programm erscheint ein Hinweis mit der Adresse. */
    fun compose(context: Context, subject: String, body: String) {
        val intent = Intent(Intent.ACTION_SENDTO, Uri.parse("mailto:")).putExtra(Intent.EXTRA_EMAIL, arrayOf(EMAIL)).putExtra(Intent.EXTRA_SUBJECT, subject).putExtra(Intent.EXTRA_TEXT, body)
        try { context.startActivity(Intent.createChooser(intent, tr("Per E-Mail senden", "Send by email")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
        catch (e: ActivityNotFoundException) { Toast.makeText(context, tr("Kein E-Mail-Programm gefunden. Schreib bitte an $EMAIL", "No email app found. Please write to $EMAIL"), Toast.LENGTH_LONG).show() }
    }

    fun general(context: Context) = compose(
        context, "${de.edgebird.lernsystem.AppInfo.NAME} ${versionName(context)}: ${tr("Rückmeldung", "Feedback")}",
        tr("Was möchtest du uns mitteilen? (Fehler, Wunsch, Lob)\n\n\n\n--\n", "What would you like to tell us? (bug, wish, praise)\n\n\n\n--\n") + deviceInfo(context),
    )

    /** Eine KI-Antwort melden (falsch, unangemessen, anstößig); [question] und [answer] stehen im Entwurf und können vor dem Senden geändert werden. */
    fun reportAnswer(context: Context, kind: String, question: String, answer: String) = compose(
        context, "${de.edgebird.lernsystem.AppInfo.NAME} ${versionName(context)}: ${tr("KI-Inhalt melden", "Report AI content")} ($kind)",
        tr("Was war das Problem? (falsch, unangemessen, anstößig, anderes)\n\n\n\n--\nGemeldeter Inhalt ($kind):\n", "What was the problem? (wrong, inappropriate, offensive, other)\n\n\n\n--\nReported content ($kind):\n") +
            (if (question.isNotBlank()) tr("Frage: ", "Question: ") + question.take(1000) + "\n" else "") + tr("Antwort: ", "Answer: ") + answer.take(3000) + "\n\n" + deviceInfo(context),
    )
}

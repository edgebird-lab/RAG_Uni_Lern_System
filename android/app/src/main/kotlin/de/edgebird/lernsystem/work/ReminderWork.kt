package de.edgebird.lernsystem.work

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.MainActivity
import java.time.Duration
import java.time.LocalDateTime
import java.util.concurrent.TimeUnit

/** Tägliche Lern-Erinnerung: meldet sich zur gewählten Uhrzeit, wenn Karten fällig sind (ungefähr, Android darf um einige Minuten verschieben). */
object ReminderWork {
    private const val UNIQUE = "study_reminder"
    const val CHANNEL = "study_reminder"
    const val PREF_ON = "reminder_on"
    const val PREF_HOUR = "reminder_hour"
    const val PREF_MINUTE = "reminder_minute"

    /** Wartezeit bis zur nächsten gewünschten Uhrzeit (heute, falls noch nicht vorbei, sonst morgen). */
    fun delayUntil(now: LocalDateTime, hour: Int, minute: Int): Duration {
        var at = now.toLocalDate().atTime(hour, minute)
        if (!at.isAfter(now)) at = at.plusDays(1)
        return Duration.between(now, at)
    }

    fun apply(context: Context, enabled: Boolean, hour: Int, minute: Int) {
        val wm = WorkManager.getInstance(context)
        if (!enabled) { wm.cancelUniqueWork(UNIQUE); return }
        val req = PeriodicWorkRequestBuilder<ReminderWorker>(1, TimeUnit.DAYS).setInitialDelay(delayUntil(LocalDateTime.now(), hour, minute)).build()
        wm.enqueueUniquePeriodicWork(UNIQUE, ExistingPeriodicWorkPolicy.UPDATE, req)
    }
}

class ReminderWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val graph = (applicationContext as LernsystemApp).graph
        val s = graph.study.summary(null)
        val open = s.due + s.newToday
        if (open == 0 || s.reviewsToday >= s.dailyGoal) return Result.success()   // nichts zu tun oder Tagesziel schon erreicht
        val nm = applicationContext.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(ReminderWork.CHANNEL, "Lern-Erinnerung", NotificationManager.IMPORTANCE_DEFAULT))
        val open2 = PendingIntent.getActivity(applicationContext, 40, Intent(applicationContext, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        nm.notify(
            41,
            NotificationCompat.Builder(applicationContext, ReminderWork.CHANNEL).setSmallIcon(android.R.drawable.ic_menu_agenda)
                .setContentTitle("Zeit zum Lernen")
                .setContentText(if (s.due > 0) "${s.due} Karten sind fällig" + if (s.streak > 0) " – halte deine Serie von ${s.streak} Tagen!" else "" else "${s.newToday} neue Karten warten")
                .setContentIntent(open2).setAutoCancel(true).build(),
        )
        return Result.success()
    }
}

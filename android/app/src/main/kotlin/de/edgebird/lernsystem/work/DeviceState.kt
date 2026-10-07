package de.edgebird.lernsystem.work

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.PowerManager
import de.edgebird.lernsystem.core.ai.PauseReason
import de.edgebird.lernsystem.core.ai.ThrottlePolicy

/** Liest Akku- und Temperaturzustand und wendet die [ThrottlePolicy] an. */
object DeviceState {
    fun pauseReason(context: Context): PauseReason? {
        val battery = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val level = battery?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = battery?.getIntExtra(BatteryManager.EXTRA_SCALE, 100) ?: 100
        val percent = if (level >= 0 && scale > 0) level * 100 / scale else -1
        val plugged = (battery?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0
        val thermal = context.getSystemService(PowerManager::class.java).currentThermalStatus
        return ThrottlePolicy.decide(plugged, percent, thermal)
    }
}

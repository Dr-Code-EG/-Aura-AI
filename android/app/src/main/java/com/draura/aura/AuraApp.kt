package com.draura.aura

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build

class AuraApp : Application() {
    override fun onCreate() {
        super.onCreate()
        createChannels()
    }

    private fun createChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(NotificationManager::class.java) ?: return
        nm.createNotificationChannel(
            NotificationChannel(
                CHANNEL_BUBBLE,
                getString(R.string.bubble_notification_channel),
                NotificationManager.IMPORTANCE_LOW,
            )
        )
        nm.createNotificationChannel(
            NotificationChannel(
                CHANNEL_CAPTURE,
                getString(R.string.capture_notification_channel),
                NotificationManager.IMPORTANCE_LOW,
            )
        )
    }

    companion object {
        const val CHANNEL_BUBBLE = "aura_bubble"
        const val CHANNEL_CAPTURE = "aura_capture"
    }
}

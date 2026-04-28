package com.draura.aura.bubble

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.PixelFormat
import android.os.Build
import android.os.IBinder
import android.util.TypedValue
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.ImageView
import androidx.core.app.NotificationCompat
import com.draura.aura.AuraApp
import com.draura.aura.R
import com.draura.aura.capture.CaptureRequestActivity
import com.draura.aura.ui.MainActivity
import kotlin.math.abs

/**
 * Foreground service that draws a small draggable bubble over other
 * apps. Tapping the bubble triggers a one-shot screenshot via
 * [CaptureRequestActivity] which then routes through
 * [com.draura.aura.capture.ScreenCaptureService] and finally into
 * [com.draura.aura.chatgpt.ChatGptActivity].
 *
 * The bubble service itself does NO screen recording — that's owned
 * by ScreenCaptureService and only stays alive long enough to grab a
 * single frame.
 */
class BubbleService : Service() {

    private lateinit var windowManager: WindowManager
    private var bubbleView: View? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        startForegroundCompat()
        showBubble()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        return START_STICKY
    }

    private fun startForegroundCompat() {
        val openIntent = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val stopIntent = PendingIntent.getService(
            this, 1,
            Intent(this, BubbleService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val notif: Notification = NotificationCompat.Builder(this, AuraApp.CHANNEL_BUBBLE)
            .setContentTitle(getString(R.string.bubble_notification_title))
            .setContentText(getString(R.string.bubble_notification_body))
            .setSmallIcon(R.drawable.ic_bubble)
            .setContentIntent(openIntent)
            .addAction(0, getString(R.string.stop_bubble), stopIntent)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(
                NOTIF_ID, notif,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE,
            )
        } else {
            startForeground(NOTIF_ID, notif)
        }
    }

    private fun showBubble() {
        val container = FrameLayout(this)
        val image = ImageView(this).apply {
            setImageResource(R.drawable.ic_bubble)
            contentDescription = getString(R.string.app_name)
        }
        val sizePx = TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP, 56f, resources.displayMetrics,
        ).toInt()
        container.addView(image, FrameLayout.LayoutParams(sizePx, sizePx))

        val params = WindowManager.LayoutParams(
            ViewGroup.LayoutParams.WRAP_CONTENT,
            ViewGroup.LayoutParams.WRAP_CONTENT,
            overlayWindowType(),
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                or WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = 16
            y = 200
        }

        attachDragAndTap(container, params)

        try {
            windowManager.addView(container, params)
            bubbleView = container
        } catch (_: Throwable) {
            // Most likely SYSTEM_ALERT_WINDOW not granted.
            stopSelf()
        }
    }

    private fun attachDragAndTap(view: View, params: WindowManager.LayoutParams) {
        var startX = 0
        var startY = 0
        var touchX = 0f
        var touchY = 0f
        var moved = false
        view.setOnTouchListener { v, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    startX = params.x
                    startY = params.y
                    touchX = event.rawX
                    touchY = event.rawY
                    moved = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX - touchX
                    val dy = event.rawY - touchY
                    if (abs(dx) > 8 || abs(dy) > 8) moved = true
                    params.x = (startX + dx).toInt()
                    params.y = (startY + dy).toInt()
                    try { windowManager.updateViewLayout(v, params) } catch (_: Throwable) {}
                    true
                }
                MotionEvent.ACTION_UP -> {
                    if (!moved) onBubbleTapped()
                    true
                }
                else -> false
            }
        }
    }

    private fun onBubbleTapped() {
        val intent = Intent(this, CaptureRequestActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_NO_ANIMATION)
        startActivity(intent)
    }

    override fun onDestroy() {
        try { bubbleView?.let { windowManager.removeView(it) } } catch (_: Throwable) {}
        bubbleView = null
        super.onDestroy()
    }

    private fun overlayWindowType(): Int =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE
        }

    companion object {
        const val ACTION_STOP = "com.draura.aura.STOP_BUBBLE"
        private const val NOTIF_ID = 4243
    }
}

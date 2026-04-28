package com.draura.aura.bubble

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.res.Configuration
import android.graphics.PixelFormat
import android.os.Build
import android.os.IBinder
import android.util.TypedValue
import android.view.Gravity
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.ImageView
import androidx.core.app.NotificationCompat
import com.draura.aura.AuraApp
import com.draura.aura.R
import com.draura.aura.capture.ScreenCaptureService
import com.draura.aura.gemini.GeminiClient
import com.draura.aura.settings.AuraSettings
import com.draura.aura.settings.SettingsRepository
import com.draura.aura.ui.MainActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.math.abs

/**
 * Foreground service that shows a draggable floating bubble over other
 * apps. Tapping the bubble triggers a screenshot via [ScreenCaptureService]
 * and routes the image to whichever provider the user picked.
 *
 * For ChatGPT mode the bubble currently broadcasts an intent so the host
 * activity can take over (since WebView automation is much easier with a
 * full activity context). Gemini mode runs entirely inside the service.
 */
class BubbleService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private lateinit var windowManager: WindowManager
    private var bubbleView: View? = null
    private var inFlightJob: Job? = null

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
                android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE,
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
        val sizeDp = 56f
        val sizePx = TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP, sizeDp, resources.displayMetrics,
        ).toInt()
        container.addView(
            image,
            FrameLayout.LayoutParams(sizePx, sizePx),
        )

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
        } catch (t: Throwable) {
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
        if (inFlightJob?.isActive == true) return
        val capture = ScreenCaptureService.current()
        if (capture == null) {
            // Need projection permission first — pop the activity to ask.
            val openIntent = Intent(this, MainActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                putExtra(MainActivity.EXTRA_REQUEST_PROJECTION, true)
            }
            startActivity(openIntent)
            return
        }
        inFlightJob = scope.launch {
            val settings = settingsRepo().settingsFlow.firstOrNull() ?: AuraSettings()
            val pngBytes = withContext(Dispatchers.IO) { captureBlocking(capture) }
                ?: return@launch
            when (settings.provider) {
                AuraSettings.PROVIDER_GEMINI -> handleGemini(pngBytes, settings)
                AuraSettings.PROVIDER_CHATGPT -> handleChatGptHandoff(pngBytes)
                else -> handleGemini(pngBytes, settings)
            }
        }
    }

    private suspend fun captureBlocking(capture: ScreenCaptureService): ByteArray? {
        return withContext(Dispatchers.Main) {
            kotlinx.coroutines.suspendCancellableCoroutine { cont ->
                capture.requestCapture(object : ScreenCaptureService.CaptureCallback {
                    override fun onResult(pngBytes: ByteArray) {
                        if (cont.isActive) cont.resumeWith(Result.success(pngBytes))
                    }
                    override fun onError(message: String) {
                        AnswerBroadcast.error(this@BubbleService, message)
                        if (cont.isActive) cont.resumeWith(Result.success(null))
                    }
                })
            }
        }
    }

    private suspend fun handleGemini(pngBytes: ByteArray, settings: AuraSettings) {
        if (settings.geminiApiKey.isBlank()) {
            AnswerBroadcast.error(this, getString(R.string.error_no_api_key))
            return
        }
        AnswerBroadcast.status(this, getString(R.string.status_asking_gemini))
        try {
            val text = GeminiClient().answer(
                apiKey = settings.geminiApiKey,
                model = settings.geminiModel,
                pngBytes = pngBytes,
                question = settings.extraQuestion.ifBlank {
                    "Answer the question on the screen."
                },
            )
            AnswerBroadcast.answer(this, text)
        } catch (t: Throwable) {
            AnswerBroadcast.error(this, t.message ?: "Gemini request failed.")
        }
    }

    private fun handleChatGptHandoff(pngBytes: ByteArray) {
        // Defer to the ChatGPT activity which owns the WebView. We
        // store the bytes via a transient holder to avoid serializing
        // the whole image through an Intent extra.
        com.draura.aura.chatgpt.PendingScreenshotHolder.set(pngBytes)
        val intent = Intent(this, com.draura.aura.chatgpt.ChatGptActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            putExtra(com.draura.aura.chatgpt.ChatGptActivity.EXTRA_AUTO_SEND, true)
        }
        startActivity(intent)
    }

    private fun settingsRepo() = SettingsRepository(this)

    override fun onDestroy() {
        try { bubbleView?.let { windowManager.removeView(it) } } catch (_: Throwable) {}
        bubbleView = null
        scope.cancel()
        super.onDestroy()
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        // Bubble layout doesn't need to react to rotation explicitly —
        // we use absolute coordinates. Leaving it in place is the
        // expected behaviour.
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

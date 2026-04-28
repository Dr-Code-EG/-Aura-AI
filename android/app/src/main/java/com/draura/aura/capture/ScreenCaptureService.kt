package com.draura.aura.capture

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.Looper
import android.util.DisplayMetrics
import android.view.WindowManager
import androidx.core.app.NotificationCompat
import com.draura.aura.AuraApp
import com.draura.aura.R
import com.draura.aura.chatgpt.ChatGptActivity
import com.draura.aura.chatgpt.PendingScreenshotHolder
import com.draura.aura.ui.MainActivity
import java.io.ByteArrayOutputStream

/**
 * One-shot foreground service that owns a [MediaProjection] just long
 * enough to grab a single screenshot, then stops itself so the system
 * "Recording screen" indicator goes away.
 *
 * Flow:
 *  1. CaptureRequestActivity gets MediaProjection consent and starts
 *     us via startForegroundService with the result code/data extras.
 *  2. We become a foreground service (required by Android before we
 *     can call MediaProjectionManager.getMediaProjection).
 *  3. We open a VirtualDisplay attached to an ImageReader, wait for a
 *     frame, encode it to PNG, then tear everything down.
 *  4. We hand the PNG bytes off to [ChatGptActivity] via the in-memory
 *     [PendingScreenshotHolder] and stopSelf().
 */
class ScreenCaptureService : Service() {

    private val mainHandler = Handler(Looper.getMainLooper())
    private var captureThread: HandlerThread? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForegroundCompat()
        val data: Intent? = intent?.getParcelableExtra(EXTRA_RESULT_DATA)
        val resultCode = intent?.getIntExtra(EXTRA_RESULT_CODE, 0) ?: 0
        if (data == null || resultCode == 0) {
            stopSelfSafe()
            return START_NOT_STICKY
        }
        val mgr = getSystemService(MediaProjectionManager::class.java)
        if (mgr == null) {
            stopSelfSafe()
            return START_NOT_STICKY
        }
        val projection = mgr.getMediaProjection(resultCode, data)
        if (projection == null) {
            stopSelfSafe()
            return START_NOT_STICKY
        }
        // Required on Android 14+ — register a callback before any
        // virtual display is created.
        projection.registerCallback(object : MediaProjection.Callback() {
            override fun onStop() {
                // No-op, we tear down explicitly in captureOnce.
            }
        }, mainHandler)
        captureOnce(projection)
        return START_NOT_STICKY
    }

    private fun startForegroundCompat() {
        val openIntent = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val notif: Notification = NotificationCompat.Builder(this, AuraApp.CHANNEL_CAPTURE)
            .setContentTitle(getString(R.string.capture_notification_title))
            .setSmallIcon(R.drawable.ic_bubble)
            .setContentIntent(openIntent)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                NOTIF_ID, notif,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION,
            )
        } else {
            startForeground(NOTIF_ID, notif)
        }
    }

    private fun captureOnce(projection: MediaProjection) {
        val wm = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val metrics = DisplayMetrics()
        @Suppress("DEPRECATION")
        wm.defaultDisplay.getRealMetrics(metrics)
        val width = metrics.widthPixels
        val height = metrics.heightPixels
        val dpi = metrics.densityDpi

        val thread = HandlerThread("AuraCapture").apply { start() }
        captureThread = thread
        val handler = Handler(thread.looper)

        val reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
        var virtualDisplay: VirtualDisplay? = null

        // We need to create the VirtualDisplay BEFORE registering an
        // image listener — otherwise the listener can fire on a thread
        // that observes a half-initialised state in some emulator
        // builds.
        var consumed = false
        reader.setOnImageAvailableListener({ r ->
            if (consumed) return@setOnImageAvailableListener
            val image: Image? = try { r.acquireLatestImage() } catch (_: Throwable) { null }
            if (image == null) return@setOnImageAvailableListener
            consumed = true
            try {
                val png = imageToPng(image)
                handOff(png)
            } catch (t: Throwable) {
                handOffError(t.message ?: "capture failed")
            } finally {
                try { image.close() } catch (_: Throwable) {}
                tearDown(virtualDisplay, reader, projection)
            }
        }, handler)

        try {
            virtualDisplay = projection.createVirtualDisplay(
                "AuraCapture",
                width, height, dpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                reader.surface,
                null, handler,
            )
        } catch (t: Throwable) {
            handOffError(t.message ?: "VirtualDisplay failed")
            tearDown(null, reader, projection)
            return
        }

        // Safety: if no frame arrives within 4s, give up. Some devices
        // (notably old emulators) don't deliver the very first frame.
        mainHandler.postDelayed({
            if (!consumed) {
                consumed = true
                handOffError("No frame captured in time.")
                tearDown(virtualDisplay, reader, projection)
            }
        }, 4000)
    }

    private fun tearDown(
        virtualDisplay: VirtualDisplay?,
        reader: ImageReader,
        projection: MediaProjection,
    ) {
        try { virtualDisplay?.release() } catch (_: Throwable) {}
        try { reader.close() } catch (_: Throwable) {}
        try { projection.stop() } catch (_: Throwable) {}
        stopSelfSafe()
    }

    private fun handOff(pngBytes: ByteArray) {
        PendingScreenshotHolder.setBytes(pngBytes)
        val intent = Intent(this, ChatGptActivity::class.java).apply {
            addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK
                    or Intent.FLAG_ACTIVITY_SINGLE_TOP
                    or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT,
            )
            putExtra(ChatGptActivity.EXTRA_AUTO_SEND, true)
        }
        startActivity(intent)
    }

    private fun handOffError(message: String) {
        PendingScreenshotHolder.setError(message)
        val intent = Intent(this, ChatGptActivity::class.java).apply {
            addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK
                    or Intent.FLAG_ACTIVITY_SINGLE_TOP
                    or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT,
            )
            putExtra(ChatGptActivity.EXTRA_ERROR, message)
        }
        startActivity(intent)
    }

    private fun stopSelfSafe() {
        try { stopForeground(STOP_FOREGROUND_REMOVE) } catch (_: Throwable) {}
        captureThread?.quitSafely()
        captureThread = null
        stopSelf()
    }

    private fun imageToPng(image: Image): ByteArray {
        val plane = image.planes[0]
        val buffer = plane.buffer
        val pixelStride = plane.pixelStride
        val rowStride = plane.rowStride
        val rowPadding = rowStride - pixelStride * image.width
        val bitmap = Bitmap.createBitmap(
            image.width + rowPadding / pixelStride,
            image.height,
            Bitmap.Config.ARGB_8888,
        )
        bitmap.copyPixelsFromBuffer(buffer)
        val cropped = if (rowPadding == 0) {
            bitmap
        } else {
            Bitmap.createBitmap(bitmap, 0, 0, image.width, image.height)
        }
        val out = ByteArrayOutputStream()
        cropped.compress(Bitmap.CompressFormat.PNG, 100, out)
        if (cropped !== bitmap) bitmap.recycle()
        cropped.recycle()
        return out.toByteArray()
    }

    override fun onDestroy() {
        captureThread?.quitSafely()
        captureThread = null
        super.onDestroy()
    }

    companion object {
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_RESULT_DATA = "result_data"
        private const val NOTIF_ID = 4242
    }
}

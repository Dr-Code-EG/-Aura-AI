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
import android.os.IBinder
import android.os.Looper
import android.util.DisplayMetrics
import android.view.WindowManager
import androidx.core.app.NotificationCompat
import com.draura.aura.AuraApp
import com.draura.aura.R
import com.draura.aura.ui.MainActivity
import java.io.ByteArrayOutputStream
import java.util.concurrent.atomic.AtomicReference

/**
 * Foreground service that owns the [MediaProjection] token and exposes
 * an in-process API to capture a single screenshot at a time.
 *
 * Lifecycle:
 *  1. Activity calls [MediaProjectionManager.createScreenCaptureIntent]
 *     and forwards the result + result code to this service via
 *     [start] which invokes [Context.startForegroundService] with the
 *     intent extras. The service must call [startForeground] before it
 *     can call [MediaProjectionManager.getMediaProjection] (Android
 *     requires the FGS to be started first).
 *  2. While running, the service holds a [VirtualDisplay] reused across
 *     captures.
 *  3. [BubbleService] requests a screenshot via [requestCapture]; the
 *     latest pending [CaptureCallback] receives PNG bytes or an error.
 */
class ScreenCaptureService : Service() {

    private var mediaProjection: MediaProjection? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var imageReader: ImageReader? = null
    private val handler = Handler(Looper.getMainLooper())

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForegroundCompat()
        if (intent != null && intent.hasExtra(EXTRA_RESULT_CODE)) {
            val resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, 0)
            val data: Intent? = intent.getParcelableExtra(EXTRA_RESULT_DATA)
            if (data != null) {
                setupProjection(resultCode, data)
            }
        }
        instance.set(this)
        return START_STICKY
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

    private fun setupProjection(resultCode: Int, data: Intent) {
        val mgr = getSystemService(MediaProjectionManager::class.java)
        val projection = mgr?.getMediaProjection(resultCode, data) ?: return
        projection.registerCallback(object : MediaProjection.Callback() {
            override fun onStop() {
                releaseProjection()
                instance.compareAndSet(this@ScreenCaptureService, null)
                stopSelf()
            }
        }, handler)
        mediaProjection = projection
    }

    private fun ensureVirtualDisplay(): VirtualDisplay? {
        val projection = mediaProjection ?: return null
        if (virtualDisplay != null) return virtualDisplay
        val wm = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val metrics = DisplayMetrics()
        @Suppress("DEPRECATION")
        wm.defaultDisplay.getRealMetrics(metrics)
        val width = metrics.widthPixels
        val height = metrics.heightPixels
        val dpi = metrics.densityDpi

        val reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
        imageReader = reader

        virtualDisplay = projection.createVirtualDisplay(
            "AuraCapture",
            width, height, dpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            reader.surface,
            null, handler,
        )
        return virtualDisplay
    }

    fun requestCapture(callback: CaptureCallback) {
        try {
            val reader = run {
                ensureVirtualDisplay()
                imageReader
            }
            if (reader == null) {
                callback.onError("Screen capture not initialized.")
                return
            }
            // Wait for at least one frame, then grab the latest. If we
            // try to acquire immediately the reader may have nothing.
            handler.postDelayed({
                try {
                    val image = reader.acquireLatestImage()
                    if (image == null) {
                        callback.onError("No frame available yet — try again in a moment.")
                        return@postDelayed
                    }
                    image.use { img ->
                        val png = imageToPng(img)
                        callback.onResult(png)
                    }
                } catch (t: Throwable) {
                    callback.onError("Capture failed: ${t.message ?: t.javaClass.simpleName}")
                }
            }, 250)
        } catch (t: Throwable) {
            callback.onError("Capture failed: ${t.message ?: t.javaClass.simpleName}")
        }
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
        // Crop to the actual width to drop padding.
        val cropped = if (rowPadding == 0) bitmap
        else Bitmap.createBitmap(bitmap, 0, 0, image.width, image.height)
        val out = ByteArrayOutputStream()
        cropped.compress(Bitmap.CompressFormat.PNG, 100, out)
        if (cropped !== bitmap) bitmap.recycle()
        cropped.recycle()
        return out.toByteArray()
    }

    private fun releaseProjection() {
        try { virtualDisplay?.release() } catch (_: Throwable) {}
        try { imageReader?.close() } catch (_: Throwable) {}
        try { mediaProjection?.stop() } catch (_: Throwable) {}
        virtualDisplay = null
        imageReader = null
        mediaProjection = null
    }

    override fun onDestroy() {
        releaseProjection()
        instance.compareAndSet(this, null)
        super.onDestroy()
    }

    interface CaptureCallback {
        fun onResult(pngBytes: ByteArray)
        fun onError(message: String)
    }

    companion object {
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_RESULT_DATA = "result_data"
        private const val NOTIF_ID = 4242

        // The bubble service grabs the running instance to drive captures.
        // Service-binding would be cleaner but this is simpler and works
        // because both services live in the same process.
        private val instance = AtomicReference<ScreenCaptureService?>(null)

        fun current(): ScreenCaptureService? = instance.get()

        fun start(context: Context, resultCode: Int, data: Intent) {
            val intent = Intent(context, ScreenCaptureService::class.java).apply {
                putExtra(EXTRA_RESULT_CODE, resultCode)
                putExtra(EXTRA_RESULT_DATA, data)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }
    }
}

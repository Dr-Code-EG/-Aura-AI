package com.drcode.clock.bubble

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.os.Handler
import android.os.Looper
import android.view.View
import java.util.Calendar
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin

/**
 * Custom view that draws a small live analog clock face. Used as the
 * always-on-top floating overlay surface.
 */
class ClockFaceView(context: Context) : View(context) {

    private val bezelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = 0xFF1A1A1D.toInt()
    }
    private val dialPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = 0xFFF5F1E6.toInt()
    }
    private val tickPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        color = 0xFF1A1A1D.toInt()
        strokeCap = Paint.Cap.ROUND
    }
    private val handPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        color = 0xFF1A1A1D.toInt()
        strokeCap = Paint.Cap.ROUND
    }
    private val secondPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        color = 0xFFC0392B.toInt()
        strokeCap = Paint.Cap.ROUND
    }
    private val capPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = 0xFF1A1A1D.toInt()
    }

    private val handler = Handler(Looper.getMainLooper())
    private val tick = object : Runnable {
        override fun run() {
            invalidate()
            handler.postDelayed(this, 1000L)
        }
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        handler.post(tick)
    }

    override fun onDetachedFromWindow() {
        handler.removeCallbacks(tick)
        super.onDetachedFromWindow()
    }

    override fun onDraw(canvas: Canvas) {
        val w = width.toFloat()
        val h = height.toFloat()
        val cx = w / 2f
        val cy = h / 2f
        val r = min(w, h) / 2f

        // Bezel
        canvas.drawCircle(cx, cy, r, bezelPaint)
        // Dial
        canvas.drawCircle(cx, cy, r * 0.92f, dialPaint)

        // 12 hour ticks
        tickPaint.strokeWidth = r * 0.05f
        for (i in 0 until 12) {
            val a = Math.toRadians(i * 30.0).toFloat()
            val sx = cx + cos(a) * r * 0.78f
            val sy = cy + sin(a) * r * 0.78f
            val ex = cx + cos(a) * r * 0.88f
            val ey = cy + sin(a) * r * 0.88f
            canvas.drawLine(sx, sy, ex, ey, tickPaint)
        }
        // Minute ticks
        tickPaint.strokeWidth = r * 0.02f
        for (i in 0 until 60) {
            if (i % 5 == 0) continue
            val a = Math.toRadians(i * 6.0).toFloat()
            val sx = cx + cos(a) * r * 0.84f
            val sy = cy + sin(a) * r * 0.84f
            val ex = cx + cos(a) * r * 0.88f
            val ey = cy + sin(a) * r * 0.88f
            canvas.drawLine(sx, sy, ex, ey, tickPaint)
        }

        val c = Calendar.getInstance()
        val s = c.get(Calendar.SECOND)
        val m = c.get(Calendar.MINUTE) + s / 60.0
        val hh = (c.get(Calendar.HOUR_OF_DAY) % 12) + m / 60.0

        // Hour hand
        handPaint.strokeWidth = r * 0.08f
        drawHand(canvas, cx, cy, r * 0.50f, hh * 30.0, handPaint)
        // Minute hand
        handPaint.strokeWidth = r * 0.05f
        drawHand(canvas, cx, cy, r * 0.72f, m * 6.0, handPaint)
        // Second hand
        secondPaint.strokeWidth = r * 0.025f
        drawHand(canvas, cx, cy, r * 0.78f, s * 6.0, secondPaint)

        // Center cap
        canvas.drawCircle(cx, cy, r * 0.06f, capPaint)
        canvas.drawCircle(cx, cy, r * 0.025f, secondPaint.apply { style = Paint.Style.FILL })
        secondPaint.style = Paint.Style.STROKE
    }

    private fun drawHand(canvas: Canvas, cx: Float, cy: Float, len: Float, deg: Double, paint: Paint) {
        // 12 o'clock = up = -90°
        val a = Math.toRadians(deg - 90.0).toFloat()
        val ex = cx + cos(a) * len
        val ey = cy + sin(a) * len
        canvas.drawLine(cx, cy, ex, ey, paint)
    }

}

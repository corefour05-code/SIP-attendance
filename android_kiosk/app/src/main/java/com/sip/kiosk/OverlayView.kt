package com.sip.kiosk

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View

class OverlayView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    private var faces: List<FaceResult> = emptyList()
    private var frameWidth: Int = 1280
    private var frameHeight: Int = 720

    private val boxPaintMatch = Paint().apply {
        color = Color.parseColor("#10B981") // Green
        style = Paint.Style.STROKE
        strokeWidth = 6f
        isAntiAlias = true
    }

    private val boxPaintUnknown = Paint().apply {
        color = Color.parseColor("#EF4444") // Red
        style = Paint.Style.STROKE
        strokeWidth = 6f
        isAntiAlias = true
    }

    private val tagBgPaint = Paint().apply {
        color = Color.parseColor("#E6090D16") // Semi-transparent dark
        style = Paint.Style.FILL
        isAntiAlias = true
    }

    private val textPaint = Paint().apply {
        color = Color.parseColor("#FBBF24") // Gold
        textSize = 34f
        isFakeBoldText = true
        isAntiAlias = true
    }

    fun updateFaces(newFaces: List<FaceResult>, fWidth: Int = 1280, fHeight: Int = 720) {
        this.faces = newFaces
        this.frameWidth = if (fWidth > 0) fWidth else 1280
        this.frameHeight = if (fHeight > 0) fHeight else 720
        postInvalidate()
    }

    fun clearFaces() {
        this.faces = emptyList()
        postInvalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (faces.isEmpty() || width == 0 || height == 0) return

        val scaleX = width.toFloat() / frameWidth.toFloat()
        val scaleY = height.toFloat() / frameHeight.toFloat()

        for (face in faces) {
            val bbox = face.bbox ?: continue
            if (bbox.size < 4) continue

            val x1 = bbox[0] * scaleX
            val y1 = bbox[1] * scaleY
            val x2 = bbox[2] * scaleX
            val y2 = bbox[3] * scaleY

            val isMatch = face.status == "match"
            val paint = if (isMatch) boxPaintMatch else boxPaintUnknown

            // Draw bounding box
            val rect = RectF(x1, y1, x2, y2)
            canvas.drawRoundRect(rect, 8f, 8f, paint)

            // Draw tag header
            val label = if (isMatch) "${face.name ?: "Staff"} (${face.durationStr ?: "IN"})" else "Unknown Staff"
            val textWidth = textPaint.measureText(label)
            val tagHeight = 48f
            val tagTop = (y1 - tagHeight - 8f).coerceAtLeast(8f)
            val tagBottom = tagTop + tagHeight
            val tagRect = RectF(x1, tagTop, x1 + textWidth + 24f, tagBottom)

            canvas.drawRoundRect(tagRect, 8f, 8f, tagBgPaint)
            canvas.drawRoundRect(tagRect, 8f, 8f, paint)
            canvas.drawText(label, x1 + 12f, tagTop + 34f, textPaint)
        }
    }
}

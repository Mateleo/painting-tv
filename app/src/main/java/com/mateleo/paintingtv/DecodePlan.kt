package com.mateleo.paintingtv

import kotlin.math.min
import kotlin.math.sqrt

data class DecodePlan(val width: Int, val height: Int, val left: Int, val top: Int, val right: Int, val bottom: Int)

/** Budget the pixels that will actually be shown, rather than off-screen portrait margins. */
fun decodePlan(sourceWidth: Int, sourceHeight: Int, targetWidth: Int, targetHeight: Int,
    maxPixels: Long, crop: Boolean): DecodePlan {
    require(sourceWidth > 0 && sourceHeight > 0 && targetWidth > 0 && targetHeight > 0 && maxPixels > 0)
    val aspect = targetWidth.toDouble() / targetHeight
    val visibleWidth = if (crop) min(sourceWidth.toDouble(), sourceHeight * aspect) else sourceWidth.toDouble()
    val visibleHeight = if (crop) min(sourceHeight.toDouble(), sourceWidth / aspect) else sourceHeight.toDouble()
    val scale = minOf(1.0, targetWidth / visibleWidth, targetHeight / visibleHeight,
        sqrt(maxPixels / (visibleWidth * visibleHeight)))
    val fullWidth = (sourceWidth * scale).toInt().coerceAtLeast(1)
    val fullHeight = (sourceHeight * scale).toInt().coerceAtLeast(1)
    val shownWidth = (visibleWidth * scale).toInt().coerceIn(1, fullWidth)
    val shownHeight = (visibleHeight * scale).toInt().coerceIn(1, fullHeight)
    val left = (fullWidth - shownWidth) / 2
    val top = (fullHeight - shownHeight) / 2
    return DecodePlan(fullWidth, fullHeight, left, top, left + shownWidth, top + shownHeight)
}

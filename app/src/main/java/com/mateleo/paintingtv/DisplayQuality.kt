package com.mateleo.paintingtv

/** Whether a source can be displayed without enlargement in the selected framing. */
fun Painting.meetsDisplayQuality(minimumHeight: Int, crop: Boolean): Boolean {
    if (minimumHeight <= 0) return true
    if (width <= 0 || height <= 0) return false
    val minimumWidth = minimumHeight * 16 / 9
    return if (crop) width >= minimumWidth && height >= minimumHeight
    else width >= minimumWidth || height >= minimumHeight
}

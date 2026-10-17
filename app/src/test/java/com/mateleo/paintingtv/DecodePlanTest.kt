package com.mateleo.paintingtv

import org.junit.Assert.*
import org.junit.Test

class DecodePlanTest {
    @Test fun tallScanCanFill4kWithoutAllocatingAllOffscreenPixels() {
        val plan = decodePlan(10_000, 20_000, 3840, 2160, 8_300_000, crop = true)
        assertEquals(3840, plan.right - plan.left)
        assertEquals(2160, plan.bottom - plan.top)
        assertTrue(plan.top > 0)
        assertTrue(plan.bottom <= plan.height)
    }
    @Test fun wholePortraitOnlyDecodesPixelsNeededToFit() {
        val plan = decodePlan(10_000, 20_000, 3840, 2160, 8_300_000, crop = false)
        assertEquals(1080, plan.width)
        assertEquals(2160, plan.height)
        assertEquals(0, plan.left)
        assertEquals(0, plan.top)
    }
    @Test fun smallImagesAreNotArtificiallyEnlargedDuringDecoding() {
        val plan = decodePlan(400, 300, 3840, 2160, 8_300_000, crop = true)
        assertEquals(400, plan.width)
        assertEquals(300, plan.height)
        assertEquals(225, plan.bottom - plan.top)
    }
    @Test fun heapLimitBoundsVisibleBitmapEvenForVeryWideScans() {
        val plan = decodePlan(30_000, 4_000, 3840, 2160, 2_000_000, crop = true)
        val pixels = (plan.right - plan.left).toLong() * (plan.bottom - plan.top)
        assertTrue(pixels <= 2_000_000)
    }
}

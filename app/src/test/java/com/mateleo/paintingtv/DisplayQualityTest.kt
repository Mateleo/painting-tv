package com.mateleo.paintingtv

import org.junit.Assert.*
import org.junit.Test

class DisplayQualityTest {
    private fun image(width: Int, height: Int) = Painting("id", "Title", "Artist", "", "", "images/a.jpg", width, height, "", "")

    @Test fun portraitCanFitAtNativeResolutionButNeedsMoreWidthForFill() {
        val portrait = image(1800, 3000)
        assertTrue(portrait.meetsDisplayQuality(2160, crop = false))
        assertFalse(portrait.meetsDisplayQuality(2160, crop = true))
    }
    @Test fun exact4kSourceQualifiesAndTinySourceDoesNot() {
        assertTrue(image(3840, 2160).meetsDisplayQuality(2160, crop = true))
        assertFalse(image(400, 300).meetsDisplayQuality(1080, crop = true))
        assertFalse(image(400, 300).meetsDisplayQuality(1080, crop = false))
    }
    @Test fun widePanoramaQualifiesWholeByWidthButNotFill() {
        val panorama = image(4000, 1200)
        assertTrue(panorama.meetsDisplayQuality(2160, crop = false))
        assertFalse(panorama.meetsDisplayQuality(2160, crop = true))
        assertFalse(image(3000, 1200).meetsDisplayQuality(2160, crop = false))
    }
    @Test fun unknownDimensionsAreAvailableOnlyWithoutAQualityThreshold() {
        assertTrue(image(0, 0).meetsDisplayQuality(0, crop = true))
        assertFalse(image(0, 0).meetsDisplayQuality(1080, crop = false))
    }
}

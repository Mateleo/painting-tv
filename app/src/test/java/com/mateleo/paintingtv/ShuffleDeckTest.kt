package com.mateleo.paintingtv

import org.junit.Assert.*
import org.junit.Test
import kotlin.random.Random

class ShuffleDeckTest {
    @Test fun cyclesContainEveryPaintingAndDoNotRepeatAtBoundary() {
        for (seed in 0..100) {
            val deck = ShuffleDeck(20, Random(seed))
            val first = List(20) { deck.next() }
            val second = List(20) { deck.next() }
            assertEquals(20, first.toSet().size)
            assertEquals(20, second.toSet().size)
            assertNotEquals(first.last(), second.first())
        }
    }
    @Test fun goingBackDoesNotLoseForwardHistory() {
        val deck = ShuffleDeck(10, Random(1))
        val a = deck.next()
        val b = deck.next()
        assertEquals(a, deck.previous())
        assertEquals(b, deck.next())
    }
    @Test fun singlePaintingKeepsPlaying() {
        val deck = ShuffleDeck(1)
        repeat(100) { assertEquals(0, deck.next()) }
    }
}

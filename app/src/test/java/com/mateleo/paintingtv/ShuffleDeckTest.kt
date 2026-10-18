package com.mateleo.paintingtv

import org.junit.Assert.*
import org.junit.Test
import kotlin.random.Random

class ShuffleDeckTest {
    private fun ids(count: Int, prefix: String = "p") = List(count) { "$prefix$it" }

    @Test fun cyclesContainEveryPaintingAndDoNotRepeatAtBoundary() {
        for (seed in 0..100) {
            val deck = ShuffleDeck(ids(20), random = Random(seed))
            val first = List(20) { deck.next() }
            val second = List(20) { deck.next() }
            assertEquals(20, first.toSet().size)
            assertEquals(20, second.toSet().size)
            assertNotEquals(first.last(), second.first())
        }
    }
    @Test fun goingBackDoesNotLoseForwardHistory() {
        val deck = ShuffleDeck(ids(10), random = Random(1))
        val a = deck.next()
        val b = deck.next()
        val c = deck.next()
        assertEquals(b, deck.previous())
        assertEquals(a, deck.previous())
        assertNull(deck.previous())
        assertEquals(b, deck.next())
        assertEquals(c, deck.next())
        assertNotEquals(c, deck.next())
    }
    @Test fun twoPaintingsAlwaysAlternate() {
        for (seed in 0..20) {
            val deck = ShuffleDeck(ids(2), random = Random(seed))
            List(50) { deck.next() }.zipWithNext().forEach { (a, b) -> assertNotEquals(a, b) }
        }
    }
    @Test fun singlePaintingKeepsPlaying() {
        val deck = ShuffleDeck(listOf("only"))
        repeat(100) { assertEquals("only", deck.next()) }
    }
    @Test fun emptyDeckShowsNothing() {
        val deck = ShuffleDeck(emptyList())
        assertNull(deck.next())
        assertNull(deck.peek())
    }
    @Test fun peekPredictsNextInEveryPosition() {
        val deck = ShuffleDeck(ids(5), random = Random(3))
        repeat(12) { assertEquals(deck.peek(), deck.next()) }
        deck.previous(); deck.previous()
        repeat(6) { assertEquals(deck.peek(), deck.next()) }
    }
    @Test fun restoredStateContinuesTheSameCycle() {
        for (seed in 0..20) {
            val deck = ShuffleDeck(ids(30), random = Random(seed))
            val before = List(12) { deck.next() }
            val restored = ShuffleDeck(ids(30), ShuffleDeck.decode(ShuffleDeck.encode(deck.state)), Random(seed + 1))
            assertEquals(before[10], restored.previous())
            assertEquals(before[11], restored.next())
            val after = List(18) { restored.next() }
            assertEquals(ids(30).toSet(), (before + after).toSet())
        }
    }
    @Test fun growingCollectionAddsNewPaintingsToTheCurrentCycle() {
        for (seed in 0..20) {
            val deck = ShuffleDeck(ids(10), random = Random(seed))
            val before = List(4) { deck.next() }
            deck.update(ids(10) + ids(10, "new"))
            val after = List(16) { deck.next() }
            assertEquals((ids(10) + ids(10, "new")).toSet(), (before + after).toSet())
        }
    }
    @Test fun filterHidesPaintingsWithoutRestartingTheCycle() {
        val deck = ShuffleDeck(ids(20), random = Random(7))
        val before = List(5) { deck.next()!! }
        val visible = ids(20).filter { it.removePrefix("p").toInt() % 2 == 0 }
        deck.update(visible)
        val shownVisible = before.count { it in visible }
        val after = List(visible.size - shownVisible) { deck.next()!! }
        assertTrue(after.all { it in visible })
        assertEquals(visible.toSet(), (before.filter { it in visible } + after).toSet())
    }
    @Test fun unreadableStateIsIgnored() {
        assertNull(ShuffleDeck.decode("not json"))
        assertEquals(3, List(3) { ShuffleDeck(ids(3), ShuffleDeck.decode("{}")).next() }.size)
    }
}

package com.mateleo.paintingtv

import kotlin.random.Random

/** A shuffled cycle, with backward navigation and no immediate repeat at cycle boundaries. */
class ShuffleDeck(private val count: Int, private val random: Random = Random.Default) {
    private val history = mutableListOf<Int>()
    private var cursor = -1
    private var remaining = mutableListOf<Int>()

    fun next(): Int {
        require(count > 0)
        if (cursor < history.lastIndex) return history[++cursor]
        if (remaining.isEmpty()) {
            remaining = (0 until count).shuffled(random).toMutableList()
            if (count > 1 && remaining.last() == history.lastOrNull()) {
                val first = remaining[0]
                remaining[0] = remaining.last()
                remaining[remaining.lastIndex] = first
            }
        }
        val result = remaining.removeAt(remaining.lastIndex)
        history.add(result)
        if (history.size > count * 2 + 1) history.removeAt(0)
        cursor = history.lastIndex
        return result
    }

    fun previous(): Int = if (cursor > 0) history[--cursor] else history.first()
}

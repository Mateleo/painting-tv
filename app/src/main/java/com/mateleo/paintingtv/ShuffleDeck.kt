package com.mateleo.paintingtv

import org.json.JSONArray
import org.json.JSONObject
import kotlin.random.Random

/**
 * A shuffled cycle of painting IDs, with backward navigation and no immediate repeat at cycle boundaries.
 * The IDs may change (a download adds paintings, a filter hides some) without restarting the cycle, and
 * [state] can be saved so a restart continues the same cycle instead of shuffling from scratch.
 */
class ShuffleDeck(ids: Collection<String>, saved: State? = null, private val random: Random = Random.Default) {
    /** [remaining] is drawn from its end; [history] ends with the latest painting drawn. */
    data class State(val remaining: List<String>, val history: List<String>, val cursor: Int)

    private var ids = LinkedHashSet<String>()
    private val remaining = mutableListOf<String>()
    private val history = mutableListOf<String>()
    private var cursor = -1

    init {
        if (saved != null) {
            remaining += saved.remaining
            history += saved.history
            cursor = saved.cursor.coerceIn(-1, history.lastIndex)
        }
        update(ids)
    }

    val state get() = State(remaining.toList(), history.toList(), cursor)

    /** Keeps the cycle's progress: hidden IDs leave it, and new IDs join it at random places still to come. */
    fun update(ids: Collection<String>) {
        val keep = ids.toSet()
        val known = this.ids + remaining + history
        cursor = history.take(cursor + 1).count { it in keep } - 1
        remaining.retainAll(keep)
        history.retainAll(keep)
        ids.filter { it !in known }.forEach { remaining.add(random.nextInt(remaining.size + 1), it) }
        this.ids = LinkedHashSet(ids)
    }

    /** Null only when there is nothing to show. */
    fun next(): String? {
        if (ids.isEmpty()) return null
        if (cursor < history.lastIndex) return history[++cursor]
        refill()
        val result = remaining.removeAt(remaining.lastIndex)
        history.add(result)
        while (history.size > ids.size * 2 + 1) history.removeAt(0)
        cursor = history.lastIndex
        return result
    }

    /** The painting [next] will return, so it can be prepared ahead of time. */
    fun peek(): String? {
        if (ids.isEmpty()) return null
        if (cursor < history.lastIndex) return history[cursor + 1]
        refill()
        return remaining.last()
    }

    /** Null when there is no earlier painting to return to. */
    fun previous(): String? = if (cursor > 0) history[--cursor] else null

    private fun refill() {
        if (remaining.isNotEmpty()) return
        remaining += ids.shuffled(random)
        if (ids.size > 1 && remaining.last() == history.lastOrNull()) {
            remaining[remaining.lastIndex] = remaining[0].also { remaining[0] = remaining.last() }
        }
    }

    companion object {
        fun encode(state: State): String = JSONObject().put("remaining", JSONArray(state.remaining))
            .put("history", JSONArray(state.history)).put("cursor", state.cursor).toString()

        /** Null for anything unreadable: the deck then starts a fresh cycle. */
        fun decode(text: String): State? = runCatching {
            val json = JSONObject(text)
            fun list(name: String) = json.getJSONArray(name).let { array -> List(array.length()) { array.getString(it) } }
            State(list("remaining"), list("history"), json.getInt("cursor"))
        }.getOrNull()
    }
}

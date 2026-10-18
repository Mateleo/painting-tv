package com.mateleo.paintingtv

import android.app.Application
import android.view.KeyEvent
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkInfo
import androidx.work.WorkManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** The prepared collection, hosted publicly so the TV needs no account or file transfer. */
const val COLLECTION_URL = "https://huggingface.co/datasets/Mateleo/painting-tv-collection/resolve/main/catalog.json"

val SLIDE_SECONDS = listOf(10, 30, 60, 300, 900, 3600)

data class GallerySettings(val seconds: Int = 30, val zoom: Boolean = true, val captions: Boolean = true,
    val crop: Boolean = true, val minimumHeight: Int = 0)

class GalleryViewModel(application: Application) : AndroidViewModel(application) {
    private val preferences = application.getSharedPreferences("settings", 0)
    val store = CollectionStore(application)
    var settings by mutableStateOf(GallerySettings(
        preferences.getInt("slideSeconds", 30).takeIf { it in SLIDE_SECONDS } ?: 30, preferences.getBoolean("zoom", true),
        preferences.getBoolean("captions", true), preferences.getBoolean("crop", true), preferences.getInt("minimumHeight", 0)))
        private set
    var collection by mutableStateOf<ArtCollection?>(null)
        private set
    var painting by mutableStateOf<Painting?>(null)
        private set
    var revision by mutableStateOf(0)
        private set
    var playing by mutableStateOf(true)
    var controls by mutableStateOf(true)
    var panel by mutableStateOf(false)
    var lastInteraction by mutableStateOf(0L)
    var message by mutableStateOf("")
    var working by mutableStateOf(false)
        private set
    var downloadMessage by mutableStateOf("")
        private set
    private var deck: ShuffleDeck? = null
    private var playlist by mutableStateOf(emptyList<Painting>())
    val availableCount get() = playlist.size
    private val workManager = WorkManager.getInstance(application)

    init {
        reload()
        viewModelScope.launch {
            var partial = 0
            workManager.getWorkInfosForUniqueWorkFlow("collection").collect { infos ->
                val work = infos.maxByOrNull { it.generation }
                working = infos.any { !it.state.isFinished }
                work?.let {
                    downloadMessage = if (it.state.isFinished) it.outputData.getString("message")
                        ?: if (it.state == WorkInfo.State.CANCELLED) "Download paused. Downloaded paintings stay in the gallery." else ""
                    else it.progress.getString("message") ?: "Preparing collection…"
                    // Pick up paintings as they finish downloading, and whatever is kept after a stop.
                    val published = it.progress.getInt("partial", 0)
                    if (published != partial) { partial = published; reload() }
                    // A cancelled worker saves its last paintings just after the state changes.
                    if (it.state.isFinished) { reload(); launch { delay(2_000); reload() } }
                }
            }
        }
    }

    private fun reload() = viewModelScope.launch {
        try {
            val loaded = withContext(Dispatchers.IO) { store.load() }
            val current = collection
            if (current != null && current.directory == loaded.directory && current.paintings.size == loaded.paintings.size) return@launch
            collection = loaded
            rebuildPlaylist(keepCurrent = current != null)
            // Point a fresh install with only the starter paintings at the one-press download, once.
            if (loaded.directory == null && !preferences.getBoolean("offeredCollection", false)) {
                preferences.edit().putBoolean("offeredCollection", true).apply()
                message = "Welcome. Choose Download full collection to install all paintings for offline viewing."
                panel = true
                interact()
            }
        } catch (e: Exception) { message = e.message ?: "Could not open collection" }
    }

    /** With [keepCurrent], a growing collection lets the painting on screen finish its time. */
    private fun rebuildPlaylist(keepCurrent: Boolean = false) {
        playlist = collection?.paintings.orEmpty().filter { it.meetsDisplayQuality(settings.minimumHeight, settings.crop) }
        deck = if (playlist.isEmpty()) null else ShuffleDeck(playlist.size)
        if (keepCurrent && painting != null && playlist.isNotEmpty()) return
        if (playlist.isNotEmpty()) return next()
        painting = null
        revision++
        message = "No paintings meet this quality filter. Choose a lower threshold or whole-painting framing."
        panel = true
        interact()
    }
    private fun show(index: Int?) { if (index != null) { painting = playlist[index]; revision++ } }
    fun next() = show(deck?.next())
    fun previous() = show(deck?.previous())
    fun interact() { controls = true; lastInteraction = android.os.SystemClock.elapsedRealtime() }

    /** Media keys always act; other keys only reveal hidden controls, then pass through for focus navigation. */
    fun remoteKey(code: Int): Boolean {
        val hidden = !controls
        val consumed = when (code) {
            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE -> { playing = !playing; true }
            KeyEvent.KEYCODE_MEDIA_PLAY -> { playing = true; true }
            KeyEvent.KEYCODE_MEDIA_PAUSE -> { playing = false; true }
            KeyEvent.KEYCODE_MEDIA_NEXT -> { next(); true }
            KeyEvent.KEYCODE_MEDIA_PREVIOUS -> { previous(); true }
            KeyEvent.KEYCODE_MENU -> { if (!hidden) panel = !panel; true }
            KeyEvent.KEYCODE_DPAD_LEFT -> { if (hidden) previous(); hidden }
            KeyEvent.KEYCODE_DPAD_RIGHT -> { if (hidden) next(); hidden }
            KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> hidden
            else -> return false
        }
        interact()
        return consumed
    }
    fun update(value: GallerySettings) {
        val refilter = settings.minimumHeight != value.minimumHeight || settings.crop != value.crop
        settings = value
        preferences.edit().putInt("slideSeconds", value.seconds).putBoolean("zoom", value.zoom)
            .putBoolean("captions", value.captions).putBoolean("crop", value.crop).putInt("minimumHeight", value.minimumHeight).apply()
        if (refilter && collection != null) rebuildPlaylist()
        interact()
    }
    fun startDownload() {
        val request = OneTimeWorkRequestBuilder<CollectionWorker>().build()
        workManager.enqueueUniqueWork("collection", ExistingWorkPolicy.KEEP, request)
        panel = true
        interact()
    }
    fun cancelDownload() { workManager.cancelUniqueWork("collection") }
    fun closePanel() { panel = false; controls = false }
    fun freeSpace(): String = "%.1f GB available".format(store.root.usableSpace / 1_000_000_000.0)
}

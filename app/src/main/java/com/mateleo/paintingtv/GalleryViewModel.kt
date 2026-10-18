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
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/** The prepared collection, hosted publicly so the TV needs no account or file transfer. */
const val COLLECTION_URL = "https://huggingface.co/datasets/Mateleo/painting-collection/resolve/main/catalog.json"

val SLIDE_SECONDS = listOf(10, 30, 60, 300, 900, 3600)

private const val UPDATE_CHECK_INTERVAL = 20 * 60 * 60 * 1000L
private const val PUBLISHED_CATALOG = "publishedCatalog"
private const val PUBLISHED_CHECKED_AT = "publishedCheckedAt"

/** Remembers the latest published catalog seen, from the update check or a finished download. */
fun recordPublishedCatalog(context: android.content.Context, sha256: String) {
    context.getSharedPreferences("settings", 0).edit().putString(PUBLISHED_CATALOG, sha256)
        .putLong(PUBLISHED_CHECKED_AT, System.currentTimeMillis()).apply()
}

data class GallerySettings(val seconds: Int = 30, val zoom: Boolean = true, val captions: Boolean = true,
    val crop: Boolean = true, val minimumHeight: Int = 0)

class GalleryViewModel(application: Application) : AndroidViewModel(application) {
    private val preferences = application.getSharedPreferences("settings", 0)
    val store = CollectionStore(application)
    /** Set by the screensaver, which never opens Settings: any key press ends it. */
    var screensaver = false
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
    /** The published catalog differs from the installed one. */
    var updateAvailable by mutableStateOf(false)
        private set
    private var deck: ShuffleDeck? = null
    private var playlist by mutableStateOf(emptyMap<String, Painting>())
    val availableCount get() = playlist.size
    private val workManager = WorkManager.getInstance(application)
    // The shuffle cycle is saved as it advances, so a restart continues it rather than starting over.
    private val deckFile = File(application.filesDir, "shuffle.json")
    private val deckSaves = Channel<String>(Channel.CONFLATED)
    private var promptedOutdated = false

    init {
        reload()
        viewModelScope.launch(Dispatchers.IO) {
            // The screen saver has its own view model: unique temporary files keep their saves apart.
            for (text in deckSaves) runCatching {
                val temporary = File.createTempFile("shuffle", ".tmp", deckFile.parentFile)
                temporary.writeText(text)
                if (!temporary.renameTo(deckFile)) temporary.delete()
            }
        }
        viewModelScope.launch {
            while (true) { checkForUpdate().join(); delay(60 * 60 * 1000L) }
        }
        viewModelScope.launch {
            var partial = 0
            workManager.getWorkInfosForUniqueWorkFlow("collection").collect { infos ->
                val work = infos.maxByOrNull { it.generation }
                working = infos.any { !it.state.isFinished }
                work?.let {
                    downloadMessage = if (it.state.isFinished) it.outputData.getString("message")
                        ?: if (it.state == WorkInfo.State.CANCELLED) string(R.string.download_paused) else ""
                    else it.progress.getString("message") ?: string(R.string.download_preparing)
                    // Pick up paintings as they finish downloading, and whatever is kept after a stop.
                    val published = it.progress.getInt("partial", 0)
                    if (published != partial) { partial = published; reload() }
                    // A cancelled worker saves its last paintings just after the state changes.
                    if (it.state.isFinished) { reload(); checkForUpdate(); launch { delay(2_000); reload() } }
                }
            }
        }
    }

    private fun string(id: Int, vararg arguments: Any) = getApplication<Application>().getString(id, *arguments)

    private fun reload() = viewModelScope.launch {
        try {
            val restoring = deck == null
            val (loaded, saved) = withContext(Dispatchers.IO) {
                store.load() to if (restoring) readDeck() else null
            }
            val current = collection
            if (current != null && current.directory == loaded.directory && current.paintings.size == loaded.paintings.size) return@launch
            collection = loaded
            rebuildPlaylist(keepCurrent = current != null, saved)
            if (screensaver) return@launch
            if (loaded.outdated && !promptedOutdated) {
                promptedOutdated = true
                message = string(R.string.collection_outdated)
                panel = true
                interact()
            } else if (loaded.directory == null && !preferences.getBoolean("offeredCollection", false)) {
                // Point a fresh install with only the starter paintings at the one-press download, once.
                preferences.edit().putBoolean("offeredCollection", true).apply()
                message = string(R.string.welcome)
                panel = true
                interact()
            }
        } catch (e: Exception) { message = e.message ?: string(R.string.collection_unreadable) }
    }

    /** With [keepCurrent], a growing collection lets the painting on screen finish its time. */
    private fun rebuildPlaylist(keepCurrent: Boolean = false, saved: ShuffleDeck.State? = null) {
        val visible = collection?.paintings.orEmpty().filter { it.meetsDisplayQuality(settings.minimumHeight, settings.crop) }
        playlist = visible.associateBy { it.id }
        val ids = visible.map { it.id }
        deck = deck?.apply { update(ids) } ?: ShuffleDeck(ids, saved)
        if (keepCurrent && painting?.id in playlist) return
        if (playlist.isNotEmpty()) return next()
        painting = null
        revision++
        if (screensaver) return
        message = string(R.string.filter_empty)
        panel = true
        interact()
    }

    private fun readDeck() = runCatching { ShuffleDeck.decode(deckFile.readText()) }.getOrNull()

    /** Continues from the saved shuffle, which the screen saver may have advanced. */
    fun restoreShuffle() = viewModelScope.launch {
        val saved = withContext(Dispatchers.IO) { readDeck() } ?: return@launch
        if (deck != null) deck = ShuffleDeck(playlist.keys, saved)
    }

    private fun show(id: String?) {
        painting = playlist[id ?: return] ?: return
        revision++
        deck?.let { deckSaves.trySend(ShuffleDeck.encode(it.state)) }
    }
    fun next() = show(deck?.next())
    fun previous() = show(deck?.previous())
    /** The painting [next] will show, so it can be decoded ahead of time. */
    fun upcoming(): Painting? = deck?.peek()?.let { playlist[it] }
    fun interact() { controls = true; lastInteraction = android.os.SystemClock.elapsedRealtime() }

    /** Compares the installed catalog with the published one, fetching the latter at most about once a day. */
    private fun checkForUpdate() = viewModelScope.launch(Dispatchers.IO) {
        val installed = store.installedManifest ?: return@launch
        var remote = preferences.getString(PUBLISHED_CATALOG, null)
        if (remote == null || System.currentTimeMillis() - preferences.getLong(PUBLISHED_CHECKED_AT, 0) > UPDATE_CHECK_INTERVAL) {
            val file = File.createTempFile("published-catalog", ".json", getApplication<Application>().cacheDir)
            runCatching {
                download(COLLECTION_URL, file, 32L * 1024 * 1024)
                CollectionStore.parse(file.readText())
                val published = sha256(file)
                remote = published
                recordPublishedCatalog(getApplication(), published)
            }
            file.delete()
        }
        val available = remote != null && remote != runCatching { sha256(installed) }.getOrNull()
        withContext(Dispatchers.Main) { updateAvailable = available }
    }

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
    fun freeSpace(): String = string(R.string.free_space, store.root.usableSpace / 1_000_000_000.0)
}

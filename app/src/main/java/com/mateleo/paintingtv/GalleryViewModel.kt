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
import androidx.work.workDataOf
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

data class GallerySettings(val seconds: Int = 10, val zoom: Boolean = true, val captions: Boolean = true,
    val crop: Boolean = true, val minimumHeight: Int = 0)

class GalleryViewModel(application: Application) : AndroidViewModel(application) {
    private val preferences = application.getSharedPreferences("settings", 0)
    val store = CollectionStore(application)
    var settings by mutableStateOf(GallerySettings(
        preferences.getInt("seconds", 10), preferences.getBoolean("zoom", true),
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
    var importMessage by mutableStateOf("")
        private set
    private var deck: ShuffleDeck? = null
    private var playlist by mutableStateOf(emptyList<Painting>())
    val availableCount get() = playlist.size
    private val workManager = WorkManager.getInstance(application)
    val inboxFile = File(application.getExternalFilesDir(null), "inbox/collection.zip")

    init {
        reload()
        viewModelScope.launch {
            workManager.getWorkInfosForUniqueWorkFlow("collection").collect { infos ->
                val work = infos.maxByOrNull { it.generation }
                working = infos.any { !it.state.isFinished }
                work?.let {
                    importMessage = if (it.state.isFinished) it.outputData.getString("message")
                        ?: if (it.state == WorkInfo.State.CANCELLED) "Import cancelled. Your gallery is unchanged." else ""
                    else it.progress.getString("message") ?: "Preparing collection…"
                    if (it.state == WorkInfo.State.SUCCEEDED) reload()
                }
            }
        }
        inboxFile.parentFile?.mkdirs()
        val signature = "${inboxFile.length()}:${inboxFile.lastModified()}"
        if (inboxFile.isFile && preferences.getString("inbox", null) != signature) {
            preferences.edit().putString("inbox", signature).apply()
            retryInbox()
        }
    }

    private fun reload() = viewModelScope.launch {
        try {
            val loaded = withContext(Dispatchers.IO) { store.load() }
            if (collection?.directory == loaded.directory && collection != null) return@launch
            collection = loaded
            rebuildPlaylist()
        } catch (e: Exception) { message = e.message ?: "Could not open collection" }
    }

    private fun rebuildPlaylist() {
        playlist = collection?.paintings.orEmpty().filter { it.meetsDisplayQuality(settings.minimumHeight, settings.crop) }
        deck = if (playlist.isEmpty()) null else ShuffleDeck(playlist.size)
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
        preferences.edit().putInt("seconds", value.seconds).putBoolean("zoom", value.zoom)
            .putBoolean("captions", value.captions).putBoolean("crop", value.crop).putInt("minimumHeight", value.minimumHeight).apply()
        if (refilter && collection != null) rebuildPlaylist()
        interact()
    }
    fun startImport(source: String, mode: String) {
        val request = OneTimeWorkRequestBuilder<CollectionWorker>()
            .setInputData(workDataOf("source" to source, "mode" to mode)).build()
        workManager.enqueueUniqueWork("collection", ExistingWorkPolicy.KEEP, request)
        panel = true
        interact()
    }
    fun cancelImport() { workManager.cancelUniqueWork("collection") }
    fun retryInbox() = startImport("file:${inboxFile.absolutePath}", "zip")
    fun freeSpace(): String = "%.1f GB available".format(store.root.usableSpace / 1_000_000_000.0)
}

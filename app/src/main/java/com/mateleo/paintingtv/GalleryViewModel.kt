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

data class GallerySettings(val seconds: Int = 10, val zoom: Boolean = true, val captions: Boolean = true, val crop: Boolean = true)

class GalleryViewModel(application: Application) : AndroidViewModel(application) {
    private val preferences = application.getSharedPreferences("settings", 0)
    val store = CollectionStore(application)
    var settings by mutableStateOf(GallerySettings(
        preferences.getInt("seconds", 10), preferences.getBoolean("zoom", true),
        preferences.getBoolean("captions", true), preferences.getBoolean("crop", true)))
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
    private val workManager = WorkManager.getInstance(application)

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
        val inbox = File(application.getExternalFilesDir(null), "inbox").apply { mkdirs() }
        val zip = File(inbox, "collection.zip")
        if (zip.isFile) {
            val signature = "${zip.length()}:${zip.lastModified()}"
            if (preferences.getString("inbox", null) != signature) {
                preferences.edit().putString("inbox", signature).apply()
                startImport("file:${zip.absolutePath}", "zip")
            }
        }
    }

    private fun reload() = viewModelScope.launch {
        try {
            val loaded = withContext(Dispatchers.IO) { store.load() }
            if (collection?.directory == loaded.directory && collection != null) return@launch
            collection = loaded
            deck = ShuffleDeck(loaded.paintings.size)
            next()
        } catch (e: Exception) { message = e.message ?: "Could not open collection" }
    }

    fun next() { deck?.let { painting = collection!!.paintings[it.next()]; revision++ } }
    fun previous() { deck?.let { painting = collection!!.paintings[it.previous()]; revision++ } }
    fun interact() { controls = true; lastInteraction = android.os.SystemClock.elapsedRealtime() }
    fun remoteKey(code: Int): Boolean {
        when (code) {
            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE -> { playing = !playing; interact(); return true }
            KeyEvent.KEYCODE_MEDIA_PLAY -> { playing = true; interact(); return true }
            KeyEvent.KEYCODE_MEDIA_PAUSE -> { playing = false; interact(); return true }
            KeyEvent.KEYCODE_MEDIA_NEXT -> { next(); interact(); return true }
            KeyEvent.KEYCODE_MEDIA_PREVIOUS -> { previous(); interact(); return true }
            KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_DPAD_LEFT,
            KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER,
            KeyEvent.KEYCODE_MENU -> {
                val wasHidden = !controls
                interact()
                if (wasHidden) {
                    if (code == KeyEvent.KEYCODE_DPAD_LEFT) previous()
                    if (code == KeyEvent.KEYCODE_DPAD_RIGHT) next()
                    return true
                }
                if (code == KeyEvent.KEYCODE_MENU) { panel = !panel; return true }
            }
        }
        return false
    }
    fun update(value: GallerySettings) {
        settings = value
        preferences.edit().putInt("seconds", value.seconds).putBoolean("zoom", value.zoom)
            .putBoolean("captions", value.captions).putBoolean("crop", value.crop).apply()
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
    fun inboxFile() = File(getApplication<Application>().getExternalFilesDir(null), "inbox/collection.zip")
    fun retryInbox() { startImport("file:${inboxFile().absolutePath}", "zip") }
    fun freeSpace(): String = "%.1f GB available".format(store.root.usableSpace / 1_000_000_000.0)
}

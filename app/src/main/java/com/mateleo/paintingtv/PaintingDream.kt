package com.mateleo.paintingtv

import android.service.dreams.DreamService
import androidx.compose.ui.platform.ComposeView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LifecycleRegistry
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.setViewTreeLifecycleOwner
import androidx.lifecycle.setViewTreeViewModelStoreOwner
import androidx.savedstate.SavedStateRegistryController
import androidx.savedstate.SavedStateRegistryOwner
import androidx.savedstate.setViewTreeSavedStateRegistryOwner

/**
 * The slideshow as the TV's screen saver: paintings only, continuing the app's shuffle cycle.
 * It is not interactive, so any key press wakes the TV as with the system screen saver.
 */
class PaintingDream : DreamService(), LifecycleOwner, ViewModelStoreOwner, SavedStateRegistryOwner {
    // Compose needs these owners, which a DreamService does not provide on its own.
    private val lifecycleRegistry = LifecycleRegistry(this)
    private val savedState = SavedStateRegistryController.create(this)
    override val lifecycle: Lifecycle get() = lifecycleRegistry
    override val viewModelStore = ViewModelStore()
    override val savedStateRegistry get() = savedState.savedStateRegistry

    override fun onCreate() {
        super.onCreate()
        savedState.performRestore(null)
        lifecycleRegistry.currentState = Lifecycle.State.CREATED
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        isInteractive = false
        isFullscreen = true
        isScreenBright = true
        // No 4K mode request here: switching the HDMI mode would blank the TV as the screen saver starts and ends.
        val gallery = ViewModelProvider(this, ViewModelProvider.AndroidViewModelFactory.getInstance(application))[GalleryViewModel::class.java]
        gallery.screensaver = true
        setContentView(ComposeView(this).apply {
            setViewTreeLifecycleOwner(this@PaintingDream)
            setViewTreeViewModelStoreOwner(this@PaintingDream)
            setViewTreeSavedStateRegistryOwner(this@PaintingDream)
            setContent { Gallery(gallery, screensaver = true) }
        })
    }

    override fun onDreamingStarted() {
        super.onDreamingStarted()
        lifecycleRegistry.currentState = Lifecycle.State.RESUMED
    }

    override fun onDreamingStopped() {
        lifecycleRegistry.currentState = Lifecycle.State.CREATED
        super.onDreamingStopped()
    }

    override fun onDestroy() {
        lifecycleRegistry.currentState = Lifecycle.State.DESTROYED
        viewModelStore.clear()
        super.onDestroy()
    }
}

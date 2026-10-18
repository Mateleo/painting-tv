package com.mateleo.paintingtv

import android.Manifest
import android.os.Build
import android.os.Bundle
import android.view.Window
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.ViewModelProvider

class MainActivity : ComponentActivity() {
    private lateinit var gallery: GalleryViewModel
    private val notifications = registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        WindowInsetsControllerCompat(window, window.decorView).apply {
            hide(WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
        window.requestUhdMode()
        gallery = ViewModelProvider(this)[GalleryViewModel::class.java]
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                when {
                    gallery.panel -> gallery.closePanel()
                    gallery.controls -> gallery.controls = false
                    else -> finish()
                }
            }
        })
        setContent { Gallery(gallery, onDownload = { requestNotifications(); gallery.startDownload() }) }
    }

    override fun onRestart() {
        super.onRestart()
        // The screen saver may have moved the shuffle on while the app was in the background.
        gallery.restoreShuffle()
    }

    private fun requestNotifications() {
        if (Build.VERSION.SDK_INT >= 33) notifications.launch(Manifest.permission.POST_NOTIFICATIONS)
    }
}

/** Requests a 4K display mode when the TV exposes one. No refresh-rate change. */
fun Window.requestUhdMode() {
    @Suppress("DEPRECATION")
    val display = windowManager.defaultDisplay
    val mode = display.supportedModes.filter { it.physicalWidth >= 3840 && it.refreshRate == display.mode.refreshRate }
        .maxByOrNull { it.physicalWidth * it.physicalHeight }
    if (mode != null) attributes = attributes.apply { preferredDisplayModeId = mode.modeId }
}

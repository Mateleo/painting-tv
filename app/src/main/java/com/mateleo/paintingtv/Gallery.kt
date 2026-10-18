package com.mateleo.paintingtv

import android.graphics.Bitmap
import android.view.KeyEvent
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Image
import androidx.compose.foundation.focusable
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.currentStateAsState
import androidx.tv.material3.Button
import androidx.tv.material3.ButtonDefaults
import androidx.tv.material3.MaterialTheme
import androidx.tv.material3.Text
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

private val Ivory = Color(0xFFF0E7D4)
private val Muted = Color(0xFFBDB9B0)
private val Panel = Color(0xF5141916)
/** Each frame owns its zoom/timer progress, so the outgoing painting keeps its scale during the dissolve. */
private class Frame(val bitmap: Bitmap, val painting: Painting, val revision: Int) { val progress = Animatable(0f) }

@Composable
fun Gallery(vm: GalleryViewModel, onDownload: () -> Unit) {
    val active = LocalLifecycleOwner.current.lifecycle.currentStateAsState().value.isAtLeast(Lifecycle.State.RESUMED)
    val configuration = LocalConfiguration.current
    val density = LocalDensity.current.density
    var frame by remember { mutableStateOf<Frame?>(null) }
    val collection = vm.collection
    val painting = vm.painting
    val revision = vm.revision
    val settings = vm.settings
    val focus = remember { FocusRequester() }
    val rootFocus = remember { FocusRequester() }

    // Keyed on the revision only: a collection that grows during a download keeps the painting on screen.
    LaunchedEffect(revision) {
        if (collection == null) return@LaunchedEffect
        if (painting == null) { frame = null; return@LaunchedEffect }
        try {
            val bitmap = withContext(Dispatchers.IO) {
                vm.store.decode(collection, painting,
                    (configuration.screenWidthDp * density).toInt(), (configuration.screenHeightDp * density).toInt(), settings.crop)
            }
            frame = Frame(bitmap, painting, revision)
            vm.message = ""
        } catch (cancelled: kotlinx.coroutines.CancellationException) {
            throw cancelled
        } catch (e: Throwable) { // Includes OutOfMemoryError from an oversized scan.
            vm.message = "Cannot open ${painting.title}. ${e.message.orEmpty()}"
            vm.interact()
            delay(5000)
            if (vm.playing && !vm.panel) vm.next()
        }
    }

    LaunchedEffect(revision, frame, settings.seconds, vm.playing, active, vm.panel) {
        val progress = frame?.takeIf { it.revision == revision && vm.playing && active && !vm.panel }?.progress ?: return@LaunchedEffect
        progress.animateTo(1f, tween(((1f - progress.value) * settings.seconds * 1000).toInt(), easing = LinearEasing))
        vm.next()
    }
    LaunchedEffect(vm.lastInteraction, vm.controls, vm.panel) {
        if (vm.controls && !vm.panel) { delay(5000); vm.controls = false }
    }
    LaunchedEffect(vm.controls, vm.panel) {
        if (vm.controls && !vm.panel) { delay(100); focus.requestFocus() }
        else if (!vm.controls) rootFocus.requestFocus()
    }

    MaterialTheme {
        Box(Modifier.fillMaxSize().background(Color.Black).focusRequester(rootFocus)
            .onPreviewKeyEvent { it.nativeKeyEvent.action == KeyEvent.ACTION_DOWN && vm.remoteKey(it.nativeKeyEvent.keyCode) }
            .focusable()) {
            AnimatedContent(frame, transitionSpec = { fadeIn(tween(1100)) togetherWith fadeOut(tween(1100)) },
                label = "Painting dissolve", modifier = Modifier.fillMaxSize()) { shown ->
                if (shown != null) {
                    val zoom = settings.zoom && settings.crop
                    Image(shown.bitmap.asImageBitmap(), contentDescription = "${shown.painting.title}, ${shown.painting.artist}",
                        contentScale = if (settings.crop) ContentScale.Crop else ContentScale.Fit,
                        modifier = Modifier.fillMaxSize().clipToBounds().graphicsLayer {
                            scaleX = if (zoom) 1f + shown.progress.value * 0.045f else 1f
                            scaleY = scaleX
                        })
                }
            }
            val shown = frame?.painting
            if (settings.captions && shown != null && !vm.panel) {
                Box(Modifier.align(Alignment.BottomStart).fillMaxWidth()
                    .background(Brush.verticalGradient(listOf(Color.Transparent, Color.Black.copy(alpha = 0.65f))))
                    .padding(start = 42.dp, end = 42.dp, top = 60.dp, bottom = if (vm.controls) 116.dp else 34.dp)) {
                    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text(shown.title, color = Color.White, fontSize = 25.sp, fontStyle = FontStyle.Italic, fontFamily = FontFamily.Serif)
                        Text(listOf(shown.artist, shown.year, shown.movement, shown.collection).filter { it.isNotBlank() }.joinToString("  ·  "),
                            color = Color.White.copy(alpha = 0.86f), fontSize = 14.sp)
                    }
                }
            }
            if (frame == null) {
                Text(if (collection != null && painting == null) "No paintings match the selected quality filter." else "Opening the gallery…",
                    color = Ivory, modifier = Modifier.align(Alignment.Center))
            }
            AnimatedVisibility(vm.controls && !vm.panel, enter = fadeIn(), exit = fadeOut(), modifier = Modifier.align(Alignment.BottomCenter)) {
                Column(Modifier.fillMaxWidth().background(Brush.verticalGradient(listOf(Color.Transparent, Color.Black.copy(alpha = 0.88f))))
                    .padding(horizontal = 42.dp, vertical = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    if (vm.message.isNotBlank()) Text(vm.message, color = Color(0xFFFFD1A4), fontSize = 13.sp)
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        GalleryButton("Previous", onClick = { vm.previous(); vm.interact() })
                        GalleryButton(if (vm.playing) "Pause" else "Play", Modifier.focusRequester(focus), onClick = { vm.playing = !vm.playing; vm.interact() })
                        GalleryButton("Next", onClick = { vm.next(); vm.interact() })
                        Spacer(Modifier.weight(1f))
                        Text("${vm.availableCount} paintings  ·  ${settings.seconds}s", color = Muted, fontSize = 13.sp)
                        GalleryButton("Settings", onClick = { vm.panel = true; vm.interact() })
                    }
                    Box(Modifier.fillMaxWidth().height(2.dp).background(Color.White.copy(alpha = 0.15f))) {
                        Box(Modifier.fillMaxWidth(frame?.progress?.value ?: 0f).fillMaxHeight().background(Ivory))
                    }
                }
            }
            if (vm.panel) SettingsPanel(vm, onDownload)
        }
    }
}

@Composable
private fun GalleryButton(label: String, modifier: Modifier = Modifier, selected: Boolean = false, onClick: () -> Unit) {
    Button(onClick, modifier, colors = ButtonDefaults.colors(
        containerColor = if (selected) Ivory.copy(alpha = 0.3f) else Color.White.copy(alpha = 0.09f),
        contentColor = Ivory, focusedContainerColor = Ivory, focusedContentColor = Color(0xFF171C18))) {
        Text(label, fontSize = 14.sp, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal)
    }
}

@Composable
private fun Heading(text: String) = Text(text, color = Muted, fontSize = 13.sp)

@Composable
private fun SettingsPanel(vm: GalleryViewModel, onDownload: () -> Unit) {
    val settings = vm.settings
    val collection = vm.collection
    val focus = remember { FocusRequester() }
    val downloadFocus = remember { FocusRequester() }
    val cancelFocus = remember { FocusRequester() }
    // Until the full collection is in, the panel opens on the download button so one OK press fetches it.
    val incomplete = collection != null && (collection.directory == null || collection.partial)
    val offerDownload = incomplete && !vm.working
    // Also moves focus when the pressed download/cancel button is swapped for the other.
    LaunchedEffect(vm.working) {
        delay(100)
        runCatching { (if (vm.working) cancelFocus else if (offerDownload) downloadFocus else focus).requestFocus() }
    }
    Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.65f)), contentAlignment = Alignment.CenterEnd) {
        Column(Modifier.width(560.dp).fillMaxHeight().background(Panel).verticalScroll(rememberScrollState()).padding(32.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                Text("Settings", color = Ivory, fontSize = 27.sp, fontFamily = FontFamily.Serif, modifier = Modifier.weight(1f))
                GalleryButton("Done", Modifier.focusRequester(focus), onClick = vm::closePanel)
            }
            Heading("Time per painting")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SLIDE_SECONDS.forEach { seconds ->
                    val label = if (seconds < 60) "${seconds}s" else if (seconds < 3600) "${seconds / 60}m" else "1h"
                    GalleryButton(label, selected = seconds == settings.seconds, onClick = { vm.update(settings.copy(seconds = seconds)) })
                }
            }
            Heading("Framing")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                GalleryButton("Fill screen", selected = settings.crop, onClick = { vm.update(settings.copy(crop = true)) })
                GalleryButton("Whole painting", selected = !settings.crop, onClick = { vm.update(settings.copy(crop = false)) })
            }
            Heading("Display")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                // Zoom only applies when the painting fills the screen.
                if (settings.crop) GalleryButton("Slow zoom", selected = settings.zoom, onClick = { vm.update(settings.copy(zoom = !settings.zoom)) })
                GalleryButton("Captions", selected = settings.captions, onClick = { vm.update(settings.copy(captions = !settings.captions)) })
            }
            Heading("Image quality")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                listOf(0 to "All", 1080 to "HD+", 2160 to "4K+").forEach { (height, label) ->
                    GalleryButton(label, selected = settings.minimumHeight == height, onClick = { vm.update(settings.copy(minimumHeight = height)) })
                }
                Text("${vm.availableCount} paintings", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(start = 8.dp))
            }
            Spacer(Modifier.height(4.dp))
            Box(Modifier.fillMaxWidth().height(1.dp).background(Color.White.copy(alpha = 0.12f)))
            Heading("Collection · ${collection?.paintings?.size ?: 0} paintings · ${vm.freeSpace()}")
            if (vm.working) {
                if (vm.downloadMessage.isNotBlank()) Text(vm.downloadMessage, color = Ivory, fontSize = 14.sp)
                GalleryButton("Cancel", Modifier.focusRequester(cancelFocus), onClick = vm::cancelDownload)
            } else {
                if (vm.downloadMessage.isNotBlank()) Text(vm.downloadMessage, color = Ivory, fontSize = 13.sp)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (incomplete) GalleryButton(if (collection?.partial == true) "Resume download" else "Download all · 2.9 GB",
                        Modifier.focusRequester(downloadFocus), onClick = onDownload)
                }
            }
            if (vm.message.isNotBlank()) Text(vm.message, color = Color(0xFFFFD1A4), fontSize = 13.sp)
        }
    }
}

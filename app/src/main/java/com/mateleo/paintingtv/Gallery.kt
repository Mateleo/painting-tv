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
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
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
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
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
private data class Frame(val bitmap: Bitmap, val painting: Painting, val revision: Int)

@Composable
fun Gallery(vm: GalleryViewModel, onImport: () -> Unit, onDownload: (String) -> Unit) {
    val owner = LocalLifecycleOwner.current
    val lifecycle by owner.lifecycle.currentStateFlow.collectAsStateWithLifecycle()
    val active = lifecycle.isAtLeast(Lifecycle.State.RESUMED)
    val configuration = LocalConfiguration.current
    val density = LocalDensity.current.density
    var frame by remember { mutableStateOf<Frame?>(null) }
    var loading by remember { mutableStateOf(true) }
    val collection = vm.collection
    val painting = vm.painting
    val revision = vm.revision
    val settings = vm.settings
    val focus = remember { FocusRequester() }
    val rootFocus = remember { FocusRequester() }
    val progress = remember(revision) { Animatable(0f) }

    LaunchedEffect(collection, revision) {
        if (collection == null) return@LaunchedEffect
        if (painting == null) { frame = null; loading = false; return@LaunchedEffect }
        loading = true
        try {
            val bitmap = withContext(Dispatchers.IO) {
                vm.store.decode(collection, painting,
                    (configuration.screenWidthDp * density).toInt(), (configuration.screenHeightDp * density).toInt())
            }
            frame = Frame(bitmap, painting, revision)
            vm.message = ""
        } catch (cancelled: kotlinx.coroutines.CancellationException) {
            throw cancelled
        } catch (e: Exception) {
            vm.message = "Cannot open ${painting.title}. Use Next to skip. ${e.message.orEmpty()}"
            vm.interact()
        } finally { loading = false }
    }

    LaunchedEffect(revision, frame, settings.seconds, vm.playing, active, vm.panel) {
        if (frame?.revision != revision || !vm.playing || !active || vm.panel) return@LaunchedEffect
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
                    Box(Modifier.fillMaxSize().clipToBounds()) {
                        val scale = if (shown.revision == revision && settings.zoom && settings.crop) 1f + progress.value * 0.045f else 1f
                        Image(shown.bitmap.asImageBitmap(), contentDescription = "${shown.painting.title}, ${shown.painting.artist}",
                            contentScale = if (settings.crop) ContentScale.Crop else ContentScale.Fit,
                            modifier = Modifier.fillMaxSize().graphicsLayer { scaleX = scale; scaleY = scale })
                    }
                }
            }
            val shown = frame?.painting
            if (settings.captions && shown != null && !vm.panel) {
                Box(Modifier.align(Alignment.BottomStart).fillMaxWidth()
                    .background(Brush.verticalGradient(listOf(Color.Transparent, Color.Black.copy(alpha = 0.65f))))
                    .padding(start = 42.dp, end = 42.dp, top = 60.dp, bottom = if (vm.controls) 116.dp else 34.dp)) {
                    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text(shown.title, color = Color.White, fontSize = 25.sp, fontStyle = FontStyle.Italic, fontFamily = FontFamily.Serif)
                        Text(listOf(shown.artist, shown.year, shown.movement).filter { it.isNotBlank() }.joinToString("  ·  "),
                            color = Color.White.copy(alpha = 0.86f), fontSize = 14.sp)
                    }
                }
            }
            if (loading && frame == null) {
                Text("Opening the gallery…", color = Ivory, modifier = Modifier.align(Alignment.Center))
            } else if (frame == null) {
                Text("No paintings match the selected quality filter.", color = Ivory, modifier = Modifier.align(Alignment.Center))
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
                        Box(Modifier.fillMaxWidth(progress.value.coerceIn(0f, 1f)).fillMaxHeight().background(Ivory))
                    }
                }
            }
            if (vm.panel) SettingsPanel(vm, onImport, onDownload)
        }
    }
}

@Composable
private fun GalleryButton(label: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Button(onClick, modifier, colors = ButtonDefaults.colors(containerColor = Color.White.copy(alpha = 0.09f),
        contentColor = Ivory, focusedContainerColor = Ivory, focusedContentColor = Color(0xFF171C18))) {
        Text(label, fontSize = 14.sp)
    }
}

@Composable
private fun SettingsPanel(vm: GalleryViewModel, onImport: () -> Unit, onDownload: (String) -> Unit) {
    val settings = vm.settings
    val focus = remember { FocusRequester() }
    var url by rememberSaveable { mutableStateOf("") }
    LaunchedEffect(Unit) { delay(100); focus.requestFocus() }
    Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.65f)), contentAlignment = Alignment.CenterEnd) {
        Column(Modifier.width(560.dp).fillMaxHeight().background(Panel).verticalScroll(rememberScrollState()).padding(32.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                Text("Gallery settings", color = Ivory, fontSize = 27.sp, fontFamily = FontFamily.Serif, modifier = Modifier.weight(1f))
                GalleryButton("Done", Modifier.focusRequester(focus), onClick = { vm.panel = false; vm.interact() })
            }
            Text("Pause here. Your gallery resumes when you close settings.", color = Muted, fontSize = 13.sp)
            Text("Time with each painting", color = Ivory, fontSize = 16.sp)
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                listOf(listOf(5, 10, 30), listOf(60, 300, 900, 3600)).forEach { group ->
                    Row(horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                        group.forEach { seconds ->
                            val label = if (seconds < 60) "${seconds}s" else if (seconds < 3600) "${seconds / 60}m" else "1h"
                            GalleryButton((if (seconds == settings.seconds) "• " else "") + label,
                                onClick = { vm.update(settings.copy(seconds = seconds)) })
                        }
                    }
                }
            }
            GalleryButton("Gentle zoom: ${if (settings.zoom) "on" else "off"}", onClick = { vm.update(settings.copy(zoom = !settings.zoom)) })
            GalleryButton("Artwork captions: ${if (settings.captions) "on" else "off"}", onClick = { vm.update(settings.copy(captions = !settings.captions)) })
            GalleryButton("Framing: ${if (settings.crop) "fill screen" else "whole painting"}", onClick = { vm.update(settings.copy(crop = !settings.crop)) })
            Text("Whole painting adds black margins and keeps the image still so its edges stay visible.", color = Muted, fontSize = 12.sp)
            Text("Minimum source quality", color = Ivory, fontSize = 16.sp)
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                listOf(0 to "All", 1080 to "HD+", 2160 to "4K+").forEach { (height, label) ->
                    GalleryButton((if (settings.minimumHeight == height) "• " else "") + label,
                        onClick = { vm.update(settings.copy(minimumHeight = height)) })
                }
            }
            Text("${vm.availableCount} of ${vm.collection?.paintings?.size ?: 0} match this framing and quality. A larger file cannot restore detail missing from its source.", color = Muted, fontSize = 12.sp)
            vm.painting?.let { Text("Current source: ${it.width} × ${it.height} pixels", color = Muted, fontSize = 12.sp) }
            Box(Modifier.fillMaxWidth().height(1.dp).background(Color.White.copy(alpha = 0.12f)))
            Text("Offline collection", color = Ivory, fontSize = 21.sp, fontFamily = FontFamily.Serif)
            Text("${vm.collection?.paintings?.size ?: 0} paintings installed · ${vm.freeSpace()}", color = Muted, fontSize = 13.sp)
            Text("Import a collection ZIP from USB, or download a prepared collection once. Playback uses local files.", color = Muted, fontSize = 13.sp)
            if (!vm.working) {
                GalleryButton("Import collection ZIP", onClick = onImport)
                if (vm.inboxFile().isFile) GalleryButton("Import inbox ZIP again", onClick = vm::retryInbox)
                Text("Collection manifest URL (HTTPS)", color = Ivory, fontSize = 13.sp)
                BasicTextField(url, onValueChange = { url = it }, singleLine = true,
                    textStyle = TextStyle(color = Ivory, fontSize = 14.sp), cursorBrush = androidx.compose.ui.graphics.SolidColor(Ivory),
                    modifier = Modifier.fillMaxWidth().border(1.dp, Color.White.copy(alpha = 0.4f), RoundedCornerShape(6.dp)).padding(14.dp),
                    decorationBox = { inner -> if (url.isEmpty()) Text("https://…/catalog.json", color = Muted, fontSize = 14.sp); inner() })
                GalleryButton("Download whole collection", onClick = {
                    if (url.trim().startsWith("https://")) onDownload(url.trim())
                    else vm.message = "Enter an HTTPS manifest URL, or import a ZIP."
                })
            } else GalleryButton("Cancel import", onClick = vm::cancelImport)
            if (vm.importMessage.isNotBlank()) Text(vm.importMessage, color = Ivory, fontSize = 13.sp)
            if (vm.message.isNotBlank()) Text(vm.message, color = Color(0xFFFFD1A4), fontSize = 13.sp)
            Text("Painting TV · Sources and image credits are preserved in the collection catalog.", color = Muted, fontSize = 11.sp)
        }
    }
}

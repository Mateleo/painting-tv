package com.mateleo.paintingtv

import android.graphics.Bitmap
import android.os.SystemClock
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
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
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
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.withContext

private val Ivory = Color(0xFFF0E7D4)
private val Muted = Color(0xFFBDB9B0)
private val Panel = Color(0xF5141916)
private const val DISSOLVE_MILLIS = 1100
/** Each frame owns its zoom/timer progress, so the outgoing painting keeps its scale during the dissolve. */
private class Frame(val bitmap: Bitmap, val painting: Painting, val revision: Int) { val progress = Animatable(0f) }
/** The next painting, decoded during the current one so its dissolve starts on time. */
private class Prepared(val painting: Painting, val crop: Boolean, val bitmap: Bitmap)

private fun durationLabel(seconds: Int) = if (seconds < 60) "${seconds}s" else if (seconds < 3600) "${seconds / 60}m" else "1h"

/** The slideshow with its remote controls and Settings; the [screensaver] shows paintings only. */
@Composable
fun Gallery(vm: GalleryViewModel, onDownload: () -> Unit = {}, screensaver: Boolean = false) {
    val active = LocalLifecycleOwner.current.lifecycle.currentStateAsState().value.isAtLeast(Lifecycle.State.RESUMED)
    val configuration = LocalConfiguration.current
    val density = LocalDensity.current.density
    var frame by remember { mutableStateOf<Frame?>(null) }
    var prepared by remember { mutableStateOf<Prepared?>(null) }
    val collection = vm.collection
    val painting = vm.painting
    val revision = vm.revision
    val settings = vm.settings
    val focus = remember { FocusRequester() }
    val rootFocus = remember { FocusRequester() }
    val context = LocalContext.current

    // The screen saver may need the memory while the app waits in the background.
    LaunchedEffect(active) { if (!active) prepared = null }

    // Keyed on the revision only: a collection that grows during a download keeps the painting on screen.
    LaunchedEffect(revision) {
        if (collection == null) return@LaunchedEffect
        if (painting == null) { frame = null; return@LaunchedEffect }
        val crop = settings.crop
        // A painting prepared for another turn or framing is dropped first, so at most two large bitmaps are alive.
        val ready = prepared?.takeIf { it.painting == painting && it.crop == crop }
        prepared = null
        try {
            frame = Frame(ready?.bitmap ?: vm.store.decode(collection, painting,
                (configuration.screenWidthDp * density).toInt(), (configuration.screenHeightDp * density).toInt(), crop), painting, revision)
            vm.message = ""
        } catch (cancelled: kotlinx.coroutines.CancellationException) {
            throw cancelled
        } catch (e: Throwable) { // Includes OutOfMemoryError from an oversized scan.
            vm.message = context.getString(R.string.cannot_open_painting, painting.title, e.message.orEmpty())
            vm.interact()
            delay(5000)
            if (vm.playing && !vm.panel) vm.next()
            return@LaunchedEffect
        }
    }

    // Settings and backgrounded screens do not need look-ahead work competing with remote input.
    // Keep this separate from the foreground decode so framing changes can still preview immediately.
    LaunchedEffect(frame, revision, active, vm.panel) {
        val shown = frame?.takeIf { it.revision == vm.revision && active && !vm.panel } ?: return@LaunchedEffect
        val loaded = vm.collection ?: return@LaunchedEffect
        val crop = vm.settings.crop
        // Wait for the dissolve to release the outgoing bitmap, then prepare the next painting.
        delay(DISSOLVE_MILLIS + 400L)
        val upcoming = vm.upcoming()?.takeIf { it != shown.painting } ?: return@LaunchedEffect
        if (prepared?.let { it.painting == upcoming && it.crop == crop } == true) return@LaunchedEffect
        try {
            prepared = Prepared(upcoming, crop, vm.store.decode(loaded, upcoming,
                (configuration.screenWidthDp * density).toInt(), (configuration.screenHeightDp * density).toInt(), crop, background = true))
        } catch (cancelled: kotlinx.coroutines.CancellationException) {
            throw cancelled
        } catch (_: Throwable) {} // Its own turn reports the error.
    }

    val controls = vm.controls && !vm.panel && !screensaver
    // Only the slow zoom and the visible progress bar need a new frame each vsync; otherwise just wait.
    val animate = settings.zoom && settings.crop || controls
    LaunchedEffect(revision, frame, settings.seconds, vm.playing, active, vm.panel, animate) {
        val progress = frame?.takeIf { it.revision == revision && vm.playing && active && !vm.panel }?.progress ?: return@LaunchedEffect
        val start = progress.value
        val remaining = ((1f - start) * settings.seconds * 1000).toLong().coerceAtLeast(1)
        if (animate) progress.animateTo(1f, tween(remaining.toInt(), easing = LinearEasing))
        else {
            val started = SystemClock.elapsedRealtime()
            // Records the time spent, so the zoom or progress bar resumes from the right place.
            try { delay(remaining) } finally {
                val elapsed = (SystemClock.elapsedRealtime() - started).toFloat() / remaining
                withContext(NonCancellable) { progress.snapTo(start + (1f - start) * elapsed.coerceAtMost(1f)) }
            }
        }
        vm.next()
    }
    // Watched outside composition, so a key press does not recompose the whole screen.
    LaunchedEffect(Unit) {
        snapshotFlow { Triple(vm.lastInteraction, vm.controls, vm.panel) }.collectLatest { (_, shown, panel) ->
            if (shown && !panel) { delay(5000); vm.controls = false }
        }
    }
    LaunchedEffect(vm.controls, vm.panel) {
        if (screensaver) return@LaunchedEffect
        if (!vm.controls) rootFocus.requestFocus()
    }

    MaterialTheme {
        Box(Modifier.fillMaxSize().background(Color.Black).focusRequester(rootFocus)
            .onPreviewKeyEvent { !screensaver && it.nativeKeyEvent.action == KeyEvent.ACTION_DOWN && vm.remoteKey(it.nativeKeyEvent.keyCode) }
            .focusable()) {
            PaintingSurface(frame, settings.crop, settings.zoom)
            val shown = frame?.painting
            if (settings.captions && shown != null && !vm.panel) {
                PaintingCaption(shown, controls, Modifier.align(Alignment.BottomStart))
            }
            if (frame == null) {
                Text(stringResource(if (collection != null && painting == null) R.string.filter_matches_nothing else R.string.opening),
                    color = Ivory, modifier = Modifier.align(Alignment.Center))
            }
            AnimatedVisibility(controls, enter = fadeIn(), exit = fadeOut(), modifier = Modifier.align(Alignment.BottomCenter)) {
                PlaybackControls(vm, frame, focus, controls)
            }
            if (vm.panel && !screensaver) SettingsPanel(vm, onDownload)
        }
    }
}

// Separate composition scopes let menu changes skip the painting and caption work.
@Composable
private fun PaintingSurface(frame: Frame?, crop: Boolean, zoom: Boolean) {
    AnimatedContent(frame, transitionSpec = { fadeIn(tween(DISSOLVE_MILLIS)) togetherWith fadeOut(tween(DISSOLVE_MILLIS)) },
        label = "Painting dissolve", modifier = Modifier.fillMaxSize()) { shown ->
        if (shown != null) {
            Image(shown.bitmap.asImageBitmap(), contentDescription = stringResource(R.string.painting_description, shown.painting.title, shown.painting.artist),
                contentScale = if (crop) ContentScale.Crop else ContentScale.Fit,
                modifier = Modifier.fillMaxSize().clipToBounds().graphicsLayer {
                    scaleX = if (zoom && crop) 1f + shown.progress.value * 0.045f else 1f
                    scaleY = scaleX
                })
        }
    }
}

@Composable
private fun PaintingCaption(shown: Painting, controls: Boolean, modifier: Modifier = Modifier) {
    Box(modifier.fillMaxWidth()
        .background(Brush.verticalGradient(listOf(Color.Transparent, Color.Black.copy(alpha = 0.65f))))
        .padding(start = 42.dp, end = 42.dp, top = 60.dp, bottom = if (controls) 116.dp else 34.dp)) {
        Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text(shown.title, color = Color.White, fontSize = 25.sp, fontStyle = FontStyle.Italic, fontFamily = FontFamily.Serif)
            Text(listOf(shown.artist, shown.year, shown.movement, shown.collection).filter { it.isNotBlank() }.joinToString("  ·  "),
                color = Color.White.copy(alpha = 0.86f), fontSize = 14.sp)
        }
    }
}

@Composable
private fun PlaybackControls(vm: GalleryViewModel, frame: Frame?, focus: FocusRequester, visible: Boolean) {
    // Request only after AnimatedVisibility has attached the button's focus target.
    LaunchedEffect(visible) { if (visible) focus.requestFocus() }
    Column(Modifier.fillMaxWidth().background(Brush.verticalGradient(listOf(Color.Transparent, Color.Black.copy(alpha = 0.88f))))
        .padding(horizontal = 42.dp, vertical = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (vm.message.isNotBlank()) Text(vm.message, color = Color(0xFFFFD1A4), fontSize = 13.sp)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
            GalleryButton(stringResource(R.string.previous), onClick = { vm.previous(); vm.interact() })
            GalleryButton(stringResource(if (vm.playing) R.string.pause else R.string.play), Modifier.focusRequester(focus),
                onClick = { vm.playing = !vm.playing; vm.interact() })
            GalleryButton(stringResource(R.string.next), onClick = { vm.next(); vm.interact() })
            Spacer(Modifier.weight(1f))
            Text(pluralStringResource(R.plurals.painting_count, vm.availableCount, vm.availableCount) +
                "  ·  " + durationLabel(vm.settings.seconds), color = Muted, fontSize = 13.sp)
            GalleryButton(stringResource(R.string.settings), onClick = { vm.panel = true; vm.interact() })
        }
        // Read while drawing, so the advancing bar does not recompose the controls every frame.
        val progress = frame?.progress
        Box(Modifier.fillMaxWidth().height(2.dp).background(Color.White.copy(alpha = 0.15f)).drawBehind {
            drawRect(Ivory, size = size.copy(width = size.width * (progress?.value ?: 0f)))
        })
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
    val collection = vm.collection
    val focus = remember { FocusRequester() }
    val downloadFocus = remember { FocusRequester() }
    val cancelFocus = remember { FocusRequester() }
    // Until the full collection is in, the panel opens on the download button so one OK press fetches it.
    val incomplete = collection != null && (collection.directory == null || collection.partial)
    val offerDownload = incomplete && !vm.working
    // Also moves focus when the pressed download/cancel button is swapped for the other.
    LaunchedEffect(vm.working) {
        (if (vm.working) cancelFocus else if (offerDownload) downloadFocus else focus).requestFocus()
    }
    Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.65f)), contentAlignment = Alignment.CenterEnd) {
        Column(Modifier.width(560.dp).fillMaxHeight().background(Panel).verticalScroll(rememberScrollState()).padding(32.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.settings), color = Ivory, fontSize = 27.sp, fontFamily = FontFamily.Serif, modifier = Modifier.weight(1f))
                GalleryButton(stringResource(R.string.done), Modifier.focusRequester(focus), onClick = vm::closePanel)
            }
            SettingsOptions(vm)
            Spacer(Modifier.height(4.dp))
            Box(Modifier.fillMaxWidth().height(1.dp).background(Color.White.copy(alpha = 0.12f)))
            CollectionSettings(vm, onDownload, downloadFocus, cancelFocus)
            SettingsMessage(vm)
            Text(stringResource(R.string.screensaver_hint), color = Muted, fontSize = 12.sp)
        }
    }
}

@Composable
private fun SettingsOptions(vm: GalleryViewModel) {
    val settings = vm.settings
    DurationOptions(settings.seconds) { vm.update(vm.settings.copy(seconds = it)) }
    FramingOptions(settings.crop) { vm.update(vm.settings.copy(crop = it)) }
    DisplayOptions(settings.crop, settings.zoom, settings.captions,
        onZoom = { vm.update(vm.settings.copy(zoom = !vm.settings.zoom)) },
        onCaptions = { vm.update(vm.settings.copy(captions = !vm.settings.captions)) })
    QualityOptions(settings.minimumHeight, vm.availableCount) { vm.update(vm.settings.copy(minimumHeight = it)) }
}

@Composable
private fun DurationOptions(selected: Int, onSelect: (Int) -> Unit) {
    Heading(stringResource(R.string.time_per_painting))
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        SLIDE_SECONDS.forEach { seconds ->
            GalleryButton(durationLabel(seconds), selected = seconds == selected, onClick = { onSelect(seconds) })
        }
    }
}

@Composable
private fun FramingOptions(crop: Boolean, onSelect: (Boolean) -> Unit) {
    Heading(stringResource(R.string.framing))
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        GalleryButton(stringResource(R.string.fill_screen), selected = crop, onClick = { onSelect(true) })
        GalleryButton(stringResource(R.string.whole_painting), selected = !crop, onClick = { onSelect(false) })
    }
}

@Composable
private fun DisplayOptions(crop: Boolean, zoom: Boolean, captions: Boolean, onZoom: () -> Unit, onCaptions: () -> Unit) {
    Heading(stringResource(R.string.display))
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        // Zoom only applies when the painting fills the screen.
        if (crop) GalleryButton(stringResource(R.string.slow_zoom), selected = zoom, onClick = onZoom)
        GalleryButton(stringResource(R.string.captions), selected = captions, onClick = onCaptions)
    }
}

@Composable
private fun QualityOptions(selected: Int, count: Int, onSelect: (Int) -> Unit) {
    Heading(stringResource(R.string.image_quality))
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        listOf(0 to stringResource(R.string.quality_all), 1080 to "HD+", 2160 to "4K+").forEach { (height, label) ->
            GalleryButton(label, selected = selected == height, onClick = { onSelect(height) })
        }
        Text(pluralStringResource(R.plurals.painting_count, count, count), color = Muted, fontSize = 13.sp, modifier = Modifier.padding(start = 8.dp))
    }
}

@Composable
private fun CollectionSettings(vm: GalleryViewModel, onDownload: () -> Unit, downloadFocus: FocusRequester, cancelFocus: FocusRequester) {
    val collection = vm.collection
    val incomplete = collection != null && (collection.directory == null || collection.partial)
    // Measured off the main thread, once when Settings opens and when a download starts or stops.
    val freeSpace by produceState("", vm.working) { value = withContext(Dispatchers.IO) { vm.freeSpace() } }
    val count = collection?.paintings?.size ?: 0
    Heading(stringResource(R.string.collection_heading, pluralStringResource(R.plurals.painting_count, count, count), freeSpace))
    if (vm.working) {
        if (vm.downloadMessage.isNotBlank()) Text(vm.downloadMessage, color = Ivory, fontSize = 14.sp)
        GalleryButton(stringResource(R.string.cancel), Modifier.focusRequester(cancelFocus), onClick = vm::cancelDownload)
    } else {
        if (vm.downloadMessage.isNotBlank()) Text(vm.downloadMessage, color = Ivory, fontSize = 13.sp)
        if (vm.updateAvailable && !incomplete) Text(stringResource(R.string.update_available), color = Ivory, fontSize = 13.sp)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (incomplete) GalleryButton(stringResource(if (collection?.partial == true) R.string.resume_download else R.string.download_all),
                Modifier.focusRequester(downloadFocus), onClick = onDownload)
            else if (vm.updateAvailable) GalleryButton(stringResource(R.string.download_update), onClick = onDownload)
        }
    }
}

@Composable
private fun SettingsMessage(vm: GalleryViewModel) {
    if (vm.message.isNotBlank()) Text(vm.message, color = Color(0xFFFFD1A4), fontSize = 13.sp)
}

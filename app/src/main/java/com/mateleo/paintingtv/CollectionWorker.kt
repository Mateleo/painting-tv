package com.mateleo.paintingtv

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.ServiceInfo
import android.graphics.BitmapFactory
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import android.os.SystemClock
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.net.URL
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong
import javax.net.ssl.HttpsURLConnection

private const val PARALLEL_DOWNLOADS = 8

/** Builds a complete collection beside the live one; only a successful download replaces it. */
class CollectionWorker(context: Context, parameters: WorkerParameters) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        // Without foreground status (e.g. started from the background on Android 12+) the download still runs.
        runCatching { setForeground(notification()) }
        val store = CollectionStore(applicationContext)
        val hash = MessageDigest.getInstance("SHA-256").digest("download:$COLLECTION_URL".toByteArray())
            .take(12).joinToString("") { "%02x".format(it) }
        // A retried download reuses verified files in its stage. Never mutate the active collection.
        val stage = File(store.root, "collection-$hash".let { if (store.activeName == it) "$it-next" else it })
        try {
            stage.mkdirs()
            setProgress(workDataOf("message" to "Preparing collection…"))
            downloadCollection(stage)
            val catalog = File(stage, "catalog.json")
            require(catalog.isFile && catalog.length() <= 32L * 1024 * 1024) { "Missing or oversized catalog.json" }
            val paintings = CollectionStore.parse(catalog.readText())
            store.activate(stage, paintings)
            Result.success(workDataOf("message" to "${paintings.size} paintings ready offline"))
        } catch (cancelled: kotlinx.coroutines.CancellationException) {
            throw cancelled
        } catch (e: Exception) {
            Result.failure(workDataOf("message" to (e.message ?: "Collection could not be downloaded").take(500)))
        }
    }

    private suspend fun downloadCollection(stage: File) {
        val store = CollectionStore(applicationContext)
        val manifestFile = File(stage, "manifest.json")
        download(COLLECTION_URL, manifestFile, 32L * 1024 * 1024)
        val text = manifestFile.readText()
        val json = JSONObject(text)
        val paintings = CollectionStore.parse(text)
        val entries = json.getJSONArray("paintings")
        // Relative image paths are hosted beside the manifest; keep the file type for the decoder.
        val addresses = paintings.mapIndexed { index, painting ->
            val address = URL(URL(COLLECTION_URL), painting.imageUrl)
            val extension = address.path.substringAfterLast('.', "").lowercase().takeIf { it in setOf("jpg", "jpeg", "png", "webp") } ?: "jpg"
            val path = "images/${painting.id}.$extension"
            entries.getJSONObject(index).put("imageUrl", path)
            address.toString() to CollectionStore.safeFile(stage, path)
        }
        val done = BooleanArray(paintings.size)
        val ready = AtomicInteger()
        val next = AtomicInteger()
        val publishing = Mutex()
        var published = 0
        var publishedAt = 0L
        val reportedAt = AtomicLong()
        // Lets the gallery play finished paintings while the rest download, and after a cancel.
        suspend fun publish(force: Boolean) = publishing.withLock {
            val count = ready.get()
            val now = SystemClock.elapsedRealtime()
            if (count == published || (!force && published > 0 && now - publishedAt < 20_000)) return@withLock
            val finished = JSONArray()
            synchronized(done) { for (index in done.indices) if (done[index]) finished.put(entries.getJSONObject(index)) }
            store.publishPartial(stage, JSONObject().put("version", 1).put("paintings", finished).toString())
            published = count
            publishedAt = now
            // A cancelled worker may no longer accept progress; the saved paintings are what matters.
            runCatching { setProgress(workDataOf("message" to "Downloading $count / ${paintings.size}", "partial" to count)) }
        }
        try {
            coroutineScope {
                repeat(PARALLEL_DOWNLOADS) {
                    launch {
                        while (true) {
                            val index = next.getAndIncrement()
                            if (index >= paintings.size) break
                            val (address, target) = addresses[index]
                            if (!isImage(target)) downloadWithRetry(address, target)
                            require(isImage(target)) { "Invalid image from source: ${paintings[index].title}" }
                            synchronized(done) { done[index] = true }
                            val count = ready.incrementAndGet()
                            if (count >= 3) publish(force = false)
                            val now = SystemClock.elapsedRealtime()
                            val last = reportedAt.get()
                            if (now - last > 500 && reportedAt.compareAndSet(last, now)) {
                                setProgress(workDataOf("message" to "Downloading $count / ${paintings.size}", "partial" to published))
                            }
                        }
                    }
                }
            }
        } finally {
            withContext(NonCancellable) { publish(force = true) }
        }
        File(stage, "catalog.json").writeText(json.toString())
    }

    /** Network hiccups on a long download should not stop the whole collection. */
    private suspend fun downloadWithRetry(address: String, target: File) {
        repeat(2) { attempt ->
            try { return download(address, target, 150L * 1024 * 1024) }
            catch (e: IOException) { delay(2_000L * (attempt + 1)) }
        }
        download(address, target, 150L * 1024 * 1024)
    }

    private suspend fun download(address: String, target: File, maxBytes: Long) {
        var url = URL(address)
        val partial = File(target.path + ".partial")
        repeat(6) {
            require(url.protocol == "https") { "Download URLs must use HTTPS" }
            val connection = url.openConnection() as HttpsURLConnection
            connection.connectTimeout = 20_000
            connection.readTimeout = 30_000
            connection.instanceFollowRedirects = false
            connection.setRequestProperty("User-Agent", "PaintingTV/0.1 (personal art viewer)")
            // Read each body to the end and close it, without disconnect(), so the connection is reused.
            try {
                val status = connection.responseCode
                if (status in listOf(301, 302, 303, 307, 308)) {
                    url = URL(url, connection.getHeaderField("Location") ?: error("Invalid redirect"))
                    connection.inputStream.use { it.readBytes() }
                } else {
                    if (status !in 200..299) throw IOException("Download failed (HTTP $status)")
                    require(connection.contentLengthLong <= maxBytes) { "Download is too large" }
                    connection.inputStream.use { copy(it, partial, maxBytes, "Download is too large") }
                    check(partial.renameTo(target)) { "Could not save download" }
                    return
                }
            } catch (e: Exception) {
                connection.disconnect()
                throw e
            }
        }
        error("Too many redirects")
    }

    /** Streams [input] to [target] with cancellation, size, and free-space checks; returns the bytes written. */
    private suspend fun copy(input: InputStream, target: File, maxBytes: Long, tooLarge: String): Long {
        target.parentFile?.mkdirs()
        val buffer = ByteArray(128 * 1024)
        var size = 0L
        target.outputStream().use { output ->
            while (true) {
                currentCoroutineContext().ensureActive()
                val read = input.read(buffer)
                if (read < 0) break
                size += read
                require(size <= maxBytes) { tooLarge }
                if (target.usableSpace < 32L * 1024 * 1024) throw IOException("Storage is full. Free space and retry.")
                output.write(buffer, 0, read)
            }
        }
        return size
    }

    private fun notification(): ForegroundInfo {
        val manager = applicationContext.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("collection", "Collection downloads", NotificationManager.IMPORTANCE_LOW))
        val notification = NotificationCompat.Builder(applicationContext, "collection")
            .setContentTitle("Preparing your painting collection")
            .setContentText("You can return to the gallery while this finishes.")
            .setSmallIcon(com.mateleo.paintingtv.R.drawable.ic_notification).setOngoing(true).build()
        return if (Build.VERSION.SDK_INT >= 29) ForegroundInfo(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        else ForegroundInfo(1, notification)
    }

    private fun isImage(file: File): Boolean {
        if (!file.isFile || file.length() == 0L) return false
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.path, bounds)
        return bounds.outWidth > 0 && bounds.outHeight > 0
    }
}

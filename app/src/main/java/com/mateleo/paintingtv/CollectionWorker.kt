package com.mateleo.paintingtv

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.ServiceInfo
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.net.URL
import java.security.MessageDigest
import java.util.zip.ZipInputStream
import javax.net.ssl.HttpsURLConnection

/** Builds a complete collection beside the live one; only a successful import replaces it. */
class CollectionWorker(context: Context, parameters: WorkerParameters) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        // Without foreground status (e.g. started from the background on Android 12+) the import still runs.
        runCatching { setForeground(notification()) }
        val store = CollectionStore(applicationContext)
        val source = inputData.getString("source") ?: return@withContext Result.failure()
        val mode = inputData.getString("mode") ?: "zip"
        val hash = MessageDigest.getInstance("SHA-256").digest("$mode:$source".toByteArray())
            .take(12).joinToString("") { "%02x".format(it) }
        // A retried download reuses verified files in its stage. Never mutate the active collection.
        val stage = File(store.root, "collection-$hash".let { if (store.activeName == it) "$it-next" else it })
        try {
            stage.mkdirs()
            setProgress(workDataOf("message" to "Preparing collection…"))
            when (mode) {
                "zip" -> importZip(source, stage)
                "download" -> downloadCollection(source, stage)
                else -> error("Unknown import type")
            }
            val catalog = File(stage, "catalog.json")
            require(catalog.isFile && catalog.length() <= 32L * 1024 * 1024) { "Missing or oversized catalog.json" }
            val paintings = CollectionStore.parse(catalog.readText())
            paintings.forEachIndexed { index, painting ->
                currentCoroutineContext().ensureActive()
                val image = CollectionStore.safeFile(stage, painting.imageUrl)
                require(isImage(image)) { "Missing or invalid image: ${painting.title}" }
                if (index % 25 == 0) setProgress(workDataOf("message" to "Checking ${index + 1} / ${paintings.size}"))
            }
            store.activate(stage, paintings)
            Result.success(workDataOf("message" to "${paintings.size} paintings ready offline"))
        } catch (cancelled: kotlinx.coroutines.CancellationException) {
            throw cancelled
        } catch (e: Exception) {
            Result.failure(workDataOf("message" to (e.message ?: "Collection could not be imported").take(500)))
        }
    }

    private suspend fun importZip(source: String, stage: File) {
        // Restart a cancelled ZIP import cleanly; the original collection remains untouched.
        stage.deleteRecursively()
        val input = if (source.startsWith("file:")) {
            val file = File(requireNotNull(Uri.parse(source).path))
            val inbox = File(applicationContext.getExternalFilesDir(null), "inbox").canonicalFile
            require(file.canonicalPath.startsWith(inbox.path + File.separator)) { "File must be in the import inbox" }
            file.inputStream()
        } else {
            require(source.startsWith("content:")) { "Choose a collection ZIP" }
            applicationContext.contentResolver.openInputStream(Uri.parse(source)) ?: error("Cannot open ZIP")
        }
        ZipInputStream(input.buffered()).use { zip ->
            var files = 0
            var total = 0L
            while (true) {
                val entry = zip.nextEntry ?: break
                val target = CollectionStore.safeFile(stage, entry.name)
                if (entry.isDirectory) { target.mkdirs(); continue }
                require(++files <= 40_001) { "Too many ZIP entries" }
                total += copy(zip, target, 150L * 1024 * 1024, "ZIP entry exceeds 150 MB")
                require(total <= 100L * 1024 * 1024 * 1024) { "Collection exceeds 100 GB" }
                if (files % 10 == 0) setProgress(workDataOf("message" to "Importing $files files · ${total / 1024 / 1024} MB"))
            }
        }
    }

    private suspend fun downloadCollection(source: String, stage: File) {
        val manifestFile = File(stage, "manifest.json")
        download(source, manifestFile, 32L * 1024 * 1024)
        val text = manifestFile.readText()
        val json = JSONObject(text)
        val paintings = CollectionStore.parse(text)
        val entries = json.getJSONArray("paintings")
        paintings.forEachIndexed { index, painting ->
            currentCoroutineContext().ensureActive()
            val path = "images/${painting.id}.jpg"
            val target = CollectionStore.safeFile(stage, path)
            setProgress(workDataOf("message" to "Downloading ${index + 1} / ${paintings.size} · ${painting.title}"))
            if (!isImage(target)) download(painting.imageUrl, target, 150L * 1024 * 1024)
            require(isImage(target)) { "Invalid image from source: ${painting.title}" }
            entries.getJSONObject(index).put("imageUrl", path)
        }
        File(stage, "catalog.json").writeText(json.toString())
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
            try {
                val status = connection.responseCode
                if (status in listOf(301, 302, 303, 307, 308)) {
                    url = URL(url, connection.getHeaderField("Location") ?: error("Invalid redirect"))
                } else {
                    require(status in 200..299) { "Download failed (HTTP $status)" }
                    require(connection.contentLengthLong <= maxBytes) { "Download is too large" }
                    connection.inputStream.use { copy(it, partial, maxBytes, "Download is too large") }
                    check(partial.renameTo(target)) { "Could not save download" }
                    return
                }
            } finally { connection.disconnect() }
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
            .setSmallIcon(com.mateleo.paintingtv.R.drawable.app_icon).setOngoing(true).build()
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

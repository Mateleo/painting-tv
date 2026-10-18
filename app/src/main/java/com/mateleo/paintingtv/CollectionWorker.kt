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
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.URL
import java.nio.file.Files
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

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
            setProgress(workDataOf("message" to applicationContext.getString(R.string.download_preparing)))
            downloadCollection(stage)
            val catalog = File(stage, "catalog.json")
            require(catalog.isFile && catalog.length() <= 32L * 1024 * 1024) { "Missing or oversized catalog.json" }
            val paintings = CollectionStore.parse(catalog.readText())
            store.activate(stage, paintings)
            recordPublishedCatalog(applicationContext, sha256(File(stage, CollectionStore.MANIFEST)))
            Result.success(workDataOf("message" to applicationContext.resources
                .getQuantityString(R.plurals.download_finished, paintings.size, paintings.size)))
        } catch (cancelled: kotlinx.coroutines.CancellationException) {
            throw cancelled
        } catch (e: Exception) {
            Result.failure(workDataOf("message" to (e.message ?: "Collection could not be downloaded").take(500)))
        }
    }

    private suspend fun downloadCollection(stage: File) {
        val store = CollectionStore(applicationContext)
        val manifestFile = File(stage, CollectionStore.MANIFEST)
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
        // Images unchanged since the installed collection are copied from it instead of downloaded again. Collections
        // installed before catalogs had checksums are matched by painting ID; the copy is checked against the checksum.
        val installed = store.activeDirectory?.takeIf { it.canonicalFile != stage.canonicalFile }?.let { directory ->
            runCatching { CollectionStore.parse(File(directory, "catalog.json").readText()) }.getOrNull()
                ?.map { it to CollectionStore.safeFile(directory, it.imageUrl) }
        }.orEmpty()
        val installedByHash = installed.filter { it.first.sha256.isNotEmpty() }.associate { it.first.sha256 to it.second }
        val installedById = installed.associate { it.first.id to it.second }
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
            store.publishPartial(stage, JSONObject().put("version", CollectionStore.CATALOG_VERSION).put("paintings", finished).toString())
            published = count
            publishedAt = now
            // A cancelled worker may no longer accept progress; the saved paintings are what matters.
            runCatching { setProgress(workDataOf("message" to progressMessage(count, paintings.size), "partial" to count)) }
        }
        try {
            coroutineScope {
                repeat(PARALLEL_DOWNLOADS) {
                    launch {
                        while (true) {
                            val index = next.getAndIncrement()
                            if (index >= paintings.size) break
                            val (address, target) = addresses[index]
                            val expected = paintings[index].sha256
                            val local = if (expected.isEmpty()) null else installedByHash[expected] ?: installedById[paintings[index].id]
                            if (!verified(target, expected) && local?.let { reuse(it, target, expected) } != true) {
                                downloadWithRetry(address, target, expected)
                            }
                            require(isImage(target)) { "Invalid image from source: ${paintings[index].title}" }
                            synchronized(done) { done[index] = true }
                            val count = ready.incrementAndGet()
                            if (count >= 3) publish(force = false)
                            val now = SystemClock.elapsedRealtime()
                            val last = reportedAt.get()
                            if (now - last > 500 && reportedAt.compareAndSet(last, now)) {
                                setProgress(workDataOf("message" to progressMessage(count, paintings.size), "partial" to published))
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

    private fun progressMessage(count: Int, total: Int) = applicationContext.getString(R.string.download_progress, count, total)

    /** Network hiccups on a long download should not stop the whole collection. */
    private suspend fun downloadWithRetry(address: String, target: File, expected: String) {
        repeat(2) { attempt ->
            try { return download(address, target, 150L * 1024 * 1024, expected) }
            catch (e: IOException) { delay(2_000L * (attempt + 1)) }
        }
        download(address, target, 150L * 1024 * 1024, expected)
    }

    /** A file left by an interrupted download must still match the catalog, which may have changed since. */
    private fun verified(file: File, expected: String): Boolean {
        if (!file.isFile || file.length() == 0L) return false
        if (if (expected.isEmpty()) isImage(file) else sha256(file) == expected) return true
        file.delete()
        return false
    }

    /** Takes an unchanged image from the installed collection: a hard link costs no space, else a copy. */
    private suspend fun reuse(source: File, target: File, expected: String): Boolean {
        if (!source.isFile) return false
        val partial = File(target.path + ".partial").apply { delete() }
        val actual = runCatching { Files.createLink(partial.toPath(), source.toPath()); sha256(partial) }
            // The partial file may already be a link to the installed image: never write through it.
            .getOrElse { partial.delete(); source.inputStream().use { copy(it, partial) } }
        if (actual != expected) { partial.delete(); return false }
        return partial.renameTo(target)
    }

    private fun notification(): ForegroundInfo {
        val manager = applicationContext.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("collection",
            applicationContext.getString(R.string.notification_channel), NotificationManager.IMPORTANCE_LOW))
        val notification = NotificationCompat.Builder(applicationContext, "collection")
            .setContentTitle(applicationContext.getString(R.string.notification_title))
            .setContentText(applicationContext.getString(R.string.notification_text))
            .setSmallIcon(R.drawable.ic_notification).setOngoing(true).build()
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

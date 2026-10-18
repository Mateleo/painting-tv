package com.mateleo.paintingtv

import android.content.Context
import android.app.ActivityManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ImageDecoder
import android.graphics.Rect
import android.graphics.ColorSpace
import android.os.Build
import org.json.JSONObject
import java.io.File
import java.io.InputStream

data class Painting(
    val id: String, val title: String, val artist: String,
    val year: String, val movement: String, val collection: String, val imageUrl: String,
    val width: Int, val height: Int, val sourceUrl: String, val license: String,
)

/** [partial] marks a download still in progress (or paused): only its finished paintings are listed. */
data class ArtCollection(val paintings: List<Painting>, val directory: File? = null, val partial: Boolean = false)

class CollectionStore(private val context: Context) {
    private val preferences = context.getSharedPreferences("gallery", Context.MODE_PRIVATE)
    val root: File get() = File(context.getExternalFilesDir(null) ?: context.filesDir, "collections").apply { mkdirs() }

    val activeName: String? get() = preferences.getString("active", null)

    fun load(): ArtCollection {
        val active = activeName?.let { File(root, it) }
        return if (active != null && File(active, "catalog.json").isFile) {
            ArtCollection(parse(File(active, "catalog.json").readText()), active)
        } else loadPartial() ?: ArtCollection(parse(context.assets.open("catalog.json").bufferedReader().use { it.readText() }))
    }

    private fun loadPartial(): ArtCollection? {
        val directory = preferences.getString("partial", null)?.let { File(root, it) } ?: return null
        val catalog = File(directory, PARTIAL_CATALOG)
        if (!catalog.isFile) return null
        return runCatching { ArtCollection(parse(catalog.readText()), directory, partial = true) }.getOrNull()
    }

    /** Records the paintings of an unfinished download so the gallery can already show them. */
    fun publishPartial(directory: File, catalog: String) {
        require(directory.parentFile?.canonicalFile == root.canonicalFile)
        val temporary = File(directory, "$PARTIAL_CATALOG.tmp")
        temporary.writeText(catalog)
        check(temporary.renameTo(File(directory, PARTIAL_CATALOG))) { "Could not save download progress" }
        preferences.edit().putString("partial", directory.name).apply()
    }

    /** Switches to [directory], then removes every other collection, including abandoned partial downloads. */
    fun activate(directory: File, paintings: List<Painting>) {
        require(directory.parentFile?.canonicalFile == root.canonicalFile)
        require(paintings.isNotEmpty())
        paintings.forEach { require(safeFile(directory, it.imageUrl).isFile) { "Missing image: ${it.title}" } }
        check(preferences.edit().putString("active", directory.name).remove("partial").commit()) { "Could not save collection" }
        File(directory, PARTIAL_CATALOG).delete()
        removeSiblings(directory)
    }

    // Leave room for Compose and the outgoing frame on televisions with small heaps.
    private val maxPixels by lazy {
        minOf(8_300_000L, context.getSystemService(ActivityManager::class.java).memoryClass.toLong() * 1024 * 1024 / 32)
    }

    @Synchronized
    fun decode(collection: ArtCollection, painting: Painting, screenWidth: Int, screenHeight: Int, crop: Boolean): Bitmap {
        val file = collection.directory?.let { safeFile(it, painting.imageUrl) }
        val targetWidth = screenWidth.coerceIn(1280, 3840)
        val targetHeight = screenHeight.coerceIn(720, 2160)
        if (Build.VERSION.SDK_INT >= 28) {
            val source = file?.let { ImageDecoder.createSource(it) } ?: ImageDecoder.createSource(context.assets, painting.imageUrl)
            return ImageDecoder.decodeBitmap(source) { decoder, info, _ ->
                val plan = decodePlan(info.size.width, info.size.height, targetWidth, targetHeight, maxPixels, crop)
                decoder.setTargetSize(plan.width, plan.height)
                if (crop) decoder.crop = Rect(plan.left, plan.top, plan.right, plan.bottom)
                decoder.setTargetColorSpace(ColorSpace.get(ColorSpace.Named.SRGB))
                decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
            }
        }
        fun open(): InputStream = file?.inputStream() ?: context.assets.open(painting.imageUrl)
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        open().use { BitmapFactory.decodeStream(it, null, bounds) }
        require(bounds.outWidth > 0 && bounds.outHeight > 0) { "Unreadable image: ${painting.title}" }
        var sample = 1
        while ((bounds.outWidth / sample).toLong() * (bounds.outHeight / sample) > maxPixels ||
            (bounds.outWidth / (sample * 2) >= targetWidth && bounds.outHeight / (sample * 2) >= targetHeight)) sample *= 2
        return open().use {
            BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply {
                inSampleSize = sample
                inPreferredConfig = Bitmap.Config.ARGB_8888
            }) ?: error("Cannot decode ${painting.title}")
        }
    }

    companion object {
        private const val PARTIAL_CATALOG = "partial.json"
        const val CATALOG_VERSION = 2

        fun removeSiblings(directory: File) {
            directory.parentFile?.listFiles()?.filter { it.name != directory.name }?.forEach { it.deleteRecursively() }
        }

        fun safeFile(root: File, path: String): File {
            require(path.isNotBlank() && !path.startsWith("/") && !path.contains(":")) { "Expected relative image path" }
            val file = File(root, path).canonicalFile
            require(file.path.startsWith(root.canonicalPath + File.separator)) { "Unsafe image path" }
            return file
        }

        fun parse(text: String): List<Painting> {
            val json = JSONObject(text)
            require(json.getInt("version") == CATALOG_VERSION) { "Unsupported catalog version" }
            val items = json.getJSONArray("paintings")
            require(items.length() in 1..20_000) { "Collection must contain 1–20,000 paintings" }
            val ids = hashSetOf<String>()
            return List(items.length()) { i ->
                val item = items.getJSONObject(i)
                val id = item.getString("id")
                require(id.matches(Regex("[A-Za-z0-9_-]{1,120}")) && ids.add(id)) { "Invalid or duplicate painting ID" }
                Painting(id, item.optString("title", "Untitled"), item.optString("artist"),
                    item.optString("year"), item.optString("movement"), item.optString("collection"), item.getString("imageUrl"),
                    item.optInt("width"), item.optInt("height"), item.optString("sourceUrl"), item.optString("license"))
            }
        }
    }
}

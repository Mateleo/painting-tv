package com.mateleo.paintingtv

import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.net.URL
import java.security.MessageDigest
import javax.net.ssl.HttpsURLConnection

private val USER_AGENT = "PaintingTV/${BuildConfig.VERSION_NAME} (personal art viewer)"

fun sha256(file: File): String = file.inputStream().use { input ->
    val digest = MessageDigest.getInstance("SHA-256")
    val buffer = ByteArray(128 * 1024)
    while (true) {
        val read = input.read(buffer)
        if (read < 0) break
        digest.update(buffer, 0, read)
    }
    digest.hex()
}

private fun MessageDigest.hex() = digest().joinToString("") { "%02x".format(it) }

/**
 * Downloads [address] to [target] over HTTPS only, following redirects by hand so none can leave HTTPS.
 * With [sha256], the bytes must match it; the file only appears at [target] once complete and verified.
 */
suspend fun download(address: String, target: File, maxBytes: Long, sha256: String = "") {
    var url = URL(address)
    val partial = File(target.path + ".partial")
    repeat(6) {
        require(url.protocol == "https") { "Download URLs must use HTTPS" }
        val connection = url.openConnection() as HttpsURLConnection
        connection.connectTimeout = 20_000
        connection.readTimeout = 30_000
        connection.instanceFollowRedirects = false
        connection.setRequestProperty("User-Agent", USER_AGENT)
        // Read each body to the end and close it, without disconnect(), so the connection is reused.
        try {
            val status = connection.responseCode
            if (status in listOf(301, 302, 303, 307, 308)) {
                url = URL(url, connection.getHeaderField("Location") ?: error("Invalid redirect"))
                connection.inputStream.use { it.readBytes() }
            } else {
                if (status !in 200..299) throw IOException("Download failed (HTTP $status)")
                require(connection.contentLengthLong <= maxBytes) { "Download is too large" }
                val actual = connection.inputStream.use { copy(it, partial, maxBytes) }
                if (sha256.isNotEmpty() && actual != sha256) {
                    partial.delete()
                    // An IOException, so a corrupted transfer is retried like any other network error.
                    throw IOException("Download does not match its checksum")
                }
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

/** Streams [input] to [target] with cancellation, size, and free-space checks; returns the SHA-256 written. */
suspend fun copy(input: InputStream, target: File, maxBytes: Long = Long.MAX_VALUE): String {
    target.parentFile?.mkdirs()
    val digest = MessageDigest.getInstance("SHA-256")
    val buffer = ByteArray(128 * 1024)
    var size = 0L
    target.outputStream().use { output ->
        while (true) {
            currentCoroutineContext().ensureActive()
            val read = input.read(buffer)
            if (read < 0) break
            size += read
            require(size <= maxBytes) { "Download is too large" }
            if (target.usableSpace < 32L * 1024 * 1024) throw IOException("Storage is full. Free space and retry.")
            output.write(buffer, 0, read)
            digest.update(buffer, 0, read)
        }
    }
    return digest.hex()
}

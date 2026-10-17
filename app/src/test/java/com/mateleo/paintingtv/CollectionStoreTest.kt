package com.mateleo.paintingtv

import java.io.File
import org.junit.Assert.*
import org.junit.Test

class CollectionStoreTest {
    private fun catalog(id: String = "abc") = """{"version":1,"paintings":[{"id":"$id","title":"La Joconde","artist":"Léonard de Vinci","year":"1519","movement":"","imageUrl":"images/a.jpg"}]}"""

    @Test fun acceptsUnicodeMetadataAndOptionalFields() {
        val painting = CollectionStore.parse(catalog()).single()
        assertEquals("La Joconde", painting.title)
        assertEquals("Léonard de Vinci", painting.artist)
        assertEquals(0, painting.width)
    }
    @Test(expected = IllegalArgumentException::class) fun rejectsDuplicateIds() {
        val item = """{"id":"abc","imageUrl":"images/a.jpg"}"""
        CollectionStore.parse("""{"version":1,"paintings":[$item,$item]}""")
    }
    @Test(expected = IllegalArgumentException::class) fun rejectsUnsafeIds() { CollectionStore.parse(catalog("../escape")) }
    @Test(expected = IllegalArgumentException::class) fun rejectsTraversal() { CollectionStore.safeFile(File("/tmp/gallery"), "../gallery-evil/image.jpg") }
    @Test(expected = IllegalArgumentException::class) fun rejectsAbsolutePaths() { CollectionStore.safeFile(File("/tmp/gallery"), "/etc/passwd") }
    @Test(expected = IllegalArgumentException::class) fun rejectsNetworkPathsInOfflineCollection() { CollectionStore.safeFile(File("/tmp/gallery"), "https://example.org/image.jpg") }
    @Test fun acceptsNestedRelativePaths() {
        assertEquals(File("/tmp/gallery/images/image.jpg"), CollectionStore.safeFile(File("/tmp/gallery"), "images/image.jpg"))
    }
}

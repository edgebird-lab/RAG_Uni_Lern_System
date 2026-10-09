// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

package de.edgebird.lernsystem.source

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

class SourceStoreTest {
    @TempDir lateinit var tmp: File

    private fun src(text: String) = File(tmp, "in-${text.hashCode()}").also { it.writeText(text) }

    @Test fun savesFindsAndReplacesOriginal() {
        val store = SourceStore(tmp)
        val f = store.save(7, src("alt"), "PDF")
        assertEquals("7.pdf", f.name); assertEquals("alt", f.readText())
        assertEquals(f, store.find(7))
        store.save(7, src("neu"), "md")          // ersetzt, auch mit anderer Endung
        assertEquals(listOf("7.md"), store.dir.list()!!.toList())
        assertEquals("neu", store.find(7)!!.readText())
    }

    @Test fun doesNotConfuseIdsWithSamePrefix() {
        val store = SourceStore(tmp)
        store.save(1, src("a"), "txt"); store.save(12, src("b"), "txt")
        assertEquals("a", store.find(1)!!.readText())
        store.delete(1)
        assertNull(store.find(1)); assertEquals("b", store.find(12)!!.readText())
    }

    @Test fun pruneRemovesOrphans() {
        val store = SourceStore(tmp)
        store.save(1, src("a"), "pdf"); store.save(2, src("b"), "pdf"); File(store.dir, "fremd.tmp").writeText("x")
        store.prune(listOf(2))
        assertFalse(File(store.dir, "1.pdf").exists()); assertTrue(File(store.dir, "2.pdf").exists()); assertFalse(File(store.dir, "fremd.tmp").exists())
    }

    @Test fun mimeTypes() {
        assertEquals("application/pdf", SourceStore.mimeFor("PDF")); assertEquals("image/jpeg", SourceStore.mimeFor("jpeg")); assertEquals("text/markdown", SourceStore.mimeFor("md"))
        assertEquals("application/octet-stream", SourceStore.mimeFor("xyz"))
    }

    @Test fun unsafeExtensionIsCleaned() {
        val store = SourceStore(tmp)
        val f = store.save(7, src("x"), "../../etc")
        assertEquals(store.dir, f.parentFile); assertEquals("7.etc", f.name)
    }
}

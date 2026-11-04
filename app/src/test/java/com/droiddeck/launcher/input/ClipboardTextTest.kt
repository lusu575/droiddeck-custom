package com.droiddeck.launcher.input

import org.junit.Assert.*
import org.junit.Test

class ClipboardTextTest {
    @Test fun mixedChineseAndEmojiRoundTripWithoutTruncation() {
        val text = "中文😀\nEnglish\t".repeat(10000)
        assertEquals(text, ClipboardText.encode(text)!!.toString(Charsets.UTF_8))
    }

    @Test fun exactByteLimitIsAcceptedAndOverflowIsRejectedWhole() {
        val text = "中".repeat(ClipboardText.MAX_BYTES / 3) + "\n"
        assertEquals(ClipboardText.MAX_BYTES, ClipboardText.encode(text)!!.size)
        assertNull(ClipboardText.encode(text + "x"))
    }

    @Test fun emptyClipboardCanClearPreviousGuestText() {
        assertEquals(0, ClipboardText.encode(null)!!.size)
        assertEquals(0, ClipboardText.encode("")!!.size)
    }

    @Test fun androidBinderOrPermissionRejectionsDoNotCrashTheSession() {
        assertFalse(ClipboardText.writeSafely("text") { throw RuntimeException("Binder rejection") })
        assertFalse(ClipboardText.writeSafely("text") { throw SecurityException("not focused") })
        var actual: String? = null
        assertTrue(ClipboardText.writeSafely("中文😀") { actual = it })
        assertEquals("中文😀", actual)
    }
}

package com.droiddeck.launcher.input

import android.app.Activity
import android.content.Context
import android.os.Looper
import android.view.KeyEvent
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.FrameLayout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(manifest = Config.NONE)
class KeyboardHostTest {
    private lateinit var imm: InputMethodManager
    private lateinit var host: KeyboardHost

    @Before fun setUp() {
        val activity = Robolectric.buildActivity(Activity::class.java).setup().get()
        imm = activity.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        host = KeyboardHost(activity)
        activity.setContentView(FrameLayout(activity).apply { addView(host) })
        idle()
    }

    @Config(sdk = [33])
    @Test fun toggleShowsAKeyboardTheSystemDismissed() {
        host.show()
        idle()
        imm.hideSoftInputFromWindow(host.windowToken, 0)
        idle()
        host.toggle()
        idle()
        assertTrue(shadowOf(imm).isSoftInputVisible)
        assertTrue(host.shown)
    }

    @Config(sdk = [28])
    @Test fun toggleHidesAKeyboardThatIsShowing() {
        host.show()
        idle()
        host.toggle()
        idle()
        assertFalse(shadowOf(imm).isSoftInputVisible)
        assertFalse(host.shown)
    }

    private fun capturingHost(events: MutableList<KeyEvent>): KeyboardHost {
        val activity = Robolectric.buildActivity(Activity::class.java).setup().get()
        return KeyboardHost(activity) { events.add(it); true }.also {
            activity.setContentView(FrameLayout(activity).apply { addView(it) })
            it.show()
        }
    }

    @Test fun fallbackPreservesSupplementaryCodePoints() {
        val events = mutableListOf<KeyEvent>()
        val inputHost = capturingHost(events)
        val input = inputHost.onCreateInputConnection(EditorInfo())!!
        assertTrue(input.commitText("😊𠮷", 1))
        idle()
        assertEquals(listOf(0x1f60a, 0x20bb7), events.filter {
            it.action == KeyEvent.ACTION_DOWN
        }.map { it.unicodeChar })
    }

    @Test fun longFallbackYieldsAndPreservesEveryCharacter() {
        val events = mutableListOf<KeyEvent>()
        val input = capturingHost(events).onCreateInputConnection(EditorInfo())!!
        val text = "😊".repeat(1000)
        input.commitText(text, 1)
        assertTrue(events.size <= 128)
        idle()
        assertEquals(1000, events.count { it.action == KeyEvent.ACTION_DOWN && it.unicodeChar == 0x1f60a })
    }

    @Test fun deletingCompositionDoesNotDeleteCommittedGuestText() {
        val events = mutableListOf<KeyEvent>()
        val input = capturingHost(events).onCreateInputConnection(EditorInfo())!!
        input.setComposingText("😊𠮷", 1)
        input.deleteSurroundingTextInCodePoints(1, 0)
        assertTrue(events.isEmpty())
        input.finishComposingText()
        idle()
        assertEquals(listOf(0x1f60a), events.filter { it.action == KeyEvent.ACTION_DOWN }.map { it.unicodeChar })
    }

    @Test fun cancellingCompositionAndClosingConnectionNeverCommitIt() {
        val events = mutableListOf<KeyEvent>()
        val input = capturingHost(events).onCreateInputConnection(EditorInfo())!!
        input.setComposingText("待取消", 1)
        input.commitText("", 1)
        input.finishComposingText()
        input.setComposingText("关闭", 1)
        input.closeConnection()
        input.finishComposingText()
        idle()
        assertTrue(events.isEmpty())
    }

    @Test fun hidingCancelsQueuedFallbackAndLateImeCallbacks() {
        val events = mutableListOf<KeyEvent>()
        val inputHost = capturingHost(events)
        val input = inputHost.onCreateInputConnection(EditorInfo())!!
        input.commitText("😊".repeat(1000), 1)
        inputHost.hide()
        val count = events.size
        input.commitText("late", 1)
        idle()
        assertEquals(count, events.size)
    }

    @Test fun oversizedCommitIsRejectedBeforeGeneratingKeys() {
        val events = mutableListOf<KeyEvent>()
        val input = capturingHost(events).onCreateInputConnection(EditorInfo())!!
        assertFalse(input.commitText("😊".repeat(262145), 1))
        idle()
        assertTrue(events.isEmpty())
    }

    @Test fun compositionNeverFallsBackAfterItsBridgeDisappears() {
        val events = mutableListOf<KeyEvent>()
        val inputHost = capturingHost(events)
        val directory = java.io.File(inputHost.context.filesDir, "session/agent").apply { mkdirs() }
        val state = java.io.File(directory, "ime.json")
        try {
            state.writeText("""{"textField":true,"focusToken":"old"}""")
            val input = inputHost.onCreateInputConnection(EditorInfo())!!
            input.setComposingText("旧字段", 1)
            state.delete()
            input.commitText("旧字段", 1)
            idle()
            assertTrue(events.isEmpty())
        } finally { state.delete() }
    }

    @Test fun changingFocusDiscardsOldComposition() {
        val events = mutableListOf<KeyEvent>()
        val inputHost = capturingHost(events)
        val directory = java.io.File(inputHost.context.filesDir, "session/agent").apply { mkdirs() }
        val state = java.io.File(directory, "ime.json")
        try {
            state.writeText("""{"textField":true,"focusToken":"old"}""")
            val input = inputHost.onCreateInputConnection(EditorInfo())!!
            input.setComposingText("旧字段", 1)
            state.writeText("""{"textField":true,"focusToken":"new"}""")
            input.finishComposingText()
            idle()
            assertTrue(events.isEmpty())
        } finally { state.delete() }
    }

    @Test fun controlKeysNeverOvertakeQueuedFallbackText() {
        val events = mutableListOf<KeyEvent>()
        val input = capturingHost(events).onCreateInputConnection(EditorInfo())!!
        input.commitText("😊".repeat(1000), 1)
        input.performEditorAction(EditorInfo.IME_ACTION_DONE)
        input.deleteSurroundingText(1, 1)
        input.sendKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_TAB))
        input.sendKeyEvent(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_TAB))
        input.commitText("𠮷", 1)
        assertEquals(64, events.count { it.action == KeyEvent.ACTION_DOWN })
        assertTrue(events.all { it.unicodeChar == 0x1f60a })
        idle()
        val down = events.filter { it.action == KeyEvent.ACTION_DOWN }
        assertEquals(1005, down.size)
        assertTrue(down.take(1000).all { it.unicodeChar == 0x1f60a })
        assertEquals(listOf(KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_DEL,
            KeyEvent.KEYCODE_FORWARD_DEL, KeyEvent.KEYCODE_TAB), down.drop(1000).take(4).map { it.keyCode })
        assertEquals(0x20bb7, down.last().unicodeChar)
    }

    @Test fun closingConnectionCancelsQueuedControlKeysToo() {
        val events = mutableListOf<KeyEvent>()
        val input = capturingHost(events).onCreateInputConnection(EditorInfo())!!
        input.commitText("😊".repeat(1000), 1)
        input.performEditorAction(EditorInfo.IME_ACTION_DONE)
        input.deleteSurroundingText(1, 0)
        input.closeConnection()
        val count = events.size
        idle()
        assertEquals(count, events.size)
        assertTrue(events.none { it.keyCode == KeyEvent.KEYCODE_ENTER || it.keyCode == KeyEvent.KEYCODE_DEL })
    }

    @Test fun bridgeBoundCommitWaitsBehindFallbackAndNeverDowngrades() {
        val events = mutableListOf<KeyEvent>()
        val inputHost = capturingHost(events)
        val directory = java.io.File(inputHost.context.filesDir, "session/agent").apply { mkdirs() }
        val state = java.io.File(directory, "ime.json")
        try {
            val input = inputHost.onCreateInputConnection(EditorInfo())!!
            input.commitText("😊".repeat(1000), 1)
            state.writeText("""{"textField":true,"focusToken":"restored"}""")
            assertTrue(input.commitText("桥接恢复", 1))
            input.performEditorAction(EditorInfo.IME_ACTION_DONE)
            assertEquals(64, events.count { it.action == KeyEvent.ACTION_DOWN })
            idle()
            val down = events.filter { it.action == KeyEvent.ACTION_DOWN }
            assertEquals(1000, down.size)
            assertTrue(down.all { it.unicodeChar == 0x1f60a })
            inputHost.hide()
            val count = events.size
            shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofSeconds(1))
            assertEquals(count, events.size)
        } finally { state.delete() }
    }

    @Test fun changedFocusCancelsBridgeRetryAndQueuedEnterTogether() {
        val events = mutableListOf<KeyEvent>()
        val inputHost = capturingHost(events)
        val directory = java.io.File(inputHost.context.filesDir, "session/agent").apply { mkdirs() }
        val state = java.io.File(directory, "ime.json")
        try {
            val input = inputHost.onCreateInputConnection(EditorInfo())!!
            input.commitText("😊".repeat(1000), 1)
            state.writeText("""{"textField":true,"focusToken":"old"}""")
            input.commitText("旧字段", 1)
            input.performEditorAction(EditorInfo.IME_ACTION_DONE)
            idle()
            assertEquals(1000, events.count { it.action == KeyEvent.ACTION_DOWN })
            state.writeText("""{"textField":true,"focusToken":"new"}""")
            shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofSeconds(1))
            assertEquals(1000, events.count { it.action == KeyEvent.ACTION_DOWN })
            assertTrue(events.none { it.keyCode == KeyEvent.KEYCODE_ENTER })
            inputHost.hide()
        } finally { state.delete() }
    }

    @Test fun fallbackPreservesMixedUnicodeEvenWhenKeyMapCannotRepresentIt() {
        val events = mutableListOf<KeyEvent>()
        val input = capturingHost(events).onCreateInputConnection(EditorInfo())!!
        val text = "A中é😊𠮷"
        assertTrue(input.commitText(text, 1))
        idle()
        val characters = events.filter { it.action == KeyEvent.ACTION_DOWN && it.unicodeChar != 0 }
            .map { it.unicodeChar }
        assertEquals(listOf(0x41, 0x4e2d, 0xe9, 0x1f60a, 0x20bb7), characters)
        assertTrue(characters.none { it in 0xd800..0xdfff })
        assertEquals(characters, events.filter { it.action == KeyEvent.ACTION_UP && it.unicodeChar != 0 }
            .map { it.unicodeChar })
    }

    private fun idle() = shadowOf(Looper.getMainLooper()).idle()
}

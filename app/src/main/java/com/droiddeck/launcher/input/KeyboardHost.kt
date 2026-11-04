package com.droiddeck.launcher.input

import android.app.Activity
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.Build
import android.text.InputType
import android.view.KeyCharacterMap
import android.view.KeyEvent
import android.view.View
import android.view.WindowInsets
import android.view.inputmethod.BaseInputConnection
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import android.view.inputmethod.InputMethodManager

class KeyboardHost(
    context: Context,
    private val sendKeyEvent: (KeyEvent) -> Boolean,
) : View(context) {
    constructor(activity: Activity) : this(activity, { activity.dispatchKeyEvent(it) })

    private val imm = context.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
    private val desktopIme = DesktopImeBridge(context)
    var imeDirectory: String
        get() = desktopIme.directory
        set(value) {
            if (desktopIme.directory == value) return
            connection?.cancel()
            connection = null
            desktopIme.directory = value
            if (shown) imm.restartInput(this)
        }
    private var connection: KeyConnection? = null
    private val fallbackHandler = Handler(Looper.getMainLooper())
    private val map: KeyCharacterMap = KeyCharacterMap.load(KeyCharacterMap.VIRTUAL_KEYBOARD)
    var shown = false
        private set
    var imeShowing = false
        private set
    var onImeChanged: ((Boolean) -> Unit)? = null

    init {
        isFocusable = false
        isFocusableInTouchMode = false
        visibility = VISIBLE
        layoutParams = android.widget.FrameLayout.LayoutParams(1, 1)
    }

    override fun onCheckIsTextEditor(): Boolean = shown

    override fun onCreateInputConnection(outAttrs: EditorInfo): InputConnection? {
        if (!shown) return null
        outAttrs.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
        outAttrs.imeOptions = EditorInfo.IME_ACTION_NONE or EditorInfo.IME_FLAG_NO_FULLSCREEN or
            EditorInfo.IME_FLAG_NO_EXTRACT_UI or EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING
        connection?.cancel()
        return KeyConnection().also { connection = it }
    }

    override fun onApplyWindowInsets(insets: WindowInsets): WindowInsets {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val visible = insets.isVisible(WindowInsets.Type.ime())
            if (visible != imeShowing) {
                imeShowing = visible
                onImeChanged?.invoke(visible)
            }
        }
        return super.onApplyWindowInsets(insets)
    }

    override fun onKeyPreIme(keyCode: Int, event: KeyEvent): Boolean {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R || keyCode != KeyEvent.KEYCODE_BACK || !shown) {
            return super.onKeyPreIme(keyCode, event)
        }
        if (event.action == KeyEvent.ACTION_UP && !event.isCanceled) {
            hide()
            onImeChanged?.invoke(false)
        }
        return true
    }

    fun toggle() = if (shown && imeVisible()) hide() else show()

    private fun imeVisible() = Build.VERSION.SDK_INT < Build.VERSION_CODES.R ||
        rootWindowInsets?.isVisible(WindowInsets.Type.ime()) != false

    fun show() {
        shown = true
        isFocusable = true
        isFocusableInTouchMode = true
        requestFocus()
        imm.restartInput(this)
        imm.showSoftInput(this, InputMethodManager.SHOW_IMPLICIT)
    }

    fun hide() {
        connection?.cancel()
        connection = null
        shown = false
        imm.hideSoftInputFromWindow(windowToken, 0)
        isFocusable = false
        isFocusableInTouchMode = false
        clearFocus()
    }

    private inner class KeyConnection : BaseInputConnection(this, false) {
        private var active = true
        private val fallback = java.util.ArrayDeque<PendingInput>()
        private var queuedFocusToken: String? = null
        private val drain = Runnable { drainFallback() }
        private var composing: String? = null
        private var composingToken: String? = null
        override fun commitText(text: CharSequence?, newCursorPosition: Int): Boolean {
            if (!active) return true
            val value = text?.toString().orEmpty()
            if (value.toByteArray(Charsets.UTF_8).size > 1024 * 1024 || '\u0000' in value) return false
            val token = composingToken ?: desktopIme.focusToken()
            composing = null
            composingToken = null
            if (text.isNullOrEmpty()) { desktopIme.send("preedit", "", token); return true }
            if (token != null) {
                if (fallback.isNotEmpty()) {
                    fallback.addLast(PendingInput.Commit(value, token))
                    return true
                }
                if (desktopIme.send("commit", value, token)) return true
                composing = value
                composingToken = token
                return false
            }
            fallback.addLast(PendingInput.Text(value))
            if (fallback.size == 1) drainFallback()
            return true
        }

        override fun setComposingText(text: CharSequence?, newCursorPosition: Int): Boolean {
            if (!active) return true
            val value = text?.toString().orEmpty()
            if (value.toByteArray(Charsets.UTF_8).size > 1024 * 1024 || '\u0000' in value) return false
            if (composing == null) composingToken = desktopIme.focusToken()
            composing = value
            desktopIme.send("preedit", composing.orEmpty(), composingToken)
            return true
        }
        override fun finishComposingText(): Boolean {
            if (!active) return true
            val pending = composing
            if (!pending.isNullOrEmpty()) return commitText(pending, 1)
            desktopIme.send("preedit", "", composingToken)
            composing = null
            composingToken = null
            return true
        }

        override fun deleteSurroundingText(beforeLength: Int, afterLength: Int): Boolean =
            delete(beforeLength, afterLength, false)

        override fun deleteSurroundingTextInCodePoints(beforeLength: Int, afterLength: Int): Boolean =
            delete(beforeLength, afterLength, true)

        private fun delete(beforeLength: Int, afterLength: Int, codePoints: Boolean): Boolean {
            if (!active) return true
            if (beforeLength < 0 || afterLength < 0) return false
            val value = composing
            if (value != null) {
                var end = if (codePoints) value.offsetByCodePoints(value.length,
                    -minOf(beforeLength, value.codePointCount(0, value.length)))
                else (value.length - beforeLength).coerceAtLeast(0)
                if (end > 0 && end < value.length && Character.isHighSurrogate(value[end - 1])) end--
                composing = value.substring(0, end)
                desktopIme.send("preedit", composing.orEmpty(), composingToken)
                return true
            }
            // Editors do not expose surrounding text through this key-only connection.
            if (beforeLength > 1024 || afterLength > 1024) return false
            repeat(beforeLength) { tap(KeyEvent.KEYCODE_DEL) }
            repeat(afterLength) { tap(KeyEvent.KEYCODE_FORWARD_DEL) }
            return true
        }

        override fun sendKeyEvent(event: KeyEvent): Boolean {
            if (!active) return true
            if (event.keyCode == KeyEvent.KEYCODE_DEL && composing != null) {
                if (event.action == KeyEvent.ACTION_DOWN) delete(1, 0, true)
                return true
            }
            return queueKeys(listOf(event))
        }

        private fun queueKeys(events: List<KeyEvent>): Boolean {
            if (fallback.isNotEmpty()) {
                fallback.addLast(PendingInput.Keys(events))
                return true
            }
            var handled = true
            events.forEach { handled = this@KeyboardHost.sendKeyEvent(it) && handled }
            return handled
        }

        override fun closeConnection() {
            cancel()
            super.closeConnection()
        }

        fun cancel() {
            if (!active) return
            desktopIme.send("preedit", "", composingToken)
            active = false
            composing = null
            composingToken = null
            fallback.clear()
            queuedFocusToken = null
            fallbackHandler.removeCallbacks(drain)
        }

        private fun drainFallback() {
            if (!active) return
            repeat(64) {
                val pending = fallback.peekFirst() ?: run {
                    queuedFocusToken = null
                    return
                }
                val expected = queuedFocusToken ?: (pending as? PendingInput.Commit)?.token
                if (expected != null) {
                    queuedFocusToken = expected
                    if (desktopIme.focusToken() != expected) {
                        fallback.clear()
                        queuedFocusToken = null
                        fallbackHandler.removeCallbacks(drain)
                        return
                    }
                }
                when (pending) {
                    is PendingInput.Commit -> {
                        if (!desktopIme.send("commit", pending.value, pending.token)) {
                            // Never redirect a bridge-bound commit to an unrelated focused field.
                            fallbackHandler.postDelayed(drain, 100)
                            return
                        }
                        fallback.removeFirst()
                    }
                    is PendingInput.Keys -> {
                        fallback.removeFirst()
                        pending.events.forEach { this@KeyboardHost.sendKeyEvent(it) }
                    }
                    is PendingInput.Text -> {
                        val cp = pending.value.codePointAt(pending.offset)
                        val events = map.getEvents(Character.toChars(cp))
                        if (events != null) events.forEach { this@KeyboardHost.sendKeyEvent(it) }
                        else {
                            val t = System.currentTimeMillis()
                            val down = KeyEvent(t, t, KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_UNKNOWN, 0, 0,
                                KeyCharacterMap.VIRTUAL_KEYBOARD, 0, 0, 0)
                            this@KeyboardHost.sendKeyEvent(CharKeyEvent(down, cp))
                            this@KeyboardHost.sendKeyEvent(CharKeyEvent(KeyEvent.changeAction(down, KeyEvent.ACTION_UP), cp))
                        }
                        if (!active) return
                        pending.offset += Character.charCount(cp)
                        if (pending.offset == pending.value.length) fallback.removeFirst()
                    }
                }
            }
            if (fallback.isNotEmpty()) fallbackHandler.post(drain)
            else queuedFocusToken = null
        }

        override fun performEditorAction(actionCode: Int): Boolean {
            if (!active) return true
            tap(KeyEvent.KEYCODE_ENTER)
            return true
        }

        private fun tap(keyCode: Int) {
            val t = System.currentTimeMillis()
            queueKeys(listOf(KeyEvent(t, t, KeyEvent.ACTION_DOWN, keyCode, 0),
                KeyEvent(t, t, KeyEvent.ACTION_UP, keyCode, 0)))
        }

        override fun getTextBeforeCursor(n: Int, flags: Int): CharSequence = ""
        override fun getTextAfterCursor(n: Int, flags: Int): CharSequence = ""
        override fun getSelectedText(flags: Int): CharSequence? = null
    }

    private sealed class PendingInput {
        class Text(val value: String, var offset: Int = 0) : PendingInput()
        class Commit(val value: String, val token: String) : PendingInput()
        class Keys(val events: List<KeyEvent>) : PendingInput()
    }

    private class CharKeyEvent(origin: KeyEvent, private val ch: Int) : KeyEvent(origin) {
        override fun getUnicodeChar(): Int = ch
        override fun getUnicodeChar(metaState: Int): Int = ch
    }
}

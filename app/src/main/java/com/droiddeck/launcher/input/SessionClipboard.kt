package com.droiddeck.launcher.input

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.system.Os
import android.util.Log
import android.widget.Toast
import com.droiddeck.launcher.R
import com.droiddeck.launcher.wayland.WaylandCompositor
import java.io.File
import java.io.IOException

class SessionClipboard(context: Context, private val hasFocus: () -> Boolean) {
    private val appContext = context.applicationContext
    private val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    private val handler = Handler(Looper.getMainLooper())
    private val hostFile = File(context.filesDir, "session/android-clipboard")
    private var active = false
    private var published = false
    private var shared: String? = null
    private var echo: String? = null
    private val androidListener = ClipboardManager.OnPrimaryClipChangedListener { refresh(changed = true) }
    private val guestListener = object : WaylandCompositor.ClipboardListener {
        override fun onGuestClipboardText(text: String) {
            handler.post {
                if (active && hasFocus() && WaylandCompositor.isClipboardListener(this)) {
                    if (ClipboardText.encode(text) == null) {
                        notice(R.string.custom_clipboard_too_large)
                        return@post
                    }
                    val current = try {
                        clipboard.primaryClip?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.text
                    } catch (_: RuntimeException) { null }
                    if (current?.toString() != text) {
                        echo = text
                        if (!ClipboardText.writeSafely(text) {
                            clipboard.setPrimaryClip(ClipData.newPlainText("DroidDeck", it))
                        }) {
                            echo = null
                            Log.w("SessionClipboard", "Android rejected clipboard synchronization")
                            notice(R.string.custom_clipboard_android_rejected)
                            return@post
                        }
                    }
                    shared = text
                    published = true
                }
            }
        }
    }

    fun start() {
        if (active) return
        active = true
        clipboard.addPrimaryClipChangedListener(androidListener)
        WaylandCompositor.setClipboardListener(guestListener)
        refresh()
    }

    fun stop() {
        if (!active) return
        active = false
        clipboard.removePrimaryClipChangedListener(androidListener)
        WaylandCompositor.clearClipboardListener(guestListener)
        handler.removeCallbacksAndMessages(null)
    }

    fun refresh(changed: Boolean = false) {
        if (!active || !hasFocus()) return
        val clip = try { clipboard.primaryClip } catch (e: RuntimeException) {
            Log.w("SessionClipboard", "Android clipboard is not currently accessible", e)
            return
        }
        if (clip != null && clip.itemCount == 0) return
        val text = clip?.getItemAt(0)?.text?.toString()
        if (echo != null && text == echo) {
            echo = null
            return
        }
        echo = null
        if (!changed && published && text == shared) return
        publish(text)
    }

    private fun publish(text: String?) {
        published = true
        shared = text
        val encoded = ClipboardText.encode(text)
        if (encoded == null) notice(R.string.custom_clipboard_too_large)
        WaylandCompositor.setClipboardText(if (encoded == null) null else text)
        val pending = File(hostFile.parentFile, "android-clipboard.pending")
        try {
            hostFile.parentFile?.mkdirs()
            pending.writeBytes(encoded ?: byteArrayOf())
            Os.rename(pending.path, hostFile.path)
        } catch (e: IOException) {
            Log.w("SessionClipboard", "Could not share text with Xwayland", e)
        } catch (e: android.system.ErrnoException) {
            Log.w("SessionClipboard", "Could not publish text for Xwayland", e)
        } finally {
            pending.delete()
        }
    }

    private fun notice(message: Int) {
        Toast.makeText(appContext, message, Toast.LENGTH_LONG).show()
    }
}

package com.droiddeck.launcher.input

import android.content.Context
import android.net.LocalSocket
import android.net.LocalSocketAddress
import android.system.Os
import android.system.OsConstants
import org.json.JSONObject
import java.io.File
import java.util.UUID

internal class DesktopImeBridge(context: Context) {
    private val session = File(context.filesDir, "session")
    var directory = "agent"

    fun focusToken(): String? = runCatching {
        val state = JSONObject(File(File(session, directory), "ime.json").readText())
        state.optString("focusToken").takeIf { state.optBoolean("textField") && it.isNotEmpty() }
    }.getOrNull()

    fun send(operation: String, text: String = "", expectedToken: String? = null): Boolean {
        var sent = false
        var pending: File? = null
        return try {
            val dir = File(session, directory)
            val state = JSONObject(File(dir, "ime.json").readText())
            val token = state.optString("focusToken")
            if (expectedToken != null && (!state.optBoolean("textField") || token != expectedToken)) return true
            if (!state.optBoolean("textField") || token.isEmpty()) false else {
                val value = if (operation == "preedit") preview(text) else text
                if ("\u0000" in value) return true
                if (value.toByteArray(Charsets.UTF_8).size > 1024 * 1024) return false
                val payload = JSONObject().put("token", token).put("operation", operation)
                if (value.length > 700) {
                    val file = File(dir, "input-${UUID.randomUUID().toString().replace("-", "")}.json")
                    pending = file
                    Os.open(file.path, android.system.OsConstants.O_WRONLY or android.system.OsConstants.O_CREAT or
                        android.system.OsConstants.O_EXCL, 0x180).let { fd ->
                        try {
                            val bytes = value.toByteArray(Charsets.UTF_8)
                            var offset = 0
                            while (offset < bytes.size) {
                                val count = Os.write(fd, bytes, offset, bytes.size - offset)
                                check(count > 0)
                                offset += count
                            }
                        } finally { Os.close(fd) }
                    }
                    payload.put("file", file.name)
                } else payload.put("text", value)
                LocalSocket(LocalSocket.SOCKET_DGRAM).use { socket ->
                    socket.connect(LocalSocketAddress(File(dir, "ime.sock").path, LocalSocketAddress.Namespace.FILESYSTEM))
                    val flags = Os.fcntlInt(socket.fileDescriptor, OsConstants.F_GETFL, 0)
                    Os.fcntlInt(socket.fileDescriptor, OsConstants.F_SETFL, flags or OsConstants.O_NONBLOCK)
                    val bytes = payload.toString().toByteArray(Charsets.UTF_8)
                    check(Os.write(socket.fileDescriptor, bytes, 0, bytes.size) == bytes.size)
                    sent = true
                }
                true
            }
        } catch (_: Exception) { sent }
        finally { if (!sent) pending?.delete() }
    }

    private fun preview(text: String): String {
        var end = minOf(700, text.length)
        if (end < text.length && Character.isHighSurrogate(text[end - 1])) end--
        return text.substring(0, end)
    }
}

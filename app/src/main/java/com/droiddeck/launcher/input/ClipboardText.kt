package com.droiddeck.launcher.input

internal object ClipboardText {
    const val MAX_BYTES = 1024 * 1024

    fun encode(text: String?): ByteArray? {
        if ((text?.length ?: 0) > MAX_BYTES) return null
        return text.orEmpty().toByteArray(Charsets.UTF_8).takeIf { it.size <= MAX_BYTES }
    }

    fun writeSafely(text: String, writer: (String) -> Unit): Boolean = try {
        writer(text)
        true
    } catch (_: RuntimeException) {
        false
    }
}

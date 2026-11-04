#include "../../app/src/main/cpp/waylandcomp/src/wl_clipboard.c"
#include <assert.h>
#include <stdio.h>

static size_t copied_bytes;
static int copies;
static unsigned char *expected;

void droiddeck_log(const char *tag, const char *fmt, ...) { (void)tag; (void)fmt; }
int wl_event_source_remove(struct wl_event_source *source) { (void)source; return 0; }
void droiddeck_on_clipboard_text(const char *text, int len) {
    copied_bytes = (size_t)len;
    copies++;
    assert(!memcmp(text, expected, copied_bytes));
}

static void copy_guest(size_t length, int should_copy) {
    FILE *file = tmpfile();
    assert(file);
    assert(fwrite(expected, 1, length, file) == length);
    rewind(file);
    struct reader *r = calloc(1, sizeof(*r));
    assert(r);
    r->fd = dup(fileno(file));
    r->mime = "text/plain;charset=utf-8";
    g_reader = r;
    int before = copies;
    on_reader_readable(r->fd, 0, r);
    assert(g_reader == NULL);
    assert(copies - before == should_copy);
    if (should_copy) assert(copied_bytes == length);
    fclose(file);
}

int main(void) {
    expected = malloc(CLIP_MAX_BYTES + 1);
    assert(expected);
    const unsigned char chinese[] = {0xe4, 0xb8, 0xad};
    for (size_t i = 0; i < CLIP_MAX_BYTES + 1; i++) expected[i] = chinese[i % 3];
    expected[CLIP_MAX_BYTES - 1] = '\n';
    expected[CLIP_MAX_BYTES] = 'x';
    copy_guest(CLIP_MAX_BYTES, 1);
    copy_guest(CLIP_MAX_BYTES + 1, 0);
    copy_guest(0, 0);
    memcpy(expected, "\xf0\x9f\x98\x80\xe4\xb8\xad\n", 8);
    copy_guest(8, 1);
    free(g_last_guest_text);
    free(expected);
    puts("Wayland clipboard: exact 1 MiB, over-limit rejection, empty text and UTF-8 passed");
    return 0;
}

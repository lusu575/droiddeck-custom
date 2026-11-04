#define main clipboard_daemon_main
#include "../linuxfs/clipboard/clipboard.c"
#undef main
#include <assert.h>

static unsigned char received[MAX_TEXT];
static size_t received_len;
static int notifications, finished;
static int change(Display *d, Window w, Atom prop, Atom type, int format, int mode,
                  const unsigned char *data, int count) {
    (void)d; (void)w; (void)prop; (void)type; (void)mode;
    if (format == 32) { notifications++; return 0; }
    assert(count <= CHUNK_SIZE);
    if (!count) finished++;
    memcpy(received + received_len, data, count);
    received_len += count;
    return 0;
}
static int select_input(Display *d, Window w, long mask) { (void)d; (void)w; assert(mask == (1L << 22)); return 0; }
static int flush(Display *d) { (void)d; return 0; }

int main(void) {
    XChangeProperty = change; XSelectInput = select_input; XFlush = flush;
    unsigned char *data = malloc(MAX_TEXT);
    for (size_t i = 0; i < MAX_TEXT; i++) data[i] = (unsigned char)(i % 251);
    assert(start_transfer(NULL, 7, 8, 9, 10, (char *)data, MAX_TEXT));
    assert(!start_transfer(NULL, 7, 8, 9, 10, "duplicate", 9));
    assert(notifications == 1);
    PropertyNotify property = {.window = 7, .atom = 8, .state = 1};
    for (size_t i = 0; i <= MAX_TEXT / CHUNK_SIZE; i++) advance_transfer(NULL, &property);
    assert(received_len == MAX_TEXT);
    assert(finished == 1);
    assert(!memcmp(received, data, MAX_TEXT));
    for (int i = 0; i < MAX_TRANSFERS; i++) assert(!transfers[i].data);
    assert(start_transfer(NULL, 7, 8, 9, 10, "snapshot", 8));
    transfers[0].touched -= TRANSFER_TIMEOUT;
    expire_transfers();
    assert(!transfers[0].data);
    free(data);
    puts("INCR: 1 MiB round-trip, snapshot isolation, completion, duplicate protection and timeout passed");
    return 0;
}

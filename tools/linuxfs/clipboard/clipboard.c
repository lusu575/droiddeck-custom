#define _GNU_SOURCE
#include <sys/inotify.h>
#include <sys/stat.h>
#include <sys/prctl.h>
#include <signal.h>
#include <poll.h>
#include <fcntl.h>
#include <unistd.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
#include <time.h>

typedef struct _XDisplay Display;
typedef unsigned long Window, Atom, Time;
typedef struct {
    int type; unsigned long serial; int send_event; Display *display;
    Window owner, requestor; Atom selection, target, property; Time time;
} SelectionRequest;
typedef struct {
    int type; unsigned long serial; int send_event; Display *display;
    Window requestor; Atom selection, target, property; Time time;
} SelectionNotify;
typedef struct {
    int type; unsigned long serial; int send_event; Display *display;
    Window window; Atom atom; Time time; int state;
} PropertyNotify;
typedef union { int type; SelectionRequest request; SelectionNotify selection; PropertyNotify property; long pad[24]; } Event;

#define API(ret, name, args) static ret (*name) args
API(Display *, XOpenDisplay, (const char *));
API(Window, XDefaultRootWindow, (Display *));
API(Window, XCreateSimpleWindow, (Display *, Window, int, int, unsigned, unsigned, unsigned, unsigned long, unsigned long));
API(Atom, XInternAtom, (Display *, const char *, int));
API(int, XSetSelectionOwner, (Display *, Atom, Window, Time));
API(Window, XGetSelectionOwner, (Display *, Atom));
API(int, XChangeProperty, (Display *, Window, Atom, Atom, int, int, const unsigned char *, int));
API(int, XSendEvent, (Display *, Window, int, long, Event *));
API(int, XPending, (Display *));
API(int, XNextEvent, (Display *, Event *));
API(int, XFlush, (Display *));
API(int, XConnectionNumber, (Display *));
API(int, XCloseDisplay, (Display *));
API(int, XSelectInput, (Display *, Window, long));
API(void *, XSetErrorHandler, (int (*)(Display *, void *)));

#define MAX_TEXT (1024 * 1024)
#define CHUNK_SIZE (16 * 1024)
#define MAX_TRANSFERS 8
#define TRANSFER_TIMEOUT 10

struct transfer { Window window; Atom property, type; unsigned char *data; size_t size, offset; time_t touched; };
static struct transfer transfers[MAX_TRANSFERS];

static void expire_transfers(void) {
    time_t now = time(NULL);
    for (int i = 0; i < MAX_TRANSFERS; i++) {
        if (transfers[i].data && now - transfers[i].touched >= TRANSFER_TIMEOUT) {
            free(transfers[i].data);
            memset(&transfers[i], 0, sizeof(transfers[i]));
        }
    }
}

static int start_transfer(Display *d, Window window, Atom property, Atom type, Atom incr,
                          const char *text, size_t len) {
    expire_transfers();
    for (int i = 0; i < MAX_TRANSFERS; i++) {
        struct transfer *t = &transfers[i];
        if (t->data && t->window == window && t->property == property) return 0;
    }
    for (int i = 0; i < MAX_TRANSFERS; i++) {
        struct transfer *t = &transfers[i];
        if (t->data) continue;
        unsigned char *copy = malloc(len);
        if (!copy) return 0;
        memcpy(copy, text, len);
        *t = (struct transfer){window, property, type, copy, len, 0, time(NULL)};
        unsigned long size = len;
        XSelectInput(d, window, 1L << 22);
        XChangeProperty(d, window, property, incr, 32, 0, (const unsigned char *)&size, 1);
        return 1;
    }
    return 0;
}

static void advance_transfer(Display *d, const PropertyNotify *event) {
    if (event->state != 1) return;
    for (int i = 0; i < MAX_TRANSFERS; i++) {
        struct transfer *t = &transfers[i];
        if (!t->data || t->window != event->window || t->property != event->atom) continue;
        size_t count = t->size - t->offset;
        if (count > CHUNK_SIZE) count = CHUNK_SIZE;
        XChangeProperty(d, t->window, t->property, t->type, 8, 0, t->data + t->offset, (int)count);
        t->offset += count;
        t->touched = time(NULL);
        if (!count) { free(t->data); memset(t, 0, sizeof(*t)); }
        XFlush(d);
        return;
    }
}
static int ignore_x_error(Display *d, void *event) { (void)d; (void)event; return 0; }

static int refresh(Display *d, Window w, Atom clipboard, const char *path,
                   char **text, size_t *len, ino_t *inode) {
    int fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return 0;
    struct stat st;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_ino == *inode) { close(fd); return 0; }
    *inode = st.st_ino;
    if (st.st_size < 0 || st.st_size > MAX_TEXT) {
        fprintf(stderr, "== clipboard: text exceeds %d bytes, not pasted\n", MAX_TEXT);
        if (XGetSelectionOwner(d, clipboard) == w) XSetSelectionOwner(d, clipboard, 0, 0);
        XFlush(d);
        free(*text); *text = NULL; *len = 0;
        close(fd); return 0;
    }
    char *copy = malloc((size_t)st.st_size + 1);
    if (!copy) { close(fd); return 0; }
    size_t got = 0;
    while (got < (size_t)st.st_size) {
        ssize_t n = read(fd, copy + got, (size_t)st.st_size - got);
        if (n > 0) got += n;
        else if (n < 0 && errno == EINTR) continue;
        else break;
    }
    close(fd);
    if (got != (size_t)st.st_size) { free(copy); return 0; }
    copy[got] = 0;
    free(*text); *text = copy; *len = got;
    if (got) XSetSelectionOwner(d, clipboard, w, 0);
    else if (XGetSelectionOwner(d, clipboard) == w) XSetSelectionOwner(d, clipboard, 0, 0);
    XFlush(d);
    fprintf(stderr, "== clipboard: Android text available in Xwayland (%zu bytes)\n", got);
    return 1;
}

int main(int argc, char **argv) {
    if (argc != 2 || !getenv("DISPLAY")) return 1;
    pid_t parent_pid = getppid();
    if (parent_pid == 1 || prctl(PR_SET_PDEATHSIG, SIGTERM) || getppid() != parent_pid) return 1;
    void *lib = dlopen("libX11.so.6", RTLD_NOW | RTLD_LOCAL);
    if (!lib) { fprintf(stderr, "== clipboard: libX11 unavailable\n"); return 1; }
#define LOAD(name) do { *(void **)(&name) = dlsym(lib, #name); if (!name) return 1; } while (0)
    LOAD(XOpenDisplay); LOAD(XDefaultRootWindow); LOAD(XCreateSimpleWindow); LOAD(XInternAtom);
    LOAD(XSetSelectionOwner); LOAD(XGetSelectionOwner); LOAD(XChangeProperty); LOAD(XSendEvent);
    LOAD(XPending); LOAD(XNextEvent); LOAD(XFlush); LOAD(XConnectionNumber); LOAD(XCloseDisplay);
    LOAD(XSetErrorHandler); LOAD(XSelectInput);
    Display *d = XOpenDisplay(NULL);
    if (!d) { fprintf(stderr, "== clipboard: cannot open Xwayland\n"); return 1; }
    XSetErrorHandler(ignore_x_error);
    Window w = XCreateSimpleWindow(d, XDefaultRootWindow(d), 0, 0, 1, 1, 0, 0, 0);
    Atom clipboard = XInternAtom(d, "CLIPBOARD", 0);
    Atom targets = XInternAtom(d, "TARGETS", 0), utf8 = XInternAtom(d, "UTF8_STRING", 0);
    Atom plain = XInternAtom(d, "text/plain;charset=utf-8", 0), text_atom = XInternAtom(d, "TEXT", 0);
    Atom string = XInternAtom(d, "STRING", 0), incr = XInternAtom(d, "INCR", 0);
    char parent[PATH_MAX];
    if (strlen(argv[1]) >= sizeof(parent)) return 1;
    strcpy(parent, argv[1]); char *slash = strrchr(parent, '/');
    if (!slash) return 1;
    *slash = 0;
    int watch = inotify_init1(IN_CLOEXEC | IN_NONBLOCK);
    if (watch < 0 || inotify_add_watch(watch, parent, IN_MOVED_TO | IN_CLOSE_WRITE) < 0) return 1;
    char *text = NULL; size_t len = 0; ino_t inode = 0;
    refresh(d, w, clipboard, argv[1], &text, &len, &inode);
    struct pollfd fds[] = {{XConnectionNumber(d), POLLIN, 0}, {watch, POLLIN, 0}};
    for (;;) {
        while (XPending(d)) {
            Event e; XNextEvent(d, &e);
            if (e.type == 28) { advance_transfer(d, &e.property); continue; }
            if (e.type != 30) continue;
            SelectionRequest *r = &e.request;
            Atom property = r->property ? r->property : r->target;
            Event reply = {0};
            reply.selection = (SelectionNotify){31, 0, 1, d, r->requestor, r->selection, r->target, 0, r->time};
            if (r->selection == clipboard && text && len) {
                size_t ascii; for (ascii = 0; ascii < len && (unsigned char)text[ascii] < 128; ascii++) {}
                if (r->target == targets) {
                    Atom supported[] = {targets, utf8, plain, text_atom, string};
                    XChangeProperty(d, r->requestor, property, 4  , 32, 0,
                                    (const unsigned char *)supported, ascii == len ? 5 : 4);
                    reply.selection.property = property;
                } else if (r->target == utf8 || r->target == plain || r->target == text_atom) {
                    if (len > CHUNK_SIZE) {
                        if (start_transfer(d, r->requestor, property, utf8, incr, text, len)) reply.selection.property = property;
                    } else {
                        XChangeProperty(d, r->requestor, property, utf8, 8, 0, (const unsigned char *)text, (int)len);
                        reply.selection.property = property;
                    }
                } else if (r->target == string) {
                    if (ascii == len) {
                        if (len > CHUNK_SIZE) {
                            if (start_transfer(d, r->requestor, property, string, incr, text, len)) reply.selection.property = property;
                        } else {
                            XChangeProperty(d, r->requestor, property, string, 8, 0, (const unsigned char *)text, (int)len);
                            reply.selection.property = property;
                        }
                    }
                }
            }
            XSendEvent(d, r->requestor, 0, 0, &reply); XFlush(d);
        }
        expire_transfers();
        if (poll(fds, 2, 1000) < 0) { if (errno == EINTR) continue; break; }
        if (fds[0].revents & (POLLERR | POLLHUP | POLLNVAL)) break;
        if (fds[1].revents & POLLIN) {
            char events[4096]; while (read(watch, events, sizeof(events)) > 0) {}
            refresh(d, w, clipboard, argv[1], &text, &len, &inode);
        }
    }
    for (int i = 0; i < MAX_TRANSFERS; i++) free(transfers[i].data);
    free(text); close(watch); XCloseDisplay(d); dlclose(lib);
    return 0;
}

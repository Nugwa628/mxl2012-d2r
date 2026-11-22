// wctl: Win32 window helper for game runs under Wine/Proton (tools/linux_window.py drives it).
//
// It runs INSIDE a game slot's Wine prefix, so it talks to the same wineserver as the game: window handles, process
// ids and named shared memory are the game's own. It never takes the focus, never moves the real cursor and never sends
// global input: it posts window messages, sizes windows with SWP_NOACTIVATE and writes the plugin test harness's
// virtual input block. Build: tools/wctl/build.sh (clang + lld + the MSVC SDK, no Visual Studio needed).
//
// Protocol: one request per line, fields separated by TAB, numbers in decimal or 0x hex. Every reply ends with one
// line that starts with "ok" or "err"; list replies send one "- ..." line per entry before it.
//   wctl.exe serve          read requests from stdin until EOF or "quit" (the Python side keeps one open per run)
//   wctl.exe CMD ARG...     run one request given on the command line (for a person at a shell)
// Requests:
//   ping                                  ok wctl 2
//   procs                                 - PID<TAB>IMAGE        (every process of this wineserver)
//   windows                               - HWND PID VIS ICONIC X11 CW CH CLASS TITLE   (top-level windows)
//   find TITLE [PID]                      ok HWND PID X11 CW CH ICONIC: visible top-level window titled TITLE or
//                                         "TITLE [..." (not a dialog), owned by PID when PID is given and not 0
//   buttons HWND                          - STYLE TEXT           (visible child buttons; STYLE = style & BS_TYPEMASK:
//                                         0/1 push buttons, 2/3/5/6 check boxes, 4/9 radio buttons)
//   rect HWND                             ok CW CH CX CY WL WT WR WB ICONIC VISIBLE  (client size, client origin on
//                                         the screen, window rect)
//   pos HWND AFTER X Y W H FLAGS          SetWindowPos -> ok RESULT FLAGS_USED. Always adds SWP_NOACTIVATE and
//                                         SWP_ASYNCWINDOWPOS (never waits for the game's thread) and drops
//                                         SWP_SHOWWINDOW; AFTER other than HWND_BOTTOM (1) becomes SWP_NOZORDER
//                                         (the helper can never activate, raise or focus a window)
//   post HWND MSG WPARAM LPARAM           PostMessageW -> ok RESULT
//   mapvk VK                              ok SCANCODE
//   alive HWND                            ok 0|1
//   fg                                    ok HWND (foreground window, for logs)
//   x11 HWND                              ok XID (the window's X11 window, 0 when it has none)
//   vopen PID                             open the plugin's input block of game process PID ("Local\mxl2012-
//                                         testharness-input-PID", else the old shared name) -> ok NAME | err ...
//   vget I / vset I V / vor I BITS / vandn I BITS    int32 cell I of the block (0..143)
//   vtext OFF TEXT                        TEXT (UTF-8, at most 500 bytes) plus a NUL at byte OFF of the block
//   sleep MS                              ok
//   quit                                  ok bye (serve ends)
#include <windows.h>
#include <tlhelp32.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <io.h>
#include <fcntl.h>

#define BLOCK_BYTES 576
#define MAXF 12

static volatile LONG *g_block;
static char g_out[8192], g_last[4];

static void out(const char *s) { strncpy(g_last, s, 3); g_last[3] = 0; fputs(s, stdout); fputc('\n', stdout); }
static void outf(const char *fmt, ...) {
  va_list ap; va_start(ap, fmt); _vsnprintf(g_out, sizeof g_out - 1, fmt, ap); va_end(ap);
  g_out[sizeof g_out - 1] = 0; out(g_out);
}
static void utf8(const wchar_t *w, char *buf, int n) {
  if (!WideCharToMultiByte(CP_UTF8, 0, w, -1, buf, n, NULL, NULL)) buf[0] = 0;
  for (char *p = buf; *p; ++p) if (*p == '\t' || *p == '\n' || *p == '\r') *p = ' ';
}
static void wide(const char *s, wchar_t *buf, int n) { if (!MultiByteToWideChar(CP_UTF8, 0, s, -1, buf, n)) buf[0] = 0; }
static unsigned long long num(const char *s) { return s ? strtoull(s, NULL, 0) : 0; }
static long long snum(const char *s) { return s ? strtoll(s, NULL, 0) : 0; }
static HWND hw(const char *s) { return (HWND)(ULONG_PTR)num(s); }
static unsigned long x11of(HWND h) { return (unsigned long)(ULONG_PTR)GetPropW(h, L"__wine_x11_whole_window"); }

static void image(DWORD pid, char *buf, int n) {
  wchar_t w[1024]; DWORD len = 1024; w[0] = 0;
  HANDLE h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
  if (h) { if (!QueryFullProcessImageNameW(h, 0, w, &len)) w[0] = 0; CloseHandle(h); }
  utf8(w, buf, n);
}

typedef struct { const wchar_t *title; DWORD pid; HWND found; int list; } Ctx;

static int title_matches(const wchar_t *t, const wchar_t *want) {
  size_t n = wcslen(want);
  if (wcsncmp(t, want, n)) return 0;
  return t[n] == 0 || (t[n] == L' ' && t[n + 1] == L'[');
}

static BOOL CALLBACK top_cb(HWND h, LPARAM lp) {
  Ctx *c = (Ctx *)lp; wchar_t cls[128], ttl[512]; DWORD pid = 0;
  cls[0] = ttl[0] = 0;
  GetClassNameW(h, cls, 128); GetWindowTextW(h, ttl, 512); GetWindowThreadProcessId(h, &pid);
  if (c->list) {
    char a[512], b[1024]; RECT r = {0}; GetClientRect(h, &r); utf8(cls, a, sizeof a); utf8(ttl, b, sizeof b);
    outf("- %llu\t%lu\t%d\t%d\t0x%lx\t%ld\t%ld\t%s\t%s", (unsigned long long)(ULONG_PTR)h, pid, IsWindowVisible(h) ? 1 : 0,
         IsIconic(h) ? 1 : 0, x11of(h), r.right, r.bottom, a, b);
    return TRUE;
  }
  if (!IsWindowVisible(h) || !wcscmp(cls, L"#32770")) return TRUE;
  if (c->pid && pid != c->pid) return TRUE;
  if (!title_matches(ttl, c->title)) return TRUE;
  c->found = h; return FALSE;
}

static BOOL CALLBACK btn_cb(HWND h, LPARAM lp) {
  (void)lp; wchar_t cls[64], ttl[256]; char b[512];
  cls[0] = ttl[0] = 0;
  GetClassNameW(h, cls, 64);
  if (!_wcsicmp(cls, L"Button") && IsWindowVisible(h)) {
    GetWindowTextW(h, ttl, 256); utf8(ttl, b, sizeof b);
    outf("- %lu\t%s", (unsigned long)(GetWindowLongW(h, GWL_STYLE) & BS_TYPEMASK), b);
  }
  return TRUE;
}

static int vopen(DWORD pid) {
  wchar_t name[96]; HANDLE m;
  if (g_block) { UnmapViewOfFile((void *)g_block); g_block = NULL; }
  swprintf(name, 96, L"Local\\mxl2012-testharness-input-%lu", pid);
  m = OpenFileMappingW(FILE_MAP_ALL_ACCESS, FALSE, name);
  if (!m) { wcscpy(name, L"Local\\mxl2012-testharness-input"); m = OpenFileMappingW(FILE_MAP_ALL_ACCESS, FALSE, name); }
  if (!m) { out("err no harness input block"); return 1; }
  g_block = (volatile LONG *)MapViewOfFile(m, FILE_MAP_ALL_ACCESS, 0, 0, BLOCK_BYTES);
  CloseHandle(m);
  if (!g_block) { out("err map failed"); return 1; }
  if (g_block[0] != 0x4d58) { UnmapViewOfFile((void *)g_block); g_block = NULL; out("err bad block magic"); return 1; }
  { char b[200]; utf8(name, b, sizeof b); outf("ok %s", b); }
  return 0;
}

static int cell(const char *s) { long long i = snum(s); return (i >= 0 && i < BLOCK_BYTES / 4) ? (int)i : -1; }

// Runs one request (f[0..n-1]); returns 0 to go on, 1 to end serve mode.
static int run(char **f, int n) {
  const char *c = f[0];
  if (!strcmp(c, "ping")) { out("ok wctl 2"); return 0; }
  if (!strcmp(c, "quit")) { out("ok bye"); return 1; }
  if (!strcmp(c, "sleep") && n > 1) { Sleep((DWORD)num(f[1])); out("ok"); return 0; }
  if (!strcmp(c, "fg")) { outf("ok %llu", (unsigned long long)(ULONG_PTR)GetForegroundWindow()); return 0; }
  if (!strcmp(c, "procs")) {
    HANDLE s = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0); PROCESSENTRY32W pe; int k = 0; char b[2048];
    pe.dwSize = sizeof pe;
    if (s != INVALID_HANDLE_VALUE) {
      for (BOOL ok = Process32FirstW(s, &pe); ok; ok = Process32NextW(s, &pe)) {
        image(pe.th32ProcessID, b, sizeof b);
        if (!b[0]) utf8(pe.szExeFile, b, sizeof b);
        outf("- %lu\t%s", pe.th32ProcessID, b); ++k;
      }
      CloseHandle(s);
    }
    outf("ok %d", k); return 0;
  }
  if (!strcmp(c, "windows")) { Ctx x = {0}; x.list = 1; EnumWindows(top_cb, (LPARAM)&x); out("ok"); return 0; }
  if (!strcmp(c, "find") && n > 1) {
    wchar_t t[512]; Ctx x = {0}; RECT r = {0}; DWORD pid = 0;
    wide(f[1], t, 512); x.title = t; x.pid = n > 2 ? (DWORD)num(f[2]) : 0;
    EnumWindows(top_cb, (LPARAM)&x);
    if (!x.found) { out("err none"); return 0; }
    GetClientRect(x.found, &r); GetWindowThreadProcessId(x.found, &pid);
    outf("ok %llu %lu 0x%lx %ld %ld %d", (unsigned long long)(ULONG_PTR)x.found, pid, x11of(x.found), r.right, r.bottom,
         IsIconic(x.found) ? 1 : 0);
    return 0;
  }
  if (!strcmp(c, "vopen") && n > 1) { vopen((DWORD)num(f[1])); return 0; }
  if (c[0] == 'v' && strcmp(c, "vopen")) {
    int i;
    if (!g_block) { out("err no block (vopen first)"); return 0; }
    if (!strcmp(c, "vtext") && n > 2) {
      long long off = snum(f[1]); size_t len = strlen(f[2]);
      if (len > 500) len = 500;
      if (off < 0 || off + (long long)len + 1 > BLOCK_BYTES) { out("err offset"); return 0; }
      memcpy((char *)g_block + off, f[2], len); ((char *)g_block)[off + len] = 0; MemoryBarrier();
      outf("ok %u", (unsigned)len); return 0;
    }
    if (n < 2 || (i = cell(f[1])) < 0) { out("err cell"); return 0; }
    if (!strcmp(c, "vget")) { outf("ok %ld", g_block[i]); return 0; }
    if (n < 3) { out("err value"); return 0; }
    if (!strcmp(c, "vset")) InterlockedExchange(&g_block[i], (LONG)snum(f[2]));
    else if (!strcmp(c, "vor")) InterlockedOr(&g_block[i], (LONG)snum(f[2]));
    else if (!strcmp(c, "vandn")) InterlockedAnd(&g_block[i], ~(LONG)snum(f[2]));
    else { out("err unknown"); return 0; }
    outf("ok %ld", g_block[i]); return 0;
  }
  if (n < 2) { out("err arguments"); return 0; }
  if (!strcmp(c, "mapvk")) { outf("ok %u", MapVirtualKeyW((UINT)num(f[1]), 0)); return 0; }
  HWND h = hw(f[1]);
  if (!strcmp(c, "alive")) { outf("ok %d", IsWindow(h) ? 1 : 0); return 0; }
  if (!IsWindow(h)) { out("err no window"); return 0; }
  if (!strcmp(c, "x11")) { outf("ok 0x%lx", x11of(h)); return 0; }
  if (!strcmp(c, "buttons")) { EnumChildWindows(h, btn_cb, 0); out("ok"); return 0; }
  if (!strcmp(c, "rect")) {
    RECT cr = {0}, wr = {0}; POINT p = {0, 0};
    GetClientRect(h, &cr); GetWindowRect(h, &wr); ClientToScreen(h, &p);
    outf("ok %ld %ld %ld %ld %ld %ld %ld %ld %d %d", cr.right, cr.bottom, p.x, p.y, wr.left, wr.top, wr.right, wr.bottom,
         IsIconic(h) ? 1 : 0, IsWindowVisible(h) ? 1 : 0);
    return 0;
  }
  if (!strcmp(c, "pos") && n > 7) {
    // Never activates or raises: SWP_NOACTIVATE always; any insert-after other than HWND_BOTTOM is dropped (NOZORDER),
    // so a caller cannot bring the game to the front or make it topmost (owner rule: no focus stealing).
    HWND after = (HWND)(LONG_PTR)snum(f[2]);
    // SWP_ASYNCWINDOWPOS: the window belongs to the game's thread; a synchronous call waits for that thread and hung
    // when it was busy (lane linctl run2).
    UINT fl = ((UINT)num(f[7]) | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS) & ~(UINT)SWP_SHOWWINDOW;
    if (after != HWND_BOTTOM) { fl |= SWP_NOZORDER; after = NULL; }
    BOOL r = SetWindowPos(h, after, (int)snum(f[3]), (int)snum(f[4]), (int)snum(f[5]), (int)snum(f[6]), fl);
    outf("ok %d 0x%x", r ? 1 : 0, fl); return 0;
  }
  if (!strcmp(c, "post") && n > 4) {
    BOOL r = PostMessageW(h, (UINT)num(f[2]), (WPARAM)num(f[3]), (LPARAM)(LONG_PTR)snum(f[4]));
    outf("ok %d", r ? 1 : 0); return 0;
  }
  out("err unknown request"); return 0;
}

static int split(char *line, char **f) {
  int n = 0; size_t L = strlen(line);
  while (L && (line[L - 1] == '\n' || line[L - 1] == '\r')) line[--L] = 0;
  if (!L) return 0;
  f[n++] = line;
  for (char *p = line; *p && n < MAXF; ++p) if (*p == '\t') { *p = 0; f[n++] = p + 1; }
  return n;
}

int wmain(int argc, wchar_t **argv) {
  static char line[4096]; char *f[MAXF];
  _setmode(_fileno(stdin), _O_BINARY); _setmode(_fileno(stdout), _O_BINARY);
  if (argc < 2) { fputs("usage: wctl serve | wctl REQUEST ARG... (see wctl.c)\n", stderr); return 2; }
  if (!wcscmp(argv[1], L"serve")) {
    out("ok wctl 2 ready"); fflush(stdout);
    while (fgets(line, sizeof line, stdin)) {
      int n = split(line, f);
      if (!n) continue;
      int end = run(f, n); fflush(stdout);
      if (end) break;
    }
    return 0;
  }
  size_t used = 0;
  for (int i = 1; i < argc && used < sizeof line - 4; ++i) {
    char b[1024]; utf8(argv[i], b, sizeof b);
    if (i > 1) line[used++] = '\t';
    size_t k = strlen(b); if (used + k >= sizeof line - 2) k = sizeof line - 2 - used;
    memcpy(line + used, b, k); used += k;
  }
  line[used] = 0;
  int n = split(line, f);
  run(f, n); fflush(stdout);
  return strcmp(g_last, "err") == 0 ? 1 : 0;
}

"""A small static file server with HTTP Range support, for testing against what tools/publish_release.py wrote (the launcher
lane's tests and a local dry run of the download host). Not for production: Caddy serves the real host (docs/hosting.md).

  py -3 tools/serve_dir.py DIR [--port 0] [--host 127.0.0.1] [--quiet]

Prints `serving <DIR> on http://127.0.0.1:<port>/` (the first line, flushed; port 0 picks a free one). GET and HEAD, one
byte range per request (`bytes=a-b`, `a-`, `-n`; 206 with Content-Range, 416 when unsatisfiable), `Accept-Ranges: bytes`,
ETag and Last-Modified (If-None-Match -> 304), and the Cache-Control of docs/hosting.md: immutable for objects/, no-cache for
channels/ and the rest. No directory listings. In a test:

  with serve_dir.running(folder) as base:        # base = "http://127.0.0.1:54321/"
      urllib.request.urlopen(base + "channels/stable.json")
"""
import argparse
import contextlib
import email.utils
import http.server
import re
import sys
import threading
from pathlib import Path

RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
CHUNK = 1 << 20


def cache_control(path: str) -> str:
    if path.startswith("/objects/"):
        return "public, max-age=31536000, immutable"
    return "no-cache"


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "serve_dir/1"
    root: Path = Path(".")
    quiet = False

    def log_message(self, fmt, *args):
        if not self.quiet:
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _resolve(self):
        rel = self.path.split("?", 1)[0].split("#", 1)[0]
        from urllib.parse import unquote
        parts = [p for p in unquote(rel).split("/") if p]
        if any(p in (".", "..") or "\\" in p or ":" in p for p in parts):
            return None
        p = self.root.joinpath(*parts)
        try:
            p.resolve().relative_to(self.root.resolve())
        except ValueError:
            return None
        return p if p.is_file() else None

    def _send_error(self, code, msg=""):
        body = (msg or http.HTTPStatus(code).phrase).encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _serve(self, head):
        p = self._resolve()
        if p is None:
            return self._send_error(404)
        st = p.stat()
        size = st.st_size
        etag = '"%x-%x"' % (st.st_mtime_ns, size)
        start, end, status = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng:
            m = RANGE_RE.match(rng.strip())
            if not m or (not m.group(1) and not m.group(2)):
                return self._send_error(416)  # not a single simple byte range
            if m.group(1):
                start = int(m.group(1))
                end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
            else:  # suffix: the last n bytes
                n = int(m.group(2))
                start, end = max(size - n, 0), size - 1
            if start >= size or start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        elif self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.end_headers()
            return
        length = end - start + 1 if size else 0
        self.send_response(status)
        self.send_header("Content-Type", "application/json" if p.suffix == ".json" else "application/octet-stream")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", email.utils.formatdate(st.st_mtime, usegmt=True))
        self.send_header("Cache-Control", cache_control(self.path))
        self.end_headers()
        if head or not length:
            return
        with open(p, "rb") as f:
            f.seek(start)
            left = length
            while left > 0:
                chunk = f.read(min(CHUNK, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    def do_GET(self):
        self._serve(False)

    def do_HEAD(self):
        self._serve(True)


def make_server(directory, host="127.0.0.1", port=0, quiet=True) -> http.server.ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"root": Path(directory), "quiet": quiet})
    srv = http.server.ThreadingHTTPServer((host, port), handler)
    srv.daemon_threads = True
    return srv


@contextlib.contextmanager
def running(directory, host="127.0.0.1", port=0):
    """Serve `directory` in a background thread; yields the base URL with a trailing slash."""
    srv = make_server(directory, host, port)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://{host}:{srv.server_address[1]}/"
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(5)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("directory", type=Path)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    if not a.directory.is_dir():
        print(f"{a.directory} is not a folder", file=sys.stderr)
        return 1
    srv = make_server(a.directory, a.host, a.port, a.quiet)
    print(f"serving {a.directory} on http://{a.host}:{srv.server_address[1]}/", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

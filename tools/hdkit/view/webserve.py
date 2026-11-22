"""Serve the browser page and one exported bundle on 127.0.0.1 only, on demand (no other host, no listing, GET/HEAD).

  python -m hdkit.view serve-web <bundle folder> [--port 8765]     then open http://127.0.0.1:8765/

Mounts: /            -> hdkit/view/web/ (index.html, viewer.js, present.wgsl)
        /shaders.wgsl -> hdkit/view/shaders.wgsl (the CLI's own shader file, not a copy)
        /bundle/      -> the bundle folder
A page opened from file:// cannot load modules or fetch files, so the page needs this (or any static server on
127.0.0.1). `--accept-results <folder>` also takes POST /__result/<name> (JSON or PNG, at most 64 MB each) and writes it
there: the headless check uses it; without the option the server is read-only.
"""
import argparse
import contextlib
import http.server
import mimetypes
import re
import sys
import threading
from pathlib import Path
from urllib.parse import unquote

WEB = Path(__file__).with_name("web")
SHADER = Path(__file__).with_name("shaders.wgsl")
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".wgsl": "text/plain; charset=utf-8",
         ".json": "application/json", ".png": "image/png", ".bin": "application/octet-stream", ".css": "text/css"}
RESULT_RE = re.compile(r"^/__result/([A-Za-z0-9_.\-]{1,80})$")


def _inside(root: Path, parts: list):
    if any(p in (".", "..") or "\\" in p or ":" in p for p in parts):
        return None
    p = root.joinpath(*parts)
    try:
        p.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return p if p.is_file() else None


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "hdkit-web/1"
    bundle: Path = Path(".")
    results: Path | None = None
    quiet = True

    def log_message(self, fmt, *args):
        if not self.quiet:
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def resolve(self):
        rel = unquote(self.path.split("?", 1)[0].split("#", 1)[0])
        parts = [p for p in rel.split("/") if p]
        if not parts:
            return WEB / "index.html"
        if parts == ["shaders.wgsl"]:
            return SHADER
        if parts[0] == "bundle":
            return _inside(self.bundle, parts[1:])
        return _inside(WEB, parts)

    def _send(self, code, body: bytes, ctype="text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        p = self.resolve()
        if p is None:
            return self._send(404, b"not found")
        ctype = TYPES.get(p.suffix.lower()) or mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        try:
            self._send(200, p.read_bytes(), ctype)
        except (BrokenPipeError, ConnectionResetError):
            pass

    do_HEAD = do_GET

    def do_POST(self):
        m = RESULT_RE.match(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        if self.results is None or not m or n > (64 << 20):
            return self._send(403, b"read-only")
        self.results.mkdir(parents=True, exist_ok=True)
        (self.results / m.group(1)).write_bytes(self.rfile.read(n))
        self._send(200, b"ok")


def make_server(bundle, port=0, results=None, quiet=True) -> http.server.ThreadingHTTPServer:
    h = type("BoundHandler", (Handler,), {"bundle": Path(bundle), "results": Path(results) if results else None,
                                          "quiet": quiet})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), h)
    srv.daemon_threads = True
    return srv


@contextlib.contextmanager
def running(bundle, port=0, results=None):
    """Serve in a background thread; yields the base URL (trailing slash); stops the server on exit."""
    srv = make_server(bundle, port, results)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield "http://127.0.0.1:%d/" % srv.server_address[1]
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(5)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hdkit.view serve-web", description=__doc__.split("\n")[0])
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--accept-results", default=None)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)
    if not (a.bundle / "scene.json").is_file():
        print("%s has no scene.json (run export-web first)" % a.bundle, file=sys.stderr)
        return 1
    srv = make_server(a.bundle, a.port, a.accept_results, not a.verbose)
    print("serving %s on http://127.0.0.1:%d/ (Ctrl+C stops it)" % (a.bundle, srv.server_address[1]), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

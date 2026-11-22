"""The map page: `python -m hdkit.view map serve [<map>] [--port 8766]`, then open http://127.0.0.1:8766/ (127.0.0.1 only;
stop with Ctrl+C). The page pans and zooms a whole map, switches classic / HD / overlay, shows a cell's info on click,
and saves a dragged region as a screenshot (the view as shown) or a fresh render at any scale (classic, HD or sheet).

Read-only GET API (renders are written below /d2work/runs/mapview/<map>/ and cached there):
  /api/maps?source=mod|d2r                          map list
  /api/info?map=&source=&work=                      map facts and the whole-map frame at `base` scale
  /api/image?map=&kind=classic|hd&scale=&layers=    a whole-map PNG (rendered on first request)
  /api/cell?map=&x=&y=&near=                        cell info (map cell JSON)
  /api/region?map=&kind=classic|hd|sheet&cells=x0,y0,x1,y1&scale=&layers=   a region PNG
  /rounds                                           the rounds page: side-by-side pictures per round (below)
  /api/rounds                                       rounds list: ROUNDS/<round>/<map>/<n>_<label>.png|jpg (+ note.txt)
  /rounds/<round>/<map>/<file>                      one picture (only below ROUNDS)
ROUNDS: env MXL_ROUNDS, else /d2work/runs/hdmaps2/rounds. A round folder holds one folder per map (or per crop); its
pictures are shown side by side in file-name order, all the same size, with one pan/zoom for all of them.
Renders run one at a time (one lock); the HD ones use the GPU (no GPU gate from the page: the owner asked for it).
"""
from __future__ import annotations

import http.server
import json
import mimetypes
import os
import threading
import traceback
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import api, classic

WEB = Path(__file__).resolve().parents[1] / "web"
LOCK = threading.Lock()
MAX_BASE_PX = 8192
PICS = (".png", ".jpg", ".jpeg", ".webp")


def rounds_root() -> Path:
    return Path(os.environ.get("MXL_ROUNDS") or "/d2work/runs/hdmaps2/rounds")


def list_rounds(root: Path) -> list:
    out = []
    if not root.is_dir():
        return out
    for rd in sorted(p for p in root.iterdir() if p.is_dir()):
        sets = []
        for st in sorted(p for p in rd.iterdir() if p.is_dir()):
            pics = sorted(p.name for p in st.iterdir() if p.suffix.lower() in PICS)
            if pics:
                note = st / "note.txt"
                sets.append({"name": st.name, "pics": pics,
                             "note": note.read_text("utf-8", "replace") if note.is_file() else ""})
        if sets:
            note = rd / "note.txt"
            out.append({"name": rd.name, "sets": sets,
                        "note": note.read_text("utf-8", "replace") if note.is_file() else ""})
    return out


def base_scale(src) -> float:
    fr = classic.frame_of(src, None, 1.0)
    w, h = fr.native_size
    s = 0.5
    while max(w, h) * s > MAX_BASE_PX and s > 1 / 64:
        s /= 2
    return s


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "mapview/1"
    default_map = None
    default_source = "auto"
    quiet = True

    def log_message(self, fmt, *args):
        if not self.quiet:
            super().log_message(fmt, *args)

    def _send(self, code, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, default=str).encode("utf-8"), "application/json")

    def _png(self, path):
        self._send(200, Path(path).read_bytes(), "image/png")

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[-1] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/map.html"):
                return self._send(200, (WEB / "map.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/map.js":
                return self._send(200, (WEB / "map.js").read_bytes(), "text/javascript; charset=utf-8")
            if u.path in ("/rounds", "/rounds.html"):
                return self._send(200, (WEB / "rounds.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/rounds":
                return self._json({"root": str(rounds_root()), "rounds": list_rounds(rounds_root())})
            if u.path.startswith("/rounds/"):
                root = rounds_root().resolve()
                f = (root / unquote(u.path[len("/rounds/"):])).resolve()
                if root not in f.parents or not f.is_file() or f.suffix.lower() not in PICS:
                    return self._send(404, b"not found", "text/plain")
                return self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
            if u.path.startswith("/api/"):
                return self.api(u.path[5:], q)
            return self._send(404, b"not found", "text/plain")
        except Exception as e:      # report to the page, keep serving
            return self._json({"error": "%s: %s" % (type(e).__name__, e), "trace": traceback.format_exc()[-1500:]}, 500)

    def api(self, what, q):
        name = q.get("map") or self.default_map
        source = q.get("source") or self.default_source
        work = q.get("work") or None
        if what == "maps":
            out = api.list_maps(q.get("source", "mod"))
            out["default"] = {"map": self.default_map, "source": self.default_source}
            return self._json(out)
        if not name:
            return self._json({"error": "no map: pick one"}, 400)
        if what == "info":
            with LOCK:
                src = api.open_map(name, source, work)
                d = api.map_info(name, source, work)
                b = base_scale(src)
                d["base_scale"] = b
                d["frame"] = classic.frame_of(src, None, b).as_dict()
            return self._json(d)
        if what == "cell":
            with LOCK:
                return self._json(api.cell_info(name, int(q["x"]), int(q["y"]), source, work,
                                                near=float(q.get("near", 0))))
        scale = float(q.get("scale", 0.5))
        layers = q.get("layers") or None
        kind = q.get("kind", "classic")
        cells = q.get("cells") if what == "region" else None
        if what not in ("image", "region"):
            return self._json({"error": "unknown api %s" % what}, 404)
        with LOCK:
            src = api.open_map(name, source, work)
            out = api.out_dir(src) / "web"
            lay_tag = ("_" + "".join(c for c in layers if c.isalnum() or c in "+-,").replace(",", ".")) if layers else ""
            png = out / ("%s_%s%s%s.png" % (kind, api.tag_of(cells, scale), lay_tag, "_work" if work else ""))
            if what == "region" or not png.exists() or work:
                if kind == "classic":
                    api.render_classic(name, cells, scale, layers, source, work, png=str(png))
                elif kind == "hd":
                    api.render_hd(name, cells, scale, layers, source, work, png=str(png), gate=False)
                elif kind == "sheet":
                    api.render_sheet(name, cells, scale, layers, None, source, work, png=str(png), gate=False)
                else:
                    return self._json({"error": "kind: classic, hd or sheet"}, 400)
        if q.get("as") == "json":
            return self._json(json.loads(png.with_suffix(".json").read_text("utf-8")))
        return self._png(png)


def serve(map_name=None, source="auto", port=8766, quiet=True, ready=None):
    H = type("H", (Handler,), {"default_map": map_name, "default_source": source, "quiet": quiet})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    url = "http://127.0.0.1:%d/" % srv.server_address[1]
    print("map page: %s  (Ctrl+C stops it)" % url, flush=True)
    if ready:
        ready(srv, url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


mimetypes.add_type("text/javascript", ".js")

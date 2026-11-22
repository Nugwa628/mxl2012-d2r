"""hdkit.view browser viewer: the local server (routes, types, read-only unless results are accepted, no escape from the
bundle), the bundle's binary layout, clip sampling, the export-web / serve-web command lines, and that the page loads
nothing from the network. No GPU, no browser."""
import json
import math
import re
import sys
import tempfile
import types
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
from hdkit.view import cli, export_web, gr2, webserve  # noqa: E402

WEB = TOOLS / "hdkit" / "view" / "web"


def _get(url, method="GET", data=None):
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.headers.get("Content-Type"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), e.read()


class Server(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.bundle, self.results = base / "bundle", base / "results"
        (self.bundle / "tex").mkdir(parents=True)
        (self.bundle / "scene.json").write_text('{"bundle_version": 1}')
        (self.bundle / "tex" / "a_m00.png").write_bytes(b"\x89PNG")
        (base / "secret.txt").write_text("outside")

    def tearDown(self):
        self.tmp.cleanup()

    def test_routes_and_types(self):
        with webserve.running(self.bundle) as base:
            self.assertTrue(base.startswith("http://127.0.0.1:"))
            code, ct, body = _get(base)
            self.assertEqual((code, ct), (200, "text/html; charset=utf-8"))
            self.assertIn(b"viewer.js", body)
            code, ct, _ = _get(base + "viewer.js")
            self.assertEqual((code, ct), (200, "text/javascript; charset=utf-8"))
            code, _, body = _get(base + "shaders.wgsl")
            self.assertEqual(body, (TOOLS / "hdkit" / "view" / "shaders.wgsl").read_bytes())  # the CLI's own shader
            self.assertEqual(_get(base + "bundle/scene.json")[:2], (200, "application/json"))
            self.assertEqual(_get(base + "bundle/tex/a_m00.png")[:2], (200, "image/png"))
            for bad in ("bundle/../secret.txt", "bundle/%2e%2e/secret.txt", "bundle/..%5csecret.txt", "../secret.txt",
                        "bundle/missing.bin", "bundle/tex"):
                self.assertEqual(_get(base + bad)[0], 404, bad)

    def test_read_only_without_results(self):
        with webserve.running(self.bundle) as base:
            self.assertEqual(_get(base + "__result/check.json", "POST", b"{}")[0], 403)
        self.assertFalse(self.results.exists())

    def test_results_posted(self):
        with webserve.running(self.bundle, 0, self.results) as base:
            self.assertEqual(_get(base + "__result/check.json", "POST", b'{"max_diff": 1}')[0], 200)
            self.assertEqual(_get(base + "__result/../x.json", "POST", b"{}")[0], 403)
            self.assertEqual(_get(base + "__result/a/b.json", "POST", b"{}")[0], 403)
        self.assertEqual(json.loads((self.results / "check.json").read_text()), {"max_diff": 1})
        self.assertEqual(sorted(p.name for p in self.results.iterdir()), ["check.json"])


class Bundle(unittest.TestCase):
    def test_blob_layout(self):
        with tempfile.TemporaryDirectory() as d:
            w = export_web._Writer(Path(d))
            parts = [("a", np.arange(3, dtype=np.uint8)), ("b", np.linspace(0, 1, 6).reshape(2, 3)),
                     ("c", np.arange(5, dtype=np.uint16)), ("d", np.ones((2, 2), np.float32))]
            info = w.blob("x.bin", parts)
            raw = (Path(d) / "x.bin").read_bytes()
            self.assertEqual(info["bytes"], len(raw))
            for key, arr in parts:
                off, dt, shape = info["fields"][key]
                self.assertEqual(off % 8, 0)
                got = np.frombuffer(raw, "<" + dt, int(np.prod(shape)), off).reshape(shape)
                np.testing.assert_array_equal(got, arr)

    def _skeleton(self):
        ns = types.SimpleNamespace
        eye = np.eye(4).ravel().tolist()
        bones = [{"Name": "root", "ParentIndex": -1, "InverseWorldTransform": eye,
                  "Transform": ns(position=[0, 0, 0], orientation=[0, 0, 0, 1], scale_shear=np.eye(3).ravel().tolist())},
                 {"Name": "b1", "ParentIndex": 0, "InverseWorldTransform": eye,
                  "Transform": ns(position=[1, 2, 3], orientation=[0, 0.6, 0, 0.8], scale_shear=(2 * np.eye(3)).ravel().tolist())}]
        return gr2.Skeleton({"Name": "sk", "Bones": bones})

    def test_sample_clip_matches_locals_at(self):
        sk = self._skeleton()
        clip = gr2.Clip("idle", 0.33, {})
        s = export_web.sample_clip(sk, clip, 50.0)
        self.assertEqual(s.shape, (math.ceil(0.33 * 50) + 1, 2, 16))
        for i in (0, 7, len(s) - 1):
            loc = gr2.locals_at(sk, clip, min(i / 50.0, 0.33))[0]
            for b, (p, q, ss) in enumerate(loc):
                np.testing.assert_array_equal(s[i, b], np.concatenate([p, q, np.asarray(ss).ravel()]))
        np.testing.assert_array_equal(s[0, 1, :7], [1, 2, 3, 0, 0.6, 0, 0.8])


class CommandLine(unittest.TestCase):
    def test_parsers(self):
        a = cli.build_parser().parse_args(["export-web", "u.json", "--out", "o", "--root", "r=1", "--no-refs"])
        self.assertEqual((a.cmd, a.asset, a.out, a.root, a.no_refs, a.clip_fps, a.ref_passes),
                         ("export-web", "u.json", "o", ["r=1"], True, 50.0, "lit,normals,depth"))
        a = cli.build_parser().parse_args(["serve-web", "b", "--port", "9000"])
        self.assertEqual((a.cmd, a.bundle, a.port, a.accept_results), ("serve-web", "b", 9000, None))

    def test_comparisons_default_to_matched_anisotropy(self):
        """CLI stills for the page's check render at anisotropy 1 unless asked otherwise (Chrome's D3D12 and the CLI's
        Vulkan filter anisotropically differently: up to 26/255 at 16, 1/255 matched); viewing keeps 16."""
        a = cli.build_parser().parse_args(["export-web", "u.json", "--out", "o"])
        self.assertEqual((a.ref_aniso, a.aniso), (1, 16))
        specs = export_web.default_refs()
        self.assertTrue(specs and all(s["aniso"] == 1 for s in specs))
        self.assertIn("aniso", export_web.REF_KEYS)
        argv = ["render", "u.json"] + [x for k, v in specs[0].items()
                                       for x in ("--" + ("pass" if k == "pass_name" else k.replace("_", "-")), str(v))]
        self.assertEqual(cli.build_parser().parse_args(argv).aniso, 1)
        js = (WEB / "viewer.js").read_text(encoding="utf-8")
        self.assertIn("aniso: a.aniso || G.matchAniso", js)          # refSpec samples at the still's anisotropy
        self.assertIn("G.matchAniso = sc.render.ref_aniso", js)
        self.assertIn("anisotropy 1 on both", (WEB / "index.html").read_text(encoding="utf-8"))

    def test_msaa_must_be_4(self):
        a = cli.build_parser().parse_args(["export-web", "u.json", "--out", "o", "--no-refs", "--msaa", "1"])
        with self.assertRaises(SystemExit):
            export_web.export_cmd(a, log=lambda *x: None)

    def test_mcp_tool_listed(self):
        try:
            from hdkit.view import mcp_server
        except ImportError as e:  # the mcp package lives in the venv
            self.skipTest(str(e))
        self.assertIn("view_export_web", mcp_server.TOOL_NAMES)


class PageIsLocal(unittest.TestCase):
    def test_no_network_urls(self):
        """The page loads its modules, shader and bundle from its own server only (no CDN, no analytics)."""
        url = re.compile(r"""(?:https?:)?//[a-z0-9.-]+\.[a-z]{2,}""", re.I)
        for p in sorted(WEB.iterdir()):
            text = p.read_text(encoding="utf-8")
            code = re.sub(r"(?m)^\s*//.*$", "", text)       # comment lines may cite sources
            self.assertEqual(url.findall(code), [], p.name)
        self.assertEqual(sorted(p.name for p in WEB.iterdir()), ["anim.js", "index.html", "map.html", "map.js", "present.wgsl", "rounds.html",
                                                                "viewer.js"])   # map.*: hdkit.view.mapview.webmap; rounds.html: /rounds


if __name__ == "__main__":
    unittest.main()

"""Stage 2: score generated shapes against the classic sprites: silhouette overlap (cam_fit IoU) in all 8 directions.

  venv python s2_score.py [--token T] <name>=<raw.npz>:<view>:<tilt>[:<keep>] [...] [--views <dir>] [--tris 39000]
                          [--elev 30] [--ky 1.0]      (fix the camera instead of taking the best of cam_fit's choices)

For each entry: s3_prep.py (generating view, tilt = stretch | pitch | none, pieces under `keep` of the faces dropped, default
0.02) into stages/2-shape/score/<name>/body.npz, then cam_fit.py (ring 4,0,5,1,6,2,7,3, front 4, sign +1, the elevation and
ky that fit best) into cams.json. Prints one table line per entry (mean, then d4 d0 d5 d1 d6 d2 d7 d3) and writes
stages/2-shape/score/scores.json (kept across calls).
"""
import json
import subprocess
import sys

import common

a = sys.argv[1:]
views = a[a.index("--views") + 1] if "--views" in a else str(common.STAGES / "1-frames" / "x4" / "nu00")
tris = a[a.index("--tris") + 1] if "--tris" in a else "39000"
fixed = [x for k in ("--elev", "--ky") if k in a for x in (k, a[a.index(k) + 1])]      # handed to cam_fit.py
OUT = common.STAGES / "2-shape" / "score"
OUT.mkdir(parents=True, exist_ok=True)
here = common.WT / "tools" / "sprite3d"
book = OUT / "scores.json"
scores = json.loads(book.read_text()) if book.is_file() else {}
for spec in [x for x in a if "=" in x]:
    name, rest = spec.split("=", 1)
    f = rest.split(":")
    nf = 2 if f[-1] in ("stretch", "pitch", "none") else 3
    path, view, tilt, keep = ":".join(f[:-nf]), f[-nf], f[1 - nf], (f[-1] if nf == 3 else "0.02")
    d = OUT / name
    d.mkdir(exist_ok=True)
    subprocess.run([sys.executable, str(here / "monster3d" / "s3_prep.py"), path, str(d / "body.npz"), "--tris", tris,
                    "--view", view, "--tilt", tilt, "--keep", keep], check=True, stdout=subprocess.DEVNULL)
    log = subprocess.run([sys.executable, str(here / "cam_fit.py"), str(d / "body.npz"), views, str(d / "cams.json"),
                          "--ring", "4,0,5,1,6,2,7,3", "--front", "4", "--gen", view, "--sign", "1"] + fixed,
                         check=True, capture_output=True, text=True).stdout
    (d / "cam_fit.log").write_text(log)
    c = json.loads((d / "cams.json").read_text())
    per = [c["cams"][str(v)]["iou"] for v in common.CLOCKWISE_8]
    scores = json.loads(book.read_text()) if book.is_file() else {}      # another s2_score.py may be running
    scores[name] = {"mean": sum(per) / 8, "per": per, "el": c["el"], "ky": c["ky"], "src": path, "view": int(view), "tilt": tilt}
    print("%-28s %.3f  %s  el %g ky %.3f" % (name, scores[name]["mean"], " ".join("%.2f" % v for v in per), c["el"], c["ky"]),
          flush=True)
    book.write_text(json.dumps(scores, indent=1))

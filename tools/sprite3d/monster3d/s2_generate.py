"""Stage 2: generate shapes for a monster from its 4x standing sprites (GPU; the gate is checked first, exit 3 = closed).

  venv python s2_generate.py [--token T] triposg <dir,dir,...> [--seeds 42,1] [--wait 60]
        one-view shapes from the views of those file directions -> stages/2-shape/raw/nu_d<N>_s<seed>.npz
  venv python s2_generate.py [--token T] parts <part_dN,part_dN,...> [--seeds 42] [--wait 60]
        one-view shapes of the pictures s2_parts.py wrote (body_d4, cap_d6, ...) -> stages/2-shape/raw/<name>_s<seed>.npz
  venv python s2_generate.py [--token T] hunyuan [--seeds 42,1] [--wait 60]
        COMPARISON ONLY (licence): front / left / back / right = directions 4 / 5 / 6 / 7 -> stages/2-shape/hunyuan/mv4567_s<seed>.npz
"""
import subprocess
import sys
import time

import common

a = sys.argv[1:]
opt = lambda n, d: a[a.index(n) + 1] if n in a else d  # noqa: E731
if not common.gpu_gate(int(opt("--wait", 60))):
    sys.exit(3)
ai = common.WT / "tools" / "sprite3d" / "ai"
x4 = common.STAGES / "1-frames" / "x4" / "nu00"
shape = common.STAGES / "2-shape"
t0 = time.time()
if a[0] == "hunyuan":
    cmd = [sys.executable, str(ai / "run_hunyuan.py"), "--src", str(common.HUNYUAN_SRC),
           "--weights", str(common.HUNYUAN_WEIGHTS), "--out", str(shape / "hunyuan"), "--name", "mv4567", "--seeds", opt("--seeds", "42,1")]
    for side, d in (("front", 4), ("left", 5), ("back", 6), ("right", 7)):
        cmd += ["--" + side, str(x4 / ("nu_d%d.png" % d))]
else:
    pics = [x4 / ("nu_d%s.png" % d) for d in a[1].split(",")] if a[0] == "triposg" else [shape / "parts" / "in" / (n + ".png") for n in a[1].split(",")]
    cmd = [sys.executable, str(ai / "run_triposg.py"), "--src", str(common.TRIPOSG_SRC),
           "--weights", str(common.TRIPOSG_WEIGHTS), "--out", str(shape / "raw"),
           "--seeds", opt("--seeds", "42,1" if a[0] == "triposg" else "42")] + [str(p) for p in pics]
rc = subprocess.run(cmd).returncode
print("%s: %.0f s, exit %d" % (a[0], time.time() - t0, rc), flush=True)
sys.exit(rc)

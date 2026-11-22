"""Lane hdtools-monster3d: read named files of D2R's own data from a test slot's CASC into monster3d/d2r (read-only on the
slot, under its lock, no game start).  python casc_get.py <slot 2|5> <rel path | @list file> ..."""
import subprocess
import sys
from pathlib import Path

import common

OUT = common.EV / "d2r"
LOCK = "hdtools-monster3d"
slot = int(sys.argv[1])
if slot not in (2, 5):
    raise SystemExit("slot %d is not a test slot of this lane" % slot)
rels = []
for a in sys.argv[2:]:
    rels += Path(a[1:]).read_text().split() if a.startswith("@") else [a]
sys.path.insert(0, str(common.WT / "tools"))
if subprocess.run([sys.executable, "tools/game_slots.py", "lock", str(slot), LOCK], cwd=common.WT).returncode != 0:
    raise SystemExit("slot %d is locked: nothing read" % slot)
try:
    import game_slots
    import native
    st = native.open_casc(game_slots.slot_dir(game_slots.require_slot(slot)))
    for rel in rels:
        dest = OUT / rel
        if dest.exists():
            continue
        try:
            data = native.casc_read(st, "data:" + rel)
        except Exception as e:  # noqa: BLE001
            print("MISSING %s (%s)" % (rel, e))
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        print("%9d %s" % (len(data), rel))
finally:
    subprocess.run([sys.executable, "tools/game_slots.py", "unlock", str(slot), LOCK], cwd=common.WT)

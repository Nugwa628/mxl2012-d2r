"""Bones and clips of a D2R unit extracted like data/hd/character/enemy/<unit>.

    py -I tools/sprite3d/donor_info.py <unit dir> [...]       (prints bone count, attachment bones, clip names + durations)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import d2r_model as dm  # noqa: E402

for arg in sys.argv[1:]:
    d = Path(arg)
    sk = next((d / "skeleton").glob("*.skeleton"))
    t = dm.parse_tree(dm.Gr2File.read(sk.read_bytes()))
    bones = [b["Name"] for b in t["Skeletons"][0]["Bones"]]
    att = [b for b in bones if "attach" in b.lower()]
    print(f"== {d.name}: {len(bones)} bones, attachment bones {att}")
    an = dm.parse_tree(dm.Gr2File.read((d / "animation" / "combined.animations").read_bytes()))
    clips = [(a["Name"], round(float(a["Duration"]), 2)) for a in an["Animations"]]
    print(f"   {len(clips)} clips: " + ", ".join(f"{n}={s}s" for n, s in clips))

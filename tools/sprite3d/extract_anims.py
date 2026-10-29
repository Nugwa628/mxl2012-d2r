"""Extract every enemy unit's combined.animations + skeleton from the game's CASC into <out dir> (donor survey).

    py tools/sprite3d/extract_anims.py <out dir> [--game <D2R dir>]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import native  # noqa: E402
import d2r_game  # noqa: E402

out = Path(sys.argv[1])
game = sys.argv[sys.argv.index("--game") + 1] if "--game" in sys.argv else d2r_game.read_game_dir()  # a slot 2 or 3 folder only
s = native.open_casc(game)
n = 0
try:
    for name, size, avail in native.casc_files(s):
        low = name.lower().replace("\\", "/")
        if avail and low.startswith("data:data/hd/character/enemy/") and low.endswith(("combined.animations", ".skeleton")):
            dest = out / low[len("data:"):]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(native.casc_read(s, name))
            n += 1
finally:
    native.casc.CascCloseStorage(s)
print(n, "files")

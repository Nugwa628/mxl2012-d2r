"""Development shortcut: copy hand-made model/texture files into an installed slot and point built units at them.

  py -3 tools/sprite3d/deploy_unit_model.py <slot 1..3> <asset dir> <new unit dir name> <Median Id> [<Median Id> ...]

<asset dir> holds `data/hd/character/enemy/<new unit dir name>/...` (torso_lod0..4.model, textures/*.texture). The engine only
loads model files at paths D2R already has (docs/hd-models.md), so <new unit dir name> must be a vanilla unit nobody uses
(wargoatman). The files are
copied into `<game>/mods/mxl2012/mxl2012.mpq/data`; for every Median Id the unit JSON `monsters.json` names is edited there:
`torso.model` of the donor unit dir becomes `<new unit dir name>/torso.model` (dependency and entity) and every texture file in
the asset dir is added to the dependencies. The skeleton, state machine and variant stay the donor's. Only the installed copy
changes (a reinstall puts the stand-in back); nothing under work/ is touched. The slot must be held (game_slots.py lock).
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import game_slots  # noqa: E402


def main():
    slot, assets, newdir, ids = int(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4:]
    data = Path(game_slots.mod_dir(slot)) / "mxl2012.mpq" / "data"
    base = assets / "data"
    for p in base.rglob("*"):
        if p.is_file():
            dst = data / p.relative_to(base)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dst)
    tex = [p.relative_to(assets).as_posix() for p in (base / "hd" / "character" / "enemy" / newdir).rglob("*.texture")]
    mj = json.loads((data / "hd" / "character" / "monsters.json").read_text("utf-8"))
    for mid in ids:
        unit = mj[mid]
        up = data / "hd" / "character" / "enemy" / (unit + ".json")
        txt = up.read_text("utf-8")
        d = json.loads(txt)
        old = next(m["path"] for m in d["dependencies"]["models"] if m["path"].endswith("/torso.model"))
        new = "data/hd/character/enemy/%s/torso.model" % newdir
        txt = txt.replace(old, new)
        d = json.loads(txt)
        have = {t["path"] for t in d["dependencies"]["textures"]}
        d["dependencies"]["textures"] += [{"path": t} for t in tex if t not in have]
        up.write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
        print(mid, unit, old, "->", new, "+", len(tex), "textures")


if __name__ == "__main__":
    main()

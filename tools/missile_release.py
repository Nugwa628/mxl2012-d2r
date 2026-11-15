"""HD missiles that another missile makes start where they are, not in the caster's hand (bug #569, docs/hd-effects.md section 13).

Some of D2R's missile models (arrow, x_bow_bolt, missile_dagger, fireball, the throwing weapons: 48 of 374) carry a
`TrackReleasePointDefinitionComponent`: the picture starts at the owner's release point (the hand or bow) and glides to the missile
in 0.5 s. That is right for a missile the unit throws. Median makes many of its projectiles from another missile instead: the
blade that stopped (Storm Crows), the minion (Widowmaker), the trap (Fireball Sentry), the spawner points of Barrage and Phalanx.
Their owner is still the player, so in HD the picture flew out of the player; legacy draws them where they are.

The step: a missile row that only another missile makes (a sub, hit sub or explosion missile; never a skill's missile column, a
monster's missile, or an item's missile type) and whose model tracks the release point gets a copy of that model without the
component, `<model>_free` (the rest of the definition unchanged). D2R's own rows keep D2R's model (vanilla's Blade Fury
fragments track too). Runs after tools/skill_looks.py, so every earlier choice of model stands.

Writes work/mod/data/hd/missiles/missiles.json and the `_free` copies; the report goes to stdout.
Usage: py -3 tools/missile_release.py [--work DIR] [--check]  (--check: audit only, exit 1 when such a row still tracks)
"""
import argparse
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import effects_hd as fx  # noqa: E402
import fxpaths  # noqa: E402

TRACK = "TrackReleasePointDefinitionComponent"
SUFFIX = "_free"
MADE_BY_MISSILE = fx.HIT_COLS + fx.SUB_COLS
MONSTER_MISSILE_COLS = ("MissA1", "MissA2", "MissS1", "MissS2", "MissS3", "MissS4", "MissC", "MissSQ")
ITEM_TABLES = ("weapons", "misc", "armor")


def tracks(d: dict | None) -> bool:
    return bool(d) and any(c.get("type") == TRACK for e in d.get("entities", []) for c in e.get("components", []))


def free_copy(d: dict, name: str) -> dict:
    """The definition under a new name without the release-point component (dependencies and every other component kept)."""
    d = copy.deepcopy(d)
    d["name"] = name
    for e in d.get("entities", []):
        e["components"] = [c for c in e.get("components", []) if c.get("type") != TRACK]
    return d


def thrown(skills: list[dict], monstats: list[dict], items: list[dict], missiles: list[dict]) -> set[str]:
    """Missile rows a unit launches itself: a skill's missile columns, a monster's missiles, an item's missile type (row id)."""
    out = {s.get(c, "").lower() for s in skills for c in fx.SKILL_MISSILE_COLS}
    out |= {m.get(c, "").lower() for m in monstats for c in MONSTER_MISSILE_COLS}
    by_id = {r.get("*ID") or str(i): r["Missile"].lower() for i, r in enumerate(missiles)}
    for it in items:
        mt = it.get("missiletype", "")
        if mt and mt != "0" and mt in by_id:
            out.add(by_id[mt])
    out.discard("")
    return out


def made_by_missile(missiles: list[dict]) -> set[str]:
    return {r.get(c, "").lower() for r in missiles for c in MADE_BY_MISSILE} - {""}


def decide(missiles: list[dict], launched: set[str], d2r_names: set[str], current: dict, get) -> list[tuple[str, str]]:
    """(row, model) for every row only another missile makes whose model tracks the release point. `get(model)` -> definition."""
    out, made = [], made_by_missile(missiles)
    for r in missiles:
        name = r["Missile"]
        low = name.lower()
        if low not in made or low in launched or low in d2r_names:
            continue
        model = current.get(fx.norm_key(name)) or current.get(low)
        if model and model.lower() != "null" and not model.endswith(SUFFIX) and tracks(get(model)):
            out.append((name, model))
    return out


def apply(decisions: list[tuple[str, str]], current: dict, out_dir: Path, get) -> tuple[dict, int]:
    final, written = dict(current), 0
    for name, model in decisions:
        free = model + SUFFIX
        if not (out_dir / f"{free}.json").exists():
            fx.write_json(out_dir / f"{free}.json", free_copy(get(model), free))
            written += 1
        final[fx.norm_key(name)] = free
        final[name.lower()] = free
    return final, written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--work", default=str(fxpaths.MOD))
    ap.add_argument("--check", action="store_true", help="audit only: exit 1 when a row only a missile makes still tracks the hand")
    args = ap.parse_args()
    work = Path(args.work)
    excel = Path(fxpaths.TABLES)
    mdir = work / "data" / "hd" / "missiles"
    current = fx.load_json(mdir / "missiles.json")
    memo: dict[str, dict | None] = {}

    def get(model: str):
        if model not in memo:
            p = next((d / f"{model}.json" for d in (mdir, fx.HDM) if (d / f"{model}.json").exists()), None)
            memo[model] = fx.load_json(p) if p else None
        return memo[model]

    _, missiles = fx.table(excel / "missiles.txt")
    _, skills = fx.table(excel / "skills.txt")
    _, monstats = fx.table(excel / "monstats.txt")
    items = [r for t in ITEM_TABLES if (excel / f"{t}.txt").exists() for r in fx.table(excel / f"{t}.txt")[1]]
    _, d2r_rows = fx.table(fxpaths.D2R_EXCEL / "missiles.txt")
    d2r_names = {r["Missile"].lower() for r in d2r_rows}
    decisions = decide(missiles, thrown(skills, monstats, items, missiles), d2r_names, current, get)
    if args.check:
        print(f"{len(decisions)} rows that only a missile makes still start in the caster's hand in HD")
        print("\n".join(f"{n}: {m}" for n, m in decisions[:60]))
        return 1 if decisions else 0
    final, written = apply(decisions, current, mdir, get)
    fx.write_json(mdir / "missiles.json", final)
    print(f"missile_release: {len(decisions)} rows made by another missile no longer start in the caster's hand "
          f"({written} models written): " + ", ".join(sorted(n for n, _ in decisions)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

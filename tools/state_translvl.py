#!/usr/bin/env python
"""Monprop state colours drawn through a free monster level (bugs.md #529, docs/hd-monsters.md section 19).

A state a monster's monprop keeps on recolours it in classic when its states.txt colorshift is not 0: 1.14d's colour pick
(STATES_UpdateColorShiftAndLight, Game.exe 0x4d97f0) takes the active state of the highest colorpri, whatever its colorshift,
and the unit is then drawn through Pal.pl2 colour table colorshift (row 1328 + colorshift) INSTEAD of its level's palshift.dat
table (GFX_DrawUnitComponents 0x470ec0: the state table, else PALSHIFT_GetMonsterTransform). D2R's HD renderer has no colour
for most of those indices (it draws the stand-in's plain model and ignores the unit's level entry), and no index colours the
unit right in both modes (section 19). So the colour moves to a monster level:

  - each monprop row whose winning state (highest colorpri, a tie to the lower id) has such a colorshift gets a copy of that
    state without colorshift (`<state>_lvl`, every other cell the same, colorpri too, so the copy wins and loses against the
    same states); the original row stays for everything else that gives the state (skills, items, other monsters);
  - a state D2R's code tests by its id (ID_KEYED: `preventheal`, the regen block) stays on the monster, and the monprop also
    gives two cover states with nothing but a colour: `<state>_lvl` (no colorshift, colorpri + 2) and `<state>_hd`
    (colorshift HD_COVER_SHIFT, colorpri + 1). Legacy takes the highest colorpri whatever its colorshift, so it draws
    `_lvl`: the level. HD skips the states without colorshift (seen in game, lane cogs529: with only the `_lvl` cover a Cog
    stays red in HD), so it draws `_hd`: the variant table's custom entry of that index, the same colour as the level entry;
  - the monsters of those rows move to a TransLvl (1..5) no other enabled monster of the same classic token or of the same HD
    variant table uses; per (token, colorshift) one level;
  - classic: the token's palshift.dat (D2R's, else identity tables) gets the state's Pal.pl2 table as the table of that level
    (the same pixels as the state drew; the act palettes differ in indices 225-254 only, `pl2_table` picks the target with
    the least error over the five acts);
  - HD: the level's entry of the unit's variant table is the level-0 entry with the measured state colour on top
    (tools/data/hd_state_colours.json, `hd_translvl.py states`), which HD draws for a monster of that level.

tools/hd_translvl.py build runs it (after hd_monsters.py build: the HD unit of each Id): `plan` + `apply_tables` before its
own level plan, `write_palshifts` and `write_entries` after its variant tables. Running it again on edited tables gives the same
plan (a copy counts as its original, the moved Ids do not hold their level).
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from txt_migrate import read_tsv, write_tsv, is_record  # noqa: E402

SUFFIX = "_lvl"
HD_SUFFIX = "_hd"
# the colorshift of an ID_KEYED state's HD cover: HD draws a variant table's customColorShiftEntries entry of this index (from
# 129 up; D2R uses 130 itself), legacy never draws it (the `_lvl` cover has the higher colorpri)
HD_COVER_SHIFT = 131
BANKS = ("", "base")
LEVELS = (5, 4, 3, 2, 1)   # TransLvl with a palshift.dat table (t + 2) and an HD entry (t + 2; 5 = `misc`); the highest first
LEVEL0 = 2
# vanilla states D2R.exe 93847 tests by immediate id (lane states' scan, mxl2012-runs/states/scratch/statescan.out; docs/
# id-mapping.md) among those a monprop colours with: a copy under a new id would lose the effect
ID_KEYED = {52: "preventheal: D2R tests state 52 at 0x448c61 and 0x4a35d2 (1.14d RegenAndPsnDecreaser 0x5a6952: no life "
                "regeneration while it is on)"}
# states.txt colorshifts D2R's HD renderer colours itself (hd_translvl.HD_STATE_SHIFTS)
HD_STATE_SHIFTS = {73, 100, 103, 104, 106, 107, 108, 130}
PL2_PALETTE = 1024
PL2_FIRST_ROW = 1328       # Pal.pl2 row of colorshift N: 1328 + N (seen in game: Cog's 101 draws row 1429)


# ------------------------------------------------------------------ tables
def bank_paths(excel: Path, name: str) -> list[Path]:
    return [p for p in ((excel / b / name) if b else (excel / name) for b in BANKS) if p.exists()]


def rows_of(path: Path) -> list[dict]:
    h, rows = read_tsv(path)
    return [dict(zip(h, r)) for r in rows if is_record(r)]


def base_name(name: str) -> str:
    """The state a `_lvl` copy or a `_hd` cover was made for (else the name itself)."""
    for suf in (SUFFIX, HD_SUFFIX):
        if name.lower().endswith(suf):
            return name[:-len(suf)]
    return name


class States:
    """states.txt of one bank: id = record index; `orig(i)` = the row a `_lvl` copy or `_hd` cover was made from (else i)."""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.by_name = {r["state"].lower(): i for i, r in enumerate(rows) if r.get("state")}

    def id_of(self, par: str) -> int | None:
        par = (par or "").strip()
        if par.isdigit():
            return int(par) if int(par) < len(self.rows) else None
        return self.by_name.get(par.lower())

    def orig(self, i: int) -> int:
        return self.by_name.get(base_name(self.rows[i]["state"]).lower(), i)

    def cs(self, i: int) -> int:
        return int(self.rows[i].get("colorshift") or 0)

    def pri(self, i: int) -> int:
        return int(self.rows[i].get("colorpri") or 0)


def blocks(header) -> dict[str, list[tuple[str, str, str]]]:
    """monprop's (prop, par, chance) columns per difficulty block ('', ' (N)', ' (H)')."""
    out: dict[str, list] = defaultdict(list)
    for c in header:
        if c.startswith("prop"):
            k = c[4:]
            n, _, d = k.partition(" ")
            out[(" " + d) if d else ""].append((c, f"par{k}", f"chance{k}"))
    return out


def given_states(r: dict, st: States) -> tuple[dict[str, set[int]], bool]:
    """Per difficulty block the original ids of the states the row gives; True when a `state` prop has a chance below 100."""
    out, chance = {}, False
    for d, cols in blocks(list(r)).items():
        ids = set()
        for p, par, ch in cols:
            if r.get(p) == "state":
                i = st.id_of(r.get(par, ""))
                if i is not None:
                    ids.add(st.orig(i))
                if (r.get(ch) or "").strip() not in ("", "0", "100"):
                    chance = True
        out[d] = ids
    return out, chance


def winner(ids: set[int], st: States) -> int | None:
    """The state 1.14d draws the colour of: the highest colorpri, a tie to the lower id (STATES_UpdateColorShiftAndLight)."""
    best, bp = None, 0
    for i in sorted(ids):
        if st.pri(i) > bp:
            best, bp = i, st.pri(i)
    return best


# ------------------------------------------------------------------ plan
def plan(excel: Path, mj: dict, table_of) -> dict:
    """{'groups': [...], 'skipped': [...]} from the bank-'' tables (both banks are edited the same way). A group is one
    (classic token, colorshift): its state, its monprop rows, its Ids, the HD tables they draw and the level picked."""
    st = States(rows_of(excel / "states.txt"))
    props, skipped = {}, []
    for r in rows_of(excel / "monprop.txt"):
        per, chance = given_states(r, st)
        allids = set().union(*per.values()) if per else set()
        w = winner(allids, st)
        if w is None or not st.cs(w) or st.cs(w) in HD_STATE_SHIFTS:
            continue
        if len({frozenset(v) for v in per.values()}) > 1 or chance:
            skipped.append({"monprop": r["Id"], "state": st.rows[w]["state"],
                            "why": "the state chance is below 100" if chance else "the difficulties give other states"})
            continue
        props[r["Id"]] = w
    groups: dict[tuple[str, int], dict] = {}
    rows = [r for p in bank_paths(excel, "monstats.txt") for r in rows_of(p)]
    tables: dict[str, str | None] = {}

    def tab(u):
        if u not in tables:
            tables[u] = table_of(u) if u else None
        return tables[u]
    moving = set()
    for r in rows:
        w = props.get(r.get("MonProp", ""))
        if w is None or not r.get("Code"):
            continue
        tok = r["Code"].lower()
        g = groups.setdefault((tok, st.cs(w)), {"token": tok, "code": r["Code"], "colorshift": st.cs(w),
                                                "state": st.rows[w]["state"], "state_id": w, "ids": [], "monprops": [],
                                                "tables": defaultdict(list), "enabled_ids": 0})
        if r["Id"] not in g["ids"]:
            g["ids"].append(r["Id"])
            g["enabled_ids"] += r.get("enabled", "1") == "1"
            t = tab(mj.get(r["Id"], ""))
            if t:
                g["tables"][t].append(r["Id"])
        if r["MonProp"] not in g["monprops"]:
            g["monprops"].append(r["MonProp"])
        moving.add(r["Id"])
    tok_used: dict[str, set[int]] = defaultdict(set)
    tab_used: dict[str, set[int]] = defaultdict(set)
    for r in rows:
        if r["Id"] in moving or not r.get("Code") or r.get("enabled", "1") != "1":
            continue
        tl = int(r.get("TransLvl") or 0)
        tok_used[r["Code"].lower()].add(tl)
        t = tab(mj.get(r["Id"], ""))
        if t:
            tab_used[t].add(tl)
    allocate(list(groups.values()), tok_used, tab_used)
    return {"groups": sorted(groups.values(), key=lambda g: (g["token"], g["colorshift"])), "skipped": skipped,
            "id_keyed": {st.rows[i]["state"]: why for i, why in ID_KEYED.items() if i < len(st.rows)}}


def allocate(groups: list[dict], tok_used: dict[str, set[int]], tab_used: dict[str, set[int]]) -> None:
    """Sets g['level'] (None + g['why'] when no level is free). A level is free for a group when no other enabled monster of
    its token or of one of its HD tables has it and no other group of the token took it; two groups may share a level of an
    HD table only with the same colorshift (the one with more Ids gives the entry). Groups with fewer free levels go first."""
    tok_taken: dict[str, set[int]] = defaultdict(set)
    tab_taken: dict[str, dict[int, int]] = defaultdict(dict)

    def options(g, share):
        out = []
        for lv in LEVELS:
            if lv in tok_used[g["token"]] or lv in tok_taken[g["token"]]:
                continue
            ok = True
            for t in g["tables"]:
                if lv in tab_used[t]:
                    ok = False
                elif lv in tab_taken[t] and (not share or tab_taken[t][lv] != g["colorshift"]):
                    ok = False
            if ok:
                out.append(lv)
        return out
    for g in sorted(groups, key=lambda g: (len(options(g, True)), -len(g["ids"]), g["token"], g["colorshift"])):
        lv = (options(g, False) or options(g, True) or [None])[0]
        g["level"] = lv
        if lv is None:
            g["why"] = "no free level (token levels " + str(sorted(tok_used[g["token"]] | tok_taken[g["token"]])) + ")"
            continue
        tok_taken[g["token"]].add(lv)
        for t in g["tables"]:
            tab_taken[t][lv] = g["colorshift"]


# ------------------------------------------------------------------ table edits
def copy_row(orig: dict, kind: str) -> dict:
    """The new row for state `orig`: `copy` = `_lvl`, the original without colorshift; `cover` = `_lvl`, only its name and
    colorpri + 2; `hd` = `_hd`, only its name, colorshift HD_COVER_SHIFT and colorpri + 1."""
    pri = int(orig.get("colorpri") or 0)
    if kind == "copy":
        out = dict(orig)
        out["colorshift"] = "0"
    else:
        out = {k: "" for k in orig}
        out["colorpri"] = str(pri + (2 if kind == "cover" else 1))
        if kind == "hd":
            out["colorshift"] = str(HD_COVER_SHIFT)
    out["state"] = orig["state"] + (HD_SUFFIX if kind == "hd" else SUFFIX)
    if "*eol" in out:
        out["*eol"] = orig.get("*eol", "0") or "0"
    return out


def apply_tables(excel: Path, p: dict) -> list[str]:
    """Edits states / monprop / monstats of both banks for the groups with a level; returns report lines. Running it again
    changes nothing."""
    lines = []
    todo = [g for g in p["groups"] if g.get("level") is not None]
    levels = {i: g["level"] for g in todo for i in g["ids"]}
    states = {g["state_id"] for g in todo}
    mprops = {m: g["state_id"] for g in todo for m in g["monprops"]}
    for sp in bank_paths(excel, "states.txt"):
        bank = sp.parent
        h, srows = read_tsv(sp)
        recs = [r for r in srows if is_record(r)]
        st = States([dict(zip(h, r)) for r in recs])
        new_id = {}
        for i in sorted(states):
            name = st.rows[i]["state"]
            ids = []
            for kind in (("cover", "hd") if i in ID_KEYED else ("copy",)):
                suf = HD_SUFFIX if kind == "hd" else SUFFIX
                cid = st.by_name.get((name + suf).lower())
                if cid is None:
                    cid = len(st.rows)
                    row = copy_row(st.rows[i], kind)
                    if "*ID" in row:
                        row["*ID"] = str(cid)
                    srows.append([row.get(c, "") for c in h])
                    st = States(st.rows + [row])
                    note = "" if kind == "copy" else f" {'HD ' if kind == 'hd' else ''}cover, colorpri {row['colorpri']}" + (
                        f", colorshift {HD_COVER_SHIFT}" if kind == "hd" else "")
                    lines.append(f"| {bank.name if bank != excel else 'rotw'} | states | {name} ({i}) -> {name}{suf} ({cid})"
                                 f"{note} |")
                ids.append(cid)
            new_id[i] = ids
        write_tsv(sp, h, srows)
        mp = bank / "monprop.txt"
        if mp.exists():
            lines += _monprop(mp, st, mprops, new_id)
        ms = bank / "monstats.txt"
        if ms.exists():
            mh, mrows = read_tsv(ms)
            ci, ti = mh.index("Id"), mh.index("TransLvl")
            n = 0
            for r in mrows:
                if is_record(r) and r[ci] in levels and r[ti] != str(levels[r[ci]]):
                    r[ti] = str(levels[r[ci]])
                    n += 1
            write_tsv(ms, mh, mrows)
            lines.append(f"| {bank.name if bank != excel else 'rotw'} | monstats | TransLvl of {n} Ids |")
    return lines


def _monprop(path: Path, st: States, mprops: dict[str, int], new_id: dict[int, int]) -> list[str]:
    h, rows = read_tsv(path)
    ix = {c: i for i, c in enumerate(h)}
    bl = blocks(h)
    out = []
    for r in rows:
        if not is_record(r) or r[0] not in mprops:
            continue
        w = mprops[r[0]]
        for d, cols in bl.items():
            have = [(p, par) for p, par, _ in cols if r[ix[p]] == "state" and st.id_of(r[ix[par]]) is not None]
            if w in ID_KEYED:
                for cid in new_id[w]:
                    if any(st.id_of(r[ix[par]]) == cid for _, par in have):
                        continue
                    free = next(((p, par, ch) for p, par, ch in cols if not r[ix[p]].strip()), None)
                    if free is None:
                        out.append(f"| {r[0]} | no free prop column for the cover state {st.rows[cid]['state']}{d} |")
                        continue
                    p, par, _ = free
                    r[ix[p]], r[ix[par]] = "state", str(cid)
                    for k in ("min", "max"):
                        c = k + p[4:]
                        if c in ix:
                            r[ix[c]] = "1"
            else:
                for _, par in have:
                    if st.orig(st.id_of(r[ix[par]])) == w:
                        r[ix[par]] = str(new_id[w][0])
    write_tsv(path, h, rows)
    return out


# ------------------------------------------------------------------ classic: palshift.dat
def pl2_table(pl2s: list[bytes], cs: int) -> tuple[bytes, int]:
    """One 256-byte table for colorshift cs that draws, in every act palette, the colour closest to that act's own table
    (Pal.pl2 row 1328 + cs); returns it and the largest squared RGB error left (0 where the acts agree)."""
    def row(b):
        o = PL2_PALETTE + (PL2_FIRST_ROW + cs) * 256
        return b[o:o + 256]
    pals = [[tuple(b[i * 4:i * 4 + 3]) for i in range(256)] for b in pl2s]
    rows = [row(b) for b in pl2s]
    out, worst = bytearray(256), 0
    for i in range(256):
        want = [pals[k][rows[k][i]] for k in range(len(pl2s))]
        if len({r[i] for r in rows}) == 1:
            out[i] = rows[0][i]
            continue
        best = min(range(256), key=lambda j: (sum(sum((a - b) ** 2 for a, b in zip(pals[k][j], want[k]))
                                                  for k in range(len(pl2s))), j != rows[0][i], j))
        out[i] = best
        worst = max(worst, max(sum((a - b) ** 2 for a, b in zip(pals[k][best], want[k])) for k in range(len(pl2s))))
    return bytes(out), worst


def write_palshifts(p: dict, data: Path, d2r: Path, pl2s: list[bytes]) -> list[str]:
    """data/global/monsters/<token>/cof/palshift.dat per token with a group: D2R's file (else identity tables) with the
    state's table at the group's level. The files of an earlier run are deleted first (only this step writes them)."""
    mon = data / "global" / "monsters"
    for f in (mon.glob("*/cof/palshift.dat") if mon.is_dir() else ()):
        f.unlink()
    by_tok: dict[str, list[dict]] = defaultdict(list)
    for g in p["groups"]:
        if g.get("level") is not None:
            by_tok[g["token"]].append(g)
    lines = []
    for tok, gs in sorted(by_tok.items()):
        src = d2r / "data" / "global" / "monsters" / tok / "cof" / "palshift.dat"
        b = bytearray(src.read_bytes()[:2048]) if src.exists() else bytearray(bytes(range(256)) * 8)
        if len(b) < 2048:
            b = bytearray(bytes(range(256)) * 8)
        for g in gs:
            t, worst = pl2_table(pl2s, g["colorshift"])
            b[(g["level"] + LEVEL0) * 256:(g["level"] + LEVEL0 + 1) * 256] = t
            g["pl2_error"] = worst
        dirs = [d for d in (mon.iterdir() if mon.is_dir() else ()) if d.is_dir() and d.name.lower() == tok]
        dest = (dirs[0] if dirs else mon / gs[0]["code"]) / "cof" / "palshift.dat"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(bytes(b))
        lines.append(f"| `{tok}` | {'D2R' if src.exists() else 'identity'} | "
                     + ", ".join(f"level {g['level']} = colorshift {g['colorshift']}" for g in gs) + " |")
    return lines


# ------------------------------------------------------------------ HD: variant table entries
def write_entries(p: dict, colours: list[dict], data: Path, d2r: Path, fill_entry, dump, hand: dict | None = None) -> list[dict]:
    """The level entry of every HD table a group draws: the level-0 entry with the group's measured colour on top (hand:
    {(token, colorshift): (adj, tint)} overrides). On a table two groups share at one level, the one with more Ids gives
    it. A group of an ID_KEYED state also gets that entry as the table's custom entry of HD_COVER_SHIFT (its `_hd` cover).
    Returns one row per (table, level) for the report."""
    meas = {(c["token"], c["colorshift"]): c for c in colours}
    want: dict[tuple[str, int], dict] = {}
    for g in p["groups"]:
        if g.get("level") is None:
            continue
        for t, ids in g["tables"].items():
            old = want.get((t, g["level"]))
            if old is None or len(ids) > len(old["ids"]):
                want[(t, g["level"])] = {"group": g, "ids": ids}
    rows = []
    for (t, lv), w in sorted(want.items()):
        g = w["group"]
        m = meas.get((g["token"], g["colorshift"]), {})
        adj, tint = (hand or {}).get((g["token"], g["colorshift"]), (m.get("adj"), m.get("tint")))
        label = "hand" if (hand or {}).get((g["token"], g["colorshift"])) else m.get("label", "not measured")
        if adj is None or label in ("none", "no art", "not measured"):
            adj, tint = [0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0, 0.0]   # the level-0 look: never another level's colour
        src = data / t if (data / t).is_file() else d2r / "data" / t
        v = json.loads(src.read_text("utf-8-sig"))
        if len(v.get("entries", [])) <= lv + LEVEL0:
            rows.append({"table": t, "level": lv, "token": g["token"], "colorshift": g["colorshift"], "ids": w["ids"],
                         "shift": label, "state": "table layout"})
            continue
        v["entries"][lv + LEVEL0] = fill_entry(v["entries"][lv + LEVEL0], v["entries"][LEVEL0], adj, tint)
        if g["state_id"] in ID_KEYED:
            set_custom_entry(v, HD_COVER_SHIFT, v["entries"][lv + LEVEL0])
        (data / t).parent.mkdir(parents=True, exist_ok=True)
        (data / t).write_bytes(dump(v))
        rows.append({"table": t, "level": lv, "token": g["token"], "colorshift": g["colorshift"], "ids": w["ids"],
                     "shift": label, "state": "written"})
    return rows


def set_custom_entry(v: dict, cs: int, entry: dict) -> None:
    """Puts a copy of `entry` into variant table v as its customColorShiftEntries entry of colorshift cs (named `S<cs>`,
    the name hd_translvl.drop_custom_state_entries clears on the stand-in tables), replacing one of that index."""
    e = json.loads(json.dumps(entry))
    e["name"] = f"S{cs}"
    for j, t in enumerate(e.get("transforms", [])):
        t["name"] = f"S{cs}{'RGB'[j] if j < 3 else j}"
    keep = [c for c in v.get("customColorShiftEntries", []) if c.get("colorShiftIndex") != cs]
    v["customColorShiftEntries"] = keep + [{"type": "CustomVariantColorShiftMap", "name": f"S{cs}", "colorShiftIndex": cs,
                                            "entry": e}]


def report(p: dict, table_lines: list[str], pal_lines: list[str], entry_rows: list[dict]) -> str:
    lines = ["", "## State colours through a free level (`tools/state_translvl.py`, bugs.md #529)", "",
             "Monprop rows whose winning state has a colorshift D2R's HD renderer has no colour for. Their monsters get a "
             f"`{SUFFIX}` copy of the state without colorshift and a free TransLvl; the token's palshift.dat draws the state's "
             "Pal.pl2 table at that level (classic), the unit's variant table the measured colour (HD). States D2R tests by id "
             f"stay on and get two cover states: `{SUFFIX}` (no colorshift, colorpri + 2: legacy draws the level) and "
             f"`{HD_SUFFIX}` (colorshift {HD_COVER_SHIFT}, colorpri + 1: HD skips colorshift 0 and draws the table's custom "
             "entry of that index, the level's colour): " +
             "; ".join(f"`{k}` ({v})" for k, v in p["id_keyed"].items()) + ".", "",
             "| Token | Colorshift | State | Level | Monprops | Ids | HD tables |", "|-|-|-|-|-|-|-|"]
    for g in p["groups"]:
        lines.append(f"| `{g['token']}` | {g['colorshift']} | {g['state']} | {g.get('level') or g.get('why')} | "
                     f"{', '.join(g['monprops'])} | {', '.join(g['ids'])} | {', '.join(sorted(g['tables']))} |")
    if p["skipped"]:
        lines += ["", "Skipped: " + "; ".join(f"{s['monprop']} ({s['state']}: {s['why']})" for s in p["skipped"])]
    lines += ["", "| Bank | Table | Edit |", "|-|-|-|", *table_lines, "", "| Token | palshift.dat base | Tables |", "|-|-|-|",
              *pal_lines, "", "| HD table | Level | Token | Colorshift | Shift | State | Ids |", "|-|-|-|-|-|-|-|"]
    lines += [f"| {r['table']} | {r['level']} | `{r['token']}` | {r['colorshift']} | {r['shift']} | {r['state']} | "
              f"{', '.join(r['ids'])} |" for r in entry_rows]
    return "\n".join(lines) + "\n"

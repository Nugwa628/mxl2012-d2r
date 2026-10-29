"""HD body animations for Median's sequence skills (Phase 5).

D2R's HD player models pick a skill's sequence animation in data/hd/character/player/<class>/<class>_state_machine.json:
an AnimationState with modeId 18 (SQ, the sequence mode) and skillIndex = the skill's ID, e.g. the Barbarian's
"PMODE_SEQUENCE_WHIRLWIND" (skillIndex 151, *_whirlwind clips). Median's skills have their own IDs (whirlwind_2 is
1306), so without a state of their own the HD model shows no sequence animation (no spin while whirlwinding).

For every class, each Median skill that uses the sequence mode (anim SQ) with the same sequence (seqnum, not empty)
as a D2R skill that has such a state gets a copy of that state with its own skillIndex. Only skills a player can have
(charclass of that class, or no class but a skilldesc: item skills such as windform) are added. Transitions: the new
state copies the source state's transition group, and every group gets an entry to the new state copied from its
entry to the source state.

Input:  D2R's state machines (the baseline extraction, else CASC of MXL_SLOT 2|3 cached in the shared d2r-cache, tools/lane_setup.py), D2R's skills.txt, work/mod/data/global/excel/skills.txt
Output: work/mod/data/hd/character/player/<class>/<class>_state_machine.json, work/mod/hd_skill_anims_report.md
Usage: python tools/hd_skill_anims.py
"""
import copy
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fxpaths  # noqa: E402

ROOT = fxpaths.ROOT
D2R_SKILLS = fxpaths.D2R_EXCEL / "skills.txt"
MOD_SKILLS = ROOT / "work" / "mod" / "data" / "global" / "excel" / "skills.txt"
OUT = ROOT / "work" / "mod" / "data" / "hd" / "character" / "player"
REPORT = ROOT / "work" / "mod" / "hd_skill_anims_report.md"
CLASSES = {"amazon": "ama", "sorceress": "sor", "necromancer": "nec", "paladin": "pal", "barbarian": "bar",
           "druid": "dru", "assassin": "ass"}
SEQUENCE_MODE = 18


def read_tsv(path: Path) -> tuple[list[str], list[list[str]]]:
    rows = list(csv.reader(open(path, encoding="latin-1", newline=""), delimiter="\t"))
    return rows[0], [r for r in rows[1:] if r and r[0] and r[0] != "Expansion"]


def add_state(sm: dict, source_id: int, skill_id: int, skill_name: str) -> int:
    """Copies state source_id for skill_id, with transitions to and from it; returns the new stateId."""
    new_id = max(s["stateId"] for s in sm["states"]) + 1
    src = next(s for s in sm["states"] if s["stateId"] == source_id)
    state = copy.deepcopy(src)
    state.update(stateId=new_id, skillIndex=skill_id, name=f"{src['name']}_MXL_{skill_name}",
                 _name=f"MXL_{skill_name}")
    sm["states"].append(state)
    for group in sm["transitions"]:
        to_src = next(t for t in group["settings"] if t["to"] == source_id)
        item = copy.deepcopy(to_src)
        item.update(to=new_id, name=f"{to_src['name']}_MXL_{skill_name}")
        group["settings"].append(item)
    src_group = next(g for g in sm["transitions"] if g["from"] == source_id)
    group = copy.deepcopy(src_group)
    group.update({"from": new_id, "name": f"{src_group['name']}_MXL_{skill_name}"})
    self_item = next(t for t in group["settings"] if t["to"] == new_id)  # source -> new: becomes new -> new
    self_item["name"] = f"transition_self_MXL_{skill_name}"
    sm["transitions"].append(group)
    return new_id


def main() -> int:
    dh, drows = read_tsv(D2R_SKILLS)
    mh, mrows = read_tsv(MOD_SKILLS)
    d2r_by_id = {int(r[dh.index("*Id")]): r for r in drows if r[dh.index("*Id")].isdigit()}
    mi = {c: mh.index(c) for c in ("*Id", "charclass", "anim", "seqnum", "skilldesc")}
    report = ["# HD sequence animations for Median skills", "",
              "| Class | Median skill (ID) | Uses the HD state of | seqnum |", "|---|---|---|---|"]
    total = 0
    for cls, code in CLASSES.items():
        path = f"data/hd/character/player/{cls}/{cls}_state_machine.json"
        sm = json.loads(fxpaths.d2r_file(path).read_text("utf-8-sig"))
        by_seq: dict[str, tuple[int, str]] = {}  # seqnum -> (source stateId, D2R skill)
        for s in sm["states"]:
            k = s.get("skillIndex", -1)
            if s.get("modeId") == SEQUENCE_MODE and k in d2r_by_id:
                seq = d2r_by_id[k][dh.index("seqnum")]
                if seq and seq not in by_seq:
                    by_seq[seq] = (s["stateId"], d2r_by_id[k][0])
        added = 0
        for r in mrows:
            sid = int(r[mi["*Id"]])
            if r[mi["anim"]] != "SQ" or sid in d2r_by_id or r[mi["seqnum"]] not in by_seq:
                continue
            if not (r[mi["charclass"]] == code or (not r[mi["charclass"]] and r[mi["skilldesc"]])):
                continue
            source, d2r_skill = by_seq[r[mi["seqnum"]]]
            add_state(sm, source, sid, r[0])
            report.append(f"| {cls} | {r[0]} ({sid}) | {d2r_skill} | {r[mi['seqnum']]} |")
            added += 1
        if added:
            dest = OUT / cls / f"{cls}_state_machine.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(sm, indent=1), encoding="utf-8")
        total += added
        print(f"   {cls}: {added} Median sequence skills given an HD state")
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Median XL 2012's own sounds in D2R: the audio of the sounds.txt rows that play a file only Median's MPQ has.

v005 adds 108 sounds.txt rows whose audio is Median's (data/global/sfx/taunt/*.wav: boss taunts, skill / state / missile /
item sounds such as `shrine_boink`). txt_migrate.py's `sound_rows` appends them after D2R's rows (sounds is d2r_wins: D2R's
own rows stay D2R's) with a .flac FileName; until this step they had no file and no Channel, so D2R played nothing.

  audio     every such row whose Median file exists (1.13c 16-bit PCM .wav, mono, 11-44 kHz) -> a lossless .flac of the same
            samples and rate at work/mod/data/global/sfx/<path>.flac (D2R reads its legacy sounds from data/global/sfx as
            .flac, FMOD; the folder-style mod MPQ is read first). One file per Median file (rows sharing a file share it).
            tools/flac.py encodes (no audio package needed) and every written file is decoded again and compared.
  Channel   blank on these rows (D2R has no taunt folder to copy one from): the D2R channel of what plays the sound, from
            the built tables' sound columns: a boss line (monsounds.Taunt, or a `*_speech` row a boss's missile says) ->
            D2R's boss-speech channel vo/eax/boss-dialog_sd (as D2R's own monster_*_taunt rows; IsLocal stays 0: the file
            is global), other monsounds -> sfx/monster_sd, items only (misc / uniqueitems / weapons / armor) ->
            sfx/items_sd, else (skills, missiles, states) sfx/player-skills_sd. A row only reached as a member of a group
            (Group Size of an earlier row) takes the head's.
  typos     TYPO_FIXES: a Median name with a typo whose real file exists (maenad1 `taunt\\ecstaticfrenzy1,.wav`) plays it.
  missing   rows whose file Median never shipped: left as they are, silent as in 1.13c; listed.
  replaced  Median's MPQ also replaces 12 vanilla files (cursor/intro/<class> select.wav, item/gem.wav,
            monster/werebear/bite1-4.wav). Owner exception (2026-10-31, audio only): Median's audio plays for those, the
            rows stay D2R's. The .flac goes to D2R's own SD path (data/global/sfx/<D2R name>.flac; D2R wrote the class
            selects with `_` for the space) and, through the row's Redirect, to its HD row's file
            (data/hd/global/sfx/<HD name>.flac): HD mode plays the HD row, so both modes play Median's. A group head's
            Redirect maps member k to HD member k. An HD file a row outside these also plays stays D2R's (reported).

No Redirect on Median's own rows: a D2R row without one plays its own file in HD mode too (1802 of D2R's own rows are like
that), so one file serves both graphics modes. Median's files never go into git: the input is fxpaths.MXL (assets/median or
extract-mpq), the output is work/mod (git-ignored).

  py -3 -I tools/sounds_port.py [build]   convert + rows -> work/mod/data/global/sfx (+ data/hd/global/sfx for the
                                          replaced files), both sounds.txt banks, work/mod/sounds_port.md
  py -3 -I tools/sounds_port.py plan      the report only, nothing written
Options: --median DIR (a folder holding data/global), --d2r DIR (D2R 93847 extraction), --mod DIR (default work/mod/data).
"""
import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fxpaths  # noqa: E402
import flac  # noqa: E402

SOUND_TABLES = ("skills", "missiles", "states", "monsounds", "misc", "weapons", "armor", "uniqueitems", "setitems", "objects",
                "overlay", "monstats2")
ITEM_TABLES = {"misc", "weapons", "armor", "uniqueitems", "setitems"}
CHANNEL_MONSTER, CHANNEL_ITEMS, CHANNEL_SKILLS = "sfx/monster_sd", "sfx/items_sd", "sfx/player-skills_sd"
CHANNEL_BOSS = "vo/eax/boss-dialog_sd"  # D2R's monster_*_taunt rows (their _hd rows: vo/eax/boss-dialog_hd)
OUR_CHANNELS = {CHANNEL_MONSTER, CHANNEL_ITEMS, CHANNEL_SKILLS, CHANNEL_BOSS}  # set by this step: a rerun may change them
TYPO_FIXES = {"taunt/ecstaticfrenzy1,": "taunt/ecstaticfrenzy1"}  # maenad1: the sounds.txt name has a stray comma


def read_tsv(path: Path) -> tuple[list[str], list[list[str]]]:
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    return (rows[0], rows[1:]) if rows else ([], [])


def write_tsv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        f.writelines("\t".join(r) + "\r\n" for r in [header, *rows])


def stem(name: str) -> str:
    """sounds.txt FileName -> lower-case path without extension, `/` separated (taunt\\Holy_Boink.wav -> taunt/holy_boink)."""
    n = name.strip().lower().replace("\\", "/")
    return n.rsplit(".", 1)[0] if "." in n.rsplit("/", 1)[-1] else n


def median_audio(sfx: Path) -> dict[str, Path]:
    """stem -> Median's .wav under data/global/sfx."""
    return {stem(p.relative_to(sfx).as_posix()): p for p in sfx.rglob("*") if p.is_file() and p.suffix.lower() == ".wav"}


def own_rows(header: list[str], rows: list[list[str]], d2r_names: set[str], d2r_files: set[str]) -> list[int]:
    """Indices of the rows D2R lacks whose file is not one of D2R's (the rows playing Median's own audio, or a file
    nobody has)."""
    s, f = header.index("Sound"), header.index("FileName")
    return [i for i, r in enumerate(rows) if len(r) > f and r[s] and r[s] not in d2r_names and r[f].strip()
            and stem(r[f]) not in d2r_files]


def sound_usage(excel: Path, keys: set[str]) -> dict[str, set[str]]:
    """key -> {"table.column"} of every built table cell that names it."""
    use: dict[str, set[str]] = defaultdict(set)
    for t in SOUND_TABLES:
        p = excel / f"{t}.txt"
        if not p.exists():
            continue
        h, rows = read_tsv(p)
        for r in rows:
            for i, v in enumerate(r[1:len(h)], 1):
                if v in keys:
                    use[v].add(f"{t}.{h[i]}")
    return use


def channel_for(uses: set[str], key: str = "") -> str:
    tables = {u.split(".", 1)[0] for u in uses}
    if "monsounds.Taunt" in uses or key.endswith("_speech"):
        return CHANNEL_BOSS
    if "monsounds" in tables:
        return CHANNEL_MONSTER
    if tables and tables <= ITEM_TABLES:
        return CHANNEL_ITEMS
    return CHANNEL_SKILLS


def group_heads(header: list[str], rows: list[list[str]]) -> dict[int, int]:
    """row index -> index of the group head whose Group Size reaches it (1.13c / D2R pick head + random(size))."""
    g = header.index("Group Size")
    heads: dict[int, int] = {}
    for i, r in enumerate(rows):
        n = int(r[g]) if len(r) > g and r[g].strip().isdigit() else 0
        for j in range(i + 1, min(i + n, len(rows))):
            heads.setdefault(j, i)
    return heads


def plan_bank(header, rows, d2r_names, d2r_files, usage):
    """[(row index, key, stem, channel or None, uses)] of the own rows; channel None = the row's Channel was set by
    someone else (kept)."""
    s, f, c = header.index("Sound"), header.index("FileName"), header.index("Channel")
    heads = group_heads(header, rows)
    out = []
    for i in own_rows(header, rows, d2r_names, d2r_files):
        key = rows[i][s]
        uses = set(usage.get(key, ()))
        if not uses and i in heads:
            uses = {f"{u} (group of {rows[heads[i]][s]})" for u in usage.get(rows[heads[i]][s], ())}
        ch = rows[i][c].strip()
        ch = channel_for({u.split(" ", 1)[0] for u in uses}, key) if not ch or ch in OUR_CHANNELS else None
        st = stem(rows[i][f])
        out.append((i, key, TYPO_FIXES.get(st, st), ch, sorted(uses)))
    return out


def d2r_sounds(d2r_excel: Path, bank: str) -> tuple[set[str], set[str]]:
    h, rows = read_tsv(d2r_excel / bank / "sounds.txt")
    s, f = h.index("Sound"), h.index("FileName")
    return {r[s] for r in rows if r}, {stem(r[f]) for r in rows if len(r) > f and r[f]}


def plan_replaced(audio: dict[str, Path], header: list[str], rows: list[list[str]]):
    """Median's replacements of D2R's files, through D2R's sounds.txt rows.
    -> ({("sd" | "hd", D2R stem): Median stem}, [report rows (median stem, D2R rows, files)], [skipped notes])"""
    s, f, r, g = (header.index(x) for x in ("Sound", "FileName", "Redirect", "Group Size"))
    norm = {m.replace(" ", "_"): m for m in audio}  # D2R renamed cursor/intro/<class> select -> <class>_select
    index = {x[s]: i for i, x in enumerate(rows) if x and x[s]}
    users: dict[str, list[int]] = defaultdict(list)
    for i, x in enumerate(rows):
        if len(x) > f and x[f].strip():
            users[stem(x[f])].append(i)
    median_of = {i: norm[stem(rows[i][f])] for st in norm if st in users for i in users[st]}  # SD row -> Median stem
    targets: dict[tuple[str, str], str] = {}
    hd_rows: dict[int, str] = {}  # HD row -> Median stem
    for i, m in sorted(median_of.items()):
        targets[("sd", stem(rows[i][f]))] = m
        j = index.get(rows[i][r].strip()) if len(rows[i]) > r else None
        if j is None:
            continue
        size = int(rows[i][g]) if rows[i][g].strip().isdigit() else 0
        hsize = int(rows[j][g]) if rows[j][g].strip().isdigit() else 0
        if size > 1 and size == hsize:  # group head -> HD group head: member k plays HD member k
            for k in range(size):
                if i + k in median_of and j + k < len(rows):
                    hd_rows.setdefault(j + k, median_of[i + k])
        else:
            hd_rows.setdefault(j, m)
    skipped = []
    for j, m in sorted(hd_rows.items()):
        st = stem(rows[j][f])
        others = [rows[u][s] for u in users[st] if u not in hd_rows]
        if others:
            skipped.append(f"{rows[j][s]} ({st}.flac) stays D2R's: also played by {', '.join(others)}")
        else:
            targets[("hd", st)] = m
    report = []
    for m in sorted(set(median_of.values())):
        sd = sorted(rows[i][s] for i, v in median_of.items() if v == m)
        files = sorted(f"{'data/hd' if kind == 'hd' else 'data'}/global/sfx/{st}.flac"
                       for (kind, st), v in targets.items() if v == m)
        hd = sorted(rows[j][s] for j, v in hd_rows.items() if v == m and ("hd", stem(rows[j][f])) in targets)
        report.append((m, sd + hd, files))
    return targets, report, skipped


class Converter:
    """Median .wav -> checked .flac bytes, once per file."""

    def __init__(self):
        self.done: dict[str, dict] = {}
        self.errors = 0

    def write(self, st: str, src: Path, dst: Path) -> bool:
        if st not in self.done:
            x, rate, bits = flac.read_wav(src)
            data = flac.encode(x, rate, bits)
            try:
                flac.check(data, x)
            except ValueError as e:
                print(f"sounds_port: {st}: {e}")
                self.errors += 1
                return False
            self.done[st] = {"rate": rate, "samples": len(x), "bytes": len(data), "data": data}
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(self.done[st]["data"])
        return True


def run(median: Path, d2r_excel: Path, mod: Path, write: bool) -> tuple[int, list[str]]:
    excel = mod / "global" / "excel"
    sfx_out = mod / "global" / "sfx"
    audio = median_audio(median / "data" / "global" / "sfx")
    report = ["# sounds_port report (tools/sounds_port.py)", "",
              "| Sound | File | Audio | Channel | Used by |", "|---|---|---|---|---|"]
    conv = Converter()
    missing: set[str] = set()
    n_own = 0
    for bank in ("", "base"):
        p = excel / bank / "sounds.txt"
        if not p.exists():
            continue
        h, rows = read_tsv(p)
        names, files = d2r_sounds(d2r_excel, bank)
        own = [rows[i][h.index("Sound")] for i in own_rows(h, rows, names, files)]
        usage = sound_usage(excel / bank, set(own))
        plan = plan_bank(h, rows, names, files, usage)
        fi, ci = h.index("FileName"), h.index("Channel")
        for i, key, st, ch, uses in plan:
            src = audio.get(st)
            if src is None:
                missing.add(st)
            elif write and not conv.write(st, src, sfx_out / f"{st}.flac"):
                continue
            if src is not None:
                rows[i][fi] = st.replace("/", "\\") + ".flac"
            if ch:
                rows[i][ci] = ch
            if bank == "":
                report.append(f"| {key} | {st}.flac | {'Median' if src else '**missing** (silent, as in 1.13c)'} | "
                              f"{ch or rows[i][ci]} | {', '.join(uses) or '-'} |")
        if write:
            write_tsv(p, h, rows)
        if bank == "":
            n_own = len(plan)
    n_missing = sum(1 for r in report if "**missing**" in r)

    dh, drows = read_tsv(d2r_excel / "sounds.txt")
    targets, replaced, skipped = plan_replaced(audio, dh, drows)
    if write:
        for (kind, st), m in sorted(targets.items()):
            conv.write(m, audio[m], (mod / "hd" / "global" / "sfx" if kind == "hd" else sfx_out) / f"{st}.flac")
    report += ["", f"## Median's replacements of D2R files ({len(replaced)}; owner exception 2026-10-31: Median's audio, "
               "D2R's rows)", "", "| Median file | D2R rows (SD, HD) | Written |", "|---|---|---|"]
    report += [f"| {m}.wav | {', '.join(rs)} | {', '.join(fs)} |" for m, rs, fs in replaced]
    report += [f"- {x}" for x in skipped]

    summary = (f"sounds_port: {n_own} rows play Median's own audio, {n_own - n_missing} with a file"
               + (f" ({len(conv.done)} .flac sources, {sum(c['bytes'] for c in conv.done.values()) / 1e6:.1f} MB)"
                  if write else "")
               + f", {n_missing} without (Median never shipped: {', '.join(sorted(missing)) or 'none'})"
               + f"; {len(replaced)} D2R files play Median's replacement ({len(targets)} SD + HD paths"
               + (f", {len(skipped)} HD files left D2R's" if skipped else "") + ")")
    report[1:1] = ["", summary]
    return conv.errors, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("cmd", nargs="?", default="build", choices=("build", "plan"))
    ap.add_argument("--median", type=Path, default=fxpaths.MXL_ROOT)
    ap.add_argument("--d2r", type=Path, default=fxpaths.D2R)
    ap.add_argument("--mod", type=Path, default=fxpaths.OUT)
    a = ap.parse_args()
    if not (a.mod / "global" / "excel" / "sounds.txt").exists():
        print(f"sounds_port: no built sounds.txt under {a.mod} (run txt_migrate.py first)")
        return 2
    if not (a.median / "data" / "global" / "sfx").is_dir():
        print(f"sounds_port: Median's data/global/sfx is not under {a.median}")
        return 2
    errors, report = run(a.median, a.d2r / "data" / "global" / "excel", a.mod, a.cmd == "build")
    print(report[2])
    if a.cmd == "build":
        (a.mod.parent / "sounds_port.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        print(f"   report -> {a.mod.parent / 'sounds_port.md'}")
    else:
        print("\n".join(report[3:]))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

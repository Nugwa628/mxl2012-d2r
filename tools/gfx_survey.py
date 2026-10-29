"""Read-only graphics and maps inventory of an extracted Median XL 2012 tree (lane gfxsurvey).

    py -3 -I tools/gfx_survey.py --mod <mod extract dir> --d2r <D2R 93847 dir> --out <dir>

Reads the mod's files and decoded excel tables, and the D2R baseline (filelist.txt and its tables).
Writes only to --out: gfx-tables.md (markdown tables and lists) and summary.json (totals).
Nothing is copied from the mod; the output holds names, counts and frame numbers only.
"""
import argparse
import csv
import json
import os
import re
import struct
import sys
from collections import Counter, defaultdict

ART_EXT = {"dc6", "dcc", "cof", "dt1", "ds1", "pl2", "tbl"}
UNRESOLVED = re.compile(r"^File\d{8}\.[A-Za-z0-9]+$")
SKILL_SHEET = {"ama": "amskillicon", "ass": "asskillicon", "bar": "baskillicon",
               "dru": "drskillicon", "nec": "neskillicon", "pal": "paskillicon",
               "sor": "soskillicon"}


def norm(p):
    return p.replace("\\", "/").lower()


def ext_of(name):
    low = name.lower()
    if low.endswith(".pl2.b"):
        return "pl2.b"
    return low.rsplit(".", 1)[-1] if "." in low else ""


def load_baseline(path):
    """Set of lower-case data/... paths in the D2R 93847 filelist (entries look like 'data:data/...')."""
    out = set()
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line.startswith("data:"):
                line = line[5:]
            if line.lower().startswith("data/"):
                out.add(norm(line))
    return out


def load_d2r_sizes(path):
    """lower-case data/... path -> size, from the D2R extract's manifest.json (absent or unreadable: empty)."""
    import json as _json
    try:
        with open(path, encoding="utf-8") as f:
            files = _json.load(f).get("files", {})
    except (OSError, ValueError):
        return {}
    return {norm(k): v for k, v in files.items()}


def walk(root):
    for dp, _dn, fn in os.walk(root):
        for name in fn:
            full = os.path.join(dp, name)
            yield os.path.relpath(full, root).replace("\\", "/"), full


def area_of(rel):
    r = norm(rel)
    if r.startswith("data/local/font"):
        return "fonts"
    if r.startswith("data/local/"):
        return "ui-local (strings/quest art)"
    if r.startswith("data/global/ui/spells"):
        return "skill/spell icons"
    if r.startswith("data/global/ui/"):
        return "ui"
    if r.startswith("data/global/items"):
        return "item icons"
    if r.startswith("data/global/chars"):
        return "players / chars"
    if r.startswith("data/global/monsters"):
        return "monsters"
    if r.startswith("data/global/missiles"):
        return "missiles"
    if r.startswith("data/global/objects"):
        return "objects"
    if r.startswith("data/global/overlays"):
        return "overlays"
    if r.startswith("data/global/tiles"):
        return "maps (ds1/dt1)"
    if r.startswith("data/global/palette"):
        return "palettes"
    if r.startswith("data/global/"):
        return "global other"
    return "outside data/"


def group_key(rel):
    parts = rel.split("/")
    if len(parts) == 1:
        return "(root, unresolved names)" if UNRESOLVED.match(rel) else "(root)"
    depth = min(4, len(parts) - 1)
    return "/".join(parts[:depth])


def kind_of(rel):
    name = rel.rsplit("/", 1)[-1]
    if UNRESOLVED.match(name):
        return "unresolved"
    e = ext_of(name)
    if e in ART_EXT or e == "pl2.b":
        return e
    return None


def dc6_frames(path):
    """(directions, frames per direction) from a DC6 header; None if not a DC6."""
    try:
        with open(path, "rb") as f:
            h = f.read(24)
    except OSError:
        return None
    if len(h) < 24:
        return None
    ver, _flags, _enc, _term, dirs, fpd = struct.unpack("<6i", h)
    if ver != 6 or dirs <= 0 or fpd <= 0:
        return None
    return dirs, fpd


def read_table(path):
    if not os.path.isfile(path):
        return [], []
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def col_index(header):
    idx = {}
    for i, h in enumerate(header):
        idx.setdefault(h.strip().lower(), i)
    return idx


def cell(row, idx, name):
    i = idx.get(name)
    if i is None or i >= len(row):
        return ""
    return row[i].strip()


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mod", required=True, help="mod extract root (the folder that holds data/)")
    ap.add_argument("--d2r", required=True, help="D2R 93847 extract root (holds filelist.txt and data/)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    base = load_baseline(os.path.join(a.d2r, "filelist.txt"))
    files = {}
    for rel, full in walk(a.mod):
        files[norm(rel)] = (rel, full)
    mod_set = set(files)

    # ---------- 1. classification and groups ----------
    d2r_sizes = load_d2r_sizes(os.path.join(a.d2r, "manifest.json"))
    class_same_size = Counter()
    class_diff_size = Counter()
    kinds = Counter()
    groups = defaultdict(lambda: Counter())
    group_area = {}
    class_totals = Counter()
    class_vanilla = Counter()
    class_new = Counter()
    new_files = defaultdict(list)
    non_art = Counter()
    unresolved = Counter()
    for key, (rel, _full) in files.items():
        k = kind_of(rel)
        if k is None:
            non_art[ext_of(rel.rsplit("/", 1)[-1]) or "(none)"] += 1
            continue
        g = group_key(rel)
        grp_area = area_of(rel)
        group_area[g] = grp_area
        same = key in base
        if same and key in d2r_sizes:
            if d2r_sizes[key] == os.path.getsize(_full):
                class_same_size[k] += 1
            else:
                class_diff_size[k] += 1
        groups[g]["total"] += 1
        groups[g]["vanilla" if same else "new"] += 1
        groups[g][k] += 1
        if k == "unresolved":
            unresolved[ext_of(rel)] += 1
        kinds[k] += 1
        class_totals[k] += 1
        if same:
            class_vanilla[k] += 1
        else:
            class_new[k] += 1
            new_files[k].append(rel)

    # ---------- 2. item icons (invfile) ----------
    mod_excel = os.path.join(a.mod, "data", "global", "excel")
    d2r_excel_dirs = [os.path.join(a.d2r, "data", "global", "excel"),
                      os.path.join(a.d2r, "data", "global", "excel", "base")]
    vanilla_inv = set()
    for d in d2r_excel_dirs:
        for t in ("armor.txt", "weapons.txt", "misc.txt"):
            h, rows = read_table(os.path.join(d, t))
            idx = col_index(h)
            for r in rows:
                for c in ("invfile", "uniqueinvfile", "setinvfile"):
                    v = cell(r, idx, c).lower()
                    if v:
                        vanilla_inv.add(v)
    inv_use = defaultdict(list)
    item_rows = []
    for t in ("armor.txt", "weapons.txt", "misc.txt"):
        h, rows = read_table(os.path.join(mod_excel, t))
        idx = col_index(h)
        for r in rows:
            name = cell(r, idx, "name")
            code = cell(r, idx, "code")
            if not code:
                continue
            for c in ("invfile", "uniqueinvfile", "setinvfile"):
                v = cell(r, idx, c).lower()
                if not v or v == "0":
                    continue
                inv_use[v].append((t.split(".")[0], c, name, code))
    inv_rows = []
    new_inv = []
    missing_inv = []
    for v in sorted(inv_use):
        path = norm("data/global/items/%s.dc6" % v)
        in_mod = path in mod_set
        in_base = path in base
        in_d2r_tbl = v in vanilla_inv
        users = inv_use[v]
        sample = ", ".join("%s (%s)" % (u[2] or "?", u[3]) for u in users[:2])
        if not in_d2r_tbl:
            new_inv.append((v, in_mod, in_base, len(users), sample))
        # the 1.13c base game supplies the vanilla item icons (not in patch_d2.mpq), so "no dc6 in
        # the mod extract" alone is not a gap; only no dc6 in the mod AND in D2R means custom art
        if not in_mod and not in_base:
            missing_inv.append((v, len(users), sample))
        inv_rows.append((v, "yes" if in_d2r_tbl else "**no**", "yes" if in_base else "no",
                         "yes" if in_mod else "**no**", len(users), sample))

    # ---------- 3. skill icons ----------
    sk_h, sk_rows = read_table(os.path.join(mod_excel, "skills.txt"))
    sk_idx = col_index(sk_h)
    sd_h, sd_rows = read_table(os.path.join(mod_excel, "skilldesc.txt"))
    sd_idx = col_index(sd_h)
    icon_of = {}
    named = set()  # skilldesc keys that have a real display name (placeholder rows have none)
    for r in sd_rows:
        k = cell(r, sd_idx, "skilldesc")
        if k:
            icon_of[k.lower()] = cell(r, sd_idx, "iconcel")
            if cell(r, sd_idx, "str name"):
                named.add(k.lower())
    sheet_skills = defaultdict(list)
    charclass_values = Counter()
    for r in sk_rows:
        name = cell(r, sk_idx, "skill")
        cc = cell(r, sk_idx, "charclass").lower()
        charclass_values[cc or "(none)"] += 1
        desc = cell(r, sk_idx, "skilldesc").lower()
        if not name:
            continue
        # only skills with a numeric icon cel sit on a sheet; classless rows without one are not icons
        if not icon_of.get(desc, "").isdigit() or desc not in named:
            continue
        sheet = SKILL_SHEET.get(cc, "skillicon") if cc else "skillicon"
        sheet_skills[sheet].append((name, icon_of[desc], cc or "(none)"))
    sheet_rows = []
    for sh in sorted(set(list(SKILL_SHEET.values()) + ["skillicon"])):
        rel = "data/global/ui/spells/%s.dc6" % sh
        in_mod = norm(rel) in mod_set
        in_base = norm(rel) in base
        if in_mod:
            fr = dc6_frames(files[norm(rel)][1])
        else:
            fr = None
        # a class sheet steps its cels by 2 (cel 0, 2, 4 ...): two frames per icon; the shared sheet steps by 1
        cels = [int(x) for _n, x, _c in sheet_skills.get(sh, [])]
        distinct = sorted(set(cels))
        frames = (fr[0] * fr[1]) if fr else None
        per_icon = ""
        if frames and distinct:
            per_icon = "%.2f" % (frames / len(distinct))
        step = ""
        if len(distinct) > 1:
            step = str(min(b - a for a, b in zip(distinct, distinct[1:])))
        d2r_fr = dc6_frames(os.path.join(a.d2r, rel.replace("/", os.sep))) if in_base else None
        sheet_rows.append((sh, "yes" if in_base else "no", "yes" if in_mod else "**no**",
                           "%d x %d" % d2r_fr if d2r_fr else "-",
                           frames if frames else "-", "%d x %d" % fr if fr else "-",
                           len(sheet_skills.get(sh, [])), len(distinct) if distinct else "-",
                           step or "-", per_icon or "-"))

    # ---------- 4. maps ----------
    lp_h, lp_rows = read_table(os.path.join(mod_excel, "lvlprest.txt"))
    lp_idx = col_index(lp_h)
    def tile_key(v):
        # lvlprest / lvltypes give tile files relative to data/global/tiles/ (e.g. Act2/Maggot/MagW.ds1)
        v = norm(v).strip()
        return v if v.startswith("data/") else "data/global/tiles/" + v

    ds1_ref = set()
    for r in lp_rows:
        for i in range(1, 7):
            v = cell(r, lp_idx, "file%d" % i)
            if v:
                ds1_ref.add(tile_key(v))
    lt_h, lt_rows = read_table(os.path.join(mod_excel, "lvltypes.txt"))
    lt_idx = col_index(lt_h)
    dt1_ref = set()
    for r in lt_rows:
        for i in range(1, 33):
            v = cell(r, lt_idx, "file %d" % i)
            if v:
                dt1_ref.add(tile_key(v))
    ds1_all = [rel for k, (rel, _f) in files.items() if k.endswith(".ds1")]
    dt1_all = [rel for k, (rel, _f) in files.items() if k.endswith(".dt1")]
    ds1_new = [rel for rel in ds1_all if norm(rel) not in base]
    dt1_new = [rel for rel in dt1_all if norm(rel) not in base]
    ds1_new_ref = [rel for rel in ds1_new if norm(rel) in ds1_ref]
    dt1_new_ref = [rel for rel in dt1_new if norm(rel) in dt1_ref]
    # a referenced map that is not in the mod extract is normally a 1.13c base-game map (the mod
    # ships only its overrides and additions); only "in neither" is a gap in the extraction
    ds1_ref_base = sorted(v for v in ds1_ref if v not in mod_set and v in base)
    ds1_missing_ref = sorted(v for v in ds1_ref if v not in mod_set and v not in base)

    # ---------- 5. monster / object tokens, missile and overlay files ----------
    tok_rows = []
    for area_dir in ("data/global/monsters", "data/global/objects"):
        toks = defaultdict(lambda: [0, 0])
        for k, (rel, _f) in files.items():
            if not k.startswith(area_dir + "/") or kind_of(rel) is None:
                continue
            parts = k.split("/")
            if len(parts) < 5:
                continue
            tok = parts[len(area_dir.split("/"))]
            toks[tok][0] += 1
            if k in base:
                toks[tok][1] += 1
        for tok, (n, v) in sorted(toks.items()):
            tok_rows.append((area_dir.split("/")[-1], tok, n, v, "vanilla" if v == n else ("NEW" if v == 0 else "mixed")))
    mis_new = sorted(rel for k, (rel, _f) in files.items()
                     if k.startswith("data/global/missiles/") and kind_of(rel) and k not in base)
    ovl_new = sorted(rel for k, (rel, _f) in files.items()
                     if k.startswith("data/global/overlays/") and kind_of(rel) and k not in base)

    # ---------- write ----------
    ordered_groups = sorted(groups)
    grp_rows = []
    for g in ordered_groups:
        c = groups[g]
        status = "vanilla" if c["new"] == 0 else ("NEW" if c["vanilla"] == 0 else "mixed")
        grp_rows.append((g, group_area[g], c["dc6"], c["dcc"], c["cof"], c["dt1"], c["ds1"],
                         c["pl2"] + c["pl2.b"], c["tbl"], c["unresolved"], c["total"], c["vanilla"], c["new"], status))

    area_rows = []
    areas = defaultdict(lambda: Counter())
    for g in ordered_groups:
        a_ = group_area[g]
        areas[a_]["total"] += groups[g]["total"]
        areas[a_]["vanilla"] += groups[g]["vanilla"]
        areas[a_]["new"] += groups[g]["new"]
        areas[a_]["groups_new"] += 1 if groups[g]["vanilla"] == 0 else 0
        areas[a_]["groups"] += 1
    for a_ in sorted(areas):
        c = areas[a_]
        area_rows.append((a_, c["groups"], c["total"], c["vanilla"], c["new"], c["groups_new"]))

    lines = []
    lines.append("## Totals\n")
    lines.append(md_table(["class", "mod files", "same path in D2R", "same path, same size", "same path, size differs", "NEW to mod"],
                          [(k, class_totals[k], class_vanilla[k], class_same_size[k], class_diff_size[k], class_new[k])
                           for k in ("dc6", "dcc", "cof", "dt1", "ds1", "pl2", "pl2.b", "tbl", "unresolved")
                           if class_totals[k]]))
    lines.append("")
    lines.append("Non-art files skipped (extension: count): " + ", ".join(
        "%s %d" % (e, n) for e, n in non_art.most_common()))
    lines.append("")
    lines.append("## By area\n")
    lines.append(md_table(["area", "folders", "art files", "same path in D2R", "NEW", "folders with no D2R path"], area_rows))
    lines.append("")
    lines.append("## By folder\n")
    lines.append(md_table(["folder", "area", "dc6", "dcc", "cof", "dt1", "ds1", "palette", "font tbl", "unresolved",
                           "total", "in D2R", "NEW", "status"], grp_rows))
    lines.append("")
    lines.append("## Item icons (invfile)\n")
    lines.append("invfile values in the mod's armor/weapons/misc tables (invfile, uniqueinvfile, setinvfile): %d; not in D2R tables (new codes): %d; no dc6 in the mod or in D2R (custom art needed): %d.\n"
                 % (len(inv_use), len(new_inv), len(missing_inv)))
    lines.append(md_table(["invfile", "in D2R tables", "dc6 in D2R", "dc6 in mod extract", "item rows", "example item (code)"], inv_rows))
    lines.append("")
    lines.append("## Skill icon sheets\n")
    lines.append("charclass values in skills.txt: " + ", ".join("%s %d" % (k, v) for k, v in charclass_values.most_common()) + "\n")
    lines.append(md_table(["sheet", "in D2R", "in mod", "D2R dirs x frames", "mod frames", "mod dirs x frames", "skills on it", "distinct icons (IconCel)", "IconCel step", "mod frames per icon"], sheet_rows))
    lines.append("")
    lines.append("## Maps\n")
    lines.append("ds1 in mod: %d (new to D2R: %d; referenced by lvlprest: %d of the new ones). dt1 in mod: %d (new: %d; referenced by lvltypes: %d of the new ones). ds1 names in lvlprest: %d only in the 1.13c base (not in the mod extract); %d in neither (gap).\n"
                 % (len(ds1_all), len(ds1_new), len(ds1_new_ref), len(dt1_all), len(dt1_new), len(dt1_new_ref), len(ds1_ref_base), len(ds1_missing_ref)))
    lines.append("## Monster / object tokens (folder under monsters/ or objects/)\n")
    lines.append(md_table(["area", "token", "files", "same path in D2R", "status"], tok_rows))
    lines.append("")
    lines.append("## Missile and overlay files NEW to the mod\n")
    lines.append("missiles new: %d; overlays new: %d.\n" % (len(mis_new), len(ovl_new)))
    lines.append("")
    lines.append("## Unresolved names\n")
    lines.append("Files the extraction named FileNNNNNNNN.ext (no name in the archive listfile): %s\n"
                 % (", ".join("%s %d" % (e, n) for e, n in unresolved.most_common()) or "none"))

    with open(os.path.join(a.out, "gfx-tables.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # lists for the doc
    lists = {
        "new_inv": new_inv,
        "missing_inv": missing_inv,
        "ds1_new": sorted(ds1_new),
        "dt1_new": sorted(dt1_new),
        "ds1_missing_ref": ds1_missing_ref,
        "ds1_ref_base": ds1_ref_base,
        "new_tokens": [t for t in tok_rows if t[4] == "NEW"],
        "mis_new": mis_new,
        "ovl_new": ovl_new,
        "new_dc6": sorted(new_files["dc6"]),
        "new_dcc": sorted(new_files["dcc"]),
        "new_cof": sorted(new_files["cof"]),
        "new_pl2": sorted(new_files["pl2"] + new_files["pl2.b"]),
        "new_tbl": sorted(new_files["tbl"]),
        "new_unresolved": sorted(new_files["unresolved"]),
        "sheets": sheet_rows,
    }
    with open(os.path.join(a.out, "lists.json"), "w", encoding="utf-8") as f:
        json.dump(lists, f, indent=1, ensure_ascii=False)
    summary = {
        "mod_root": a.mod,
        "baseline_paths": len(base),
        "classes": {k: {"total": class_totals[k], "vanilla": class_vanilla[k], "new": class_new[k]}
                    for k in class_totals},
        "non_art": dict(non_art),
        "invfile_values": len(inv_use), "invfile_not_in_d2r": len(new_inv), "invfile_custom_art": len(missing_inv),
        "ds1": len(ds1_all), "ds1_new": len(ds1_new), "ds1_new_referenced": len(ds1_new_ref),
        "ds1_ref_in_base_only": len(ds1_ref_base), "ds1_ref_missing": len(ds1_missing_ref),
        "dt1": len(dt1_all), "dt1_new": len(dt1_new), "dt1_new_referenced": len(dt1_new_ref),
        "missiles_new": len(mis_new), "overlays_new": len(ovl_new),
        "tokens_new": sum(1 for t in tok_rows if t[4] == "NEW"), "tokens": len(tok_rows),
        "unresolved": dict(unresolved),
    }
    with open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    sys.exit(main())

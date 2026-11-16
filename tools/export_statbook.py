"""Export the standalone Stat Book plugin (statbook/) as a self-contained source tree for its public repository
"D2R Advanced Stats" (docs/statbook.md). The tree builds on its own (PluginSDK fetched at the pinned commit), runs its own
unit tests and holds the art plain D2R installs need.

What goes in:
  statbook/src (not the dev-only test harness), statbook/tests      -> src/, tests/
  plugin/src panel_shared.cpp/.h, panel_logic.h, block_rate_logic.h  -> src/shared/ (includes rewritten)
  plugin/src/rotw_stash_logic.h's HdModeRva                          -> src/shared/hd_mode.h (the only part panel_shared uses)
  statbook/statbook.toml                                             -> statbook.toml
  tools/statbook.py, tools/statbook_layout.py                        -> tools/ (imports pointed at the two small modules below)
  tools/d2r_ui.py            the sprite / layout helpers they use, copied function by function from ui_art, dc6,
                             median_stash, pad_ui and rotw_stash_legacy (VENDOR)
  tools/advanced_stats.py    the All Stats groups and texts statbook.py reads (VENDOR)
  data/statbook_pages.tsv, data/advanced_stats.tsv (its `source` column left out)
  data/hd/global/ui/panel/statbook/*.sprite   the art a plain install ships (statbook_layout.PLAIN_OWN_ART): built here
                             from D2R's sprites (`statbook_layout.plain_art`), or copied from --art DIR
  data/global/ui/panel/statbook/*.dc6         the legacy graphics art (statbook_plain_legacy.h LegacyArt): built here by
                             `statbook_legacy.plain_art`, or copied from the same --art DIR
  docs/statbook-layout.md    from this repository's, internal notes left out (DOC_RULES)
  docs/images/*.png          README screenshots from --images DIR
  statbook/export/*          the files of the public repository only: CMakeLists.txt, README.md, LICENSE, docs/statbook.md,
                             tools/d2r_paths.py, tools/package.py, tools/tests/, .gitignore, the GitHub Actions workflow (OVERLAY)

Every copied text file goes through SCRUB (each rule must still match: a changed source fails the export instead of leaking
a note) and the path rewrite (statbook/src/ -> src/, plugin/src/<shared> -> src/shared/, a docs/ or tools/ path the export
does not hold -> "D2R-XL 2012's <path>"). The generated headers and book (statbook_plain_layout.h, statbook_plain_legacy.h,
default_book.inc) are copied byte for byte: the exported tools must reproduce the first and the book; the legacy header and
its art come from this repository's tools/statbook_legacy.py (the classic sheet tools stay here).

  py -3 tools/export_statbook.py [--out DIR] [--art DIR | --no-art] [--images DIR] [--force]
      default --out <runs>/sbexport/repo, --images <runs>/sbexport/images; --force empties an existing --out first
"""
from __future__ import annotations

import argparse
import ast
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

OVERLAY = ROOT / "statbook" / "export"
SHARED = ("panel_shared.cpp", "panel_shared.h", "panel_logic.h", "block_rate_logic.h")
SKIP_SRC = {"testharness.cpp", "testharness.h"}          # the dev-only background-input harness (STATBOOK_TEST_HARNESS)
VERBATIM = {"src/statbook_plain_layout.h", "src/statbook_plain_legacy.h", "src/default_book.inc"}   # generated
ART_DIR = Path("data") / "hd" / "global" / "ui" / "panel" / "statbook"
LEGACY_ART_DIR = Path("data") / "global" / "ui" / "panel" / "statbook"
# overlay names that cannot sit under their real name in this repository
RENAMES = {"gitignore.txt": ".gitignore", "github-build.yml": ".github/workflows/build.yml"}
TEXT_SUFFIXES = {".cpp", ".h", ".inc", ".rc", ".txt", ".toml", ".py", ".md", ".tsv", ".yml", ".json", ""}

# Functions and constants the exported tools use from modules that stay here: module -> names (copied in this order).
VENDOR = {
    "d2r_ui": [("dc6", ["HEADER", "sprite_bytes", "sprite_info"]),
               ("ui_art", ["read_sprite", "write_sprite"]),
               ("median_stash", ["lowend"]),
               ("rotw_stash_legacy", ["lenient_json"]),
               ("pad_ui", ["load"])],
    "advanced_stats": [("advanced_stats", ["GROUPS", "TEXTS", "AVOID_STATS", "KINDS", "read_rows"])],
}
VENDOR_HEAD = {
    "d2r_ui": ('"""D2R file helpers of the Stat Book tools: read and write D2R\'s .sprite files (version 31, RGBA), the\n'
               'half-size .lowend copy, and D2R\'s layout JSON (// comments, trailing commas). Copied from the D2R-XL 2012\n'
               'tools by its tools/export_statbook.py; edit them there."""\n'
               "import json\nimport re\nimport struct\nfrom pathlib import Path\n\nfrom PIL import Image\n"),
    "advanced_stats": ('"""The All Stats groups (data/advanced_stats.tsv): the rows in display order, the group headings and the\n'
                       'own rows\' texts that tools/statbook.py writes into the book. Copied from the D2R-XL 2012 tools by its\n'
                       'tools/export_statbook.py; edit them there.\n\n'
                       'data/advanced_stats.tsv, one row per All Stats row in display order inside its group:\n'
                       '  stat    itemstatcost row name; several joined by "," for a row of several stats\n'
                       '  show    always / nonzero\n'
                       '  group   one of GROUPS\n'
                       '  row     empty = D2R\'s own row text (the item tooltip line); else the plugin\'s own row:\n'
                       '          range:<Key>  min and max stat     value:<Key>  one percent stat based on 100\n'
                       '          avoid        passive_dodge, passive_avoid, passive_evade\n"""\n'
                       "from pathlib import Path\n\nROOT = Path(__file__).resolve().parent.parent\n"
                       'TSV = ROOT / "data" / "advanced_stats.tsv"\n'),
}
# Module renames inside the exported tools: `import <old>` -> `import <new> as <old>`.
IMPORTS = {"ui_art": "d2r_ui", "median_stash": "d2r_ui", "pad_ui": "d2r_ui", "fxpaths": "d2r_paths"}

# Internal notes (bug and lane names, owner rulings, test runs) left out of the copies: (export path, regex, replacement).
SCRUB = [
    ("src/advstats.cpp", r"\(bugs #581 / #582, off word advstats, docs/plugin-plan\.md section 37\)",
     "(part advstats, statbook.toml `advanced_stats`)"),
    ("src/advstats.cpp", r" \(#582\)", ""),
    ("src/advstats.h", r"\(advstats\.cpp, bugs #581 / #582\)", "(advstats.cpp)"),
    ("src/advstats_logic.h", r"bugs #581 / #582; unit test plugin/tests/advstats_test\.cpp", "unit test tests/advstats_test.cpp"),
    ("src/advstats_logic.h", r"; #582\)", ")"),
    ("tests/advstats_test.cpp", r"refresh \(#582\):", "refresh:"),
    ("src/statbook.cpp", r"\(lane sbresearch,\n// docs/statbook\.md", "(see\n// docs/statbook.md"),
    ("src/statbook_config.h", r" \(lane sbresearch\)", ""),
    ("src/statbook_config.h", r" Lane sbresearch findings\.", ""),
    ("tools/statbook_layout.py", r" \(owner rule\)", ""),
    ("docs/statbook-layout.md", r" \(slot 4, 2026-11-15, without the statbook plugin\)", " (seen in game without the plugin)"),
    ("docs/statbook-layout.md", r" \(checkpoint 4 shot `statbook_allstats_search`\)", ""),
    ("docs/statbook-layout.md", r"\n`tools/tests/test_statbook_layout\.py` checks that this page, `contract_names\(\)` in the tool and both built layouts agree\.",
     ""),
    ("docs/statbook-layout.md", r"The tool's docstring has the method\. Nothing of Blizzard's art goes into git\.",
     "The tool's docstring has the method. This repository holds the sprites a plain D2R install needs\n"
     "(`data/hd/global/ui/panel/statbook/`, `py -3 -I tools/statbook_layout.py art` rebuilds them from your own D2R files)."),
]
# Words that must not be left in any exported text file (checked after SCRUB; tests/test_export_statbook.py too), on top of
# tools/check_public.py's rules (machine and host names, user-home paths, e-mail addresses, other projects' names).
FORBIDDEN = [r"\blane [a-z]", r"\bLane [a-z]", r"\bbugs? #?\d", r"#5\d\d\b", r"\bowner\b", r"mxl2012-runs", r"checks-\d{8}",
             r"wyrd\.games", r"\bforge\b", r"Claude", r"DECISIONS",
             r"\.\./\.\./plugin/", r"\.\./plugin/src"]


def runs_dir() -> Path:
    import localconfig
    return Path(localconfig.runs_dir())


# ---- copying and rewriting -----------------------------------------------------------------------------------------------
def vendor_module(name: str) -> str:
    """The text of tools/<name>.py in the export: VENDOR_HEAD plus each named function / constant, copied from its module."""
    parts = [VENDOR_HEAD[name]]
    for module, names in VENDOR[name]:
        src = (ROOT / "tools" / f"{module}.py").read_text("utf-8")
        tree = ast.parse(src)
        found = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
                found[node.name] = ast.get_source_segment(src, node)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, ast.Name) and t.id in names:
                        found[t.id] = ast.get_source_segment(src, node)
        missing = [n for n in names if n not in found]
        if missing:
            raise SystemExit(f"tools/{module}.py has no {', '.join(missing)} any more: update VENDOR in {Path(__file__).name}")
        parts.append(f"\n\n# from tools/{module}.py\n")
        for n in names:
            text = found[n].replace("dc6.", "")
            text = re.sub(r"^\s*from rotw_stash_legacy import lenient_json\n", "", text, flags=re.M)
            parts.append("\n\n" + text + "\n" if not text.startswith(("HEADER", "GROUPS", "TEXTS", "AVOID", "KINDS")) else "\n" + text + "\n")
    return re.sub(r"\n{4,}", "\n\n\n", "".join(parts)).rstrip("\n") + "\n"


def rewrite_imports(text: str) -> str:
    for old, new in IMPORTS.items():
        text = re.sub(rf"^(\s*)import {old}\b(?! as)", rf"\1import {new} as {old}", text, flags=re.M)
    return text


def rewrite_paths(text: str, have: set[str]) -> str:
    """Monorepo paths in comments and docs to the export's: statbook/src/ -> src/, plugin/src/<shared> -> src/shared/, a
    docs/ or tools/ file the export does not hold -> "D2R-XL 2012's <path>"."""
    text = re.sub(r"(?<![\w./-])statbook/(src|tests)/", r"\1/", text)
    text = re.sub(r"(?<![\w./-])statbook/statbook\.toml", "statbook.toml", text)
    text = re.sub(r"(?<![\w./-])statbook/tests\b", "tests", text)
    text = re.sub(r"(?<![\w./-])plugin/src/(" + "|".join(re.escape(s) for s in SHARED) + ")", r"src/shared/\1", text)

    def other(m):
        moved = re.sub(r"^plugin/tests/", "tests/", m.group(0))   # the Stat Book's tests that moved with it
        return m.group(0) if m.group(0) in have else moved if moved in have else "D2R-XL 2012's " + m.group(0)
    return re.sub(r"(?<![\w./-])(?:docs|tools|plugin)/[\w./-]*\w", other, text)


def scrub(rel: str, text: str) -> str:
    for path, rx, new in SCRUB:
        if path == rel:
            text, n = re.subn(rx, new, text)
            if not n:
                raise SystemExit(f"{rel}: scrub rule {rx!r} no longer matches: update SCRUB in {Path(__file__).name}")
    return text


def forbidden_hits(rel: str, text: str) -> list[str]:
    import check_public
    hits = [f"{rel}:{text.count(chr(10), 0, m.start()) + 1}: {m.group(0)!r}" for rx in FORBIDDEN for m in re.finditer(rx, text)]
    for n, line in enumerate(text.splitlines(), 1):
        hits += [f"{rel}:{n}: [{rule}] {s!r}" for rule, s in check_public.scan_line(line) + check_public.scan_mentions(line)]
    return hits


def shared_hd_mode() -> str:
    m = re.search(r"inline constexpr uint64_t HdModeRva = (0x[0-9a-f]+);", (ROOT / "plugin" / "src" / "rotw_stash_logic.h").read_text("utf-8"))
    if not m:
        raise SystemExit("plugin/src/rotw_stash_logic.h: HdModeRva not found")
    return ("// D2R's \"is HD graphics on\" query (a function of D2R's image 0x6ab3782c), the one entry of D2R-XL 2012's\n"
            "// rotw_stash_logic.h that panel_shared.cpp uses.\n#pragma once\n\n#include <cstdint>\n\nnamespace rotw_stash {\n"
            f"inline constexpr uint64_t HdModeRva = {m.group(1)};\n}}  // namespace rotw_stash\n")


def plan() -> dict[str, tuple[str, object]]:
    """export path -> (kind, source): kind 'copy' (a monorepo file, rewritten), 'raw' (byte copy), 'text' (a string)."""
    out: dict[str, tuple[str, object]] = {}
    for p in sorted((ROOT / "statbook" / "src").iterdir()):
        if p.is_file() and p.name not in SKIP_SRC:
            rel = f"src/{p.name}"
            out[rel] = ("raw" if rel in VERBATIM else "copy", p)
    for p in sorted((ROOT / "statbook" / "tests").iterdir()):
        if p.is_file():
            out[f"tests/{p.name}"] = ("copy", p)
    for s in SHARED:
        out[f"src/shared/{s}"] = ("copy", ROOT / "plugin" / "src" / s)
    out["src/shared/hd_mode.h"] = ("text", shared_hd_mode())
    out["statbook.toml"] = ("copy", ROOT / "statbook" / "statbook.toml")
    out["tools/statbook.py"] = ("copy", ROOT / "tools" / "statbook.py")
    out["tools/statbook_layout.py"] = ("copy", ROOT / "tools" / "statbook_layout.py")
    for name in VENDOR:
        out[f"tools/{name}.py"] = ("text", vendor_module(name))
    out["data/statbook_pages.tsv"] = ("copy", ROOT / "data" / "statbook_pages.tsv")
    out["data/advanced_stats.tsv"] = ("text", drop_column((ROOT / "data" / "advanced_stats.tsv").read_text("utf-8"), "source"))
    out["docs/statbook-layout.md"] = ("copy", ROOT / "docs" / "statbook-layout.md")
    for p in sorted(OVERLAY.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            rel = p.relative_to(OVERLAY).as_posix()
            out[RENAMES.get(rel, rel)] = ("copy", p)
    return out


def drop_column(text: str, name: str) -> str:
    rows = [ln.split("\t") for ln in text.splitlines()]
    i = rows[0].index(name)
    return "\n".join("\t".join(r[:i] + r[i + 1:]) for r in rows) + "\n"


def fix_includes(rel: str, text: str) -> str:
    """#include "../../plugin/src/x.h" -> "shared/x.h" (src/ files); panel_shared.cpp's rotw_stash_logic.h -> hd_mode.h."""
    text = re.sub(r'#include "\.\./\.\./plugin/src/([\w.]+)"', r'#include "shared/\1"', text)
    if rel == "src/shared/panel_shared.cpp":
        text, n = re.subn(r'#include "rotw_stash_logic\.h"', '#include "hd_mode.h"', text)
        if not n:
            raise SystemExit("plugin/src/panel_shared.cpp no longer includes rotw_stash_logic.h: update fix_includes")
    return text


def export(out: Path, art: Path | None = None, build_art: bool = True, images: Path | None = None, force: bool = False) -> dict:
    """Write the tree; returns {"files": [...], "problems": [...]} (problems: FORBIDDEN words left, missing art)."""
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        if not force:
            raise SystemExit(f"{out} is not empty (--force empties it first)")
        for c in out.iterdir():           # only this export's own output folder
            shutil.rmtree(c) if c.is_dir() else c.unlink()
    out.mkdir(parents=True, exist_ok=True)
    files = plan()
    have = set(files)
    problems: list[str] = []
    for rel, (kind, src) in files.items():
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if kind == "raw":                 # unchanged but its line ends (the repository stores LF)
            dst.write_bytes(Path(src).read_bytes().replace(b"\r\n", b"\n"))
            continue
        text = src if kind == "text" else Path(src).read_text("utf-8").replace("\r\n", "\n")
        if kind == "copy" and Path(src).suffix in TEXT_SUFFIXES and not str(Path(src)).startswith(str(OVERLAY)):
            text = scrub(rel, text)
            text = rewrite_paths(text, have)
            text = fix_includes(rel, text)
            if rel.startswith("tools/"):
                text = rewrite_imports(text)
                text = text.replace('ROOT / "statbook" / "src"', 'ROOT / "src"')
        problems += forbidden_hits(rel, text)
        dst.write_text(text, "utf-8", newline="\n")
    used = {p for p, _rx, _n in SCRUB}
    if used - have:
        problems.append(f"SCRUB names files the export does not hold: {sorted(used - have)}")
    names = write_art(out / ART_DIR, art, build_art) + write_legacy_art(out / LEGACY_ART_DIR, art, build_art)
    if images:
        for p in sorted(Path(images).glob("*.png")):
            dst = out / "docs" / "images" / p.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dst)
    listed = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    if build_art or art:
        import statbook_layout as L
        want = {f"{ART_DIR.as_posix()}/{a.lower()}{ext}" for a in L.PLAIN_OWN_ART for ext in (".sprite", ".lowend.sprite")}
        want = {f"{LEGACY_ART_DIR.as_posix()}/{n}" for n in legacy_art_names()}
        problems += [f"missing art {w}" for w in sorted(want - set(listed))]
    return {"files": listed, "problems": problems, "art": names}


def write_art(dst: Path, art: Path | None, build: bool) -> list[str]:
    import statbook_layout as L
    if art:
        names = []
        for a in L.PLAIN_OWN_ART:
            for ext in (".sprite", ".lowend.sprite"):
                p = Path(art) / f"{a.lower()}{ext}"
                if p.is_file():
                    dst.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(p, dst / p.name)
                    names.append(p.name)
        return names
    if not build:
        return []
    import fxpaths
    data = dst.parents[4]          # <out>/data (ART_DIR is data/hd/global/ui/panel/statbook)
    return L.plain_art(Path(fxpaths.D2R), data)


def legacy_art_names() -> list[str]:
    """The DC6 files statbook_plain_legacy.h names (LegacyArt)."""
    text = (ROOT / "statbook" / "src" / "statbook_plain_legacy.h").read_text("utf-8")
    m = re.search(r"LegacyArt\[\] = \{([^}]*)\}", text)
    if not m:
        raise SystemExit("statbook/src/statbook_plain_legacy.h has no LegacyArt list")
    return re.findall(r'"([^"]+\.dc6)"', m.group(1))


def write_legacy_art(dst: Path, art: Path | None, build: bool) -> list[str]:
    if art:
        names = []
        for n in legacy_art_names():
            p = Path(art) / n
            if p.is_file():
                dst.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, dst / n)
                names.append(n)
        return names
    if not build:
        return []
    import fxpaths
    import statbook_legacy
    statbook_legacy.plain_art(Path(fxpaths.D2R), dst.parents[3])   # <out>/data (LEGACY_ART_DIR is data/global/ui/panel/statbook)
    return [n for n in legacy_art_names() if (dst / n).is_file()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--art", type=Path, help="copy the plain install's sprites and DC6s from this folder instead of building them")
    ap.add_argument("--no-art", action="store_true")
    ap.add_argument("--images", type=Path, help="README screenshots (*.png) for docs/images/")
    ap.add_argument("--force", action="store_true", help="empty a non-empty --out first")
    a = ap.parse_args(argv)
    out = a.out or runs_dir() / "sbexport" / "repo"
    images = a.images or (runs_dir() / "sbexport" / "images")
    r = export(out, a.art, not a.no_art, images if images.is_dir() else None, a.force)
    size = sum((out / f).stat().st_size for f in r["files"])
    print(f"{out}: {len(r['files'])} files, {size / 1024:.0f} KiB")
    for p in r["problems"]:
        print("PROBLEM", p)
    return 1 if r["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())

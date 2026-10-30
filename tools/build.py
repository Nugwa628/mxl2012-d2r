"""Run the whole data pipeline in order (after the one-time extractions mpq_extract.py and casc_extract.py).

Skeleton of another port's build.py. The steps below are the game-generic ones; a step whose script is not in
tools/ yet is reported as skipped, so the list can run as it is while the lanes add the 2012 versions (docs/PLAN.md phases 1-2).
Not carried over: names/IDs renumbering for another Median XL release (mxl_names.py), D2Sigma-only tables (sigma_tables.py), and the
plugin-header data generators (sigma_data.py, items_data.py, ...): Median XL 2012 has none of them (docs/plugin-plan.md).

  mxl2012_prep.py    the pure v005 MPQ's tables (assets/median) -> work/named/ (UTF-8, normalised, docs/txt-migrate.md)
  tbl2json.py        strings                  -> work/mod/data/local/lng/ (namespace mxl2012, docs/strings.md)
  txt_migrate.py     D2R table layout         -> work/mod/data/global/excel/{base,} (ids: tools/idmap.py, docs/id-mapping.md)
  d2r_adds.py        D2R's own additions (Terror Zones and others) switched off, docs/d2r-additions.md
  chronicle.py       D2R's Chronicle over Median's uniques / sets / runewords: item type UI categories, disableChronicle
                     (docs/d2r-additions.md)
  warlock_scale.py apply  the Warlock's skills on Median's rules and power (data/warlock_rules.tsv, data/warlock_balance.tsv,
                     docs/warlock-balance.md)
  string_gaps.py     keys no .tbl defines: names and description lines have text in words, blank names get a key (docs/text-audit.md)
  shared_icons.py tables  class-less skills' icons: the shared icon sheet in pairs (IconCel + 1 = the pressed button), class
                     rows an item skill shares split into `<row>~shared`, plan -> work/mod/shared_icons.json (docs/hd-icons.md)
  objstr.py          object ids of the maps vs D2R's ObjPreset, the automap, work/mod/ds1_ids.json (docs/id-mapping.md)
  cube_rules_check.py  every cubemain row: Median's cubemain.bin (what 1.13c ran) vs its .txt, the source vs both built banks
                     by meaning, and what D2R's reader takes otherwise -> work/mod/cube_rules_report.md (docs/median-rules-audit.md)
  strings_check.py   string keys of the migrated tables (--rewritten) + the text audit (tools/text_audit.py: key names, placeholders,
                     empty names, `@key`s in the layouts fail the build)
  merge_string_overrides.py  skill_tab_titles.json (skill_tree_art.py) -> mxl2012/overrides.json; runs after the writer, then
                     strings_check.py again
  art_fix.py         missile CelFiles and overlay Filenames that exist nowhere -> the closest existing art (both banks)
  own_tokens.py tables  own monster tokens (Slayer e9 -> KS): the Code of the split rows (docs/legacy-graphics.md section 6)
  gfx_placeholders.py  D2R graphics for Median-only monsters (until the art port) + hd/character/monsters.json
  art_provenance.py  Median's missile/overlay/monster DCCs matched to D2R's own by image (cache: work/art_provenance)
  hd_monsters.py build --out work/mod/data   donor, scale and colour per monster token (HD units) -> hd/character
  hd_translvl.py build  per-TransLvl colours: the classic palshift.dat level shifts D2R's HD units lack, as variant table
                     entries (docs/hd-monsters.md section 8)
  animdata_merge.py  merge Median animation data into D2R's animdata
  hd_skill_anims.py  HD skill animation data for Median skills (D2R's player state machines: read once from the CASC of
                     MXL_SLOT 2|3 and cached in work/d2r-cache when the baseline extraction lacks them)
  missile_hd.py      HD models for Median's missiles (by CelFile) -> hd/missiles/missiles.json
  effects_hd.py      every Median missile/overlay row -> exact D2R HD effect, scaled variant or closest stand-in; a
                     recoloured vanilla effect gets a gradient tint (tools/hd_recolour.py, D2R vfx from the shared cache)
                     (also refreshes the committed data/hd-effects-map.tsv); build_effects.py --check-only checks the result
  hd_icons.py baseline + build   skill icon sheets (the shared one from shared_icons.json, + its classic DC6), HD item
                     pictures + hd/items/*.json, both icon checks
                     (MXL2012_HD_OUT=work/mod; the baseline copy is work/d2r-baseline)
  hd_ui.py baseline + build      skill tree pages (the mod's own page art), inventory / cube panels, layouts, ui_check
                     (MXL2012_UI_OUT=work/mod; writes skill_tab_titles.json for merge_string_overrides.py)
  maps_hd.py build work/mod/data   HD scenes for the maps D2R lacks + Median's tiles with the .ds1 monster ids renumbered
  walls_hd.py build work/mod/data  wall scenes of D2R's own wall models for Median's 17 own maps (docs/maps-hd.md
                     "Walls"; D2R's scenes come from the shared cache, MXL_SLOT=2..5 fills it once)
  legacy_art.py      Median's classic (legacy-mode, Alt+G) art files -> work/mod/data/global (docs/legacy-graphics.md)
  rotw_stash_legacy.py build  classic layout + art of D2R's RotW Gems / Materials / Runes stash pages, down-rendered from
                     D2R's HD art (docs/legacy-graphics.md section 9); staged in work/rotw_stash_legacy, into the mod
                     only with MXL2012_ROTW_LEGACY=1 (owner test on a RotW account)
  merge_string_overrides.py, strings_check.py   as above, after the writers
  validate.py        D2R schema checks        -> work/mod/validate_report.md

The plugin is built separately: tools/build_plugin.ps1 [-Sdk DIR] [-Release] [-Tests].

(missile_art.py, Median's own missile/overlay animations as HD flipbook effects, is run by hand.)

Before the steps it checks that assets/ (Median XL 2012's files, HD art) is the pack pinned in assets.lock (tools/asset_pack.py):
a missing or different assets/ stops the build (exit 2) and says how to fetch it; a missing one is fetched here when a local
source is given (MXL_ASSETS), when the build PC's pack folder <MXL2012_RUNS>/assetpack/pack has the pinned pack (assets/ becomes
a junction to its unpacked tree, or a copy of the pack), or with --fetch-assets (download); an existing but different one is
never replaced by the build.
MXL_SKIP_ASSET_CHECK=1 builds with a modified assets/ (a pack in the making), with a warning. While no assets.lock exists yet
(no pack published) the check is skipped with a note.

The data tools read D2R's own tables from a game slot's folder (tools/d2r_game.py: MXL_SLOT=1..5, prefer 2 to 5).

A fresh worktree: `py -3 tools/lane_setup.py` first (docs/setup.md, "New worktree"). It writes the git-ignored .mxl-local.json
(tools/localconfig.py) with the defaults below, so no variable has to be set by hand; build.py stops before running anything when
the D2R extraction or the Median tables are missing.

Where the data comes from (env, defaults for the build PC): MXL2012_SRC = the pure v005 MPQ's data/global/excel (default: that of
tools/fxpaths.py's Median tree, i.e. assets/median from the asset pack, else <MXL2012_RUNS>/extract-mpq; the .tbl files are read
from its sibling data/local/lng/eng), MXL_D2R_EXTRACT = D2R 93847's extraction
(casc_extract.py output). --data-only stops after validate.py (skips the art / HD steps and the asset check).

Where Median's files come from for the art steps: tools/fxpaths.py (MXL_EXTRACT > assets/median > <MXL2012_RUNS>/extract-mpq);
the D2R baseline: MXL_D2R_EXTRACT (> extract/d2r/93847 > the machine's extract_dir, read-only). Nothing is written into either.

--keep-going: a failing art step is reported and the build goes on; the summary lists the failed steps and the exit code
is 1. A failing data step always stops the build (the art steps need its tables).
Each step's whole output is in work/build-logs/<n>-<step>.log.

Usage: python tools/build.py [--fetch-assets] [--data-only] [--keep-going]   (exit code = validate.py's: 1 if there are errors)
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import fxpaths  # noqa: E402
import localconfig  # noqa: E402  (.mxl-local.json defaults: written by tools/lane_setup.py; every step inherits them)
SRC = Path(os.environ.get("MXL2012_SRC") or fxpaths.MXL_EXCEL)
D2R_EXTRACT = Path(os.environ.get("MXL_D2R_EXTRACT") or fxpaths.D2R)
MOD = ROOT / "work" / "mod"
DATA_STEPS = [["mxl2012_prep.py", "--src", str(SRC)],
              ["tbl2json.py", "--tbl-dir", str(SRC.parent.parent / "local" / "lng" / "eng"),
               "--d2r-lng", str(D2R_EXTRACT / "data" / "local" / "lng"), "--excel-dir", str(ROOT / "work" / "named")],
              ["txt_migrate.py"],
              ["d2r_adds.py", "--mod", str(ROOT / "work" / "mod"), "--d2r", str(D2R_EXTRACT)],
              ["chronicle.py", "--mod", str(ROOT / "work" / "mod"), "--d2r", str(D2R_EXTRACT)],
              ["warlock_scale.py", "apply", "--mod", str(ROOT / "work" / "mod")],
              ["string_gaps.py", "apply", "--excel-dir", str(ROOT / "work" / "mod" / "data" / "global" / "excel"),
               "--d2r-lng", str(D2R_EXTRACT / "data" / "local" / "lng")],
              ["shared_icons.py", "tables", "--d2r", str(D2R_EXTRACT)],
              ["objstr.py", "--mod", str(SRC), "--tiles", str(SRC.parent / "tiles")],
              ["cube_rules_check.py", "--src", str(SRC)],
              ["strings_check.py", "--excel-dir", str(ROOT / "work" / "mod" / "data" / "global" / "excel"), "--rewritten", "--warn-missing",
               "--d2r-lng", str(D2R_EXTRACT / "data" / "local" / "lng")]]
STRING_MERGE = [["merge_string_overrides.py"], DATA_STEPS[-1]]
# [script, args..., {env}]: a trailing dict is extra environment for that step
ART_STEPS = [["art_fix.py"], ["own_tokens.py", "tables"], ["gfx_placeholders.py"], ["art_provenance.py"],
             ["hd_monsters.py", "build", "--d2r", str(D2R_EXTRACT), "--out", str(MOD / "data")],
             ["hd_translvl.py", "build", "--d2r", str(D2R_EXTRACT)],
             ["animdata_merge.py"], ["hd_skill_anims.py"], ["missile_hd.py"], ["effects_hd.py"],
             ["build_effects.py", "--check-only"],
             ["hd_icons.py", "baseline", str(D2R_EXTRACT)], ["hd_icons.py", "build", {"MXL2012_HD_OUT": str(MOD)}],
             ["hd_ui.py", "baseline", str(D2R_EXTRACT)], ["hd_ui.py", "build", {"MXL2012_UI_OUT": str(MOD)}],
             ["maps_hd.py", "build", str(MOD / "data"), "--d2r", str(D2R_EXTRACT), "--out", str(MOD / "maps_hd")],
             ["walls_hd.py", "build", str(MOD / "data"), "--d2r", str(D2R_EXTRACT)],  # after maps_hd: replaces its 17 minimal scenes
             ["legacy_art.py", "build", "--d2r", str(D2R_EXTRACT), "--out", str(MOD / "data")],  # after the tiles: it checks them
             # after legacy_art: its item pictures. Staged outside the mod unless MXL2012_ROTW_LEGACY=1 (the classic slot widget
             # crashes D2R without RotW, docs/legacy-graphics.md 9.4)
             ["rotw_stash_legacy.py", "build", "--d2r", str(D2R_EXTRACT), "--mod", str(MOD / "data"), "--out",
              str(MOD / "data" if os.environ.get("MXL2012_ROTW_LEGACY") == "1" else ROOT / "work" / "rotw_stash_legacy" / "data")]]
STEPS = [*DATA_STEPS, *ART_STEPS, *STRING_MERGE, ["validate.py"]]
LOGS = ROOT / "work" / "build-logs"


def run(step: list, n: int = 0) -> int:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")  # the steps' output is read as UTF-8 whatever the console's code page
    if step and isinstance(step[-1], dict):
        env.update(step[-1])
        step = step[:-1]
    script = ROOT / "tools" / step[0]
    if not script.exists():
        print(f"== {' '.join(step)}: skipped (tools/{step[0]} is not in this repository yet)", flush=True)
        return 0
    print(f"== {' '.join(step)}", flush=True)
    r = subprocess.run([sys.executable, str(script), *step[1:]], cwd=ROOT, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    sub = f"-{step[1]}" if len(step) > 1 and step[1].isalpha() else ""
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / f"{n:02d}-{Path(step[0]).stem}{sub}.log").write_text(r.stdout, encoding="utf-8")
    print("\n".join(f"   {line}" for line in r.stdout.strip().splitlines()[-4:]))
    return r.returncode


def ensure_assets(download: bool) -> int:
    """0 when assets/ is the pinned pack; otherwise fetch it if allowed, else say what to do. Never builds without it."""
    sys.path.insert(0, str(ROOT / "tools"))
    import asset_pack
    if not asset_pack.LOCK.exists():
        print("== assets.lock does not exist yet (no asset pack published): asset check skipped", flush=True)
        return 0
    ok, why = asset_pack.assets_ok()
    if ok:
        print(f"== assets/: {why}", flush=True)
        return 0
    if os.environ.get("MXL_SKIP_ASSET_CHECK") == "1":
        print(f"WARNING: assets/ does not match assets.lock ({why}); building anyway because MXL_SKIP_ASSET_CHECK=1", flush=True)
        return 0
    print(f"== assets/ is not the pack pinned in assets.lock: {why}", flush=True)
    present = asset_pack.ASSETS.exists() or asset_pack.is_link(asset_pack.ASSETS)
    local = asset_pack.local_source(asset_pack.read_lock(), prefer_tree=True)
    if (os.environ.get("MXL_ASSETS") or download or local) and not present:
        if asset_pack.main(["fetch", "--link"] if local and not os.environ.get("MXL_ASSETS") else ["fetch"]) == 0:
            return 0
    else:
        hint = ("assets/ exists, so add --force to replace it (changes in it are lost)." if present
                else "or run `tools/build.py --fetch-assets` to download it now.")
        print("   fetch it:  py -3 tools/asset_pack.py fetch              (downloads the pack named in assets.lock)")
        print("              py -3 tools/asset_pack.py fetch --from PATH   (a local pack file, folder or unpacked tree; or set MXL_ASSETS)")
        print(f"   {hint} docs/setup.md has the details.")
    return 2


def preflight() -> None:
    """The inputs every step needs, checked before anything is deleted or run: a missing one used to show up as a step that
    silently wrote nothing."""
    localconfig.require_d2r_extract(D2R_EXTRACT, "build")
    if not (SRC / "skills.txt").exists():
        raise SystemExit(f"build: Median XL 2012's extracted tables are not at {SRC} (MXL2012_SRC); {localconfig.SETUP_HINT}")


def main() -> int:
    sys.stdout.reconfigure(errors="replace")  # a console code page (cp932, cp1252) without some of the steps' characters
    data_only = "--data-only" in sys.argv[1:]
    preflight()
    keep_going = "--keep-going" in sys.argv[1:]
    rc = 0 if data_only else ensure_assets("--fetch-assets" in sys.argv[1:])
    if rc:
        return rc
    for d in (MOD, LOGS):
        shutil.rmtree(d, ignore_errors=True)
    rc = 0
    failed = []
    steps = [*DATA_STEPS, STRING_MERGE[0], ["validate.py"]] if data_only else STEPS
    for n, step in enumerate(steps, 1):
        rc = run(step, n)
        if rc and step[0] != "validate.py":
            if not keep_going or step in DATA_STEPS:  # the art steps need the migrated tables
                print(f"step failed ({rc}); its output: {LOGS}")
                return rc
            print(f"   step FAILED ({rc}); going on (--keep-going)")
            failed.append(" ".join(a for a in step if isinstance(a, str)))
    if failed:
        print(f"== {len(failed)} step(s) failed (logs in {LOGS}):")
        for f in failed:
            print(f"   {f}")
        return rc or 1
    return rc


if __name__ == "__main__":
    sys.exit(main())

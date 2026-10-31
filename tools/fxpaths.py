"""Where the HD-effect tools (effects_hd.py, art_provenance.py, build_effects.py) find their inputs and put their outputs.

The repo layout of the build (tools/build.py) is used when it is there; the environment and the lane's read-only sources
fill in when it is not (a fresh checkout has no extract/ and no assets/).

  Median XL 2012 (data/global with excel/, missiles/, overlays/)
      MXL_EXTRACT or MXL2012_EXTRACT (a folder holding data/global)  >  <repo>/assets/median (the asset pack: tools/mpq_extract.py
      of the ModDB original's patch_d2.mpq, docs/source-inventory.md)  >  <MXL2012_RUNS>/extract-mpq (the same tree, made
      from the repack's identical MPQ; default R/mxl2012-runs, R = two levels above a lane worktree)
  D2R baseline (data/global tables and legacy DCCs, data/hd json, units palette, filelist.txt of the CASC names)
      MXL_D2R_BASE or MXL_D2R_EXTRACT  >  <repo>/extract/d2r/93847  >  <reference checkout>/extract/d2r/93847 (read-only)
      An extraction without filelist.txt gets one cached at work/d2r-filelist.txt (D2R_FILELIST); nothing is ever written
      into the baseline folder (the reference checkout's is read-only).
  tables the rows are read from (missiles.txt, overlay.txt, skills.txt, states.txt)
      MXL_TABLES  >  work/mod/data/global/excel when txt_migrate.py has made them  >  Median's own tables
  the prior mapping (another port's decisions, reused by art file, read-only)
      the reference checkout: localconfig.reference_dir() (MXL_REFERENCE or machine.json reference_checkout); none = no prior mapping
  outputs: work/mod/ (gitignored): data/hd/**, effects_hd.md, art_provenance.json; the committed table data/hd-effects-map.tsv
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import localconfig  # noqa: E402  (.mxl-local.json: MXL_D2R_EXTRACT, MXL_D2R_CACHE, ... as defaults)

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
MOD = WORK / "mod"
OUT = MOD / "data"
RUNS = localconfig.runs_dir()
REFERENCE = localconfig.reference_dir()  # None when this machine has no reference checkout


def _first(env: str | tuple[str, ...], *candidates: Path, probe: str) -> Path:
    """The folder of the (first set) environment variable, else the first candidate that has `probe`, else the last one."""
    for e in (env,) if isinstance(env, str) else env:
        if os.environ.get(e):
            return Path(os.environ[e])
    for c in candidates:
        if (c / probe).exists():
            return c
    return candidates[-1]


MXL_ROOT = _first(("MXL_EXTRACT", "MXL2012_EXTRACT"), ROOT / "assets" / "median", RUNS / "extract-mpq",
                  probe="data/global/excel/missiles.txt")
MXL = MXL_ROOT / "data" / "global"  # Median's excel/, missiles/, overlays/
D2R = _first(("MXL_D2R_BASE", "MXL_D2R_EXTRACT"), ROOT / "extract" / "d2r" / "93847",
             *([REFERENCE / "extract" / "d2r" / "93847"] if REFERENCE else []), probe="data/global/excel/missiles.txt")
D2R_DATA = D2R / "data"
D2R_EXCEL = D2R_DATA / "global" / "excel"
PALETTE = D2R_DATA / "global" / "palette" / "units" / "pal.dat"
MXL_EXCEL = MXL / "excel"
TABLES = Path(os.environ["MXL_TABLES"]) if os.environ.get("MXL_TABLES") else (
    OUT / "global" / "excel" if all((OUT / "global" / "excel" / t).exists()
                                    for t in ("missiles.txt", "overlay.txt", "skills.txt", "states.txt")) else MXL_EXCEL)
D2R_FILELIST = D2R / "filelist.txt" if (D2R / "filelist.txt").exists() else WORK / "d2r-filelist.txt"
# D2R files the baseline extraction lacks, read once from a game slot's CASC (tools/lane_setup.py fills it): MXL_D2R_CACHE (one
# read-only cache for all worktrees, <runs>/shared/d2r-cache), else work/d2r-cache of this checkout.
D2R_CACHE = Path(os.environ["MXL_D2R_CACHE"]) if os.environ.get("MXL_D2R_CACHE") else WORK / "d2r-cache"
PLAYER_CLASSES = ("amazon", "sorceress", "necromancer", "paladin", "barbarian", "druid", "assassin")
VFX_LIST = ROOT / "tools" / "data" / "d2r_vfx_files.txt"  # the particles / gradients tools/hd_recolour.py reads


def _listed(path: Path) -> tuple[str, ...]:
    if not path.exists():
        return ()
    return tuple(x.strip() for x in path.read_text("utf-8").splitlines() if x.strip() and not x.startswith("#"))


# what the build reads through d2r_file(): tools/hd_skill_anims.py (state machines), missile_hd.py, animdata_merge.py,
# hd_recolour.py (VFX_LIST), maps_hd.py floor_biomes (the biomes of the maps with new floor tiles, and their tile mask),
# map_tint.py (the day visual data of those biomes; the act palettes for `measure`), rotw_stash_legacy.py (the classic
# font of the stash tab names)
CACHED_FILES = ("data/global/animdata.d2", "data/hd/missiles/missiles.json", "data/hd/model_lod_desc.bin",
                *(f"data/hd/character/player/{c}/{c}_state_machine.json" for c in PLAYER_CLASSES),
                *(f"data/hd/env/biome/{b}.json" for b in ("act3_docktown", "act4_fort", "act4_mesa")),
                "data/hd/env/tilemasks/tile_masks.json", *_listed(VFX_LIST),
                *(f"data/hd/env/vis/{v}.json" for v in ("act3_docktown_day", "act4_fort_day", "act4_mesa_day")),
                *(f"data/global/palette/act{a}/pal.dat" for a in range(1, 6)),
                "data/local/font/latin/font6.tbl", "data/local/font/latin/font6.dc6")
MAP_TSV = ROOT / "data" / "hd-effects-map.tsv"  # the committed mapping table (art file -> HD stand-in)
PICKS_TSV = ROOT / "data" / "hd-effects-picks.tsv"  # hand-picked stand-ins (art file -> HD effect), applied by effects_hd.py


def palette() -> list[tuple[int, int, int]]:
    """D2R's units palette (pal.dat is stored BGR)."""
    d = PALETTE.read_bytes()
    return [(d[i * 3 + 2], d[i * 3 + 1], d[i * 3]) for i in range(256)]


def d2r_file(rel: str) -> Path:
    """A file of D2R's data (rel = 'data/global/...'): the baseline's copy, else D2R_CACHE (the shared cache that
    tools/lane_setup.py fills, else read once from a game slot's CASC: MXL_SLOT=2|3, tools/d2r_game.py). Nothing is written
    into the baseline folder."""
    p = D2R / rel
    if p.exists():
        return p
    cache = D2R_CACHE / rel
    if not cache.exists():
        if not os.environ.get("MXL_SLOT") and not os.environ.get("MXL_D2R_GAME"):
            raise SystemExit(f"{rel} is in neither the D2R extraction ({D2R}) nor the cache ({D2R_CACHE}); "
                             f"{localconfig.SETUP_HINT} to fill the shared cache (or set MXL_SLOT=2|3 to read it from a slot's CASC)")
        import d2r_game  # only here: reading the game's CASC needs a slot
        import native
        data = native.casc_read(native.open_casc(d2r_game.read_game_dir()), "data:" + rel)
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_name(cache.name + f".{os.getpid()}.tmp")  # a shared cache: readers never see half a file
        tmp.write_bytes(data)
        os.replace(tmp, cache)
    return cache

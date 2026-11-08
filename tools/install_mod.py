"""Install the generated mod into D2R's mods folder as a D2RLoader-ready folder mod.

<game>/mods/mxl2012/
  mxl2012.mpq/modinfo.json         {"name": "mxl2012", "savepath": "mxl2012/"}  (own save folder; D2R reads it
                                    inside the folder MPQ; a copy also sits at the mod root)
  d2rloader/metadata.json           schemaVersion 1 + "namespace": "mxl2012" (Median-only strings, docs/strings-namespace.md;
                                    the folder MPQ needs no (listfile): it is a directory, not a packed archive)
  d2rloader/config/d2rloader.toml   [d2rcore.save_format] mode = "extended" (Median's wider item/stat IDs)
                                    [d2rcore.stash] add_shared_tabs >= 2 (5 shared pages in every game, as a RotW game
                                    has; a higher value set by hand stays: items on those pages, bug #535)
                                    [d2rcore.player] always_enable_rotw_legacy_graphics_keybind = true (G in RotW games)
  mxl2012.mpq/data/...             copy of work/mod/data (folder-style MPQ) + global/dataversionbuild.txt
                                    + Median's classic tiles/maps (global/tiles)

Only mxl2012.mpq/data is replaced on reinstall; saves live elsewhere (Saved Games) and are never touched. Nothing outside
mods\\<name> is written: the slot's game-wide d2rloader\\config is shared with the other mod (tools/slot_share.py).
--placeholder installs an EMPTY mod (modinfo.json only: no data, no plugin, no d2rloader folder), for checking that a
run starts mod mxl2012 without anything of ours in it.
tools/package_release.py builds the same folder for a player release (build_data + write_mod_files).
The stash layouts with the MEDIAN / ORBS tabs (tools/median_tabs.py) and the plugin part medtab ship together: write_mod_files
refuses data with those layouts and no plugin, or a plugin without the part (tab 6 would assert and crash the game).
Usage: MXL_SLOT=2 MXL_RUN=<lock owner> python tools/install_mod.py [--slot 1|2|3|4|5|all] [--name mxl2012] [--placeholder]
(`all` = those of slots 2 to 5 that exist; a named slot that is missing is refused; slot 1, the owner's own game in Program Files, only by name. A write the folder refuses ends the
install with a message: nothing is elevated or retried another way.)
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "work" / "mod" / "data"
NAMESPACE = "mxl2012"  # tbl2json.py writes the namespaced strings under lng/strings/<NAMESPACE>/
DEFAULT_GAME = os.environ.get("MXL_D2R_GAME", "")  # only the folder of a game slot is accepted (see game_ctl.py)
D2R_BUILD = "93847"  # the game build the data and the plugin are made for; data/global/dataversionbuild.txt holds it
sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import fxpaths  # noqa: E402  (Median's files: MXL_EXTRACT / assets/median / extract-mpq; the D2R baseline's filelist)

MXL_GLOBAL = fxpaths.MXL
PLUGIN = Path(os.environ.get("MXL_PLUGIN") or ROOT / "build" / "plugin" / "Release" / "mxl2012-core.dll")
# The plugin's own settings ([mapreveal] exclude, [fonts], ...): installed when missing, never overwritten (the player's changes stay).
CORE_CONFIG = ROOT / "plugin" / "mxl2012-core.toml"
D2R_FILELIST = fxpaths.D2R_FILELIST


# D2R 3.3 gives a classic / expansion game 3 shared stash pages and a RotW game 5 (plus the Gems / Materials / Runes pages);
# D2RLoader's add_shared_tabs adds pages after the vanilla ones. Owner 2026-11-04 (bug #535): as many tabs as RotW has.
EXTRA_SHARED_TABS = 2
# Keys of the mod's own d2rloader.toml (D2RLoader lays an active mod's config over the game-wide one): (section, key, value,
# why). The G toggle in RotW games is on (owner decision 2026-10-29, bugs.md #498: the Warlock's classic files are checked
# by tools/warlock_legacy_check.py; still untested on a RotW account).
# The save format first: a d2rloader.toml that was already there (another mod's copy, an old install) can lack it, and then
# D2RLoader writes retail saves, which cannot hold Median's stats 511-537 (docs/bugs.md #512; the plugin part savemode does the same
# repair for players). D2RCore's Ctrl stat ranges migrate to true once (owner decision 2026-11-07, #528),
# then respect player edits. Some automagic lines repeat (D2RLoader/PluginSDK issue 6). The G toggle in a RotW game is on
# (owner decision 2026-11-04, bug #498: the game-wide file says false and the mod's file must win). Forced keys get their value whatever the file says; the others keep a
# value set by hand. The downloader sets the same keys in a kept file with the same rules (launcher ModConfigKeys /
# EnsureModConfigKeys). The shared tabs are a minimum ("min"): a smaller value is raised, a larger one (set by hand, another mod's
# file) stays, as lowering it would hide the items on the pages past it (bug #535). (section, key, value, forced, why)
TOML_KEYS = [("d2rcore.save_format", "mode", '"extended"', True, "D2RLoader's extended saves, bug #512"),
             ("d2rcore.player", "always_enable_rotw_legacy_graphics_keybind", "true", True, "G toggle in RotW games, bug #498"),
             ("d2rcore.items", "item_stat_ranges", "true", "once", "Ctrl stat ranges back on, bug #528"),
             ("d2rcore.stash", "add_shared_tabs", str(EXTRA_SHARED_TABS), "min", "5 shared stash pages as in RotW, bug #535")]


def _toml_header(line: str):
    """The table name of a `[name]` line (a comment after it allowed), else None."""
    t = line.strip()
    return t[1:t.index("]")].strip() if t.startswith("[") and "]" in t else None


def _is_key_line(bare: str, key: str) -> bool:
    return bare.startswith(key) and bare[len(key):].lstrip().startswith("=")


def _set_value(line: str, key: str, value: str) -> str:
    """A `key = old  # comment` line with the value replaced; indent, comment and line ending kept."""
    body = line.rstrip("\r\n")
    ending = line[len(body):]
    indent = body[:len(body) - len(body.lstrip())]
    rest = body.strip()[len(key):].lstrip()[1:]
    quote, cut = None, len(rest)
    for i, c in enumerate(rest):
        if quote:
            quote = None if c == quote else quote
        elif c in "\"'":
            quote = c
        elif c == "#":
            cut = i
            break
    old, comment = rest[:cut].strip(), rest[cut:].strip()
    if old == value:
        return line
    return f"{indent}{key} = {value}" + (f" {comment}" if comment else "") + ending


def ensure_toml_key(text: str, section: str, key: str, value: str, force: bool = False) -> str:
    """Return `text` with `key = value` in [section]. An uncommented key already there (in [section], or the dotted
    `section.key` before the first table) is the user's and is kept, or with `force` gets `value` in place (indent and
    comment kept); a commented template line (D2RLoader writes
    `# key = default`; any number of `#` and spaces) is replaced; else the key goes right under the header; else the
    table is appended. A UTF-8 BOM and the line endings stay. The downloader does the same (launcher/src/core/paths.h
    EnsureTomlKey)."""
    bom = "﻿" if text.startswith("﻿") else ""
    body = text[len(bom):]
    eol = "\r\n" if "\r\n" in body else "\n"
    lines = body.splitlines(keepends=True)
    start, end = None, len(lines)
    for i, line in enumerate(lines):
        name = _toml_header(line)
        if name is None:
            if start is None and not any(_toml_header(l) is not None for l in lines[:i]) and \
                    _is_key_line(line.strip(), f"{section}.{key}"):
                if not force:
                    return text  # the dotted key before the first table: set by hand
                lines[i] = _set_value(line, f"{section}.{key}", value)
                return bom + "".join(lines)
            continue
        if start is not None:
            end = i
            break
        if name == section:
            start = i
    if start is None:
        kept = body.rstrip("\r\n")
        return bom + (kept + eol + eol if kept else "") + f"[{section}]{eol}{key} = {value}{eol}"
    for i in range(start + 1, end):
        if _is_key_line(lines[i].strip(), key):
            if not force:
                return text  # set by hand: leave it
            lines[i] = _set_value(lines[i], key, value)
            return bom + "".join(lines)
    for i in range(start + 1, end):
        bare = lines[i].strip()
        if bare.startswith("#") and _is_key_line(bare.lstrip("#").strip(), key):
            ending = lines[i][len(lines[i].rstrip("\r\n")):] or eol
            lines[i] = f"{key} = {value}{ending}"
            return bom + "".join(lines)
    if not lines[start].endswith("\n"):
        lines[start] += eol
    lines.insert(start + 1, f"{key} = {value}{eol}")
    return bom + "".join(lines)


# D2RLoader stores every registered action's key in <game>/d2rloader/config/input-bindings.toml the first time the plugin registers it,
# so changing a default in the plugin does not reach a player who already ran an older build: the old key stays. The first port
# registered Map Reveal on R and the cube transmute on C, which are D2R's run toggle and Character screen (a press did both). Those
# two stored entries, and only an entry that still holds the old default, are dropped here so the next start registers the new ones
# (travel_logic.h Hotkeys). A key someone chose by hand is not on the old default and is kept.
OLD_HOTKEY_DEFAULTS = {"mxl2012-core/mxl_map_reveal": 0x52, "mxl2012-core/mxl_transmute": 0x43}  # R, C


def migrate_hotkey_bindings(text: str) -> str:
    """`input-bindings.toml` text without the [bindings."<id>"] tables of OLD_HOTKEY_DEFAULTS whose primary key is still the old one."""
    blocks, cur = [], []
    for line in text.split("\n"):
        if line.startswith("[") and cur:
            blocks.append(cur)
            cur = []
        cur.append(line)
    blocks.append(cur)
    kept = []
    for blk in blocks:
        stale = any(blk[0].strip() == f'[bindings."{ident}"]' and f"primary_key = {key}" in (l.strip() for l in blk)
                    for ident, key in OLD_HOTKEY_DEFAULTS.items())
        if not stale:
            kept.append("\n".join(blk))
    return "\n".join(kept)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=DEFAULT_GAME)
    ap.add_argument("--name", default="mxl2012")
    ap.add_argument("--slot", default=os.environ.get("MXL_SLOT"), help="game slot 1 to 5, or 'all' (slots 2 to 5 that exist); default MXL_SLOT, no other default; overrides --game")
    ap.add_argument("--savepath", help="save folder name written to modinfo.json (default <name>/, slots: <name>-sN/)")
    ap.add_argument("--placeholder", action="store_true", help="an empty mod: modinfo.json only (no data, no plugin)")
    args = ap.parse_args()

    if not args.placeholder and not (SRC / "global" / "excel").exists():
        print("work/mod/data is missing: run tools/build.py first")
        return 1
    import game_slots
    game_slots.require_machine("install_mod")
    if not args.slot:
        n = game_slots.slot_of_game_dir(args.game) if args.game else None  # --game / MXL_D2R_GAME naming a slot's folder
        if n is None:
            print("no game slot: pass --slot 1|2|3|4|5|all or set MXL_SLOT (only the folders of the game slots are installed into)")
            return 2
        return install_one(Path(args.game), args.name, args.savepath or f"{args.name}-s{n}/", placeholder=args.placeholder)
    slots = game_slots.present_set() if args.slot == "all" else [game_slots.require_present(args.slot, "install_mod")]
    rc, first = 0, None
    for n in slots:
        savepath = args.savepath or f"{args.name}-s{n}/"
        print(f"== slot {n}: {game_slots.slot_dir(n)} (saves {savepath})")
        rc = install_one(Path(game_slots.slot_dir(n)), args.name, savepath, first, placeholder=args.placeholder)
        if rc:
            return rc
        first = None if args.placeholder else first or Path(game_slots.slot_dir(n)) / "mods" / args.name / f"{args.name}.mpq" / "data"
        game_slots.setup(n)  # own save folder and loader copy (the shared d2rloader\config is not touched)
    return rc


def install_one(game: Path, name: str, savepath: str, copy_data_from: Path = None, placeholder: bool = False) -> int:
    """Install into one game folder. copy_data_from: the data folder of an install made a moment ago (skips the
    ds1 renumbering and the file merging, copies the finished tree). A game slot is installed into only by the holder of
    its lock (MXL_RUN) and never while its game runs; another mod's folder (machine.json protected_mod_folders) is never a target."""
    import game_slots
    owner = os.environ.get("MXL_RUN")
    slot = game_slots.slot_of_game_dir(str(game))
    if name.lower() != game_slots.MOD.lower() or game_slots.protected(name):
        print(f"refusing install: mod name {name!r} (only {game_slots.MOD}; other mods' folders are never written)")
        return 1
    if slot is not None:
        info = game_slots.lock_info(slot)
        if not owner or not info or not info[1] or info[1].split()[0] != owner:
            print(f"refusing install: {game} is not locked by MXL_RUN={owner!r}")
            return 1
        if game_slots.slot_processes(str(game)):
            print(f"refusing install: {game} still has a running game")
            return 1
    try:
        return install_checked(game, name, savepath, copy_data_from, placeholder, slot)
    except PermissionError as e:  # a write refused half way (the check above passed): stop, never elevate or retry
        print(f"install failed: no write access to {e.filename} ({e.strerror}); {game_slots.ELEVATION_NOTE}")
        return 1
    except SystemExit as e:
        print(e)
        return 1


def install_checked(game: Path, name: str, savepath: str, copy_data_from: Path = None, placeholder: bool = False,
                    slot: int = None) -> int:
    import game_slots
    if not (game / "D2R.exe").exists() or not (game / "D2RLoader.exe").exists():
        print(f"{game} does not look like a D2R folder with D2RLoader installed")
        return 1
    if slot is not None:  # slot 1 sits in Program Files: a refused write stops here, before anything is changed
        game_slots.need_write([str(game / "mods" / name)], f"refusing install into slot {slot}", root=str(game))

    mod = game / "mods" / name
    if placeholder:
        return install_placeholder(mod, name, savepath)
    mpq = mod / f"{name}.mpq"
    data = mpq / "data"
    if data.exists():
        shutil.rmtree(data)
    if copy_data_from is not None:
        shutil.copytree(copy_data_from, data)
    else:
        build_data(data, game)
    return finish_install(game, name, savepath, mod, mpq, data)


def build_data(data: Path, game: Path) -> None:
    """Write the mod's data folder (`data` must not exist yet): work/mod/data plus what is merged at install time.
    Reads D2R's own files from the game folder `game` (CASC, for maps_hd) but copies none of them."""
    shutil.copytree(SRC, data)
    (data / "global" / "dataversionbuild.txt").write_text(D2R_BUILD, encoding="ascii")
    # Classic map tiles and presets (.dt1/.ds1, the .ds1 monster ids renumbered) and the HD scenes for the maps D2R has
    # none for: `maps_hd.py build work/mod/data`, a step of the full tools/build.py. After a --data-only build they are
    # made here, because the level types name Median's own tiles (tiles/mxl/...) and D2R loads them even in HD.
    if not (SRC / "global" / "tiles").exists():
        import maps_hd
        inp = maps_hd.Inputs.load()
        maps, _dt1s, _levels = maps_hd.plan(inp)
        maps_hd.build(data, maps)
        s = maps_hd.write_tiles(data, maps_hd.default_extract() / "data" / "global" / "tiles")
        print("ds1 ids: " + ", ".join(f"{k}={v}" for k, v in sorted(s.items())))
    # Median-only missile and overlay animations (.dcc): D2R crashes on a missing classic graphics file. Median-only
    # inventory pictures (items/*.dc6, the invfile/uniqueinvfile/setinvfile names): classic mode (G) draws items from
    # them. Files D2R already has are left alone so its own effects and items keep matching their HD versions.
    d2r_files = set(D2R_FILELIST.read_text("utf-8").splitlines()) if D2R_FILELIST.exists() else set()
    # Monsters (Phase 5): Median's own animations (COF + DCC); gfx_placeholders.py lets monsters these complete keep
    # their own Code (HD still shows a borrowed model), and animdata_merge.py adds their timing.
    for sub in ("missiles", "overlays", "items", "monsters"):
        for p in (MXL_GLOBAL / sub).rglob("*"):
            rel = p.relative_to(MXL_GLOBAL.parent.parent).as_posix().lower()  # data/global/...
            if p.is_file() and f"data:{rel}" not in d2r_files:
                dest = data / "global" / p.relative_to(MXL_GLOBAL)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)


DEV_METADATA = {"modVersion": "0.1.0-dev", "description": "D2R-XL 2012: work-in-progress port of Median XL to D2R.", "website": ""}


def _toml_value(line: str, key: str) -> str:
    """The value of a `key = value  # comment` line, as written (quotes kept)."""
    rest, quote = line.strip()[len(key):].lstrip()[1:], None
    for i, c in enumerate(rest):
        if quote:
            quote = None if c == quote else quote
        elif c in "\"'":
            quote = c
        elif c == "#":
            return rest[:i].strip()
    return rest.strip()


def ensure_toml_min(text: str, section: str, key: str, value: str) -> str:
    """`key` in [section] at least the integer `value`: a larger integer (set by hand) is kept, a smaller one or one that is not an
    integer gets `value` in place; a missing key as ensure_toml_key. The downloader does the same (paths.h ApplyModConfigKey)."""
    body = text[1:] if text.startswith("﻿") else text
    lines, table, top = body.splitlines(), None, True
    for line in lines:
        name = _toml_header(line)
        if name is not None:
            table, top = name, False
            continue
        for k in ((key,) if table == section else ()) + ((f"{section}.{key}",) if top else ()):
            if _is_key_line(line.strip(), k):
                old = _toml_value(line, k)
                if old.isdigit() and int(old) >= int(value):
                    return text
                return ensure_toml_key(text, section, key, value, True)
    return ensure_toml_key(text, section, key, value)


def apply_toml_key(text: str, section: str, key: str, value: str, forced) -> str:
    """One TOML_KEYS entry applied: forced True (always this value), False (a value set by hand stays) or "min" / "once"."""
    if forced == "once":
        marker = "# mxl2012 migration: ctrl-stat-ranges-on-v1"
        if marker in text.lstrip("\ufeff").splitlines():
            return text  # already migrated: respect player edits, including a removed key
        out = ensure_toml_key(text, section, key, value, True)
        nl = "\r\n" if "\r\n" in text else "\n"
        bom = "\ufeff" if out.startswith("\ufeff") else ""
        return bom + marker + nl + out[len(bom):]
    if forced == "min":
        return ensure_toml_min(text, section, key, value)
    return ensure_toml_key(text, section, key, value, forced)


def medtab_pair_problem(data: Path, plugin: Path) -> str:
    """Why the mod's data and `plugin` must not ship together, or "": stash layouts with the 7 tabs (median_tabs.LAYOUT_MARK)
    need a plugin with the part medtab (its DLL names the mark); without it tab 6 asserts and the game crashes."""
    import median_tabs
    layouts = [data / "global" / "ui" / "layouts" / f for f in ("bankexpansionlayouthd.json", "bankexpansionlayout.json")]
    if not any(p.exists() and median_tabs.LAYOUT_MARK in p.read_text("utf-8", errors="replace") for p in layouts):
        return ""
    if not plugin.exists():
        return f"the stash layouts have the Median tabs but there is no plugin at {plugin} (run tools/build_plugin.ps1)"
    if median_tabs.LAYOUT_MARK.encode() not in plugin.read_bytes():
        return f"the stash layouts have the Median tabs but {plugin} has no medtab part (an older plugin): build this one"
    return ""


def write_mod_files(mod: Path, name: str, savepath: str, plugin: Path = PLUGIN, metadata: dict = None) -> None:
    """Everything of the mod folder except <name>.mpq/data: modinfo.json, d2rloader/{metadata.json, plugins, config, patches}.
    metadata: modVersion / description / website for d2rloader/metadata.json (default: the dev install's).
    Refuses (SystemExit) when <name>.mpq/data and `plugin` are not a pair (medtab_pair_problem)."""
    mpq = mod / f"{name}.mpq"
    problem = medtab_pair_problem(mpq / "data", plugin)
    if problem:
        raise SystemExit(f"install refused: {problem}")
    mpq.mkdir(parents=True, exist_ok=True)
    # D2R (and D2RLoader's mod detection) read modinfo.json inside the folder-style MPQ; the copy at the mod
    # root follows the D2RLoader guide's layout and is harmless.
    modinfo = json.dumps({"name": name, "savepath": savepath}, indent=2)
    for target in (mpq / "modinfo.json", mod / "modinfo.json"):
        target.write_text(modinfo, encoding="utf-8")
    d2rl = mod / "d2rloader"
    (d2rl / "config").mkdir(parents=True, exist_ok=True)
    (d2rl / "plugins").mkdir(exist_ok=True)
    (d2rl / "patches").mkdir(exist_ok=True)
    meta = {"schemaVersion": 1, "namespace": NAMESPACE,
            "metadata": {"name": "mxl2012", "author": "mxl2012-d2r", **DEV_METADATA, **(metadata or {})}}
    (d2rl / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    # The mxl2012-core plugin (plugin/, built by tools/build_plugin.ps1) loads only with this mod (mod-scoped)
    if plugin.exists():
        shutil.copy2(plugin, d2rl / "plugins" / "mxl2012-core.dll")
        print(f"plugin {plugin.name} ({plugin.stat().st_size // 1024} KB)")
    else:
        print(f"no plugin at {plugin} (run tools/build_plugin.ps1); installing data only")
    core_config = d2rl / "config" / "mxl2012-core.toml"
    if CORE_CONFIG.is_file() and not core_config.exists():
        shutil.copy2(CORE_CONFIG, core_config)
    toml = d2rl / "config" / "d2rloader.toml"
    if not toml.exists():  # never overwrite a config someone edited
        toml.write_text('[d2rcore.save_format]\nmode = "extended"\n', encoding="utf-8")
    for section, key, value, forced, why in TOML_KEYS:
        text = toml.read_text(encoding="utf-8")
        added = apply_toml_key(text, section, key, value, forced)
        if added != text:
            toml.write_text(added, encoding="utf-8")
            print(f"d2rloader.toml: {key} = {value} ({why})")


def install_placeholder(mod: Path, name: str, savepath: str) -> int:
    """An empty mod: the folder MPQ with modinfo.json (and its copy at the mod root), nothing else. A previous install of
    ours in that folder is replaced (it is mods\\mxl2012, never another mod)."""
    if mod.exists():
        shutil.rmtree(mod)
    (mod / f"{name}.mpq").mkdir(parents=True)
    modinfo = json.dumps({"name": name, "savepath": savepath}, indent=2)
    for target in (mod / f"{name}.mpq" / "modinfo.json", mod / "modinfo.json"):
        target.write_text(modinfo, encoding="utf-8")
    print(f"placeholder mod (modinfo.json only, savepath {savepath}) -> {mod}")
    return 0


def finish_install(game: Path, name: str, savepath: str, mod: Path, mpq: Path, data: Path) -> int:
    # The game-wide <game>\d2rloader\config\input-bindings.toml is not migrated here (migrate_hotkey_bindings is for a
    # player's own D2R): on a test slot it is shared with the other mod and every run's own changes are undone by slot_share.py.
    write_mod_files(mod, name, savepath)

    for rel in ("strings/%s/median.json", "strings/%s/overrides.json", "strings-legacy/%s/median.json"):
        ns_file = data / "local" / "lng" / (rel % NAMESPACE)
        if not ns_file.exists():
            print(f"warning: {ns_file.relative_to(data)} is missing: no Median strings (run tools/tbl2json.py)")
    files = sum(1 for _ in data.rglob("*") if _.is_file())
    size = sum(p.stat().st_size for p in data.rglob("*") if p.is_file()) / 1e6
    print(f"installed {files} files ({size:.0f} MB) -> {mod}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

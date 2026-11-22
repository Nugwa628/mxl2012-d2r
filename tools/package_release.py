"""Player release of the port: the launcher's feed (release-manifest.json) and a .7z for manual / offline install.

From a finished build (tools/build.py -> work/mod) and the release plugin (cmake -DMXL_RELEASE=ON: no test harness, built
here unless --plugin is given) it writes into dist/:

  D2R-XL-2012-<version>.7z      solid LZMA2 7z (-mx7), top folder mxl2012/, the folder tools/install_mod.py writes into
                                 <D2R>\\mods:
                                   mxl2012.mpq/modinfo.json   {"name": "mxl2012", "savepath": "mxl2012/"}
                                   mxl2012.mpq/data/...       install_mod.build_data (work/mod/data + the install-time merges)
                                   d2rloader/plugins/mxl2012-core.dll, d2rloader/config/d2rloader.toml + mxl2012-core.toml, d2rloader/patches/,
                                   d2rloader/metadata.json     (modVersion = <version>, website = the GitHub repo)
                                   d2rloader/plugins/drawcap.dll, d2rloader/config/drawcap.toml (our standalone draw list
                                   cap plugin, drawcap/, built by tools/build_plugin.ps1 unless --drawcap is given)
                                   d2rloader/plugins/statbook.dll, d2rloader/config/statbook.toml (our standalone Stat Book
                                   plugin, statbook/, the same way unless --statbook is given)
                                   d2rloader/plugins/legacy169.dll, d2rloader/config/legacy169.toml (D2R Legacy 16:9 at
                                   the pinned commit, tools/build_legacy169.ps1 unless --legacy169 is given)
                                   d2rloader/plugins/d2rl-buff-panel.dll + .mpq + licences, d2rloader/config/buff-panel.toml
                                   (Buff HUD, our fork of Lukaszpg's plugin at the pinned commit, tools/build_buffhud.ps1
                                   unless --buffhud is given)
                                   d2rloader/plugins/d2rl-auto-belt-refill.dll, d2rloader/config/auto-belt-refill.toml
                                   (Auto Belt Refill by jaycachou-svg at the pinned commit + our patches,
                                   tools/build_beltrefill.ps1 unless --beltrefill is given)
                                   d2rloader/plugins/d2rl-charm-inv.dll + .mpq, d2rloader/config/charm-inv.toml (CharmInv
                                   1.0.1 by Dimentio, the author's files checked by sha256: --charminv DIR or
                                   charminv_dir())
                                   d2rloader/plugins/Controller QOL Updates.dll + licences,
                                   d2rloader/config/controller-qol-updates.toml (PyreFly's controller-qol at the pinned
                                   commit + our patches, the mxl2012 skill seed embedded; tools/build_controllerqol.ps1
                                   unless --controllerqol is given)
                                   d2rloader/plugins/d2rl-celestialrayone-damage-overflow-fix.dll + licence,
                                   d2rloader/config/celestialrayone.damage-overflow-fix.toml (Damage Overflow Fix 2.4.0 by
                                   CelestialRayOne, the author's DLL checked by sha256: --dof DIR or dof_dir())
                                   d2rloader/plugins/d2rl-enemy-health-bars.dll + licences, notices and its source zip
                                   (Enemy Health Bars by Graxy_TV, GPL-3.0, the pinned source + our patches;
                                   tools/build_enemyhealthbars.ps1 unless --ehb is given)
                                   d2rloader/plugins/d2rl-ruffneckk-floating-damage.dll + licences, notices, font,
                                   d2rloader/config/ruffneckk-floating-damage.toml (Floating Damage by RuffnecKk at the
                                   pinned commit + our patches, tools/build_floatingdamage.ps1 unless --fd is given)
                                   d2rloader/plugins/d2rl-celestialrayone-monster-display.dll + licence,
                                   d2rloader/config/celestialrayone.monster-display.toml and its HD layouts and frames in
                                   mxl2012.mpq/data (Monster Display 1.0.18 by CelestialRayOne, the author's files checked
                                   by sha256: --md DIR or md_dir())
                                   d2rloader/plugins/d2rl-ruffneckk-vendor-stock-refresh.dll + .mpq, licence, notices,
                                   d2rloader/config/ruffneckk-vendor-stock-refresh.toml (Vendor Stock Refresh 2.1.7 by
                                   RuffnecKk at the pinned commit, tools/build_vendorstockrefresh.ps1 unless --vsr is
                                   given; the author's hub MPQ checked by sha256: --vsr-mpq DIR or vsr_mpq_dir())
                                 The manual download for players, and where tools/publish_release.py reads the file bytes
                                 from. There is no zip (owner decision 2026-10-26). Needs 7-Zip: the run stops without it.
  release-manifest.json          schemaVersion 2: version, required D2R build, required D2RLoader + sha256, every file of
                                 the mod folder with size and sha256, the 7z as "archive" (docs/release.md "Release manifest")
  RELEASE_NOTES-<version>.md     the player's notes: NOTES below (downloader install), or --notes TEMPLATE
                                 (tools/data/release_notes_alpha.md: the hand-copied alpha, manual install only)
  SHA256SUMS                     of the 7z, the manifest and the notes

Nothing else goes in: no test harness files, test configs, saves or logs (checked), and no file that is a byte copy of one in
the D2R baseline (fxpaths.D2R: MXL_D2R_EXTRACT / extract/d2r/93847 / the machine's extract_dir) or the shared D2R cache (Blizzard's own
files: D2R reads those from its own install). Without a baseline that check cannot run, so a package with data stops.
The release plugin is built by tools/build_plugin.ps1 -Release (CMake on PATH or Visual Studio's, the PluginSDK of
.mxl-local.json; nothing is downloaded). tools/verify_package.py checks the finished 7z; tools/cut_alpha.ps1 runs it all.

  py -3 tools/package_release.py [--version 0.70.0] [--plugin DLL] [--drawcap DLL] [--legacy169 DLL] [--buffhud DLL] [--beltrefill DLL] [--controllerqol DLL] [--charminv DIR] [--dof DIR] [--ehb DLL] [--fd DLL] [--md DIR] [--vsr DLL] [--vsr-mpq DIR] [--data-from DIR] [--game DIR] [--out dist] [--notes MD]
  py -3 tools/package_release.py --no-data --plugin build/mxl2012-core.dll   (CI: no game files there; plugin + config only)
Version: PluginVersion of plugin/src/mxl2012_core.cpp; --version must equal it (only --no-data builds may differ).
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import charm_inventory  # noqa: E402  (the one switch between CharmInv and invtabs, shared with tools/build.py)
import install_mod  # noqa: E402
import legacy_fonts  # noqa: E402  (classic font checks, the clear set the setting needs)
import fxpaths  # noqa: E402  (the D2R baseline and the shared D2R cache, .mxl-local.json)

ROOT = install_mod.ROOT
NAME = "mxl2012"
REPO_URL = "https://github.com/Nugwa628/mxl2012-d2r"
EXTRACT = fxpaths.D2R  # D2R 93847's extraction (MXL_D2R_EXTRACT > extract/d2r/93847 > the machine's extract_dir, read-only)
RELEASE_BUILD = ROOT / "build" / "plugin-release"
D2R = {"build": install_mod.D2R_BUILD, "version": "3.3.0", "imageTimestamp": "0x6ab3782c"}  # plugin/src/image_guard_logic.h
# The pinned D2RLoader (docs/setup.md step 10). The downloader's Install D2RLoader fetches `url` (https on d2rloader.net
# only) when the player asks and installs it only when `size` and `sha256` match (docs/launcher.md "Install D2RLoader").
D2RLOADER = {"version": "1.3.1-beta", "url": "https://d2rloader.net/download/D2RLoader-1.3.1-beta.zip", "size": 47652455,
             "sha256": "9286c6b5bff7f1043658411dbea305faa9698b6a455e6441668fc6d02c22aad7",
             "signerThumbprint": "8001082E968FADAA58BF2F73EFA1810A11D0C28F"}
# What the game folder's own d2rloader/config/d2rloader.toml needs for this mod ([d2rloader] section of D2RLoader's config):
# the mod starts by itself. The player sets it in the game (Default Mod); the downloader does not write that file. No -txt:
# D2RLoader 1.3.1 compiles the mod's .txt tables itself at each start (docs/launcher.md "How the player starts the game").
LAUNCH = {"default_mod": NAME, "launch_arguments": ""}
# Our own standalone drawcap plugin (drawcap/README.md: D2R's legacy draw list cap; no dependency on mxl2012-core), built from
# this repository by tools/build_plugin.ps1 into build/drawcap, shipped next to mxl2012-core.dll. One build for dev installs and
# releases (it has no test harness; its cap raise is on and its probe off unless drawcap.toml or the test switch files drawcap-nopatch.txt and drawcap-probe.txt say otherwise). Its default config
# is a `preserve` file.
INVTABS = {"name": "Inventory Tabs", "dll": "d2rloader/plugins/invtabs.dll", "config": "d2rloader/config/invtabs.toml",
           "author": "D2R-XL 2012, built on wild-healer's Player Page Host and Charm Inventory (used with his OK, 2026-11-11)",
           "upstream": "https://github.com/wild-healer/D2R-Tools", "upstream_commit": "6722cc545f52a012460f5e9a825632a7f5e38eb5"}
# The package's charm inventory, ONE switch (tools/charm_inventory.py CHARM_INVENTORY, shared with tools/build.py): "charminv"
# (Dimentio's CharmInv 1.0.1) or "invtabs" (our inventory tabs plugin, docs/invtabs.md). With "invtabs" the package holds
# invtabs.dll and invtabs.toml in d2rloader/, invtabs' mod data (INVTABS_DATA: tab type tables, HD cells, classic panel art and
# the classic inventory's Charms button, made by the build's invtabs steps) in mxl2012.mpq/data, and none of CharmInv's files or
# tables. --charm-inventory (or MXL2012_CHARM_INVENTORY) overrides it for one run; data built for the other one is refused.
CHARM_INVENTORY = charm_inventory.CHARM_INVENTORY
CHARM_INVENTORIES = charm_inventory.CHARM_INVENTORIES
INVTABS_DLL = ROOT / "build" / "invtabs" / "Release" / "invtabs.dll"  # tools/build_plugin.ps1
# relative to mxl2012.mpq/data; the HD and classic panel layouts are generated by the plugin at run time (none in the data)
INVTABS_DATA = charm_inventory.INVTABS_DATA

DRAWCAP = {"name": "Draw List Cap", "dll": "d2rloader/plugins/drawcap.dll", "config": "d2rloader/config/drawcap.toml"}
# Our own standalone Stat Book plugin (docs/statbook.md), shipped like drawcap; the book it shows is mod data (STATBOOK_DATA).
STATBOOK = {"name": "Stat Book", "dll": "d2rloader/plugins/statbook.dll", "config": "d2rloader/config/statbook.toml"}
STATBOOK_DATA = "statbook/statbook.txt"  # relative to mxl2012.mpq/data (tools/statbook.py book)
# Our own D2R Legacy 16:9 plugin (docs/bundled-plugins.md), shipped in the mod folder: built from its source at the commit
# the gitlink third_party/D2R-Legacy169 pins (tools/build_legacy169.ps1), unless --legacy169 is given. Its default config goes
# in too, as a `preserve` file: D2RLoader would write it at the first start, but the downloader removes files the release does
# not list, so a player's `enabled = false` would not survive an update.
LEGACY169 = {"name": "D2R Legacy 16:9", "version": "0.1.2", "repo": "https://github.com/Nugwa628/D2R-Legacy169",
             "dll": "d2rloader/plugins/legacy169.dll", "config": "d2rloader/config/legacy169.toml"}
LEGACY169_BUILD = ROOT / "build" / "legacy169"
# Buff HUD by Lukaszpg (MIT), shipped as our fork (branch mxl2012: the generic fixes offered upstream plus the Median XL 2012
# buff list inside its companion MPQ), docs/bundled-plugins.md. Built from the commit the gitlink third_party/d2rl-buff-hud pins
# (tools/build_buffhud.ps1), unless --buffhud is given. The MPQ sits next to the DLL; the fork's MIT licence (copyright
# Lukaszpg) and the PluginSDK licence it links go next to them. Its default config is a `preserve` file, as legacy169's.
BUFFHUD = {"name": "Buff HUD", "version": "1.2.0", "repo": "https://github.com/Nugwa628/d2rl-buff-hud",
           "upstream": "https://github.com/Lukaszpg/d2rl-buff-hud", "author": "Lukaszpg",
           "dll": "d2rloader/plugins/d2rl-buff-panel.dll", "mpq": "d2rloader/plugins/d2rl-buff-panel.mpq",
           "config": "d2rloader/config/buff-panel.toml",
           "licence": "d2rloader/plugins/d2rl-buff-panel-LICENSE.txt",
           "sdk_licence": "d2rloader/plugins/d2rl-buff-panel-PluginSDK-LICENSE.txt"}
BUFFHUD_BUILD = ROOT / "build" / "buffhud"
BUFFHUD_FILES = ("dll", "mpq", "config", "licence", "sdk_licence")
# Auto Belt Refill by jaycachou-svg, shipped with the author's permission (2026-11-06; the repository has no licence file),
# docs/bundled-plugins.md. Built from the author's source at the commit the gitlink third_party/auto-belt-refill pins, with our
# patches (third_party/auto-belt-refill-mxl2012/*.patch: PluginSDK renames, Median belt rows, first-slot
# matching and belt counts, the counts as HUD text) applied at build time (tools/build_beltrefill.ps1), unless --beltrefill is given. Its config is ours
# (columns follow their first slot, elixirs never refilled, keys unbound) and a
# `preserve` file, as legacy169's. The author's prebuilt DLL is for an older D2RLoader ABI and is refused.
BELTREFILL = {"name": "Auto Belt Refill", "version": "0.35.9", "repo": "https://github.com/jaycachou-svg/auto-belt-refill",
              "author": "jaycachou-svg", "dll": "d2rloader/plugins/d2rl-auto-belt-refill.dll",
              "config": "d2rloader/config/auto-belt-refill.toml"}
BELTREFILL_BUILD = ROOT / "build" / "beltrefill"
BELTREFILL_OURS = ROOT / "third_party" / "auto-belt-refill-mxl2012"  # the patches, our CMakeLists.txt and the config
BELTREFILL_FILES = ("dll", "config")
BELTREFILL_AUTHOR_DLL = "77c7d1b9068c8cacc2fded62ff1120b441001d601ad65a8ee3043e3b61c650db"  # its plugins/ at the pinned commit
# Controller QOL Updates by PyreFly (Pyre-Flies/D2R-Mods plugins/controller-qol), shipped with PyreFly's permission (given to the
# project owner 2026-11-04; the repository's LICENSE reserves all rights), docs/bundled-plugins.md. Built from PyreFly's source at
# the commit the gitlink third_party/D2R-Mods pins with our patches (third_party/controller-qol-mxl2012/*.patch: the belt_actions
# switch, off in our config so Auto Belt Refill keeps the belt; the MEDIAN / ORBS stash tabs) and the mxl2012 skill seed
# (tools/controller_skill_profile.py from the package's skills.txt) embedded as its skill defaults (tools/build_controllerqol.ps1),
# unless --controllerqol is given. Its config (the patched controller-qol-updates.toml) is a `preserve` file, as legacy169's;
# PyreFly's LICENSE and the PluginSDK's go next to the DLL.
CONTROLLERQOL = {"name": "Controller QOL Updates", "version": "1.3.1+rev.95", "repo": "https://github.com/Pyre-Flies/D2R-Mods",
                 "path": "plugins/controller-qol", "author": "PyreFly", "dll": "d2rloader/plugins/Controller QOL Updates.dll",
                 "config": "d2rloader/config/controller-qol-updates.toml",
                 "licence": "d2rloader/plugins/Controller QOL Updates-LICENSE.txt",
                 "sdk_licence": "d2rloader/plugins/Controller QOL Updates-PluginSDK-LICENSE.txt"}
CONTROLLERQOL_BUILD = ROOT / "build" / "controllerqol"
CONTROLLERQOL_SRC = ROOT / "build" / "controllerqol-src"
CONTROLLERQOL_OURS = ROOT / "third_party" / "controller-qol-mxl2012"  # the patches
CONTROLLERQOL_PROFILE = ROOT / "build" / "controllerqol-profile"  # the generated skill seed
CONTROLLERQOL_FILES = ("dll", "config", "licence", "sdk_licence")
# CharmInv by Dimentio (D2RLoader's author), docs/bundled-plugins.md and third_party/charm-inv/README.md: the author's DLL and
# companion MPQ unchanged (no source is published), redistributed with D2RLoader by the owner's decision (2026-11-10). The two
# files are not in git; charminv_dir() finds them and every byte is checked against `sha256`. Our config (third_party/charm-inv/
# charm-inv.toml: allow_inventory_charms = true, Median's charms work from the inventory too) is a `preserve` file, as
# legacy169's. Median's charm types and the grid are mod data (tools/charm_inv.py), not in the plugin's files.
CHARMINV = {"name": "CharmInv", "version": "1.0.1", "author": "Dimentio",
            "source": "https://d2rloader.net/hub/plugins/charm-inventory",
            "dll": "d2rloader/plugins/d2rl-charm-inv.dll", "mpq": "d2rloader/plugins/d2rl-charm-inv.mpq",
            "config": "d2rloader/config/charm-inv.toml",
            "sha256": {"dll": "b14f6a0bd4c9df0af9c392ea97dc879ad3760592481517dbdb0983595145d88b",
                       "mpq": "e01163aac3b0d76c3cbdad56e19350692864b51484d9ad6dfbc41f28023fb0ac"},
            "size": {"dll": 68952, "mpq": 9591921}}
CHARMINV_OURS = ROOT / "third_party" / "charm-inv"  # README, our charm-inv.toml (and a git-ignored local copy of the files)
CHARMINV_FILES = ("dll", "mpq", "config")
# Damage Overflow Fix by CelestialRayOne (Bogdan Bulai), MIT, docs/bundled-plugins.md and third_party/damage-overflow-fix/
# README.md: the author's release DLL as committed at the pinned commit (its release/ folder), checked by sha256, not in git;
# dof_dir() finds it. Its MIT licence goes next to it, and our config (the author's default with debug_log and log_each_site
# off) is a `preserve` file, as legacy169's.
DOF = {"name": "Damage Overflow Fix", "version": "2.4.0", "author": "CelestialRayOne (Bogdan Bulai)",
       "repo": "https://github.com/CelestialRayOne/d2rloader_plugins", "commit": "924072545985e0d1bef58c3362c1c1572531aa2e",
       "path": "release/d2rl-celestialrayone-damage-overflow-fix.dll",
       "dll": "d2rloader/plugins/d2rl-celestialrayone-damage-overflow-fix.dll",
       "licence": "d2rloader/plugins/d2rl-celestialrayone-damage-overflow-fix-license.txt",
       "config": "d2rloader/config/celestialrayone.damage-overflow-fix.toml",
       "sha256": "cfc95e328230c86d4659f04d223552afd90f3fd4990f3fd62c48e9770f144a58", "size": 111616}
DOF_OURS = ROOT / "third_party" / "damage-overflow-fix"  # README, LICENSE, our config (and a git-ignored local copy of the DLL)
DOF_FILES = ("dll", "licence", "config")
# Monster Display by CelestialRayOne (Bogdan Bulai), MIT, docs/bundled-plugins.md and third_party/monster-display/README.md:
# the author's release DLL and its HD files (release/MonsterDisplay: three hudmonsterhealthhd layouts and the frame sprites)
# as committed at the pinned commit, checked by sha256, not in git; md_dir() finds the release folder. The layouts and
# sprites go into mxl2012.mpq/data where the author's Readme puts them. Its MIT licence goes next to the DLL, and its
# config (the author's default, unchanged) is a `preserve` file, as legacy169's.
MD = {"name": "Monster Display", "version": "1.0.18", "author": "CelestialRayOne (Bogdan Bulai)",
      "repo": DOF["repo"], "commit": DOF["commit"], "path": "release/d2rl-celestialrayone-monster-display.dll",
      "dll": "d2rloader/plugins/d2rl-celestialrayone-monster-display.dll",
      "licence": "d2rloader/plugins/d2rl-celestialrayone-monster-display-license.txt",
      "config": "d2rloader/config/celestialrayone.monster-display.toml",
      "sha256": "bc5fa7d7ed6468981f8c165b8c3bdde49e475f68a8371d93e2f2eba3b566eaed", "size": 119296,
      # sha256 of the "<sha256>  <path>" lines (sorted, LF) of release/MonsterDisplay's .json and .sprite files
      "data_sha256": "afcf2de29d6edb09667efa59f36a0acfc3769715a481079bc3d09bea37f5a264"}
MD_OURS = ROOT / "third_party" / "monster-display"  # README, LICENSE, the config
MD_FILES = ("dll", "licence", "config")
MD_LAYOUTS = {"hudmonsterhealthhd_pc.json": "global/ui/layouts/hudmonsterhealthhd.json",
              "hudmonsterhealthhd_controller.json": "global/ui/layouts/controller/hudmonsterhealthhd.json",
              "hudmonsterhealthhd_controller_pc.json": "global/ui/layouts/controller/pc/hudmonsterhealthhd.json"}
# Median's monumod.txt 36-39 (ghostly, fanatic, possessed, berserk): xfer 1, so they reach minions, where Monster
# Display must leave them out (our config adds them to the author's minion_hidden_affixes).
MD_MINION_HIDDEN = ("36", "37", "38", "39")
MD_FRAMES = "hd/global/ui/panel/monsterdisplayframes"  # the folder the layouts name (PANEL/MonsterDisplayFrames/...)
MD_SPRITES = tuple(f"{part}{low}.sprite" for part in
                   ("boss_left", "boss_mid", "boss_right", "normal_left", "normal_mid", "normal_right",
                    "resist_bar_center", "resist_bar_left", "resist_bar_mid", "resist_bar_right",
                    "unique_left", "unique_mid", "unique_right", "unique_skull") for low in ("", ".lowend"))
# Enemy Health Bars by Graxy_TV, GPL-3.0-only, docs/bundled-plugins.md and third_party/enemy-health-bars-mxl2012/README.md:
# built from the author's source (the source zip inside the release zip of the pinned commit) with our patches
# (tools/build_enemyhealthbars.ps1, which records them in build/enemyhealthbars-src/EnemyHealthBars/PATCHES). The GPL wants
# the corresponding source with the binary: the patched source as built, with our patches, goes next to the DLL as a zip,
# with the author's licence and third-party notices. Its config is the patched source's (our defaults: bars only on damaged
# monsters, show_full_health = false) and a `preserve` file, as legacy169's.
EHB = {"name": "Enemy Health Bars", "version": "0.2.6+mxl2012", "author": "Graxy_TV", "licence_id": "GPL-3.0-only",
       "repo": "https://github.com/graxytv/D2R-Over-the-Head-Health-Bars", "commit": "e6b929bfa5c59e79e0cbabf898eb777f6d359132",
       "dll": "d2rloader/plugins/d2rl-enemy-health-bars.dll",
       "licence": "d2rloader/plugins/d2rl-enemy-health-bars-license.txt",
       "notices": "d2rloader/plugins/d2rl-enemy-health-bars-third-party.txt",
       "imgui_licence": "d2rloader/plugins/d2rl-enemy-health-bars-imgui-license.txt",
       "mapsense_licence": "d2rloader/plugins/d2rl-enemy-health-bars-mapsense-api-license.txt",
       "sdk_licence": "d2rloader/plugins/d2rl-enemy-health-bars-pluginsdk-license.txt",
       "source": "d2rloader/plugins/d2rl-enemy-health-bars-source.zip",
       "config": "d2rloader/config/enemy-health-bars.toml"}
# Floating Damage by RuffnecKk, MIT, docs/bundled-plugins.md and third_party/floating-damage-mxl2012/README.md: built from the
# gitlink third_party/RuffnecKk-D2RLoader-Suite with our patches (the legacy graphics projection, the bundled font) by
# tools/build_floatingdamage.ps1, which records the commit and patches in build/floatingdamage-src. Next to the DLL: the suite's
# MIT licence, one third-party file (the suite's THIRD_PARTY_NOTICES.md and the licence texts it retains: PluginSDK, ImGui,
# MinHook, D2R Damage Numbers ...), the font (Cinzel Bold) and its SIL OFL. Its config (the author's with our comment) is a
# `preserve` file, as legacy169's.
FD = {"name": "Floating Damage", "version": "1.5.6", "author": "RuffnecKk",
      "repo": "https://github.com/RuffDood/RuffnecKk-D2RLoader-Suite", "path": "plugins/floating-damage",
      "dll": "d2rloader/plugins/d2rl-ruffneckk-floating-damage.dll",
      "licence": "d2rloader/plugins/d2rl-ruffneckk-floating-damage-license.txt",
      "notices": "d2rloader/plugins/d2rl-ruffneckk-floating-damage-third-party.txt",
      "font": "d2rloader/plugins/ruffneckk-floating-damage-font.ttf",
      "font_licence": "d2rloader/plugins/ruffneckk-floating-damage-font-license.txt",
      "config": "d2rloader/config/ruffneckk-floating-damage.toml"}
# Vendor Stock Refresh by RuffnecKk, MIT, docs/bundled-plugins.md and third_party/vendor-stock-refresh/README.md: built
# unchanged from the gitlink third_party/RuffnecKk-D2RLoader-Suite (the commit Floating Damage comes from) by
# tools/build_vendorstockrefresh.ps1. Its companion MPQ (the button art) is not in the author's repository: it is the file
# of the author's hub release of the same version, checked by sha256 (the hash the source itself checks,
# src/companion_hash.hpp), not in git; vsr_mpq_dir() finds it. Next to them: the suite's MIT licence and one third-party
# file, as Floating Damage's. Its config (the author's) is a `preserve` file.
VSR = {"name": "Vendor Stock Refresh", "version": "2.1.7", "author": "RuffnecKk",
       "repo": "https://github.com/RuffDood/RuffnecKk-D2RLoader-Suite", "path": "plugins/vendor-stock-refresh",
       "hub": "https://d2rloader.net/hub/plugins/vendor-stock-refresh",
       "dll": "d2rloader/plugins/d2rl-ruffneckk-vendor-stock-refresh.dll",
       "mpq": "d2rloader/plugins/d2rl-ruffneckk-vendor-stock-refresh.mpq",
       "licence": "d2rloader/plugins/d2rl-ruffneckk-vendor-stock-refresh-license.txt",
       "notices": "d2rloader/plugins/d2rl-ruffneckk-vendor-stock-refresh-third-party.txt",
       "config": "d2rloader/config/ruffneckk-vendor-stock-refresh.toml",
       "mpq_sha256": "0014c677e24979275307fd2194b4d6c31167a46ab8eb9c0f005b6a8cddedc5f6", "mpq_size": 5651640}
VSR_BUILD = ROOT / "build" / "vendorstockrefresh"
VSR_SRC = ROOT / "build" / "vendorstockrefresh-src"
VSR_OURS = ROOT / "third_party" / "vendor-stock-refresh"  # README (and a git-ignored local copy of the MPQ)
VSR_FILES = ("dll", "mpq", "licence", "notices", "config")
VSR_FROM = {"dll": "d2rl-ruffneckk-vendor-stock-refresh.dll", "licence": "LICENSE-vendor-stock-refresh.txt",
            "config": "ruffneckk-vendor-stock-refresh.toml"}  # in build/vendorstockrefresh/Release
FD_BUILD = ROOT / "build" / "floatingdamage"
FD_SRC = ROOT / "build" / "floatingdamage-src"
FD_OURS = ROOT / "third_party" / "floating-damage-mxl2012"  # the patches, our tests, the font
FD_FILES = ("dll", "licence", "notices", "font", "font_licence", "config")
FD_FROM = {"dll": "d2rl-ruffneckk-floating-damage.dll", "licence": "LICENSE-floating-damage.txt",
           "font": "ruffneckk-floating-damage-font.ttf", "font_licence": "LICENSE-floating-damage-font.txt",
           "config": "ruffneckk-floating-damage.toml"}  # in build/floatingdamage/Release
EHB_BUILD = ROOT / "build" / "enemyhealthbars"
EHB_SRC = ROOT / "build" / "enemyhealthbars-src" / "EnemyHealthBars"
EHB_OURS = ROOT / "third_party" / "enemy-health-bars-mxl2012"  # the patches
EHB_FILES = ("dll", "licence", "notices", "imgui_licence", "mapsense_licence", "sdk_licence", "source", "config")
# where each shipped file comes from in build/enemyhealthbars (tools/build_enemyhealthbars.ps1)
EHB_FROM = {"dll": "Release/d2rl-enemy-health-bars.dll", "licence": "LICENSE", "notices": "THIRD_PARTY.md",
            "imgui_licence": "licenses/ImGui.txt", "mapsense_licence": "licenses/MapSense-API-LICENSE.txt",
            "sdk_licence": "licenses/PluginSDK.txt", "source": "d2rl-enemy-health-bars-source.zip",
            "config": "enemy-health-bars.toml"}
# The player's own settings: the downloader writes these only when they are missing (docs/release.md).
PRESERVE = ["d2rloader/config/d2rloader.toml", "d2rloader/config/mxl2012-core.toml"]
SCHEMA = 2  # 2: the 7z ("archive") replaced the zip; the downloader installs from it or from objects (docs/release.md)
STAMP = (2026, 1, 1, 0, 0, 0)  # the staged files' mtime
# 7z: LZMA2, one solid block, multithreaded. No time stamps go in the archive (-mtm/-mtc/-mta off) and the staged files get
# STAMP as mtime anyway; the same input gives the same bytes with the same 7-Zip build (docs/release.md).
SEVENZ_ARGS = ["a", "-t7z", "-m0=lzma2", "-mx=7", "-ms=on", "-mmt=on", "-mtm=off", "-mtc=off", "-mta=off", "-bd", "-y"]
SEVENZ_NAMES = ("7z", "7zz", "7za", "7zr")
NO_7Z = ("no 7-Zip found (Program Files\\7-Zip\\7z.exe, or 7z / 7zz / 7za / 7zr on PATH). A release is a .7z only: install "
         "7-Zip (https://www.7-zip.org; Debian / Ubuntu: apt install 7zip) and run again")

FORBIDDEN = re.compile(r"(^|/)(mxl2012-testharness[^/]*|legacy169-testharness[^/]*|mxl2012-core-off\.txt|drawcap-probe\.txt|drawcap-nopatch\.txt|drawcap-stats\.csv|input-bindings\.toml|imgui\.ini|debugsettings\.json)$"
                       r"|\.(d2s|d2i|d2x|d2rl|ctc|ctl|key|map|ma\d|log|dmp|pdb|orig)$", re.I)  # saves: D2R and D2RLoader sidecars


def plugin_version() -> str:
    m = re.search(r'PluginVersion = "([^"]+)"', (ROOT / "plugin" / "src" / "mxl2012_core.cpp").read_text("utf-8"))
    return m.group(1)


def drawcap_version() -> str:
    m = re.search(r'PluginVersion = "([^"]+)"', (ROOT / "drawcap" / "src" / "drawcap.cpp").read_text("utf-8"))
    return m.group(1) if m else "?"


def statbook_version() -> str:
    m = re.search(r'PluginVersion = "([^"]+)"', (ROOT / "statbook" / "src" / "statbook.cpp").read_text("utf-8"))
    return m.group(1) if m else "?"


def plugin_manifest_abi(data: bytes):
    """The plugin ABI in a DLL's D2RLoader plugin manifest (RCDATA resource 0x3e9, one DWORD; D2RLoader rejects a DLL without
    it as "an old alpha plugin"): None when the bytes are not a PE image, 0 when the PE has no manifest."""
    import struct
    try:
        pe = struct.unpack_from("<I", data, 0x3c)[0]
        if data[pe:pe + 4] != b"PE\0\0":
            return None
    except struct.error:
        return None
    try:
        nsec, optsize = struct.unpack_from("<H", data, pe + 6)[0], struct.unpack_from("<H", data, pe + 20)[0]
        opt = pe + 24
        dirs = opt + (112 if struct.unpack_from("<H", data, opt)[0] == 0x20b else 96)
        rsrc = struct.unpack_from("<I", data, dirs + 2 * 8)[0]  # data directory 2: resources
        secs = [struct.unpack_from("<IIII", data, opt + optsize + 40 * i + 8) for i in range(nsec)]  # vsize, va, rawsize, raw

        def off(rva):
            return next(raw + rva - va for vsize, va, rawsize, raw in secs if va <= rva < va + max(vsize, rawsize))

        def find(table, want):
            named, ids = struct.unpack_from("<HH", data, table + 12)
            for k in range(named + ids):
                ident, target = struct.unpack_from("<II", data, table + 16 + 8 * k)
                if ident == want:
                    return target
            return None

        if not rsrc:
            return 0
        root = off(rsrc)
        kind = find(root, 10)  # RT_RCDATA
        name = find(root + (kind & 0x7fffffff), 0x3e9) if kind is not None and kind & 0x80000000 else None
        if name is None or not name & 0x80000000:
            return 0
        entry = struct.unpack_from("<II", data, root + (name & 0x7fffffff) + 16)[1]  # the first language
        if entry & 0x80000000:
            return 0
        rva, size = struct.unpack_from("<II", data, root + entry)
        return struct.unpack_from("<I", data, off(rva))[0] if size >= 4 else 0
    except (struct.error, StopIteration):
        return 0


def check_drawcap(dll: Path) -> list:
    """Problems of a drawcap.dll for a release: it must be the drawcap plugin of this source's version and, a real PE image,
    carry the D2RLoader plugin manifest (the test fixtures' fake DLLs are not PE images)."""
    b = dll.read_bytes()
    if b"Draw List Cap\0" not in b or b"drawcap\0" not in b or drawcap_version().encode() + b"\0" not in b:
        return [f"{dll} is not drawcap {drawcap_version()} (build it with tools/build_plugin.ps1)"]
    if plugin_manifest_abi(b) == 0:
        return [f"{dll} has no D2RLoader plugin manifest, D2RLoader rejects it (drawcap/src/drawcap.rc)"]
    return []


def check_statbook(dll: Path) -> list:
    """Problems of a statbook.dll for a release, as check_drawcap."""
    b = dll.read_bytes()
    if b"Stat Book\0" not in b or b"statbook\0" not in b or statbook_version().encode() + b"\0" not in b:
        return [f"{dll} is not statbook {statbook_version()} (build it with tools/build_plugin.ps1)"]
    if plugin_manifest_abi(b) == 0:
        return [f"{dll} has no D2RLoader plugin manifest, D2RLoader rejects it (statbook/src/statbook.rc)"]
    return []


def build_release_plugin() -> Path:
    """tools/build_plugin.ps1 -Release: the dev DLL (build/plugin) and the player DLL (-DMXL_RELEASE=ON, build/plugin-release).
    The script finds CMake (PATH or Visual Studio's) and the PluginSDK (.mxl-local.json, else the submodule) and never
    downloads anything (a bare `cmake` is not on PATH on the build PC, and `git submodule update` would need the network)."""
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise SystemExit("no PowerShell to run tools/build_plugin.ps1 -Release: build the plugin there and pass --plugin DLL")
    subprocess.check_call([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(ROOT / "tools" / "build_plugin.ps1"), "-Release"], cwd=ROOT)
    return RELEASE_BUILD / "Release" / "mxl2012-core.dll"


def pinned_commit(path: str) -> str:
    """The commit a gitlink of this repo pins (index, as HEAD in a clean checkout)."""
    out = subprocess.run(["git", "ls-files", "-s", path], cwd=ROOT, capture_output=True, text=True).stdout.split()
    if len(out) < 2 or out[0] != "160000":
        raise SystemExit(f"{path} is not a pinned submodule of this repo")
    return out[1]


def legacy169_commit() -> str:
    """The D2R-Legacy169 commit this repo pins: the gitlink third_party/D2R-Legacy169."""
    return pinned_commit("third_party/D2R-Legacy169")


def buffhud_commit() -> str:
    """The d2rl-buff-hud fork commit this repo pins: the gitlink third_party/d2rl-buff-hud."""
    return pinned_commit("third_party/d2rl-buff-hud")


def beltrefill_commit() -> str:
    """The auto-belt-refill commit this repo pins: the gitlink third_party/auto-belt-refill."""
    return pinned_commit("third_party/auto-belt-refill")


def beltrefill_patches(ours: Path = BELTREFILL_OURS) -> list:
    """Our patches as tools/build_beltrefill.ps1 records them in PATCHES: "<sha256>  <name>", in name order."""
    return [f"{sha256(p)}  {p.name}" for p in sorted(ours.glob("*.patch"), key=lambda p: p.name)]


def controllerqol_commit() -> str:
    """The Pyre-Flies/D2R-Mods commit this repo pins (controller-qol's source): the gitlink third_party/D2R-Mods."""
    return pinned_commit("third_party/D2R-Mods")


def controllerqol_patches(ours: Path = CONTROLLERQOL_OURS) -> list:
    """Our patches as tools/build_controllerqol.ps1 records them in PATCHES: "<sha256>  <name>", in name order."""
    return [f"{sha256(p)}  {p.name}" for p in sorted(ours.glob("*.patch"), key=lambda p: p.name)]


def controllerqol_profile(excel: Path, out: Path = CONTROLLERQOL_PROFILE) -> Path:
    """The mxl2012 skill seed for controller-qol from a finished build's skills.txt / skilldesc.txt (docs/controller-support.md
    section 5): out/mxl2012.overrides.toml."""
    import controller_skill_profile as csp
    text, _entries = csp.generate(csp.read_table(excel / "skills.txt"), csp.read_table(excel / "skilldesc.txt"),
                                  json.loads((csp.DATA / "controller_skill_overrides.json").read_text(encoding="utf-8")))
    out.mkdir(parents=True, exist_ok=True)
    path = out / "mxl2012.overrides.toml"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def build_controllerqol(profile: Path) -> Path:
    """tools/build_controllerqol.ps1: Controller QOL Updates.dll from the pinned commit's source with our patches and `profile`
    embedded as its skill defaults (its unit tests run)."""
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise SystemExit("no PowerShell to run tools/build_controllerqol.ps1: build Controller QOL there and pass --controllerqol DLL")
    subprocess.check_call([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(ROOT / "tools" / "build_controllerqol.ps1"), "-SkillProfile", str(profile)], cwd=ROOT)
    return CONTROLLERQOL_BUILD / "Release" / "Controller QOL Updates.dll"


def check_controllerqol(dll: Path) -> list:
    """Problems of a Controller QOL build for a release: the pinned version, and our patched build (its embedded config has
    the belt_actions switch, off)."""
    b = dll.read_bytes()
    problems = []
    if b"controller-qol-updates\0" not in b or CONTROLLERQOL["version"].encode() + b"\0" not in b:
        problems.append(f"{dll} does not carry Controller QOL Updates version {CONTROLLERQOL['version']}")
    if b"belt_actions = false" not in b:
        problems.append(f"{dll} is not our patched build (no belt_actions switch): build it with tools/build_controllerqol.ps1")
    return problems


def build_legacy169() -> Path:
    """tools/build_legacy169.ps1: legacy169.dll from the pinned commit's source (release options, its unit tests run)."""
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise SystemExit("no PowerShell to run tools/build_legacy169.ps1: build legacy169.dll there and pass --legacy169 DLL")
    subprocess.check_call([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(ROOT / "tools" / "build_legacy169.ps1")], cwd=ROOT)
    return LEGACY169_BUILD / "Release" / "legacy169.dll"


def check_legacy169(dll: Path) -> list:
    """Problems of a legacy169.dll for a release: no test build (harness or bad-bytes table), the pinned version."""
    b = dll.read_bytes()
    problems = []
    if b"legacy169-testharness" in b or b"-test\0" in b:
        problems.append(f"{dll} is a legacy169 test build (build it with tools/build_legacy169.ps1)")
    if b"legacy169" not in b or LEGACY169["version"].encode() + b"\0" not in b:
        problems.append(f"{dll} does not carry legacy169 version {LEGACY169['version']}")
    return problems


def build_buffhud() -> Path:
    """tools/build_buffhud.ps1: d2rl-buff-panel.dll + .mpq from the pinned commit's source (the fork's release preset and tests)."""
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise SystemExit("no PowerShell to run tools/build_buffhud.ps1: build Buff HUD there and pass --buffhud DLL")
    subprocess.check_call([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(ROOT / "tools" / "build_buffhud.ps1")], cwd=ROOT)
    return BUFFHUD_BUILD / "Release" / "d2rl-buff-panel.dll"


def check_buffhud(dll: Path) -> list:
    """Problems of a Buff HUD build for a release: our fork (its buff-panel.toml switch is embedded), the pinned version, and
    a packed companion MPQ next to the DLL."""
    b = dll.read_bytes()
    problems = []
    if b"buff-panel" not in b or BUFFHUD["version"].encode() + b"\0" not in b:
        problems.append(f"{dll} does not carry Buff HUD version {BUFFHUD['version']}")
    if b"[buff_panel]" not in b:
        problems.append(f"{dll} is not our fork's build (no buff-panel.toml embedded): build it with tools/build_buffhud.ps1")
    mpq = dll.with_suffix(".mpq")
    if not mpq.is_file():
        problems.append(f"no {mpq.name} next to {dll}")
    elif mpq.read_bytes()[:4] != b"MPQ\x1a":
        problems.append(f"{mpq} is not a packed MPQ")
    return problems


def charminv_dir(given: Path = None) -> Path:
    """The folder with CharmInv's two files: `given` (--charminv) as it is, else MXL_CHARMINV_DIR, else third_party/charm-inv
    when it holds both, else <MXL2012_RUNS>/shared/charm-inv-<version>. None when none of them has both files."""
    if given is not None:
        return given
    names = [Path(CHARMINV[k]).name for k in ("dll", "mpq")]
    env = os.environ.get("MXL_CHARMINV_DIR")
    for d in (Path(env) if env else None, CHARMINV_OURS, fxpaths.localconfig.shared_dir() / f"charm-inv-{CHARMINV['version']}"):
        if d is not None and all((d / n).is_file() for n in names):
            return d
    return None


def check_charminv(folder: Path) -> list:
    """Problems of CharmInv's DLL and MPQ in `folder` (as they go into the package): both there, the pinned bytes."""
    problems = []
    for k in ("dll", "mpq"):
        f = folder / Path(CHARMINV[k]).name
        if not f.is_file():
            problems.append(f"no {f.name} in {folder}")
        elif f.stat().st_size != CHARMINV["size"][k] or sha256(f) != CHARMINV["sha256"][k]:
            problems.append(f"{f} is not CharmInv {CHARMINV['version']} (sha256 {sha256(f)[:16]}..., want "
                            f"{CHARMINV['sha256'][k][:16]}...)")
    return problems


def dof_dir(given: Path = None) -> Path:
    """The folder with Damage Overflow Fix's DLL: `given` (--dof) as it is, else MXL_DOF_DIR, else third_party/damage-overflow-fix
    when it holds it, else <MXL2012_RUNS>/shared/damage-overflow-fix-<version>. None when none of them has it."""
    if given is not None:
        return given
    name = Path(DOF["dll"]).name
    env = os.environ.get("MXL_DOF_DIR")
    for d in (Path(env) if env else None, DOF_OURS, fxpaths.localconfig.shared_dir() / f"damage-overflow-fix-{DOF['version']}"):
        if d is not None and (d / name).is_file():
            return d
    return None


def check_dof(folder: Path) -> list:
    """Problems of Damage Overflow Fix's DLL in `folder` (as it goes into the package): there, the pinned bytes."""
    f = folder / Path(DOF["dll"]).name
    if not f.is_file():
        return [f"no {f.name} in {folder}"]
    if f.stat().st_size != DOF["size"] or sha256(f) != DOF["sha256"]:
        return [f"{f} is not Damage Overflow Fix {DOF['version']} (sha256 {sha256(f)[:16]}..., want {DOF['sha256'][:16]}...)"]
    return []


def dof_config_problems(text: str) -> list:
    """Our settings the package must carry: no per-hit log, no line per site, leech on."""
    want = {"debug_log": "false", "log_each_site": "false", "leech": "true"}
    got = dict(re.findall(r"(?m)^(\w+)\s*=\s*(\w+)\s*$", text))
    return [f"{DOF['config']}: {k} must be {v}" for k, v in want.items() if got.get(k) != v]


def md_data(folder: Path) -> dict:
    """Monster Display's HD files in a release folder (`folder`/MonsterDisplay/...) -> their paths in mxl2012.mpq/data."""
    src = folder / "MonsterDisplay"
    out = {src / name: rel for name, rel in MD_LAYOUTS.items()}
    out.update({src / "monsterdisplayframes" / s: f"{MD_FRAMES}/{s}" for s in MD_SPRITES})
    return out


def md_package_paths() -> list:
    """Every file Monster Display adds to the package (its DLL, licence, config and HD files)."""
    return [MD[k] for k in MD_FILES] + [f"{NAME}.mpq/data/{rel}" for rel in md_data(Path(".")).values()]


def md_data_digest(folder: Path) -> str:
    """MD["data_sha256"] of a release folder: sha256 of its MonsterDisplay .json and .sprite files' "<sha256>  <path>"
    lines, sorted."""
    src = folder / "MonsterDisplay"
    files = sorted(p for p in src.rglob("*") if p.is_file() and p.suffix in (".json", ".sprite"))
    lines = "".join(f"{sha256(p)}  {p.relative_to(src).as_posix()}\n" for p in files)
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def md_dir(given: Path = None) -> Path:
    """The folder with Monster Display's DLL and its MonsterDisplay/ files (the author's release/ folder): `given` (--md)
    as it is, else MXL_MD_DIR, else <MXL2012_RUNS>/shared/monster-display-<version>. None when none of them has it."""
    if given is not None:
        return given
    name = Path(MD["dll"]).name
    env = os.environ.get("MXL_MD_DIR")
    for d in (Path(env) if env else None, fxpaths.localconfig.shared_dir() / f"monster-display-{MD['version']}"):
        if d is not None and (d / name).is_file() and (d / "MonsterDisplay").is_dir():
            return d
    return None


def check_md(folder: Path) -> list:
    """Problems of Monster Display in `folder` (the author's release folder): the pinned DLL and the pinned HD files."""
    f = folder / Path(MD["dll"]).name
    if not f.is_file():
        return [f"no {f.name} in {folder}"]
    if f.stat().st_size != MD["size"] or sha256(f) != MD["sha256"]:
        return [f"{f} is not Monster Display {MD['version']} (sha256 {sha256(f)[:16]}..., want {MD['sha256'][:16]}...)"]
    missing = [p.name for p in md_data(folder) if not p.is_file()]
    if missing:
        return [f"{folder / 'MonsterDisplay'} lacks " + ", ".join(missing)]
    if md_data_digest(folder) != MD["data_sha256"]:
        return [f"{folder / 'MonsterDisplay'} is not Monster Display {MD['version']}'s (its .json / .sprite files differ)"]
    return []


def md_config_problems(text: str) -> list:
    """The package's Monster Display config: on, resistances as the hovering player's hits meet them, and Median's
    minion affixes 36-39 (ghostly, fanatic, possessed, berserk) hidden on minions."""
    values = toml_values(text)
    want = {"enabled": "true", "resistances.mode": '"effective"'}
    problems = [f"{MD['config']}: {k} must be {v}" for k, v in want.items() if values.get(k) != v]
    hidden = values.get("text.minion_hidden_affixes", "").strip("[]").replace(" ", "").split(",")
    missing = [i for i in MD_MINION_HIDDEN if i not in hidden]
    if missing:
        problems.append(f"{MD['config']}: minion_hidden_affixes must hold {', '.join(missing)}")
    return problems


def vsr_mpq_dir(given: Path = None) -> Path:
    """The folder with Vendor Stock Refresh's companion MPQ: `given` (--vsr-mpq) as it is, else MXL_VSR_MPQ_DIR, else
    third_party/vendor-stock-refresh when it holds it, else <MXL2012_RUNS>/shared/vendor-stock-refresh-<version>."""
    if given is not None:
        return given
    name = Path(VSR["mpq"]).name
    env = os.environ.get("MXL_VSR_MPQ_DIR")
    for d in (Path(env) if env else None, VSR_OURS,
              fxpaths.localconfig.shared_dir() / f"vendor-stock-refresh-{VSR['version']}"):
        if d is not None and (d / name).is_file():
            return d
    return None


def check_vsr_mpq(folder: Path) -> list:
    f = folder / Path(VSR["mpq"]).name
    if not f.is_file():
        return [f"no {f.name} in {folder}"]
    if f.stat().st_size != VSR["mpq_size"] or sha256(f) != VSR["mpq_sha256"]:
        return [f"{f} is not Vendor Stock Refresh {VSR['version']}'s companion MPQ (sha256 {sha256(f)[:16]}..., want "
                f"{VSR['mpq_sha256'][:16]}...)"]
    return []


def vsr_config_problems(text: str) -> list:
    """The package's Vendor Stock Refresh config: on, and no diagnostics log."""
    values = toml_values(text)
    want = {"plugin.enabled": "true", "diagnostics.enabled": "false"}
    return [f"{VSR['config']}: [{k.split('.')[0]}] {k.split('.')[1]} must be {v}" for k, v in want.items()
            if values.get(k) != v]


def build_vsr() -> Path:
    """tools/build_vendorstockrefresh.ps1: d2rl-ruffneckk-vendor-stock-refresh.dll from the pinned commit."""
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        raise SystemExit("no PowerShell to run tools/build_vendorstockrefresh.ps1: build it there and pass --vsr DLL")
    subprocess.check_call([pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(ROOT / "tools" / "build_vendorstockrefresh.ps1")], cwd=ROOT)
    return VSR_BUILD / "Release" / VSR_FROM["dll"]


def check_vsr(dll: Path) -> list:
    """Problems of a Vendor Stock Refresh DLL: the author's version."""
    if f"VendorStockRefresh {VSR['version']} by RuffnecKk".encode() not in dll.read_bytes():
        return [f"{dll} is not Vendor Stock Refresh {VSR['version']}: build it with tools/build_vendorstockrefresh.ps1"]
    return []


def toml_values(text: str) -> dict:
    """"section.key" -> value (the raw text, comments cut) of a flat TOML file."""
    out, section = {}, ""
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
        elif "=" in line:
            k, v = line.split("=", 1)
            out[f"{section}.{k.strip()}" if section else k.strip()] = v.strip()
    return out


def ehb_config_problems(text: str) -> list:
    """Our Enemy Health Bars defaults the package must carry: on, bars only on damaged monsters (show_full_health is the
    setting for all monsters), on all monsters, not only uniques and bosses (uniques_bosses_only, patch 0005, the key the
    Controls action "Enemy Health Bars Mode" sets), the dev-only capture option not on."""
    got = toml_values(text)
    want = {"bars.enabled": "true", "bars.show_full_health": "false", "bars.uniques_bosses_only": "false"}
    problems = [f"{EHB['config']}: {k.split('.', 1)[1]} must be {v}" for k, v in want.items() if got.get(k) != v]
    if got.get("bars.dev_keep_visible_unfocused", "false") != "false":
        problems.append(f"{EHB['config']}: dev_keep_visible_unfocused is for test captures only")
    return problems


FD_LEGACY_TEXT_SCALE = "2.5"  # owner, 2026-11-17: the numbers in legacy graphics 2.5 times their HD size


def fd_config_problems(text: str) -> list:
    """Floating Damage is on by default: [general] enabled = true (the setting that turns it off) and show_numbers = true
    (patch 0006, the key the Controls action "Floating Damage Numbers" sets), and its numbers are FD_LEGACY_TEXT_SCALE times
    bigger in legacy graphics: [appearance] legacy_text_scale (patch 0004)."""
    values = toml_values(text)
    problems = []
    if values.get("general.enabled") != "true":
        problems.append(f"{FD['config']}: [general] enabled must be true (on by default)")
    if values.get("general.show_numbers") != "true":
        problems.append(f"{FD['config']}: [general] show_numbers must be true (numbers shown by default)")
    if values.get("appearance.legacy_text_scale") != FD_LEGACY_TEXT_SCALE:
        problems.append(f"{FD['config']}: [appearance] legacy_text_scale must be {FD_LEGACY_TEXT_SCALE}")
    return problems


def fd_commit() -> str:
    """The RuffnecKk-D2RLoader-Suite commit this repo pins: the gitlink third_party/RuffnecKk-D2RLoader-Suite."""
    return pinned_commit("third_party/RuffnecKk-D2RLoader-Suite")


def fd_patches(ours: Path = FD_OURS) -> list:
    """Our Floating Damage patches as tools/build_floatingdamage.ps1 records them in PATCHES: "<sha256>  <name>"."""
    return [f"{sha256(p)}  {p.name}" for p in sorted(ours.glob("*.patch"), key=lambda p: p.name)]


def build_fd() -> Path:
    """tools/build_floatingdamage.ps1: d2rl-ruffneckk-floating-damage.dll from the pinned commit with our patches."""
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        raise SystemExit("no PowerShell to run tools/build_floatingdamage.ps1: build it there and pass --fd DLL")
    subprocess.check_call([pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(ROOT / "tools" / "build_floatingdamage.ps1")], cwd=ROOT)
    return FD_BUILD / "Release" / FD_FROM["dll"]


def check_fd(dll: Path) -> list:
    """Problems of a Floating Damage DLL: ours (the author's version, with our font patch's file name and our patch 0006's
    export for the Controls action in it)."""
    b = dll.read_bytes()
    if (FD["version"].encode() not in b or Path(FD["font"]).name.encode() not in b
            or b"Mxl2012FloatingDamageSetShownV1" not in b):
        return [f"{dll} is not Floating Damage {FD['version']} with our patches: build it with tools/build_floatingdamage.ps1"]
    return []


def fd_notices(src: Path) -> str:
    """One third-party file: the suite's THIRD_PARTY_NOTICES.md, then every licence text it keeps (third_party/notices/*.txt
    and the PluginSDK's LICENSE), each under its path."""
    parts = [(src / "THIRD_PARTY_NOTICES.md").read_text("utf-8")]
    for f in sorted((src / "third_party" / "notices").glob("*.txt")) + [src / "third_party" / "PluginSDK" / "LICENSE"]:
        parts.append(f"\n\n===== {f.relative_to(src).as_posix()} =====\n\n" + f.read_text("utf-8"))
    return "".join(parts).replace("\r\n", "\n")


def stage_fd(mod: Path, dll: Path, src: Path = FD_SRC, ours: Path = FD_OURS) -> None:
    """Floating Damage's DLL, licences, third-party notices and font into d2rloader/plugins/ (mod-scoped) and its config into
    d2rloader/config/. The build must come from the pinned commit with this repo's patches (tools/build_floatingdamage.ps1
    records both in build/floatingdamage-src)."""
    pinned = (src / "PINNED_COMMIT").read_text("ascii").strip() if (src / "PINNED_COMMIT").is_file() else ""
    if pinned != fd_commit():
        raise SystemExit(f"{src} is not the pinned commit {fd_commit()[:9]} (it is {pinned}): run tools/build_floatingdamage.ps1")
    applied = (src / "PATCHES").read_text("ascii").splitlines() if (src / "PATCHES").is_file() else []
    if [ln.strip() for ln in applied if ln.strip()] != fd_patches(ours):
        raise SystemExit(f"{src} was not built with the patches in {ours}: run tools/build_floatingdamage.ps1")
    for k in FD_FILES:
        target = mod / FD[k]
        target.parent.mkdir(parents=True, exist_ok=True)
        if k == "notices":
            target.write_text(fd_notices(src), encoding="utf-8", newline="\n")
            continue
        source = dll if k == "dll" else dll.parent / FD_FROM[k]
        if not source.is_file():
            raise SystemExit(f"no {source} (Floating Damage {k}): run tools/build_floatingdamage.ps1")
        if k == "config" and fd_config_problems(source.read_text("utf-8")):
            raise SystemExit("; ".join(fd_config_problems(source.read_text("utf-8"))))
        shutil.copy2(source, target)


def ehb_patches(ours: Path = EHB_OURS) -> list:
    """Our Enemy Health Bars patches as tools/build_enemyhealthbars.ps1 records them in PATCHES: "<sha256>  <name>"."""
    return [f"{sha256(p)}  {p.name}" for p in sorted(ours.glob("*.patch"), key=lambda p: p.name)]


def build_ehb() -> Path:
    """tools/build_enemyhealthbars.ps1: d2rl-enemy-health-bars.dll from the pinned source with our patches."""
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        raise SystemExit("no PowerShell to run tools/build_enemyhealthbars.ps1: build it there and pass --ehb DLL")
    subprocess.check_call([pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(ROOT / "tools" / "build_enemyhealthbars.ps1")], cwd=ROOT)
    return EHB_BUILD / EHB_FROM["dll"]


def check_ehb(dll: Path) -> list:
    """Problems of an Enemy Health Bars DLL: ours (the version our patch sets, the dev option of our second patch, the
    legacy graphics placement of our third, the mode export of our fifth)."""
    b = dll.read_bytes()
    problems = []
    if (EHB["version"].encode() not in b or b"dev_keep_visible_unfocused" not in b
            or b"legacy graphics placement" not in b or b"Mxl2012EnemyBarsSetModeV1" not in b):
        problems.append(f"{dll} is not Enemy Health Bars {EHB['version']} with our patches: build it with "
                        "tools/build_enemyhealthbars.ps1")
    return problems


def stage_ehb(mod: Path, dll: Path, src: Path = EHB_SRC, ours: Path = EHB_OURS) -> None:
    """Enemy Health Bars' DLL, the author's licence and notices, and the corresponding source (GPL) into d2rloader/plugins/
    (mod-scoped). The build must come from the pinned source with this repo's patches (PATCHES in the patched tree)."""
    applied = (src / "PATCHES").read_text("ascii").splitlines() if (src / "PATCHES").is_file() else []
    if [ln.strip() for ln in applied if ln.strip()] != ehb_patches(ours):
        raise SystemExit(f"{src} was not built with the patches in {ours}: run tools/build_enemyhealthbars.ps1")
    if EHB["commit"] not in (src / "SOURCE.txt").read_text("ascii"):
        raise SystemExit(f"{src} is not the source of commit {EHB['commit'][:9]}: run tools/build_enemyhealthbars.ps1")
    build = dll.parent.parent  # build/enemyhealthbars/Release/<dll>
    for k in EHB_FILES:
        source = dll if k == "dll" else build / EHB_FROM[k]
        if not source.is_file():
            raise SystemExit(f"no {source} (Enemy Health Bars {k}): run tools/build_enemyhealthbars.ps1")
        if k == "config" and ehb_config_problems(source.read_text("utf-8")):
            raise SystemExit("; ".join(ehb_config_problems(source.read_text("utf-8"))))
        (mod / EHB[k]).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, mod / EHB[k])


def build_beltrefill() -> Path:
    """tools/build_beltrefill.ps1: d2rl-auto-belt-refill.dll from the pinned commit's source with our patches."""
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise SystemExit("no PowerShell to run tools/build_beltrefill.ps1: build Auto Belt Refill there and pass --beltrefill DLL")
    subprocess.check_call([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(ROOT / "tools" / "build_beltrefill.ps1")], cwd=ROOT)
    return BELTREFILL_BUILD / "Release" / "d2rl-auto-belt-refill.dll"


def check_beltrefill(dll: Path) -> list:
    """Problems of an Auto Belt Refill build for a release: the pinned version, and not the author's prebuilt DLL (written for
    an older D2RLoader ABI, without the Median belt rows)."""
    b = dll.read_bytes()
    problems = []
    if b"auto-belt-refill\0" not in b or BELTREFILL["version"].encode() + b"\0" not in b:
        problems.append(f"{dll} does not carry Auto Belt Refill version {BELTREFILL['version']}")
    if hashlib.sha256(b).hexdigest() == BELTREFILL_AUTHOR_DLL:
        problems.append(f"{dll} is the author's prebuilt DLL (older D2RLoader ABI): build it with tools/build_beltrefill.ps1")
    return problems


def check_release_plugin(dll: Path, version: str) -> list:
    """Problems of a plugin DLL for a release: the test harness must be compiled out, and the version must be the release's."""
    b = dll.read_bytes()
    problems = []
    if b"mxl2012-testharness" in b:
        problems.append(f"{dll} has the test harness (build it with -DMXL_RELEASE=ON)")
    if version.encode() + b"\0" not in b:
        problems.append(f"{dll} does not carry PluginVersion {version}")
    return problems


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stage(mod: Path, version: str, plugin: Path, game: Path, data_from: Path = None, no_data: bool = False,
          legacy169: Path = None, buffhud: Path = None, beltrefill: Path = None, controllerqol: Path = None,
          profile: Path = None, drawcap: Path = None, charminv: Path = None, invtabs: Path = None,
          statbook: Path = None, dof: Path = None, ehb: Path = None, fd: Path = None, md: Path = None,
          vsr: Path = None, vsr_mpq: Path = None) -> None:
    if invtabs is not None and charminv is not None:
        raise SystemExit("invtabs and CharmInv cannot be staged together")
    if data_from is not None:
        legacy_fonts.check_tree(data_from)
    if mod.exists():
        shutil.rmtree(mod)
    data = mod / f"{NAME}.mpq" / "data"
    if data_from is not None:
        shutil.copytree(data_from, data)
    elif not no_data:
        install_mod.build_data(data, game)
    legacy_fonts.check_tree(data)
    install_mod.write_mod_files(mod, NAME, f"{NAME}/", plugin, {
        "modVersion": version, "website": REPO_URL,
        "description": "D2R-XL 2012: Median XL 2012 (v005) for Diablo II: Resurrected through D2RLoader."},
        drawcap, statbook)
    if legacy169 is not None:
        stage_legacy169(mod, legacy169)
    if buffhud is not None:
        stage_buffhud(mod, buffhud)
    if beltrefill is not None:
        stage_beltrefill(mod, beltrefill)
    if controllerqol is not None:
        stage_controllerqol(mod, controllerqol, profile)
    if invtabs is not None:
        stage_invtabs(mod, invtabs)
    if charminv is not None:
        stage_charminv(mod, charminv)
    if dof is not None:
        stage_dof(mod, dof)
    if ehb is not None:
        stage_ehb(mod, ehb)
    if fd is not None:
        stage_fd(mod, fd)
    if md is not None:
        stage_md(mod, md)
    if vsr is not None:
        stage_vsr(mod, vsr, vsr_mpq)
    # the data must be built for the charm inventory the package ships (tools/build.py --charm-inventory): invtabs' files and
    # classic Charms button only with invtabs, CharmInv's tables never with it
    wrong = [] if no_data else charm_inventory.data_problems(data, "invtabs" if invtabs is not None else "charminv")
    if wrong:
        raise SystemExit("; ".join(f"{NAME}.mpq/data/{w}" for w in wrong))


def stage_legacy169(mod: Path, dll: Path, src: Path = ROOT / "build" / "legacy169-src") -> None:
    """legacy169.dll into d2rloader/plugins/ (mod-scoped: only with this mod) and its default legacy169.toml from the pinned
    source (tools/build_legacy169.ps1 exports it to build/legacy169-src) into d2rloader/config/."""
    pinned = (src / "PINNED_COMMIT").read_text("ascii").strip() if (src / "PINNED_COMMIT").is_file() else None
    if pinned != legacy169_commit():
        raise SystemExit(f"{src} is not the pinned commit {legacy169_commit()[:9]} (it is {pinned}): run "
                         "tools/build_legacy169.ps1")
    shutil.copy2(dll, mod / LEGACY169["dll"])
    shutil.copy2(src / "legacy169.toml", mod / LEGACY169["config"])


def stage_buffhud(mod: Path, dll: Path, src: Path = ROOT / "build" / "buffhud-src") -> None:
    """d2rl-buff-panel.dll and its companion MPQ (the Median buff list is inside it) into d2rloader/plugins/ (mod-scoped), the
    fork's LICENSE and its PluginSDK's next to them, and the default buff-panel.toml into d2rloader/config/, all from the pinned
    source that tools/build_buffhud.ps1 exports to build/buffhud-src."""
    pinned = (src / "PINNED_COMMIT").read_text("ascii").strip() if (src / "PINNED_COMMIT").is_file() else None
    if pinned != buffhud_commit():
        raise SystemExit(f"{src} is not the pinned commit {buffhud_commit()[:9]} (it is {pinned}): run tools/build_buffhud.ps1")
    shutil.copy2(dll, mod / BUFFHUD["dll"])
    shutil.copy2(dll.with_suffix(".mpq"), mod / BUFFHUD["mpq"])
    shutil.copy2(src / "LICENSE", mod / BUFFHUD["licence"])
    shutil.copy2(src / "external" / "PluginSDK" / "LICENSE", mod / BUFFHUD["sdk_licence"])
    shutil.copy2(src / "buff-panel.toml", mod / BUFFHUD["config"])


def stage_beltrefill(mod: Path, dll: Path, src: Path = ROOT / "build" / "beltrefill-src", ours: Path = BELTREFILL_OURS) -> None:
    """d2rl-auto-belt-refill.dll into d2rloader/plugins/ (mod-scoped) and our auto-belt-refill.toml (the locked Median columns)
    into d2rloader/config/. The build must come from the pinned commit with this repo's patches (tools/build_beltrefill.ps1
    records both in build/beltrefill-src)."""
    pinned = (src / "PINNED_COMMIT").read_text("ascii").strip() if (src / "PINNED_COMMIT").is_file() else None
    if pinned != beltrefill_commit():
        raise SystemExit(f"{src} is not the pinned commit {beltrefill_commit()[:9]} (it is {pinned}): run tools/build_beltrefill.ps1")
    applied = (src / "PATCHES").read_text("ascii").splitlines() if (src / "PATCHES").is_file() else []
    if [ln.strip() for ln in applied if ln.strip()] != beltrefill_patches(ours):
        raise SystemExit(f"{src} was not built with the patches in {ours}: run tools/build_beltrefill.ps1")
    shutil.copy2(dll, mod / BELTREFILL["dll"])
    shutil.copy2(ours / "auto-belt-refill.toml", mod / BELTREFILL["config"])


def stage_controllerqol(mod: Path, dll: Path, profile: Path, src: Path = CONTROLLERQOL_SRC, ours: Path = CONTROLLERQOL_OURS) -> None:
    """Controller QOL Updates.dll into d2rloader/plugins/ (mod-scoped) with PyreFly's LICENSE and the PluginSDK's next to it, and
    its patched controller-qol-updates.toml (belt_actions = false) into d2rloader/config/. The build must come from the pinned
    commit with this repo's patches and `profile` (this package's skill seed) embedded: tools/build_controllerqol.ps1 records
    all three in build/controllerqol-src."""
    pinned = (src / "PINNED_COMMIT").read_text("ascii").strip() if (src / "PINNED_COMMIT").is_file() else None
    if pinned != controllerqol_commit():
        raise SystemExit(f"{src} is not the pinned commit {controllerqol_commit()[:9]} (it is {pinned}): run tools/build_controllerqol.ps1")
    applied = (src / "PATCHES").read_text("ascii").splitlines() if (src / "PATCHES").is_file() else []
    if [ln.strip() for ln in applied if ln.strip()] != controllerqol_patches(ours):
        raise SystemExit(f"{src} was not built with the patches in {ours}: run tools/build_controllerqol.ps1")
    seed = (src / "SKILL_PROFILE").read_text("ascii").strip() if (src / "SKILL_PROFILE").is_file() else None
    if profile is None or seed != sha256(profile):
        raise SystemExit(f"{src} was not built with this package's skill seed {profile}: run tools/build_controllerqol.ps1 "
                         "-SkillProfile (package_release.py does)")
    shutil.copy2(dll, mod / CONTROLLERQOL["dll"])
    shutil.copy2(src / "plugins" / "controller-qol" / "controller-qol-updates.toml", mod / CONTROLLERQOL["config"])
    shutil.copy2(src / "LICENSE", mod / CONTROLLERQOL["licence"])
    shutil.copy2(src / "PluginSDK-LICENSE", mod / CONTROLLERQOL["sdk_licence"])


def check_invtabs_data(data: Path) -> list:
    """invtabs' files missing from a mod data folder (mxl2012.mpq/data)."""
    return [f"{NAME}.mpq/data/{rel} is missing (invtabs: the build's invtabs steps, docs/invtabs.md \"Build wiring\")"
            for rel in INVTABS_DATA if not (data / rel).is_file()]


def invtabs_entry() -> dict:
    """The manifest's bundledPlugins entry of invtabs (credit to wild-healer, whose code it is built on)."""
    return {"name": INVTABS["name"], "author": INVTABS["author"], "upstream": INVTABS["upstream"],
            "upstreamCommit": INVTABS["upstream_commit"], "files": [INVTABS["dll"], INVTABS["config"]]}


def check_invtabs(dll: Path) -> list:
    if not dll.is_file():
        return [f"no invtabs.dll at {dll}"]
    body = dll.read_bytes()
    return [] if body.startswith(b"MZ") and b"invtabs\0" in body else [f"{dll} is not an invtabs plugin DLL"]


def stage_invtabs(mod: Path, dll: Path) -> None:
    if any((mod / CHARMINV[k]).exists() for k in CHARMINV_FILES):
        raise SystemExit("invtabs and CharmInv cannot be staged together")
    problems = check_invtabs(dll)
    if problems:
        raise SystemExit("\n".join(problems))
    for key, source in (("dll", dll), ("config", ROOT / "invtabs/invtabs.toml")):
        target = mod / INVTABS[key]
        target.parent.mkdir(parents=True, exist_ok=True)
        if key == "dll" or not target.exists():
            shutil.copy2(source, target)


def stage_charminv(mod: Path, folder: Path, ours: Path = CHARMINV_OURS) -> None:
    """CharmInv's DLL and companion MPQ (the author's bytes, checked) into d2rloader/plugins/ (mod-scoped) and our
    charm-inv.toml into d2rloader/config/."""
    if (mod / INVTABS["dll"]).exists():
        raise SystemExit("invtabs and CharmInv cannot be staged together")
    problems = check_charminv(folder)
    if problems:
        raise SystemExit("; ".join(problems))
    for k in ("dll", "mpq"):
        (mod / CHARMINV[k]).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(folder / Path(CHARMINV[k]).name, mod / CHARMINV[k])
    (mod / CHARMINV["config"]).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ours / "charm-inv.toml", mod / CHARMINV["config"])


def stage_dof(mod: Path, folder: Path, ours: Path = DOF_OURS) -> None:
    """Damage Overflow Fix's DLL (the author's bytes, checked) and its MIT licence into d2rloader/plugins/ (mod-scoped) and
    our config into d2rloader/config/."""
    problems = check_dof(folder) + dof_config_problems((ours / Path(DOF["config"]).name).read_text("utf-8"))
    if problems:
        raise SystemExit("; ".join(problems))
    for k, source in (("dll", folder / Path(DOF["dll"]).name), ("licence", ours / "LICENSE"),
                      ("config", ours / Path(DOF["config"]).name)):
        (mod / DOF[k]).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, mod / DOF[k])


def stage_md(mod: Path, folder: Path, ours: Path = MD_OURS) -> None:
    """Monster Display's DLL (the author's bytes, checked) and its MIT licence into d2rloader/plugins/ (mod-scoped), its
    config into d2rloader/config/, and its layouts and frame sprites into mxl2012.mpq/data. The mod's own data must not
    hold any of those files: the plugin's layouts replace the game's whole hover panel."""
    problems = check_md(folder) + md_config_problems((ours / Path(MD["config"]).name).read_text("utf-8"))
    data = mod / f"{NAME}.mpq" / "data"
    problems += [f"{NAME}.mpq/data/{rel} is already in the mod's data" for rel in md_data(folder).values()
                 if (data / rel).exists()]
    if problems:
        raise SystemExit("; ".join(problems))
    for k, source in (("dll", folder / Path(MD["dll"]).name), ("licence", ours / "LICENSE"),
                      ("config", ours / Path(MD["config"]).name)):
        (mod / MD[k]).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, mod / MD[k])
    for source, rel in md_data(folder).items():
        (data / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, data / rel)


def stage_vsr(mod: Path, dll: Path, mpq_dir: Path, src: Path = VSR_SRC) -> None:
    """Vendor Stock Refresh's DLL, companion MPQ (checked), licence and third-party notices into d2rloader/plugins/
    (mod-scoped) and its config into d2rloader/config/. The build must come from the pinned commit
    (tools/build_vendorstockrefresh.ps1 records it in build/vendorstockrefresh-src)."""
    pinned = (src / "PINNED_COMMIT").read_text("ascii").strip() if (src / "PINNED_COMMIT").is_file() else ""
    if pinned != fd_commit():
        raise SystemExit(f"{src} is not the pinned commit {fd_commit()[:9]} (it is {pinned}): run "
                         "tools/build_vendorstockrefresh.ps1")
    problems = check_vsr(dll) + check_vsr_mpq(mpq_dir)
    cfg = dll.parent / VSR_FROM["config"]
    problems += vsr_config_problems(cfg.read_text("utf-8")) if cfg.is_file() else [f"no {cfg}"]
    if problems:
        raise SystemExit("; ".join(problems))
    for k in VSR_FILES:
        target = mod / VSR[k]
        target.parent.mkdir(parents=True, exist_ok=True)
        if k == "notices":
            target.write_text(fd_notices(src), encoding="utf-8", newline="\n")
            continue
        source = mpq_dir / Path(VSR["mpq"]).name if k == "mpq" else dll if k == "dll" else dll.parent / VSR_FROM[k]
        if not source.is_file():
            raise SystemExit(f"no {source} (Vendor Stock Refresh {k}): run tools/build_vendorstockrefresh.ps1")
        shutil.copy2(source, target)


def preserve_list(mod: Path) -> list:
    """PRESERVE plus the bundled plugins' configs the package holds."""
    return PRESERVE + [c for c in (DRAWCAP["config"], STATBOOK["config"], INVTABS["config"], LEGACY169["config"], BUFFHUD["config"], BELTREFILL["config"], CONTROLLERQOL["config"],
                                   CHARMINV["config"], DOF["config"], EHB["config"], FD["config"],
                                   MD["config"], VSR["config"])
                       if (mod / c).is_file()]


def bundled_plugins(legacy169: bool, buffhud: bool, beltrefill: bool = False, controllerqol: bool = False,
                    charminv: bool = False, dof: bool = False, ehb: bool = False, fd: bool = False,
                    md: bool = False, vsr: bool = False) -> list:
    """The manifest's bundledPlugins: name, version, repository, source commit and files of each plugin the package holds."""
    out = []
    if legacy169:
        out.append({"name": LEGACY169["name"], "version": LEGACY169["version"], "repo": LEGACY169["repo"],
                    "commit": legacy169_commit(), "files": [LEGACY169["dll"], LEGACY169["config"]]})
    if buffhud:
        out.append({"name": BUFFHUD["name"], "version": BUFFHUD["version"], "repo": BUFFHUD["repo"],
                    "upstream": BUFFHUD["upstream"], "author": BUFFHUD["author"], "commit": buffhud_commit(),
                    "files": [BUFFHUD[k] for k in BUFFHUD_FILES]})
    if beltrefill:
        out.append({"name": BELTREFILL["name"], "version": BELTREFILL["version"], "repo": BELTREFILL["repo"],
                    "author": BELTREFILL["author"], "commit": beltrefill_commit(), "patches": beltrefill_patches(),
                    "files": [BELTREFILL[k] for k in BELTREFILL_FILES]})
    if controllerqol:
        out.append({"name": CONTROLLERQOL["name"], "version": CONTROLLERQOL["version"], "repo": CONTROLLERQOL["repo"],
                    "path": CONTROLLERQOL["path"], "author": CONTROLLERQOL["author"], "commit": controllerqol_commit(),
                    "patches": controllerqol_patches(), "files": [CONTROLLERQOL[k] for k in CONTROLLERQOL_FILES]})
    if charminv:
        out.append({"name": CHARMINV["name"], "version": CHARMINV["version"], "source": CHARMINV["source"],
                    "author": CHARMINV["author"], "sha256": dict(CHARMINV["sha256"]),
                    "files": [CHARMINV[k] for k in CHARMINV_FILES]})
    if dof:
        out.append({"name": DOF["name"], "version": DOF["version"], "repo": DOF["repo"], "path": DOF["path"],
                    "author": DOF["author"], "commit": DOF["commit"], "sha256": DOF["sha256"],
                    "files": [DOF[k] for k in DOF_FILES]})
    if ehb:
        out.append({"name": EHB["name"], "version": EHB["version"], "repo": EHB["repo"], "author": EHB["author"],
                    "licence": EHB["licence_id"], "commit": EHB["commit"], "patches": ehb_patches(),
                    "files": [EHB[k] for k in EHB_FILES]})
    if fd:
        out.append({"name": FD["name"], "version": FD["version"], "repo": FD["repo"], "path": FD["path"],
                    "author": FD["author"], "commit": fd_commit(), "patches": fd_patches(),
                    "files": [FD[k] for k in FD_FILES]})
    if md:
        out.append({"name": MD["name"], "version": MD["version"], "repo": MD["repo"], "path": MD["path"],
                    "author": MD["author"], "commit": MD["commit"], "sha256": MD["sha256"],
                    "files": md_package_paths()})
    if vsr:
        out.append({"name": VSR["name"], "version": VSR["version"], "repo": VSR["repo"], "path": VSR["path"],
                    "author": VSR["author"], "commit": fd_commit(), "hub": VSR["hub"],
                    "mpqSha256": VSR["mpq_sha256"], "files": [VSR[k] for k in VSR_FILES]})
    return out


def baselines(extract: Path = EXTRACT, cache: Path = None) -> list:
    """The folders holding D2R's own data/... files: the baseline extraction and the shared D2R cache (fxpaths.D2R_CACHE:
    the files the extraction lacks, e.g. animdata.d2, missiles.json), those that exist."""
    cache = fxpaths.D2R_CACHE if cache is None else cache
    return [b for b in (extract, cache) if b and (Path(b) / "data").is_dir()]


def drop_blizzard_copies(mod: Path, extract: Path = EXTRACT, cache: Path = None) -> int:
    """Remove files that are byte copies of D2R's own (same path under <baseline>/data, baselines()): the game has them
    already. dataversionbuild.txt is ours (install_mod writes it). -> number removed."""
    data = mod / f"{NAME}.mpq" / "data"
    n = 0
    roots = baselines(extract, cache)
    if not roots or not data.is_dir():
        return 0
    for p in sorted(data.rglob("*")):
        if not p.is_file() or p.name.lower() == "dataversionbuild.txt":
            continue
        rel = p.relative_to(data)
        size = p.stat().st_size
        for b in roots:
            twin = Path(b) / "data" / rel
            if twin.is_file() and twin.stat().st_size == size and twin.read_bytes() == p.read_bytes():
                p.unlink()
                n += 1
                for d in p.parents:  # a folder emptied this way is not ours either (no emptyDirs entry for it)
                    if d == data or any(d.iterdir()):
                        break
                    d.rmdir()
                break
    return n


def forbidden_files(mod: Path) -> list:
    return [p.relative_to(mod).as_posix() for p in mod.rglob("*") if p.is_file() and FORBIDDEN.search(p.relative_to(mod).as_posix())]


def file_list(mod: Path) -> list:
    return [{"path": p.relative_to(mod).as_posix(), "size": p.stat().st_size, "sha256": sha256(p)}
            for p in sorted(mod.rglob("*"), key=lambda q: q.relative_to(mod).as_posix()) if p.is_file()]


def empty_dirs(mod: Path) -> list:
    """Folders with nothing in them (d2rloader/patches): listed in the manifest, so the server builds the same 7z."""
    return sorted(p.relative_to(mod).as_posix() for p in mod.rglob("*") if p.is_dir() and not any(p.iterdir()))


def find_7z():
    """The 7-Zip command line: 7-Zip\\7z.exe under Program Files, else 7z / 7zz / 7za / 7zr on PATH. None when there is none."""
    for var in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(var)
        exe = Path(base) / "7-Zip" / "7z.exe" if base else None
        if exe and exe.is_file():
            return str(exe)
    for name in SEVENZ_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def fix_mtimes(mod: Path) -> None:
    """Every staged file and folder gets STAMP as its mtime."""
    t = time.mktime(STAMP + (0, 0, -1))
    for p in [mod, *mod.rglob("*")]:
        os.utime(p, (t, t))
    if os.name != "nt":
        # 7-Zip on Linux stores the Unix mode of every entry, so the umask would change the archive's bytes: files 0644
        # and folders 0755, the modes tools/dl_ingest.py rebuilds the server's copy with (Windows has no such bits)
        for p in [mod, *mod.rglob("*")]:
            if not p.is_symlink():
                os.chmod(p, 0o755 if p.is_dir() else 0o644)


def write_7z(mod: Path, out: Path, sevenzip=None) -> None:
    """Solid LZMA2 7z of the staged folder, top folder mxl2012/ (empty folders kept). Raises RuntimeError when there is no
    7-Zip or it fails; nothing is left behind then."""
    exe = sevenzip or find_7z()
    if not exe:
        raise RuntimeError(NO_7Z)
    fix_mtimes(mod)
    out.unlink(missing_ok=True)  # `7z a` would add to an existing archive
    r = subprocess.run([exe, *SEVENZ_ARGS, str(out.resolve()), mod.name], cwd=mod.parent, capture_output=True, text=True,
                       errors="replace")
    if r.returncode != 0 or not out.is_file():
        out.unlink(missing_ok=True)
        raise RuntimeError(f"7-Zip failed ({r.returncode}): {(r.stdout + r.stderr).strip()[-600:]}")


LOADER_HOST = "d2rloader.net"


def loader_problems(block: dict) -> list:
    """What keeps the downloader from installing the manifest's d2rloader block (the same rules as
    launcher/src/core/loaderpkg.cpp LoaderPackageUsable): a version, an https url on d2rloader.net ending in a .zip name,
    a size, a 64-digit sha256."""
    out = []
    if not block.get("version"):
        out.append("d2rloader.version is missing")
    url = urllib.parse.urlsplit(block.get("url") or "")
    host = (url.hostname or "").lower()
    if url.scheme != "https":
        out.append("d2rloader.url is not https://")
    elif host != LOADER_HOST and not host.endswith("." + LOADER_HOST):
        out.append(f"d2rloader.url is not on {LOADER_HOST}")
    elif not url.path.lower().endswith(".zip") or url.path.endswith("/.zip"):
        out.append("d2rloader.url does not name a .zip")
    size = block.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= 512 << 20:
        out.append("d2rloader.size is missing or out of range")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", block.get("sha256") or ""):
        out.append("d2rloader.sha256 is not 64 hex digits")
    return out


def manifest(version: str, files: list, archive_path: Path, complete: bool, dirs=(), preserve=None, bundled=()) -> dict:
    """archive_path: the .7z. The launcher installs from the objects (docs/release.md), never from the archive."""
    problems = loader_problems(D2RLOADER)
    if problems:
        raise ValueError("D2RLOADER: " + "; ".join(problems))
    return {
        "schemaVersion": SCHEMA,
        "name": NAME,
        "version": version,
        "pluginVersion": plugin_version(),
        "released": datetime.date.today().isoformat(),
        "complete": complete,  # false: a --no-data build (no mxl2012.mpq/data); not for players
        "d2r": D2R,
        "d2rloader": D2RLOADER,
        "launch": LAUNCH,
        "modFolder": NAME,  # the paths below are relative to <D2R>/mods/<modFolder>/
        "saveFolder": f"{NAME}/",  # under Saved Games/Diablo II Resurrected/mods/ (modinfo.json savepath)
        "preserve": PRESERVE if preserve is None else preserve,
        "bundledPlugins": list(bundled),  # our other plugins in the mod folder: name, version, repo, commit, files
        "archive": {"format": "7z", "name": archive_path.name, "size": archive_path.stat().st_size,
                    "sha256": sha256(archive_path)},  # the manual download
        "emptyDirs": list(dirs),  # folders the 7z holds although no file is in them (d2rloader/patches)
        "fileCount": len(files),
        "totalSize": sum(f["size"] for f in files),
        "files": files,
    }


UNPACK_7Z = ("Unpack `{archive}` into `<D2R folder>\\mods\\` so that `<D2R folder>\\mods\\mxl2012\\mxl2012.mpq\\modinfo.json` exists\n"
             "   (Windows 11 opens .7z files; otherwise use 7-Zip, https://www.7-zip.org).")

NOTES = """# D2R-XL 2012 {version}

D2R-XL 2012 is Median XL 2012 (v005, by Brother Laz) ported to Diablo II: Resurrected through the D2RLoader plugin mxl2012-core {plugin}.

## Requirements

- Diablo II: Resurrected. No game version or build is required; the mod was tested on D2R 3.3 and 3.4.
  On D2R 3.4, D2RLoader {loader} shows its own notice "This D2R version hasn't been fully tested yet" at each start:
  click OK, or tick "Don't remind me again for D2R 3.4" once.
- D2RLoader **{loader}** ({loader_url}, sha256 `{loader_sha}`). With another D2RLoader version the plugin installs nothing
  and shows "D2R-XL 2012 {plugin}: this D2RLoader version is not supported by the mod yet. The mod's engine changes are off."

## Install

1. Install D2RLoader {loader} from https://d2rloader.net/ into your D2R folder.
2. Run `D2R-XL-2012-Downloader.exe` (downloads from https://files.wyrd.games/mxl2012/) and press **Install** (or **Update**). It puts the mod
   in `<D2R folder>\\mods\\mxl2012` and changes nothing else.
3. How to play: press **Play** in the downloader (it starts `D2RLoader.exe -mod mxl2012` in your D2R folder). Or start
   `D2RLoader.exe` yourself: the first time, click the gear on the character screen, set Default Mod to D2R-XL 2012, Apply,
   and start D2RLoader again.

By hand (offline), into a D2R folder that has D2RLoader {loader}:

1. {unpack}
2. Set the default mod as in step 3 above, the D2RLoader.exe way (or `default_mod = "mxl2012"` in
   `<D2R folder>\\d2rloader\\config\\d2rloader.toml`).
3. Start `D2RLoader.exe`. Characters are saved in `Saved Games\\Diablo II Resurrected\\mods\\mxl2012\\`.
   To update, delete `mods\\mxl2012\\mxl2012.mpq\\data` and unpack the new release; keep your
   `mods\\mxl2012\\d2rloader\\config\\d2rloader.toml` if you changed it.

## Changes

- TODO

## Known issues

- TODO (docs/unported.md lists what is not ported yet)

## Checksums

See SHA256SUMS.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", help="release version (default: PluginVersion)")
    ap.add_argument("--plugin", type=Path, help="a release mxl2012-core.dll (default: build it with -DMXL_RELEASE=ON)")
    ap.add_argument("--drawcap", type=Path, help="a drawcap.dll of this source (default: build/drawcap/Release/drawcap.dll, "
                    "built by tools/build_plugin.ps1; --no-data builds leave it out when there is none)")
    ap.add_argument("--statbook", type=Path, help="a statbook.dll of this source (default: build/statbook/Release/statbook.dll, "
                    "built by tools/build_plugin.ps1; --no-data builds leave it out when there is none)")
    ap.add_argument("--legacy169", type=Path, help="a release legacy169.dll of the pinned commit (default: build it with "
                    "tools/build_legacy169.ps1; --no-data builds leave it out unless given)")
    ap.add_argument("--buffhud", type=Path, help="a release d2rl-buff-panel.dll of the pinned fork commit, its .mpq next to it "
                    "(default: build both with tools/build_buffhud.ps1; --no-data builds leave it out unless given)")
    ap.add_argument("--beltrefill", type=Path, help="a release d2rl-auto-belt-refill.dll of the pinned commit with our patches "
                    "(default: build it with tools/build_beltrefill.ps1; --no-data builds leave it out unless given)")
    ap.add_argument("--controllerqol", type=Path, help="a release 'Controller QOL Updates.dll' of the pinned commit with our "
                    "patches and this package's skill seed (default: build it with tools/build_controllerqol.ps1; --no-data "
                    "builds leave it out)")
    ap.add_argument("--charminv", type=Path, help="a folder holding CharmInv's d2rl-charm-inv.dll and .mpq (checked by sha256; "
                    "default: charminv_dir(); --no-data builds leave it out unless given)")
    ap.add_argument("--dof", type=Path, help="a folder holding Damage Overflow Fix's d2rl-celestialrayone-damage-overflow-fix.dll "
                    "(checked by sha256; default: dof_dir(); --no-data builds leave it out unless given)")
    ap.add_argument("--ehb", type=Path, help="a release d2rl-enemy-health-bars.dll of the pinned source with our patches, in "
                    "build/enemyhealthbars/Release with its licences and source zip (default: build it with "
                    "tools/build_enemyhealthbars.ps1; --no-data builds leave it out unless given)")
    ap.add_argument("--fd", type=Path, help="a release d2rl-ruffneckk-floating-damage.dll of the pinned commit with our patches, "
                    "its licences, font and config next to it (default: build it with tools/build_floatingdamage.ps1; "
                    "--no-data builds leave it out unless given)")
    ap.add_argument("--md", type=Path, help="the author's release folder of Monster Display: its "
                    "d2rl-celestialrayone-monster-display.dll and MonsterDisplay/ (checked by sha256; default: md_dir(); "
                    "--no-data builds leave it out)")
    ap.add_argument("--vsr", type=Path, help="a release d2rl-ruffneckk-vendor-stock-refresh.dll of the pinned commit, its "
                    "licence and config next to it (default: build it with tools/build_vendorstockrefresh.ps1; --no-data "
                    "builds leave it out unless given)")
    ap.add_argument("--vsr-mpq", type=Path, help="a folder holding Vendor Stock Refresh's companion "
                    "d2rl-ruffneckk-vendor-stock-refresh.mpq (checked by sha256; default: vsr_mpq_dir())")
    ap.add_argument("--no-bundled", action="store_true", help="leave out legacy169, Buff HUD, Auto Belt Refill, Controller "
                    "QOL, CharmInv, Damage Overflow Fix, Enemy Health Bars, Floating Damage, Monster Display and Vendor "
                    "Stock Refresh unless given "
                    "(unit tests; "
                    "tools/verify_package.py refuses such a package)")
    ap.add_argument("--data-from", type=Path, help="copy this finished mxl2012.mpq/data instead of building it")
    ap.add_argument("--no-data", action="store_true", help="no mxl2012.mpq/data (CI): manifest says complete=false")
    ap.add_argument("--game", type=Path, default=Path(install_mod.DEFAULT_GAME), help="D2R folder read for maps_hd (CASC)")
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    ap.add_argument("--launcher-min", help="oldest downloader that may install this release (manifest launcherMin): an older one "
                    "refuses it and offers its own update first")
    ap.add_argument("--notes", type=Path, help="release notes template (str.format fields as NOTES; default NOTES)")
    ap.add_argument("--invtabs", type=Path, help="opt in to invtabs (requires --no-charminv)")
    ap.add_argument("--no-charminv", action="store_true", help="omit CharmInv")
    ap.add_argument("--charm-inventory", choices=CHARM_INVENTORIES, default=charm_inventory.chosen(),
                    help="the package's charm inventory (default: MXL2012_CHARM_INVENTORY, else CHARM_INVENTORY; now %(default)s); "
                    "invtabs takes --invtabs or build/invtabs/Release/invtabs.dll and leaves CharmInv out. work/mod must be "
                    "built for it (tools/build.py --charm-inventory)")
    a = ap.parse_args()
    if a.charm_inventory == "invtabs":
        if a.charminv is not None:
            ap.error("invtabs and CharmInv cannot be staged together")
        a.no_charminv = True
        # a code-only package (--no-data, CI) carries no other plugin than the core, so no invtabs either unless it is named
        a.invtabs = a.invtabs or (None if a.no_data else INVTABS_DLL)
    if a.invtabs is not None and (a.charminv is not None or not a.no_charminv):
        ap.error("invtabs and CharmInv cannot be staged together")
    if a.invtabs is not None and check_invtabs(a.invtabs):
        ap.error("; ".join(check_invtabs(a.invtabs)))

    version = (a.version or plugin_version()).lstrip("v")
    if version != plugin_version():
        # One number for the release and the plugin inside it (the build guard and `mxl` show PluginVersion): a player
        # release must raise PluginVersion in plugin/src/mxl2012_core.cpp, even for a repackage. --no-data builds (CI, tests)
        # are not player releases and may differ.
        if not a.no_data:
            print(f"error: release {version} but PluginVersion is {plugin_version()}: set PluginVersion in "
                  f"plugin/src/mxl2012_core.cpp to {version} (or leave out --version)")
            return 1
        print(f"note: release {version}, plugin PluginVersion {plugin_version()} (--no-data: allowed)")
    sevenzip = find_7z()
    if not sevenzip:  # before the long part of the run
        print(f"error: {NO_7Z}")
        return 1
    if not a.no_data and a.data_from is None and not (install_mod.SRC / "global" / "excel").exists():
        print("work/mod/data is missing: run tools/build.py first")
        return 1
    if not a.no_data and not (EXTRACT / "data").is_dir():
        print(f"error: no D2R {install_mod.D2R_BUILD} baseline at {EXTRACT}, so Blizzard's own files cannot be left out: "
              f"{fxpaths.localconfig.SETUP_HINT} (or set MXL_D2R_EXTRACT)")
        return 1
    template = NOTES
    if a.notes:
        if not a.notes.is_file():
            print(f"no notes template at {a.notes}")
            return 1
        template = a.notes.read_text("utf-8")
    plugin = a.plugin or build_release_plugin()
    if not plugin.is_file():
        print(f"no plugin at {plugin}")
        return 1
    problems = check_release_plugin(plugin, plugin_version())
    drawcap = a.drawcap or install_mod.DRAWCAP
    if drawcap.is_file():
        problems += check_drawcap(drawcap)
    elif a.no_data and a.drawcap is None:
        drawcap = None
    else:
        problems.append(f"no drawcap.dll at {drawcap} (run tools/build_plugin.ps1)")
    statbook = a.statbook or install_mod.STATBOOK
    if statbook.is_file():
        problems += check_statbook(statbook)
    elif a.no_data and a.statbook is None:
        statbook = None
    else:
        problems.append(f"no statbook.dll at {statbook} (run tools/build_plugin.ps1)")
    legacy169 = a.legacy169 or (None if a.no_data or a.no_bundled else build_legacy169())
    if legacy169 is not None:
        problems += check_legacy169(legacy169) if legacy169.is_file() else [f"no legacy169.dll at {legacy169}"]
    buffhud = a.buffhud or (None if a.no_data or a.no_bundled else build_buffhud())
    if buffhud is not None:
        problems += check_buffhud(buffhud) if buffhud.is_file() else [f"no d2rl-buff-panel.dll at {buffhud}"]
    beltrefill = a.beltrefill or (None if a.no_data or a.no_bundled else build_beltrefill())
    if beltrefill is not None:
        problems += check_beltrefill(beltrefill) if beltrefill.is_file() else [f"no d2rl-auto-belt-refill.dll at {beltrefill}"]
    # the skill seed comes from this package's skills.txt, so a package without data has no Controller QOL
    profile = None
    if not a.no_data and (a.controllerqol or not a.no_bundled):
        profile = controllerqol_profile((a.data_from or install_mod.SRC) / "global" / "excel")
    controllerqol = a.controllerqol or (None if profile is None else build_controllerqol(profile))
    if controllerqol is not None:
        problems += (check_controllerqol(controllerqol) if controllerqol.is_file()
                     else [f"no 'Controller QOL Updates.dll' at {controllerqol}"])
    charminv = None if a.no_charminv else (charminv_dir(a.charminv) if a.charminv or not (a.no_data or a.no_bundled) else None)
    if not (a.no_data or a.no_bundled or a.no_charminv) and charminv is None:
        problems.append("CharmInv's d2rl-charm-inv.dll / .mpq not found: pass --charminv DIR (third_party/charm-inv/README.md)")
    if charminv is not None:
        problems += check_charminv(charminv)
    dof = dof_dir(a.dof) if a.dof or not (a.no_data or a.no_bundled) else None
    if not (a.no_data or a.no_bundled) and dof is None:
        problems.append("Damage Overflow Fix's DLL not found: pass --dof DIR (third_party/damage-overflow-fix/README.md)")
    if dof is not None:
        problems += check_dof(dof)
    ehb = a.ehb or (None if a.no_data or a.no_bundled else build_ehb())
    if ehb is not None:
        problems += check_ehb(ehb) if ehb.is_file() else [f"no d2rl-enemy-health-bars.dll at {ehb}"]
    fd = a.fd or (None if a.no_data or a.no_bundled else build_fd())
    if fd is not None:
        problems += check_fd(fd) if fd.is_file() else [f"no d2rl-ruffneckk-floating-damage.dll at {fd}"]
    # Monster Display's files go into the data, so a package without data has none of it
    md = None if a.no_data else (md_dir(a.md) if a.md or not a.no_bundled else None)
    if not (a.no_data or a.no_bundled) and md is None:
        problems.append("Monster Display's release folder not found: pass --md DIR (third_party/monster-display/README.md)")
    if md is not None:
        problems += check_md(md)
    vsr = a.vsr or (None if a.no_data or a.no_bundled else build_vsr())
    vsr_mpq = None
    if vsr is not None:
        problems += check_vsr(vsr) if vsr.is_file() else [f"no d2rl-ruffneckk-vendor-stock-refresh.dll at {vsr}"]
        vsr_mpq = vsr_mpq_dir(a.vsr_mpq)
        problems += (check_vsr_mpq(vsr_mpq) if vsr_mpq is not None else
                     ["Vendor Stock Refresh's companion MPQ not found: pass --vsr-mpq DIR "
                      "(third_party/vendor-stock-refresh/README.md)"])
    if problems:
        print("\n".join(problems))
        return 1

    a.out.mkdir(parents=True, exist_ok=True)
    mod = a.out / "stage" / NAME
    stage(mod, version, plugin, a.game, a.data_from, a.no_data, legacy169, buffhud, beltrefill, controllerqol, profile, drawcap, charminv, a.invtabs,
          statbook, dof, ehb, fd, md, vsr, vsr_mpq)
    dropped = drop_blizzard_copies(mod)
    if dropped:
        print(f"left out {dropped} files that are byte copies of D2R's own (extract/d2r/{install_mod.D2R_BUILD})")
    missing = [] if a.no_data else legacy_fonts.missing_clear(mod / f"{NAME}.mpq" / "data")
    if missing:
        print("error: the clear legacy fonts (the in-game setting's files) are missing, run tools/build.py with the repack "
              "archive (MXL2012_LEGACY_FONT_ARCHIVE): " + ", ".join(missing))
        return 1
    bad = forbidden_files(mod)
    if bad:
        print("refusing to package test or player files: " + ", ".join(bad[:20]))
        return 1

    for old in a.out.glob("D2R-XL-2012-*.zip"):  # an earlier packager's zip must not sit next to this release
        old.unlink()
    seven_path = a.out / f"D2R-XL-2012-{version}{'-nodata' if a.no_data else ''}.7z"
    t7 = time.time()
    try:
        write_7z(mod, seven_path, sevenzip)
    except RuntimeError as e:
        print(f"error: {e}")
        return 1
    t7 = time.time() - t7
    files = file_list(mod)
    man_path = a.out / "release-manifest.json"
    bundled = bundled_plugins(legacy169 is not None, buffhud is not None, beltrefill is not None, controllerqol is not None,
                              charminv is not None, dof is not None, ehb is not None, fd is not None,
                              md is not None, vsr is not None)
    if a.invtabs is not None:
        bundled.append(invtabs_entry())
    man = manifest(version, files, seven_path, not a.no_data, empty_dirs(mod), preserve_list(mod), bundled)
    if a.launcher_min:
        if not re.fullmatch(r"\d+\.\d+\.\d+", a.launcher_min):
            raise SystemExit(f"--launcher-min {a.launcher_min!r}: x.y.z")
        man["launcherMin"] = a.launcher_min
    man_path.write_text(json.dumps(man, indent=1) + "\n", encoding="utf-8")
    notes = a.out / f"RELEASE_NOTES-{version}.md"
    notes.write_text(template.format(version=version, plugin=plugin_version(), build=D2R["build"], d2rver=D2R["version"],
                                  loader=D2RLOADER["version"], loader_url=D2RLOADER["url"], loader_sha=D2RLOADER["sha256"],
                                  unpack=UNPACK_7Z.format(archive=seven_path.name), archive=seven_path.name,
                                  archive_mb=round(seven_path.stat().st_size / 1e6), unpacked_mb=round(sum(f["size"] for f in files) / 1e6),
                                  file_count=len(files), save_folder=f"{NAME}/"), encoding="utf-8")
    (a.out / "SHA256SUMS").write_text("".join(f"{sha256(p)}  {p.name}\n" for p in (seven_path, man_path, notes)), encoding="utf-8")
    shutil.rmtree(a.out / "stage")
    print(f"{seven_path.name}: {len(files)} files, {sum(f['size'] for f in files) / 1e6:.0f} MB unpacked, "
          f"{seven_path.stat().st_size / 1e6:.0f} MB as 7z ({t7:.0f} s); {man_path.name}, {notes.name}, SHA256SUMS in {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

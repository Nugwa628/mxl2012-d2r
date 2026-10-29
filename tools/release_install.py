"""Put a game slot on a PLAYER install: the published D2R-XL 2012 Downloader installs the live release (7z from
files.werdegames.com) and the slot's runs use the release's launch arguments, instead of tools/install_mod.py's
developer install (docs/testing.md "Test what players get").

  py -3 tools/release_install.py install --slot N [--channel stable] [--downloader <exe>] [--release-dll]
  py -3 tools/release_install.py install --slot N --package <dist>\\D2R-XL-2012-<v>.7z [--release-dll]
  py -3 tools/release_install.py restore --slot N
  py -3 tools/release_install.py status  --slot N

`install` needs the slot lock held by MXL_RUN (like install_mod.py), never runs on slot 1 (the owner's game in Program
Files: the backup would be a new folder next to it, `C:\\Program Files (x86)\\Diablo II Resurrected.release-backup`, and a
player install there is the owner's to make) and refuses while a game runs in the slot. It moves the slot's mods\\mxl2012 aside (<slot>.release-backup, same volume), then runs `D2R-XL-2012-Downloader.exe --cli install` into the empty mod folder, exactly
as a player's first install. `--package` tests a release candidate that is not published instead: the hand-copied alpha's
player path (tools/data/release_notes_alpha.md, Install step 2), its 7z unpacked with 7-Zip into the slot's `mods\\`
folder, launch arguments from the release-manifest.json next to it; nothing is downloaded. Afterwards only what the background harness strictly needs is changed, and each change is
written to <runs>\\release-install-sN\\release-install.json:
  - mxl2012-core.dll: the release DLL has the test harness compiled out (cmake -DMXL_RELEASE=ON), so background input and
    `volserial` (slots 2 to 5) need the dev build of the same code: build\\plugin\\Release\\mxl2012-core.dll goes in, the
    release DLL is kept in the state folder. --release-dll keeps the release DLL (the game cannot be driven then; useful
    for its mxl2012-core.log only).
  - modinfo.json savepath: the slot's own save folder (mxl2012-sN/), never slot 1's mxl2012/.
  - launch arguments: the release's (manifest `launch`, "" since 0.69.2: no -txt) plus "-w" (windowed: the harness sizes
    and captures the window; it does not change what data is loaded), kept in release-install.json. game_ctl starts the
    loader with them and `-mod mxl2012` (tools/slot_share.py). The slot's game-wide d2rloader.toml is shared with the other mod
    and is not edited (the release's default_mod is what a player sets; on a slot the command line picks the mod).
`restore` deletes the release install and puts the backup back (and the d2rloader.toml backup of an older install).
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game_slots  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://files.werdegames.com/mxl2012/"
DEV_DLL = os.path.join(ROOT, "build", "plugin", "Release", "mxl2012-core.dll")
MOD = game_slots.MOD


def state_dir(n):
    return os.path.join(game_slots.RUNS, f"release-install-s{n}")


def backup_dir(n):
    return os.path.normpath(game_slots.slot_dir(n)) + ".release-backup"


def toml_path(n):
    return os.path.join(game_slots.slot_dir(n), "d2rloader", "config", "d2rloader.toml")


def fetch(url):
    # the channel file is served with max-age=14400: a query string asks for the current one
    req = urllib.request.Request(url + ("&" if "?" in url else "?") + f"t={int(time.time())}", headers={"User-Agent": "mxl2012-d2r release_install"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def manifest(channel):
    ch = json.loads(fetch(SITE + f"channels/{channel}.json"))
    raw = fetch(SITE + ch["manifest"])
    if hashlib.sha256(raw).hexdigest() != ch["manifestSha256"]:
        raise SystemExit("release manifest does not match the channel's sha256")
    return json.loads(raw)


def downloader(man, folder):
    """The release's own downloader (manifest `launcher`), checked against its sha256, in its own folder. A release
    published without a `launcher` entry (0.69.5, 0.69.10) falls back to this checkout's built downloader, which is what
    players already have; with neither, it stops before anything on the slot is touched."""
    l = man.get("launcher")
    if not l:
        built = os.path.join(ROOT, "build", "launcher", "Release", "D2R-XL-2012-Downloader.exe")
        if os.path.isfile(built):
            print(f"release {man['version']} lists no downloader: using the built one, {built}")
            return built
        raise SystemExit(f"release {man['version']} lists no downloader and none is built here: pass --downloader <exe>")
    os.makedirs(folder, exist_ok=True)
    exe = os.path.join(folder, os.path.basename(l["path"]))
    if not os.path.exists(exe) or sha256(exe) != l["sha256"]:
        with open(exe + ".part", "wb") as f:
            f.write(fetch(SITE + l["path"]))
        if sha256(exe + ".part") != l["sha256"]:
            raise SystemExit(f"downloader {l['path']} does not match the manifest's sha256")
        os.replace(exe + ".part", exe)
    return exe


RELEASE_SLOTS = tuple(n for n in game_slots.SLOTS if n not in game_slots.OWNER_SLOTS)  # 2 to 5, never slot 1


def check_slot(n):
    if n == 1:
        raise SystemExit("never on slot 1 (the owner's game in Program Files: no backup folder next to it): use slot 2, 3, 4 or 5")
    owner = os.environ.get("MXL_RUN")
    info = game_slots.lock_info(n)
    if not owner or not info or not info[1] or info[1].split()[0] != owner:
        raise SystemExit(f"slot {n} is not locked by MXL_RUN={owner!r} (py -3 tools/game_slots.py lock {n} <name>)")
    if game_slots.slot_processes(game_slots.slot_dir(n)):
        raise SystemExit(f"slot {n} still has a running game")


def package_manifest(package):
    """The release-manifest.json that package_release.py writes next to the 7z."""
    p = os.path.join(os.path.dirname(os.path.abspath(package)), "release-manifest.json")
    if not os.path.isfile(package) or not os.path.isfile(p):
        raise SystemExit(f"--package needs the 7z and the release-manifest.json next to it ({package})")
    return json.load(open(p, encoding="utf-8"))


def unpack(package, n):
    """Install step 2 of the alpha's notes: the 7z (top folder mxl2012/) unpacked into <D2R folder>\\mods\\."""
    import package_release
    z = package_release.find_7z()
    if not z:
        raise SystemExit("no 7-Zip found to unpack the package")
    mods = os.path.join(game_slots.slot_dir(n), "mods")
    os.makedirs(mods, exist_ok=True)
    cmd = [str(z), "x", "-y", "-bso0", "-bsp0", f"-o{mods}", os.path.abspath(package)]
    print(" ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def install(n, channel, exe=None, release_dll=False, package=None):
    check_slot(n)
    st, bak, mod = state_dir(n), backup_dir(n), game_slots.mod_dir(n)
    man = package_manifest(package) if package else manifest(channel)
    print(f"release {man['version']} (plugin {man['pluginVersion']}), launch keys {man['launch']}")
    os.makedirs(st, exist_ok=True)
    if not package:
        exe = exe or downloader(man, os.path.join(st, "downloader"))  # before the slot is touched: a failure here changes nothing
    if os.path.exists(os.path.join(st, "release-install.json")):
        print("slot already holds a release install: the backup stays as it is, the release is installed again")
        shutil.rmtree(mod, ignore_errors=True)
    else:
        if os.path.exists(bak):
            raise SystemExit(f"{bak} exists but no release-install.json: look at it and remove it by hand")
        os.makedirs(bak)
        if os.path.isdir(mod):
            os.replace(mod, os.path.join(bak, MOD))  # same volume: a rename, not a 1.2 GB copy
    if package:
        r = unpack(package, n)
    else:
        cmd = [exe, "--cli", "install", "--game-dir", game_slots.slot_dir(n), "--data-dir", os.path.join(st, "data")]
        print(" ".join(cmd))
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    lines = [l for l in r.stdout.splitlines() if "MB of" not in l]
    print("\n".join(lines[-6:]))
    if r.returncode != 0 or not os.path.isdir(mod):
        print(r.stderr[-2000:])
        raise SystemExit(f"the {'unpack' if package else 'downloader'} failed (restore with: release_install.py restore)")
    marker_path = os.path.join(mod, "mxl2012-install.json")  # written by the downloader; a hand-unpacked 7z has none
    marker = json.load(open(marker_path, encoding="utf-8")) if os.path.exists(marker_path) else {"version": man["version"]}
    changes = {"release": marker.get("version"), "channel_version": man["version"], "launch_release": man["launch"]}
    if package:
        changes["package"] = os.path.abspath(package)
    if marker.get("version") != man["version"]:
        print(f"WARNING: the downloader installed {marker.get('version')} while the channel says {man['version']} "
              "(a cached channel file); the release under test is the installed one")
    plugins = os.path.join(mod, "d2rloader", "plugins")
    shutil.copy2(os.path.join(plugins, "mxl2012-core.dll"), os.path.join(st, "mxl2012-core.release.dll"))
    if not release_dll:
        if not os.path.exists(DEV_DLL):
            raise SystemExit(f"no dev DLL at {DEV_DLL}: build it (tools/build_plugin.ps1) or pass --release-dll")
        shutil.copy2(DEV_DLL, os.path.join(plugins, "mxl2012-core.dll"))
        dev = open(DEV_DLL, "rb").read()
        changes["dll"] = "dev build (test harness) " + ("same PluginVersion" if (marker.get("version") or "").encode() + b"\0" in dev
                                                        else "with ANOTHER PluginVersion than the release")
    else:
        changes["dll"] = "release (no harness: no background input)"
    game_slots.set_savepath(n)
    args = " ".join(a for a in (man["launch"].get("launch_arguments", ""), "-w") if a)
    if man["launch"].get("default_mod", MOD) != MOD:
        print(f"NOTE: the release's default_mod is {man['launch'].get('default_mod')!r}; slot runs start {MOD} with -mod")
    changes.update(savepath=game_slots.save_name(n) + "/", launch_arguments=args, at=time.strftime("%Y-%m-%d %H:%M:%S"))
    json.dump(changes, open(os.path.join(st, "release-install.json"), "w", encoding="utf-8"), indent=2)
    print(json.dumps(changes, indent=2))
    return 0


def restore(n):
    check_slot(n)
    st, bak, mod = state_dir(n), backup_dir(n), game_slots.mod_dir(n)
    if not os.path.exists(os.path.join(st, "release-install.json")):
        raise SystemExit(f"slot {n} holds no release install (no {st}\\release-install.json)")
    shutil.rmtree(mod, ignore_errors=True)
    if os.path.isdir(os.path.join(bak, MOD)):
        os.replace(os.path.join(bak, MOD), mod)
    if os.path.exists(os.path.join(bak, "d2rloader.toml")):  # an install made before tools/slot_share.py
        shutil.copy2(os.path.join(bak, "d2rloader.toml"), toml_path(n))
        os.remove(os.path.join(bak, "d2rloader.toml"))
    os.rmdir(bak)
    os.remove(os.path.join(st, "release-install.json"))
    print(f"slot {n}: developer install back")
    return 0


def status(n):
    p = os.path.join(state_dir(n), "release-install.json")
    print(open(p, encoding="utf-8").read() if os.path.exists(p) else f"slot {n}: no release install")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("install", "restore", "status"))
    ap.add_argument("--slot", type=int, default=int(os.environ.get("MXL_SLOT", "0")))
    ap.add_argument("--channel", default="stable")
    ap.add_argument("--downloader", help="a D2R-XL-2012-Downloader.exe (default: the release manifest's, sha256-checked)")
    ap.add_argument("--release-dll", action="store_true", help="keep the release mxl2012-core.dll (no test harness)")
    ap.add_argument("--package", help="a local release 7z (package_release.py) unpacked by hand, the alpha's player path")
    a = ap.parse_args()
    game_slots.require_machine(f"release_install {a.cmd}")
    if a.slot not in RELEASE_SLOTS:
        raise SystemExit("--slot 2, 3, 4 or 5 (or MXL_SLOT)")
    if a.cmd == "install":  # restore / status still work on a slot whose folder went away (they only read the state folder)
        game_slots.require_present(a.slot, "release_install")
    if a.cmd == "install":
        return install(a.slot, a.channel, a.downloader, a.release_dll, a.package)
    return restore(a.slot) if a.cmd == "restore" else status(a.slot)


if __name__ == "__main__":
    sys.exit(main())

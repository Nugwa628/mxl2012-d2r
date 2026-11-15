"""The release zip: an empty D2R mod with the plugin, its config and its art, laid out to unpack into the game folder.

  mods/<MOD>/modinfo.json                                   {"name": MOD, "savepath": MOD/}
  mods/<MOD>/<MOD>.mpq/modinfo.json                         (D2R reads this one; the copy at the mod root is for D2RLoader)
  mods/<MOD>/<MOD>.mpq/data/hd/global/ui/panel/statbook/    the Stat Book's sprites (data/hd/... of this repository)
  mods/<MOD>/d2rloader/plugins/statbook.dll
  mods/<MOD>/d2rloader/config/statbook.toml
  mods/<MOD>/README.md, LICENSE

  py -3 tools/package.py --dll build/Release/statbook.dll [--out dist] [--mod AdvancedStats]
"""
import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = Path("data") / "hd" / "global" / "ui" / "panel" / "statbook"
MOD = "AdvancedStats"


def version() -> str:
    m = re.search(r'PluginVersion = "(\d+\.\d+\.\d+)"', (ROOT / "src" / "statbook.cpp").read_text("utf-8"))
    if not m:
        raise SystemExit("PluginVersion not found in src/statbook.cpp")
    return m.group(1)


def entries(dll: Path, mod: str = MOD) -> list[tuple[str, bytes]]:
    """(path in the zip, bytes), in zip order."""
    base = f"mods/{mod}"
    info = (json.dumps({"name": mod, "savepath": mod + "/"}, indent=2) + "\n").encode()
    out = [(f"{base}/modinfo.json", info), (f"{base}/{mod}.mpq/modinfo.json", info)]
    sprites = sorted((ROOT / ART).glob("*.sprite"))
    if not sprites:
        raise SystemExit(f"no sprites in {ROOT / ART}")
    out += [(f"{base}/{mod}.mpq/{ART.as_posix()}/{p.name}", p.read_bytes()) for p in sprites]
    out.append((f"{base}/d2rloader/plugins/statbook.dll", Path(dll).read_bytes()))
    out.append((f"{base}/d2rloader/config/statbook.toml", (ROOT / "statbook.toml").read_bytes()))
    out += [(f"{base}/{n}", (ROOT / n).read_bytes()) for n in ("README.md", "LICENSE")]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dll", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    ap.add_argument("--mod", default=MOD, help="the mod folder name (default %(default)s)")
    a = ap.parse_args(argv)
    if not a.dll.is_file():
        raise SystemExit(f"{a.dll} missing: build first (README, Building)")
    if b"statbook-testharness" in a.dll.read_bytes():
        raise SystemExit(f"{a.dll} is a test build (STATBOOK_TEST_HARNESS): build the release DLL")
    a.out.mkdir(parents=True, exist_ok=True)
    z = a.out / f"d2r-advanced-stats-{version()}.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as f:
        for name, data in entries(a.dll, a.mod):
            f.writestr(name, data)
    print(z)
    return 0


if __name__ == "__main__":
    sys.exit(main())

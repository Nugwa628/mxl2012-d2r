"""Clearer classic Latin fonts from the 2023 D2SE/D2GL repack, for the in-game setting; see docs/legacy-font-research.md.

The build stages six pinned custom pairs (font6/8/16/30, fontexocet8, ReallyTheLastSucker) under
data/local/font/latin/clear/, never under D2R's own names. The plugin part clearfonts (mxl2012-core.toml
[fonts] legacy_clear_fonts, Controls action "Clear Legacy Fonts") points D2R's classic font loader at that
folder while the setting is on; off, D2R loads its stock fonts as before.
Formal10/11/12 and chat stay stock (the repack's formal11 crashes D2R); fontformal8 has no D2R font id.

Archive: MXL2012_LEGACY_FONT_ARCHIVE, else the repack's data/local.zip under <MXL2012_RUNS>/extract-merged.
MXL2012_LEGACY_FONTS=0 leaves the set out. No downloading and no HD assets. Staging removes only files this tool
installed, including those of the earlier build option (the same names in latin/ itself).
"""
import argparse
import hashlib
import json
import os
import struct
import zipfile
from pathlib import Path

import dc6

ROOT = Path(__file__).resolve().parent.parent
PIN = Path(__file__).parent / "data" / "legacy-font-repack.json"
LATIN = Path("local/font/latin")
CLEAR = LATIN / "clear"
STATE = "legacy_fonts.json"
# D2R 93847's font ids 0-13 (name table 0x1d84a00) whose repack pair is safe; the plugin redirects exactly these.
SHIPPED = ("font6", "font8", "font16", "font30", "fontexocet8", "reallythelastsucker")
STOCK = {"fontformal10", "fontformal11", "fontformal12", "fontingamechat"}


def default_archive() -> Path | None:
    import fxpaths
    path = fxpaths.RUNS / "extract-merged" / "data" / "local.zip"
    return path if path.is_file() else None


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_font(tbl: bytes, picture: bytes, label: str = "font") -> None:
    """Reject the zero divisor at D2R 93847 +90DD16, and malformed frame references.

    Byte 10 is the nominal line height, not the height of an individual glyph.
    Glyph advances can legally be zero (stock fonts contain them); they are not divisors here.
    """
    if len(tbl) != 12 + 256 * 14 or tbl[:4] != b"Woo!" or struct.unpack_from("<IH", tbl, 4) != (1, 256):
        raise ValueError(f"{label}: invalid classic font header/table")
    if tbl[10] == 0:
        raise ValueError(f"{label}: zero line height at TBL offset 0x0A (D2R text layout divisor)")
    try:
        frames = dc6.parse_dc6(picture)
        if len(frames) != 256 or any(w <= 0 or h <= 0 for w, h, *_ in frames):
            raise ValueError("expected 256 nonempty DC6 frames")
        chars = []
        for i in range(256):
            char, _, _, _, _, _, frame, _ = struct.unpack_from("<HBBBBHHI", tbl, 12 + 14 * i)
            chars.append(char)
            if frame >= len(frames):
                raise ValueError(f"glyph {char}: frame {frame} out of range")
        if len(set(chars)) != 256:
            raise ValueError("duplicate character mappings")
    except (struct.error, IndexError, ValueError) as exc:
        raise ValueError(f"{label}: invalid glyph/DC6 data: {exc}") from exc


def check_tree(data: Path) -> None:
    """Also called by the packager: hand-copied invalid fonts must not enter a release (latin/ and latin/clear/)."""
    for folder in (data / LATIN, data / CLEAR):
        if not folder.exists():
            continue
        files = {p.name.lower(): p for p in folder.iterdir() if p.is_file()}
        names = {Path(n).stem for n in files if n.endswith((".tbl", ".dc6"))}
        # default.tbl and fonter.tbl are not DC6 font metrics.
        names -= {"default", "fonter"}
        for name in sorted(names):
            if name + ".tbl" not in files or name + ".dc6" not in files:
                raise ValueError(f"{folder / name}: matching DC6/TBL pair missing")
            validate_font(files[name + ".tbl"].read_bytes(), files[name + ".dc6"].read_bytes(), name)


def missing_clear(data: Path) -> list[str]:
    """The files of the clear set the plugin needs that are not in `data` (the packager refuses a release without them)."""
    return [f"{CLEAR.as_posix()}/{n}{ext}" for n in SHIPPED for ext in (".dc6", ".tbl") if not (data / CLEAR / (n + ext)).is_file()]


def prepare(archive: Path, pin: dict | None = None) -> dict[str, bytes]:
    """Verify the repack's identity, then keep both files of each shipped font."""
    pin = json.loads(PIN.read_text(encoding="utf-8")) if pin is None else pin
    with zipfile.ZipFile(archive) as source:
        members = {}
        for info in source.infolist():
            path = info.filename.replace("\\", "/").lower()
            if "/font/latin/" in "/" + path and not info.is_dir():
                name = path.rsplit("/", 1)[-1]
                if name in pin["files"]:
                    if name in members:
                        raise ValueError(f"duplicate font member {name}")
                    members[name] = info
        result = {}
        for name, expected in pin["files"].items():
            if name not in members:
                raise ValueError(f"archive lacks {name}")
            data = source.read(members[name])
            if len(data) != expected["size"] or digest(data) != expected["sha256"]:
                raise ValueError(f"{name}: differs from audited 2023 repack; refusing untested font bytes")
            result[name] = data
    result = {n: b for n, b in result.items() if Path(n).stem in SHIPPED}
    for name in result:
        if name.endswith(".tbl"):
            validate_font(result[name], result[name[:-4] + ".dc6"], name)
    return result


def apply(mod: Path, enabled: bool, archive: Path | None = None) -> None:
    """Stage the clear set (enabled) or remove it. Manifest paths are relative to latin/ ("clear/font8.tbl"); the earlier
    build option's manifest named files in latin/ itself, and those are removed as well."""
    state = mod / STATE
    old = json.loads(state.read_text(encoding="utf-8")) if state.exists() else {}
    data = mod / "data"
    # Validate all inputs and ownership before changing any output.
    if enabled and archive is None:
        raise ValueError("set MXL2012_LEGACY_FONT_ARCHIVE to the local repack data/local.zip or font.zip")
    wanted = {"clear/" + n: b for n, b in prepare(archive).items()} if enabled else {}
    for name, sha in old.items():
        parts = Path(name).parts
        if not name.endswith((".tbl", ".dc6")) or not (len(parts) == 1 or (len(parts) == 2 and parts[0] == "clear")):
            raise ValueError("invalid managed font manifest")
        path = data / LATIN / name
        if path.exists() and digest(path.read_bytes()) != sha:
            raise ValueError(f"{path}: changed since staging; refusing to overwrite/remove it")
    for name in wanted:
        if (data / LATIN / name).exists() and name not in old:
            raise ValueError(f"{name}: existing font is not managed by legacy_fonts.py")
    for name in old:
        (data / LATIN / name).unlink(missing_ok=True)
    state.unlink(missing_ok=True)
    if wanted:
        (data / CLEAR).mkdir(parents=True, exist_ok=True)
        for name, content in wanted.items():
            (data / LATIN / name).write_bytes(content)
        state.write_text(json.dumps({n: digest(b) for n, b in sorted(wanted.items())}, indent=2) + "\n", encoding="utf-8")
    elif (data / CLEAR).is_dir() and not any((data / CLEAR).iterdir()):
        (data / CLEAR).rmdir()
    check_tree(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mod", type=Path, default=ROOT / "work/mod")
    parser.add_argument("--check", action="store_true", help="only validate staged classic font pairs")
    args = parser.parse_args(argv)
    try:
        if args.check:
            check_tree(args.mod / "data")
            print("classic font metrics valid")
            return 0
        value = os.environ.get("MXL2012_LEGACY_FONTS", "1")
        if value not in ("0", "1"):
            raise ValueError("MXL2012_LEGACY_FONTS must be 0 or 1")
        source = os.environ.get("MXL2012_LEGACY_FONT_ARCHIVE")
        archive = Path(source) if source else default_archive()
        if value == "1" and archive is None:
            raise ValueError("no repack archive for the clear fonts: set MXL2012_LEGACY_FONT_ARCHIVE to the 2023 D2SE/D2GL "
                             "repack's data/local.zip (or MXL2012_LEGACY_FONTS=0 to build without them; the in-game setting "
                             "then has no effect and a release refuses to package)")
        apply(args.mod, value == "1", archive)
        print(f"classic font metrics valid; clear fonts {'staged in data/' + CLEAR.as_posix() if value == '1' else 'left out'}")
        return 0
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"legacy fonts: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

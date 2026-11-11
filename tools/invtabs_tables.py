"""Build/check invtabs tables without running a mod data build."""
import argparse
import re
import tomllib
from pathlib import Path
import charm_inv

ROOT = Path(__file__).resolve().parent.parent
TABLE_DIR = Path("data/global/excel/d2rloader/invtabs")
HEADER = "name\tlabel\tcolumns\trows\ttypes"


def token(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]+", value) is not None


def pack(tabs):
    """Host fresh packing: stable area descending, height descending; y then x, no rotation."""
    if not 1 <= len(tabs) <= 12:
        raise ValueError("expected 1..12 tabs")
    occupied = set()
    spots = {}
    for tab in tabs:
        for key in ("columns", "rows"):
            if type(tab[key]) is not int or not 1 <= tab[key] <= 16:
                raise ValueError("tab sides must be integers in 1..16")
    for t in sorted(tabs, key=lambda t: (-t["columns"] * t["rows"], -t["rows"])):
        w, h = t["columns"], t["rows"]
        for y in range(17-h):
            for x in range(17-w):
                cells = {(cx, cy) for cy in range(y,y+h) for cx in range(x,x+w)}
                if not cells & occupied:
                    occupied |= cells
                    spots[t["name"]] = (x,y)
                    break
            else:
                continue
            break
        else:
            raise ValueError("tabs do not fit the 16 x 16 page")
    return spots


def read(path, header):
    text = path.read_bytes().decode("ascii")
    lines = text.splitlines()
    if not text.endswith("\n") or "\r" in text or not lines or lines[0] != header:
        raise ValueError(f"{path}: expected strict LF TSV header {header!r}")
    rows = [line.split("\t") for line in lines[1:]]
    if any(len(r) != len(header.split("\t")) for r in rows):
        raise ValueError(f"{path}: wrong column count")
    return rows


def validate(tabs, folder, itemtypes):
    names, files = set(), set()
    known = {r["Code"] for r in itemtypes if r.get("Code")}
    for t in tabs:
        name, label, file = t["name"], t["label"], t["types"]
        if not token(name) or name in names:
            raise ValueError("invalid or duplicate tab name")
        if not label or any(not 32 <= ord(c) < 127 for c in label):
            raise ValueError("label must be printable ASCII")
        if not re.fullmatch(r"types_[A-Za-z0-9_-]+\.txt", file) or file in files:
            raise ValueError("invalid or duplicate types file")
        names.add(name); files.add(file)
        codes = [r[0] for r in read(folder / file, "itemType")]
        if not codes or len(codes) != len(set(codes)):
            raise ValueError("empty or duplicate item types")
        for code in codes:
            charm_inv.check_code(code)
            if code not in known:
                raise ValueError(f"unknown item type: {code}")
    return pack(tabs)


def build(out, config=ROOT / "invtabs/invtabs.toml"):
    cfg = tomllib.loads(config.read_text("utf-8"))
    tabs = [dict(t, name=name) for name,t in cfg["tabs"].items()]
    itemtypes = charm_inv.read_tsv(out / "data/global/excel/itemtypes.txt")
    folder = out / TABLE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    # Other tab files are modder-owned; never overwrite them.
    if any(t["name"] == "charms" for t in tabs):
        t = next(t for t in tabs if t["name"] == "charms")
        if not re.fullmatch(r"types_[A-Za-z0-9_-]+\.txt", t["types"]):
            raise ValueError("invalid types filename")
        (folder / t["types"]).write_bytes(("itemType\n" + "".join(c+"\n" for c in charm_inv.charm_types(itemtypes))).encode("ascii"))
    validate(tabs, folder, itemtypes)
    body = HEADER + "\n" + "".join("\t".join(str(t[k]) for k in HEADER.split("\t")) + "\n" for t in tabs)
    (folder / "tabs.txt").write_bytes(body.encode("ascii"))
    return tabs


def check(out):
    folder = out / TABLE_DIR
    tabs = [dict(zip(HEADER.split("\t"), r)) for r in read(folder / "tabs.txt", HEADER)]
    for t in tabs:
        for k in ("columns", "rows"):
            if not re.fullmatch(r"[0-9]+", t[k]):
                raise ValueError("invalid tab dimension")
            t[k] = int(t[k])
    return validate(tabs, folder, charm_inv.read_tsv(out / "data/global/excel/itemtypes.txt"))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("build", "check"))
    ap.add_argument("--out", type=Path, required=True, help="mod root containing data/")
    ap.add_argument("--config", type=Path, default=ROOT / "invtabs/invtabs.toml")
    a = ap.parse_args()
    try:
        build(a.out, a.config) if a.command == "build" else check(a.out)
    except (ValueError, OSError, KeyError) as e:
        ap.exit(1, f"invtabs: {e}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

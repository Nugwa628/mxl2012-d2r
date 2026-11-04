#!/usr/bin/env python
"""Writes sample-loader.zip and sample-loader.json for the ZIP reader unit test (launcher/tests/core_tests.cpp TestZip): a
small archive laid out like the official D2RLoader ZIP (D2RLoader.exe, D2RCore.dll, d2rloader.mpq and d2rloader/config/
d2rloader.toml at the same places, empty folders mods/ and d2rloader/plugins/). Generated data only, no D2RLoader file.
Deflate at three levels so stored, fixed and dynamic Huffman blocks all occur.

  py -3 launcher/tests/data/make_sample_zip.py      (the output is committed)
"""
import hashlib
import json
import random
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def files():
    rnd = random.Random(1304)
    text = "".join(f"line {i}: the quick brown fox {i % 17}\n" for i in range(20000)).encode()  # dynamic Huffman
    noise = bytes(rnd.randrange(256) for _ in range(70000))  # incompressible: stored blocks
    return [
        ("D2RLoader.exe", b"MZ" + noise, zipfile.ZIP_DEFLATED, 9),
        ("D2RCore.dll", b"MZ" + text, zipfile.ZIP_DEFLATED, 6),
        ("d2rloader.mpq", b"MPQ\x1a" + b"ab" * 10, zipfile.ZIP_DEFLATED, 1),  # short: fixed Huffman
        ("d2rloader/config/d2rloader.toml", b'[d2rloader]\ndefault_mod = ""\n', zipfile.ZIP_STORED, None),
        ("d2rloader/empty.txt", b"", zipfile.ZIP_DEFLATED, 9),
    ]


def main():
    out = HERE / "sample-loader.zip"
    with zipfile.ZipFile(out, "w") as z:
        for d in ("mods/", "d2rloader/", "d2rloader/plugins/"):
            z.writestr(zipfile.ZipInfo(d, (2026, 9, 23, 2, 56, 0)), b"")
        for name, data, method, level in files():
            info = zipfile.ZipInfo(name, (2026, 9, 23, 2, 56, 0))
            info.compress_type = method
            z.writestr(info, data, compresslevel=level)
    listing = {"files": [{"path": n, "size": len(d), "sha256": hashlib.sha256(d).hexdigest()} for n, d, _, _ in files()],
               "dirs": ["mods", "d2rloader", "d2rloader/plugins"]}
    (HERE / "sample-loader.json").write_text(json.dumps(listing, indent=1) + "\n", encoding="utf-8")
    print(out, out.stat().st_size, "bytes")


if __name__ == "__main__":
    main()

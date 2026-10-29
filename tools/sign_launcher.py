#!/usr/bin/env python
"""The downloader's release step between the build and tools/publish_release.py (docs/launcher.md "Release and signing").

The build (launcher/CMakeLists.txt) leaves an UNSIGNED D2R-XL-2012-Downloader.exe and D2R-XL-2012-Downloader.exe.sha256. This
step takes that pair and writes the exe to publish into --out, unsigned or signed by whichever service we end up with:

  py -3 tools/sign_launcher.py --exe build/launcher/Release/D2R-XL-2012-Downloader.exe --out dist-launcher
        [--command "signtool sign /fd SHA256 /tr <timestamp url> /td SHA256 ... {file}"]   sign here (a local tool)
        [--signed FILE]                                                                   signed elsewhere (SignPath)
        [--allow-untrusted]                                                               test certificates

  then: py -3 tools/publish_release.py publish ... --launcher dist-launcher/D2R-XL-2012-Downloader.exe

Checks:
  - the exe still matches the build's .sha256 (the file that is signed is the file that was built and tested);
  - a signed exe is the same program: its bytes equal the unsigned build except the PE checksum, the security
    directory entry, the zero padding and the signature appended at the end (the parts Authenticode leaves out);
  - on Windows, Get-AuthenticodeSignature must say Valid and show a timestamp (--allow-untrusted: any signature).

Writes --out/D2R-XL-2012-Downloader.exe, .sha256 (of the final file: publish_release puts that in the release manifest,
and the downloader's self-update checks it, signed or not) and signing.json (what was done).
"""
import argparse
import hashlib
import json
import os
import shlex
import shutil
import struct
import subprocess
import sys
from pathlib import Path

NAME = "D2R-XL-2012-Downloader.exe"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pe_layout(data: bytes):
    """(checksum offset, security directory entry offset, certificate table offset, size) of a PE file."""
    if data[:2] != b"MZ":
        raise ValueError("not an exe (no MZ)")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("not a PE file")
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic not in (0x10B, 0x20B):
        raise ValueError(f"unknown optional header magic {magic:#x}")
    dirs = opt + (96 if magic == 0x10B else 112)
    sec = dirs + 4 * 8  # IMAGE_DIRECTORY_ENTRY_SECURITY
    cert_off, cert_size = struct.unpack_from("<II", data, sec)
    return opt + 64, sec, cert_off, cert_size


def program_bytes(data: bytes) -> bytes:
    """The bytes Authenticode signs: without checksum, security entry and the certificate table (plus its padding)."""
    chk, sec, cert_off, cert_size = pe_layout(data)
    body = bytearray(data[:cert_off] if cert_size else data)
    body[chk:chk + 4] = b"\0" * 4
    body[sec:sec + 8] = b"\0" * 8
    if cert_size:
        if cert_off + cert_size != len(data):
            raise ValueError("the signature is not at the end of the file")
        pad = 0
        while pad < 7 and len(body) > pad and body[-1 - pad] == 0:
            pad += 1
        body = body[:len(body) - pad] if pad else body
    return bytes(body)


def same_program(unsigned: bytes, signed: bytes) -> bool:
    a, b = program_bytes(unsigned), program_bytes(signed)
    # the unsigned build may itself end in zero bytes that look like padding
    return a.rstrip(b"\0") == b.rstrip(b"\0") and abs(len(a) - len(b)) < 8


def authenticode(path: Path):
    """Windows only: Get-AuthenticodeSignature's status, signer and timestamp signer; None elsewhere."""
    if sys.platform != "win32":
        return None
    ps = ("$s = Get-AuthenticodeSignature -LiteralPath $env:MXL_SIGNED_FILE; "
          "[pscustomobject]@{status = [string]$s.Status; signer = $s.SignerCertificate.Subject; "
          "thumbprint = $s.SignerCertificate.Thumbprint; timestamp = $s.TimeStamperCertificate.Subject} | ConvertTo-Json -Compress")
    env = dict(os.environ, MXL_SIGNED_FILE=str(path))
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError("Get-AuthenticodeSignature failed: " + r.stderr.strip())
    return json.loads(r.stdout)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", type=Path, required=True, help="the unsigned build output (its .sha256 next to it)")
    ap.add_argument("--out", type=Path, required=True)
    how = ap.add_mutually_exclusive_group()
    how.add_argument("--command", help="signing command; {file} is replaced by the exe to sign in place")
    how.add_argument("--signed", type=Path, help="the same exe, signed by an outside service")
    ap.add_argument("--allow-untrusted", action="store_true", help="accept a signature Windows does not trust (tests)")
    a = ap.parse_args()

    unsigned = a.exe.read_bytes()
    sums = a.exe.with_name(a.exe.name + ".sha256")
    if not sums.is_file():
        print(f"{sums}: missing (the build writes it)")
        return 1
    want = sums.read_text("utf-8").split()[0].lower()
    if sha256(unsigned) != want:
        print(f"{a.exe}: sha256 {sha256(unsigned)} is not the build's {want}")
        return 1
    if pe_layout(unsigned)[3]:
        print(f"{a.exe}: already signed; give the unsigned build")
        return 1

    a.out.mkdir(parents=True, exist_ok=True)
    out = a.out / NAME
    shutil.copyfile(a.exe, out)
    if a.command:
        # Windows paths keep their backslashes (posix=False); quotes around a part are removed
        parts = [p[1:-1] if len(p) > 1 and p[0] == p[-1] == '"' else p for p in shlex.split(a.command, posix=False)]
        cmd = [p.replace("{file}", str(out)) for p in parts]
        r = subprocess.run(cmd)
        if r.returncode != 0:
            print(f"signing command failed ({r.returncode})")
            return 1
    elif a.signed:
        shutil.copyfile(a.signed, out)

    final = out.read_bytes()
    signed = bool(pe_layout(final)[3])
    record = {"unsignedSha256": want, "sha256": sha256(final), "size": len(final), "signed": signed,
              "programSha256": sha256(program_bytes(final))}
    if (a.command or a.signed) and not signed:
        print(f"{out}: no signature after signing")
        return 1
    if signed:
        if not same_program(unsigned, final):
            print(f"{out}: differs from the unsigned build beyond the signature; refusing it")
            return 1
        sig = authenticode(out)
        if sig is not None:
            record["authenticode"] = sig
            if sig["status"] != "Valid" and not a.allow_untrusted:
                print(f"{out}: signature status {sig['status']} (signer {sig.get('signer')})")
                return 1
            if not sig.get("timestamp") and not a.allow_untrusted:  # short-lived certificates (Azure: 3 days) need one
                print(f"{out}: the signature has no timestamp (signtool /tr <timestamp url> /td SHA256)")
                return 1
    (a.out / (NAME + ".sha256")).write_text(f"{record['sha256']}  {NAME}\n", encoding="utf-8")
    (a.out / "signing.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print(f"{out}: {'signed' if signed else 'unsigned'}, {len(final)} bytes, sha256 {record['sha256']}")
    if signed and record.get("authenticode"):
        s = record["authenticode"]
        print(f"  {s['status']}: {s.get('signer')}; timestamp {s.get('timestamp') or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

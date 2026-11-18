#!/usr/bin/env python
"""Sign the downloader with Azure Artifact Signing (formerly Trusted Signing) on the release PC (docs/launcher.md
"Release and signing").

signtool.exe (Windows SDK) signs through Microsoft's Artifact Signing dlib, which reads the account from a metadata.json and
gets its Azure token from one credential chosen here. tools/sign_launcher.py runs the command (--command) and checks the
result (same program as the build, valid timestamped signature).

  py -3 tools/artifact_signing.py setup        fetch the pinned dlib NuGet package into work/signing-tools (checked by
                                               SHA-256; nothing is installed on the PC) and report signtool and .NET 8
  py -3 tools/artifact_signing.py check        the same checks, no download
  py -3 tools/artifact_signing.py sign --exe build/launcher/Release/D2R-XL-2012-Downloader.exe --out dist-launcher
  py -3 tools/artifact_signing.py command      print the --command for tools/sign_launcher.py

The account is never written into git. It comes from environment variables or from --config FILE (a JSON file outside git,
for example work/signing-tools/account.json):

  MXL_SIGNING_ENDPOINT   https://<region>.codesigning.azure.net/  (the region of the Artifact Signing account)
  MXL_SIGNING_ACCOUNT    the Artifact Signing account name
  MXL_SIGNING_PROFILE    the certificate profile name
  MXL_SIGNING_AUTH       cli | env (default cli)
      cli  AzureCliCredential: `az login` as a user (or service principal) with the role "Artifact Signing Certificate
           Profile Signer" on the certificate profile, before signing
      env  EnvironmentCredential: AZURE_TENANT_ID, AZURE_CLIENT_ID and AZURE_CLIENT_SECRET of an app registration with that
           role, set in this process only at run time (never saved)
Every other credential of the Azure SDK chain is excluded in metadata.json, so the dlib never picks up some other
sign-in on the PC (Visual Studio, managed identity, a browser window).
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)

WORK = ROOT / "work" / "signing-tools"
# The last dlib built for .NET 8 (1.0.147 and later need the .NET 10 runtime; this PC has .NET 8).
DLIB_PACKAGE = "Microsoft.ArtifactSigning.Client"
DLIB_VERSION = "1.0.146"
DLIB_SHA256 = "7761e5d8f31e54b764da21d33cd8b0a2940e1b05526c7dfcb5e94b0431426f70"
DLIB_URL = ("https://api.nuget.org/v3-flatcontainer/{id}/{v}/{id}.{v}.nupkg")
DLIB_RUNTIME = "8."  # Microsoft.NETCore.App major version the pinned dlib needs (x64)
TIMESTAMP_URL = "http://timestamp.acs.microsoft.com"
MIN_SIGNTOOL_SDK = (10, 0, 22621)  # Microsoft: Windows SDK signtool 10.0.22621.755 or later
ENDPOINT_RE = re.compile(r"^https://[a-z0-9]+\.codesigning\.azure\.net/?$")

CREDENTIALS = ("EnvironmentCredential", "WorkloadIdentityCredential", "ManagedIdentityCredential",
               "SharedTokenCacheCredential", "VisualStudioCredential", "VisualStudioCodeCredential", "AzureCliCredential",
               "AzurePowerShellCredential", "AzureDeveloperCliCredential", "InteractiveBrowserCredential")
AUTH = {"cli": "AzureCliCredential", "env": "EnvironmentCredential"}


class SigningError(Exception):
    pass


# ---------------------------------------------------------------- the account

def load_account(config=None, environ=None) -> dict:
    environ = os.environ if environ is None else environ
    data = json.loads(Path(config).read_text(encoding="utf-8")) if config else {}
    acc = {
        "endpoint": data.get("endpoint") or environ.get("MXL_SIGNING_ENDPOINT", ""),
        "account": data.get("account") or environ.get("MXL_SIGNING_ACCOUNT", ""),
        "profile": data.get("profile") or environ.get("MXL_SIGNING_PROFILE", ""),
        "auth": data.get("auth") or environ.get("MXL_SIGNING_AUTH", "cli"),
    }
    missing = [k for k in ("endpoint", "account", "profile") if not acc[k]]
    if missing:
        raise SigningError("missing " + ", ".join(missing) + " (MXL_SIGNING_ENDPOINT / _ACCOUNT / _PROFILE or --config)")
    if not ENDPOINT_RE.match(acc["endpoint"]):
        raise SigningError(f"endpoint {acc['endpoint']!r} is not https://<region>.codesigning.azure.net/")
    if acc["auth"] not in AUTH:
        raise SigningError(f"auth {acc['auth']!r}: use " + " or ".join(AUTH))
    return acc


def metadata(acc: dict) -> dict:
    """metadata.json for the dlib: the account, and every credential but the chosen one excluded."""
    keep = AUTH[acc["auth"]]
    return {"Endpoint": acc["endpoint"], "CodeSigningAccountName": acc["account"],
            "CertificateProfileName": acc["profile"], "ExcludeCredentials": [c for c in CREDENTIALS if c != keep]}


def auth_problems(acc: dict, environ=None, which=shutil.which) -> list[str]:
    environ = os.environ if environ is None else environ
    if acc["auth"] == "env":
        miss = [v for v in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET") if not environ.get(v)]
        return [f"auth env: {', '.join(miss)} not set in this process"] if miss else []
    if not which("az"):
        return ["auth cli: the Azure CLI (az) is not found; `az login` first (see docs/launcher.md)"]
    return []


# ---------------------------------------------------------------- tools on the PC

def sdk_version(name: str):
    try:
        return tuple(int(x) for x in name.split("."))
    except ValueError:
        return None


def find_signtool(kits=None, environ=None) -> Path:
    environ = os.environ if environ is None else environ
    if environ.get("MXL_SIGNTOOL"):
        p = Path(environ["MXL_SIGNTOOL"])
        if not p.is_file():
            raise SigningError(f"MXL_SIGNTOOL {p} does not exist")
        return p
    kits = Path(kits or Path(environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Windows Kits" / "10" / "bin")
    found = []
    if kits.is_dir():
        for d in kits.iterdir():
            v = sdk_version(d.name)
            if v and v[:3] >= MIN_SIGNTOOL_SDK and (d / "x64" / "signtool.exe").is_file():
                found.append((v, d / "x64" / "signtool.exe"))
    if not found:
        raise SigningError(f"no x64 signtool.exe of Windows SDK {'.'.join(map(str, MIN_SIGNTOOL_SDK))} or newer in {kits}")
    return max(found)[1]


def dotnet_runtimes(run=subprocess.run) -> list[str]:
    try:
        r = run(["dotnet", "--list-runtimes"], capture_output=True, text=True)
    except OSError:
        return []
    return [ln.split()[1] for ln in r.stdout.splitlines() if ln.startswith("Microsoft.NETCore.App ")]


def dlib_dir(work=WORK) -> Path:
    return Path(work) / f"{DLIB_PACKAGE}.{DLIB_VERSION}" / "bin" / "x64"


def install_dlib(data: bytes, work=WORK, sha=DLIB_SHA256) -> Path:
    """Unpack the pinned NuGet package (bin/x64 only) after checking its SHA-256."""
    got = hashlib.sha256(data).hexdigest()
    if got != sha:
        raise SigningError(f"{DLIB_PACKAGE} {DLIB_VERSION}: sha256 {got}, expected {sha}")
    out = dlib_dir(work)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            if info.filename.startswith("bin/x64/") and not info.is_dir():
                name = info.filename[len("bin/x64/"):]
                if "/" in name or "\\" in name or name.startswith("."):
                    continue
                (out / name).write_bytes(z.read(info))
    if not (out / "Azure.CodeSigning.Dlib.dll").is_file():
        raise SigningError("the package has no bin/x64/Azure.CodeSigning.Dlib.dll")
    return out


def fetch_dlib(work=WORK) -> Path:
    import urllib.request
    pid = DLIB_PACKAGE.lower()
    with urllib.request.urlopen(DLIB_URL.format(id=pid, v=DLIB_VERSION), timeout=120) as r:
        data = r.read()
    return install_dlib(data, work)


def check(acc=None, work=WORK) -> list[str]:
    """Problems that stop a signing run (empty: ready). Prints what it found."""
    problems = []
    try:
        print(f"signtool: {find_signtool()}")
    except SigningError as e:
        problems.append(str(e))
    d = dlib_dir(work) / "Azure.CodeSigning.Dlib.dll"
    if d.is_file():
        print(f"dlib: {d} ({DLIB_PACKAGE} {DLIB_VERSION})")
    else:
        problems.append(f"no dlib at {d}: run `py -3 tools/artifact_signing.py setup`")
    rts = dotnet_runtimes()
    if any(v.startswith(DLIB_RUNTIME) for v in rts):
        print(f".NET runtime: {', '.join(v for v in rts if v.startswith(DLIB_RUNTIME))}")
    else:
        problems.append(f"no .NET {DLIB_RUNTIME}x runtime (x64) for the dlib (dotnet --list-runtimes: {rts or 'none'})")
    if acc:
        problems += auth_problems(acc)
    return problems


# ---------------------------------------------------------------- signing

def command(signtool: Path, dlib: Path, meta: Path) -> str:
    """The --command for tools/sign_launcher.py; {file} is the exe it signs."""
    return (f'"{signtool}" sign /v /fd SHA256 /tr {TIMESTAMP_URL} /td SHA256 '
            f'/dlib "{dlib}" /dmdf "{meta}" {{file}}')


def write_metadata(acc: dict, work=WORK) -> Path:
    p = Path(work) / "metadata.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(metadata(acc), indent=1) + "\n", encoding="utf-8")
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup")
    for name in ("check", "command", "sign"):
        s = sub.add_parser(name)
        s.add_argument("--config", type=Path, help="JSON with endpoint, account, profile, auth (outside git)")
        if name == "sign":
            s.add_argument("--exe", type=Path, required=True)
            s.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "setup":
            print(f"dlib: {fetch_dlib()}")
            problems = check()
        elif a.cmd == "check":
            problems = check(load_account(a.config) if (a.config or os.environ.get("MXL_SIGNING_ACCOUNT")) else None)
        else:
            acc = load_account(a.config)
            if a.cmd == "command":
                print(command(find_signtool(), dlib_dir() / "Azure.CodeSigning.Dlib.dll", write_metadata(acc)))
                return 0
            problems = check(acc)
            if not problems:
                cmd = command(find_signtool(), dlib_dir() / "Azure.CodeSigning.Dlib.dll", write_metadata(acc))
                return subprocess.run([sys.executable, str(TOOLS / "sign_launcher.py"), "--exe", str(a.exe),
                                       "--out", str(a.out), "--command", cmd]).returncode
    except SigningError as e:
        problems = [str(e)]
    for p in problems:
        print(f"artifact_signing: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

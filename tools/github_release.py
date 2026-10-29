#!/usr/bin/env python3
"""Create (or update) a GitHub or Forgejo release for a D2R-XL 2012 version from its CHANGELOG.md section (docs/release.md step 5).

  --forge: the release goes to the forge (git.werdegames.com, WerdeGames/mxl2012-d2r) through its API instead, with the
  token from $MXL_FORGE_TOKEN or ~/.mxl2012-d2r/forge_token; --commit is then the FORGE's commit (its history is not scrubbed, so ids differ).

  py -3 tools/github_release.py 0.1.0 --commit <sha on GitHub main> [--downloader build/launcher/Release/D2R-XL-2012-Downloader.exe]
                                       [--repo Nugwa628/mxl2012-d2r] [--latest] [--dry-run]

The body is the "### <version>" section of CHANGELOG.md, plus the download links: the downloader (always the newest
installer) and the release's 7z on files.werdegames.com. The 7z itself is not attached; it lives on the download host,
because hundreds of MB over the developer's uplink are too slow. --downloader attaches the exe (2 MB) to the release. The tag
`v<version>` is created on --commit, a commit of the public (scrubbed) main: the forge's commit ids differ, see
docs/release.md. Needs the GitHub CLI (`gh`), logged in.
"""
import pathlib as _pl, sys as _sys; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent)); import projtemp  # noqa: E402,E702,F401  (temp files stay inside the project, tools/projtemp.py)
import argparse
import json
import os
import re
import urllib.error
import urllib.request
import uuid
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://files.werdegames.com/mxl2012/"


def changelog_section(text: str, version: str) -> str:
    """The body of the first "### <version>" heading of CHANGELOG.md (the D2R-XL 2012 part comes first), without the heading."""
    m = re.search(rf"^### {re.escape(version)}\b[^\n]*\n(.*?)(?=^### |^## |\Z)", text, re.M | re.S)
    if not m:
        raise SystemExit(f"CHANGELOG.md has no '### {version}' section")
    return m.group(1).strip()


def release_body(version: str, section: str, downloader_version: str = "") -> str:
    section = section.replace("](docs/", "](https://github.com/Nugwa628/mxl2012-d2r/blob/main/docs/")  # release pages have no relative links
    lines = [section, "", "**Install or update:** run the D2R-XL 2012 Downloader"]
    if downloader_version:
        lines[-1] += f" ({SITE}launcher/{downloader_version}/D2R-XL-2012-Downloader.exe)"
    lines[-1] += ". It installs the newest release into your D2R folder's `mods\\mxl2012`."
    lines += ["", f"**Manual install:** [D2R-XL-2012-{version}.7z]({SITE}releases/{version}/D2R-XL-2012-{version}.7z), unpacked into "
              "your D2R `mods` folder (see the README).",
              "",
              "Needs Diablo II: Resurrected build 93847 (Battle.net) and D2RLoader 1.3.1. "
              "Known bugs: [docs/bugs.md](https://github.com/Nugwa628/mxl2012-d2r/blob/main/docs/bugs.md)."]
    return "\n".join(lines) + "\n"


FORGE_API = "https://git.werdegames.com/api/v1/repos/WerdeGames/mxl2012-d2r"


def forge(method, path, token, body=None, data=None, ctype="application/json"):
    req = urllib.request.Request(FORGE_API + path, method=method, data=data if data is not None else
                                 (json.dumps(body).encode() if body is not None else None),
                                 headers={"Authorization": f"token {token}", "Content-Type": ctype, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def forge_release(version, commit, body, downloader, latest, token):
    tag = f"v{version}"
    try:
        rel = forge("GET", f"/releases/tags/{tag}", token)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        rel = None
    fields = {"name": f"D2R-XL 2012 {version}", "body": body, "draft": False, "prerelease": False}
    if rel:
        rel = forge("PATCH", f"/releases/{rel['id']}", token, fields)
    else:
        rel = forge("POST", "/releases", token, {**fields, "tag_name": tag, "target_commitish": commit})
    if downloader:
        for a in rel.get("assets") or []:
            if a["name"] == downloader.name:
                forge("DELETE", f"/releases/{rel['id']}/assets/{a['id']}", token)
        b = uuid.uuid4().hex
        crlf = "\r\n"
        head = (f"--{b}{crlf}Content-Disposition: form-data; name=\"attachment\"; filename=\"{downloader.name}\"{crlf}"
                f"Content-Type: application/octet-stream{crlf}{crlf}")
        data = head.encode() + downloader.read_bytes() + f"{crlf}--{b}--{crlf}".encode()
        forge("POST", f"/releases/{rel['id']}/assets?name={downloader.name}", token, data=data,
              ctype=f"multipart/form-data; boundary={b}")
    return rel["html_url"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("version")
    ap.add_argument("--commit", required=True, help="commit on the GitHub main to tag")
    ap.add_argument("--repo", default="Nugwa628/mxl2012-d2r")
    ap.add_argument("--downloader", type=Path, help="D2R-XL-2012-Downloader.exe to attach")
    ap.add_argument("--downloader-version", default="", help="its version, for the link (default: read from the exe)")
    ap.add_argument("--latest", action="store_true", help="mark as the latest release")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--forge", action="store_true", help="release on the forge (token in $MXL_FORGE_TOKEN), not GitHub")
    a = ap.parse_args()

    dv = a.downloader_version
    if a.downloader and not dv:
        sys.path.insert(0, str(ROOT / "tools"))
        import publish_release
        dv = publish_release.exe_version(a.downloader)
    body = release_body(a.version, changelog_section((ROOT / "CHANGELOG.md").read_text("utf-8"), a.version), dv)
    tag = f"v{a.version}"
    if a.dry_run:
        print(f"{tag} on {a.commit}\n\n{body}")
        return 0
    if a.forge:
        token = os.environ.get("MXL_FORGE_TOKEN", "")
        tok_file = Path.home() / ".mxl2012-d2r" / "forge_token"  # a forge access token (repository + issue), outside the repo
        if not token and tok_file.is_file():
            token = tok_file.read_text(encoding="utf-8").strip()
        if not token:
            raise SystemExit("no forge token: set MXL_FORGE_TOKEN or save one in ~/.mxl2012-d2r/forge_token")
        print(forge_release(a.version, a.commit, body, a.downloader, a.latest, token))
        return 0
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(body)
    exists = subprocess.run(["gh", "release", "view", tag, "--repo", a.repo], capture_output=True).returncode == 0
    if exists:
        cmd = ["gh", "release", "edit", tag, "--repo", a.repo, "--notes-file", f.name, "--title", f"D2R-XL 2012 {a.version}"]
    else:
        cmd = ["gh", "release", "create", tag, "--repo", a.repo, "--target", a.commit, "--title", f"D2R-XL 2012 {a.version}",
               "--notes-file", f.name]
    cmd += ["--latest"] if a.latest else (["--latest=false"] if not exists else [])
    subprocess.check_call(cmd)
    if a.downloader:
        subprocess.check_call(["gh", "release", "upload", tag, str(a.downloader), "--repo", a.repo, "--clobber"])
    print(f"https://github.com/{a.repo}/releases/tag/{tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Scan the repository for private details that must not be public.

Usage:
  py -3 tools/check_public.py              scan tracked text files (assets/ excluded)
  py -3 tools/check_public.py --history    also scan every added line of `git log --all -p` and all commit messages
  py -3 tools/check_public.py --repo DIR   scan another checkout / bare repo (for example a rewritten mirror)
  py -3 tools/check_public.py --strings    list the distinct private strings found (input for the history scrub)

Prints `path:line: [rule] text` and exits 1 on hits. In history mode the location is `<commit>:<path>:<line in diff>`.
Intentional hits go in tools/check_public.allow: `path-glob | regex matched against the line`, one per line, `#` comments.
The rules cover: the private words of the machine's private-terms file (machine and host names, kept out of the repo), user-home paths, e-mail addresses other than
noreply addresses (personal e-mail included), internal host names (the public forge git.werdegames.com, the download host dl.werdegames.com and its CDN mirror files.werdegames.com are fine), and credentials.
The tree scan (not --history, not tools/asset_pack.py's scan of game data) also runs the `mention` rule: names of other
projects that must not appear in this repository. Its regexes come from machine.json `public_check_patterns`
(tools/localconfig.py); without one (CI, another PC) the encoded built-in copy MENTION_FALLBACK is used, so CI blocks
new mentions too. The copy is base64 of the JSON list so that this file does not spell the names out itself; to change
it, edit machine.json and re-encode: py -3 -c "import base64,json,sys; print(base64.b64encode(json.dumps(json.load(open(sys.argv[1]))['public_check_patterns']).encode()).decode())" <machine.json>
"""
import argparse
import base64
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOW_FILE = Path(__file__).with_name("check_public.allow")
SELF = {"tools/check_public.py", "tools/check_public.allow"}
MAX_BYTES = 5_000_000

# E-mail addresses that may appear: noreply addresses only (the commit identity is Nugwa628's GitHub noreply address).
ALLOWED_EMAIL = re.compile(r"^(noreply@anthropic\.com|noreply@openai\.com|t3code@users\.noreply\.github\.com|"
                           r"[\w.+-]+@users\.noreply\.github\.com|noreply@github\.com)$", re.I)
# Placeholder user names that are fine in a home path.
HOME_OK = {"public", "default", "all", "username", "user", "you", "me", "name", "yourname", "<user>", "%username%",
           "$user", "${user}", "{user}", "runner", "<name>", "x"}
# Public hosts under our own domain: the forge, the download host and its Spaces/Cloudflare mirror (docs/hosting.md).
HOST_OK = {"git.werdegames.com", "dl.werdegames.com", "files.werdegames.com"}

# Private words (machine names, the CI host, ...) are NOT listed here: this file is public. They live outside the
# repository, one regex per line (case-insensitive, `#` comments), in $MXL_PRIVATE_TERMS or machine.json private_terms_file.
# Without that file only the generic rules below run (CI). Every IPv4 address is flagged by the generic ip rule anyway.


def _machine():
    """machine.json (tools/localconfig.py), {} without one. Read directly: this tool runs as `python3 -I` in CI."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import localconfig
        return localconfig.machine()
    except (ImportError, SystemExit):
        return {}
    finally:
        sys.path.pop(0)


MACHINE = _machine()
PRIVATE_TERMS = Path(os.environ.get("MXL_PRIVATE_TERMS") or MACHINE.get("private_terms_file") or ROOT / ".no-private-terms")
# Built-in copy of the mention rule's regexes for machines without machine.json (base64 of a JSON list, see the docstring).
MENTION_FALLBACK = ("WyJEMlItWEwoPyFbIC1dMjAxMikiLCAiKD9pKXNpc3Rlcig/IXMnPyAoPzpidXJpYWx8b2YgdGhlIHNpZ2h0bGVzc3x0byB0aGUgc2xhdWdodG"
                    "VyKSkiLCAiKD9pKW14bC1kMnIiLCAiMlxcLjE0KFxcLjQpP1xcYiIsICJNZWRpYW4gWEwgMlxcLjEiXQ==")


def load_mentions(cfg=None):
    """The mention rule's compiled regexes: machine.json public_check_patterns, else the built-in copy."""
    cfg = MACHINE if cfg is None else cfg
    pats = cfg.get("public_check_patterns") or json.loads(base64.b64decode(MENTION_FALLBACK))
    return [re.compile(x) for x in pats]


MENTIONS = load_mentions()


def scan_mentions(line, mentions=None):
    """[("mention", matched string)] for one line of a tracked file."""
    return [("mention", m.group(0)) for rx in (MENTIONS if mentions is None else mentions) for m in rx.finditer(line)]


def load_private_terms():
    if not PRIVATE_TERMS.is_file():
        return []
    out = []
    for ln in PRIVATE_TERMS.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            out.append(("private", re.compile(ln, re.I)))
    return out


RULES = load_private_terms() + [
    ("secret", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bglpat-[\w-]{20,}\b|"
                          r"(?:password|passwd|token|secret|api[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9+/_-]{20,}", re.I)),
]
HOME_RE = re.compile(r"(?:\b[A-Za-z]:[\\/]{1,4}Users|(?<![\w.~-])/(?:Users|home))[\\/]{1,4}([^\\/\s\"'`<>|:*?,;)\]]+)", re.I)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
HOST_RE = re.compile(r"\b((?:[a-z0-9-]+\.)+(?:werdegames\.com|lan|local|internal|corp|ts\.net))\b", re.I)
IPV4_RE = re.compile(r"(?<![\w.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\w.])")


def load_allow():
    out = []
    if ALLOW_FILE.exists():
        for ln in ALLOW_FILE.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#") or "|" not in ln:
                continue
            g, rx = ln.split("|", 1)
            out.append((g.strip(), re.compile(rx.strip())))
    return out


def scan_line(line):
    """Return [(rule, matched string)] for one line of text."""
    hits = []
    for name, rx in RULES:
        for m in rx.finditer(line):
            hits.append((name, m.group(0)))
    for m in HOME_RE.finditer(line):
        who = m.group(1)
        if who.lower() in HOME_OK or who.startswith(("<", "%", "$", "{")):
            continue
        hits.append(("home-path", m.group(0)))
    for m in EMAIL_RE.finditer(line):
        if not ALLOWED_EMAIL.match(m.group(0)):
            hits.append(("email", m.group(0)))
    for m in HOST_RE.finditer(line):
        if m.group(1).lower() not in HOST_OK:
            hits.append(("host", m.group(1)))
    for m in IPV4_RE.finditer(line):
        o = [int(x) for x in m.groups()]
        if any(x > 255 for x in o) or o[0] in (0, 127) or o == [255, 255, 255, 255]:
            continue
        hits.append(("ip", m.group(0)))
    return hits


def allowed(path, line, allow):
    return any(fnmatch.fnmatch(path, g) and rx.search(line) for g, rx in allow)


def git(repo, *args, text=True):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=False, check=True).stdout


def scan_tree(repo, allow):
    out = []
    files = git(repo, "ls-files", "-z").decode("utf-8", "replace").split("\0")
    for rel in files:
        if not rel or rel.startswith("assets/") or rel in SELF:
            continue
        p = Path(repo) / rel
        try:
            if not p.is_file() or p.stat().st_size > MAX_BYTES:
                continue
            data = p.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:8192]:
            continue
        for n, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            for rule, s in scan_line(line) + scan_mentions(line):
                if not allowed(rel, line, allow):
                    out.append((f"{rel}:{n}", rule, s, line.strip()[:200]))
    return out


def scan_history(repo, allow, with_assets=False):
    """Added lines of every commit on every ref plus commit messages (author lines included)."""
    out = []
    sep = "\x1e@@COMMIT@@"
    proc = subprocess.Popen(
        ["git", "-C", str(repo), "log", "--all", "-p", "--no-color", "--no-ext-diff", "-U0", "--text",
         f"--format={sep}%H%n%an <%ae>|%cn <%ce>%n%B%n\x1e@@BODYEND@@"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    commit = path = None
    in_msg = False
    seen = set()
    for raw in proc.stdout:
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if line.startswith(sep):
            commit, path, in_msg, first = line[len(sep):][:10], "<message>", True, True
            continue
        if in_msg:
            if line.startswith("\x1e@@BODYEND@@"):
                in_msg = False
                path = None
                continue
            where = f"{commit}:<message>"
            for rule, s in scan_line(line):
                if (where, s) not in seen and not allowed("<message>", line, allow):
                    seen.add((where, s))
                    out.append((where, rule, s, line.strip()[:200]))
            continue
        if line.startswith("+++ "):
            path = line[4:].removeprefix("b/")
            continue
        if line.startswith("--- ") or not line.startswith("+") or path is None:
            continue
        if (path.startswith("assets/") and not with_assets) or path in SELF:
            continue
        body = line[1:]
        for rule, s in scan_line(body):
            key = (commit, path, s)
            if key not in seen and not allowed(path, body, allow):
                seen.add(key)
                out.append((f"{commit}:{path}", rule, s, body.strip()[:200]))
    proc.wait()
    return out


def main():
    sys.stdout.reconfigure(errors="replace")  # binary-looking lines on a non-UTF-8 console
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=str(ROOT))
    ap.add_argument("--history", action="store_true", help="also scan all history and commit messages")
    ap.add_argument("--history-only", action="store_true")
    ap.add_argument("--assets", action="store_true", help="history scan: include assets/ (the tree scan never does)")
    ap.add_argument("--strings", action="store_true", help="print the distinct matched strings with counts")
    ap.add_argument("--no-allow", action="store_true", help="ignore tools/check_public.allow")
    a = ap.parse_args()
    allow = [] if a.no_allow else load_allow()
    hits = []
    if not a.history_only:
        hits += scan_tree(a.repo, allow)
    if a.history or a.history_only:
        hits += scan_history(a.repo, allow, a.assets)
    if a.strings:
        from collections import Counter
        for (rule, s), n in sorted(Counter((r, s) for _, r, s, _ in hits).items()):
            print(f"{n:6d}  [{rule}] {s}")
    else:
        for where, rule, s, line in hits:
            print(f"{where}: [{rule}] {s}  <- {line}")
    print(f"{len(hits)} hit(s)", file=sys.stderr)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())

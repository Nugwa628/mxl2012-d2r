#!/usr/bin/env python
"""ON HOLD (owner, 2026-11-17): the separate downloader repository and SignPath are on hold (Azure Artifact Signing signs
the downloader from this repository); kept as it was, not extended.

Export the downloader into its own public repository (github.com/Nugwa628/d2r-xl-2012-downloader, MIT).

This repository stays the source of truth; the downloader repository holds only what the downloader's build, its tests and
its signing need (docs/launcher.md "Release and signing"):

  launcher/                      the source, resources, tests and SignPath artifact configuration (as here)
  tools/sign_launcher.py         and tools/test_sign_launcher.py (as here)
  LICENSE                        MIT (as here)
  docs/launcher.md               trimmed: no "Testing" section and no lane validation notes; links to pages that are not
                                 exported point at the mod's GitHub repository
  docs/code-signing-policy.md    (links as above)
  downloader-repo/*              written for that repository, exported to its root: README.md, NOTICE.md (limited to the
                                 downloader), .gitignore, .github/workflows/sign-launcher.yml, tools/projtemp.py

Every file under launcher/ and downloader-repo/ must match ALLOW: a new file there stops the export until it is added
here on purpose. The whole export is scanned like tools/check_public.py (private terms, player names, home paths,
e-mail addresses, hosts, IPs, tokens, the retired domain) plus DENY (wild-healer, Laz's sites, Nexus, Discord, the runs
folder, the wiki tools); any hit stops it before anything is written.

  py -3 tools/downloader_repo.py list                     the files and where they go
  py -3 tools/downloader_repo.py check                    allow-list and scan only
  py -3 tools/downloader_repo.py export DIR [--worktree]  write the tree into DIR (an empty or earlier export folder)
  py -3 tools/downloader_repo.py commit CLONE             export into a clone of the downloader repository and commit
                                                          what changed: "Sync from MXL2012-D2R <commit>: <subject>"

By default the files come from a commit (--rev, default HEAD), so the commit named in the message is exactly what was
exported; --worktree (export / check / list only) reads the working tree instead. commit never pushes: push the clone
yourself, its workflow then builds, tests and (on request) signs.
"""
import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import check_public  # noqa: E402

REPO_URL = "https://github.com/Nugwa628/d2r-xl-2012-downloader"
MOD_BLOB = "https://github.com/Nugwa628/mxl2012-d2r/blob/main/"
SOURCE_NAME = "MXL2012-D2R"

ROOTS = ("launcher/", "downloader-repo/")
CURATED = "downloader-repo/"
# Files outside ROOTS, exported at the same path.
EXTRA = ("LICENSE", "tools/sign_launcher.py", "tools/test_sign_launcher.py", "docs/launcher.md",
         "docs/code-signing-policy.md")

# One pattern per path; "*" never crosses a "/" (match()).
ALLOW = (
    "launcher/CMakeLists.txt",
    "launcher/signpath-artifact-configuration.xml",
    "launcher/cmake/*.cmake",
    "launcher/res/ART.md",
    "launcher/res/launcher.manifest",
    "launcher/res/launcher.rc",
    "launcher/res/OFL-*.txt",
    "launcher/res/*.ttf",
    "launcher/res/*.png",
    "launcher/res/*.svg",
    "launcher/res/*.ico",
    "launcher/src/core/*.h",
    "launcher/src/core/*.cpp",
    "launcher/src/win/*.h",
    "launcher/src/win/*.cpp",
    "launcher/tests/CMakeLists.txt",
    "launcher/tests/*.cpp",
    "launcher/tests/data/*.py",
    "launcher/tests/data/*.json",
    "launcher/tests/data/*.zip",
    "launcher/tests/data/*.7z",
    "launcher/tests/fake_loader/*.cpp",
    "launcher/tests/fake_loader/*.rc",
    "launcher/third_party/lzma/README.md",
    "launcher/third_party/lzma/lzma-sdk.txt",
    "launcher/third_party/lzma/lzma.cmake",
    "launcher/third_party/lzma/C/*.c",
    "launcher/third_party/lzma/C/*.h",
    "downloader-repo/README.md",
    "downloader-repo/NOTICE.md",
    "downloader-repo/.gitignore",
    "downloader-repo/.github/workflows/sign-launcher.yml",
    "downloader-repo/tools/projtemp.py",
)

# check_public.allow for the export (its own list: what is fine in the mod's repository is not automatically fine here).
EXPORT_ALLOW = [(g, re.compile(rx)) for g, rx in (
    ("launcher/res/launcher.manifest", r'Microsoft\.Windows\.Common-Controls" version="6\.0\.0\.0"'),
    ("launcher/*", r"1\.3\.1\.[02]"),
    ("docs/launcher.md", r"`1\.3\.1\.0`"),
    ("launcher/res/OFL-CinzelDecorative.txt", r"^Copyright \(c\) 2012 Natanael Gama \(info@ndiscovered\.com\)"),
)]
DENY = [(name, re.compile(rx, re.I)) for name, rx in (
    ("wild-healer", r"wild[-_ ]?healer"),
    ("laz-site", r"modsbylaz|EnaiSiaion|median-xl\.com"),
    ("nexus", r"nexusmods"),
    ("discord", r"discord"),
    ("runs-folder", r"mxl2012-runs|MXL2012_RUNS"),
    ("wiki", r"tools/wiki|class-texts|2012wiki"),
)]


class ExportError(Exception):
    pass


def match(path: str, pattern: str) -> bool:
    a, b = path.split("/"), pattern.split("/")
    return len(a) == len(b) and all(fnmatch.fnmatchcase(x, y) for x, y in zip(a, b))


def allowed(path: str) -> bool:
    return any(match(path, p) for p in ALLOW)


def dest_of(src: str) -> str:
    return src[len(CURATED):] if src.startswith(CURATED) else src


def git(repo, *args, check=True, input=None) -> bytes:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, input=input)
    if check and r.returncode:
        raise ExportError(f"git {' '.join(args)}: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout


# ---------------------------------------------------------------- source

class Source:
    """The files of this repository at a commit (rev) or in the working tree (rev None)."""

    def __init__(self, repo=ROOT, rev="HEAD"):
        self.repo = Path(repo)
        self.rev = rev
        if rev is not None:
            self.sha = git(repo, "rev-parse", "--verify", rev + "^{commit}").decode().strip()
            self.subject = git(repo, "log", "-1", "--format=%s", self.sha).decode("utf-8", "replace").strip()

    def files(self) -> list[str]:
        pats = [r.rstrip("/") for r in ROOTS] + list(EXTRA)
        if self.rev is None:
            out = git(self.repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *pats)
            names = [n for n in out.decode("utf-8").split("\0") if n and (self.repo / n).is_file()]
        else:
            out = git(self.repo, "ls-tree", "-r", "-z", "--name-only", self.sha, "--", *pats)
            names = [n for n in out.decode("utf-8").split("\0") if n]
        return sorted(set(names))

    def read(self, path: str) -> bytes:
        if self.rev is None:
            return (self.repo / path).read_bytes()
        return git(self.repo, "cat-file", "blob", f"{self.sha}:{path}")


# ---------------------------------------------------------------- transforms

LINK_RE = re.compile(r"\]\(([^)#:\s]+\.md)(#[^)\s]*)?\)")


def rewrite_links(text: str, page: str, exported: set[str]) -> str:
    """A relative .md link to a page that is not exported points at that page in the mod's GitHub repository."""
    base = PurePosixPath(page).parent

    def fix(m):
        target = str(PurePosixPath(*_norm((base / m.group(1)).parts)))
        if target in exported:
            return m.group(0)
        return f"]({MOD_BLOB}{target}{m.group(2) or ''})"
    return LINK_RE.sub(fix, text)


def _norm(parts):
    out = []
    for p in parts:
        if p == "..":
            if out:
                out.pop()
        elif p != ".":
            out.append(p)
    return out


def drop_section(text: str, heading: str) -> str:
    """Remove a '## heading' section up to the next '## ' heading or the end."""
    lines = text.split("\n")
    out, skip = [], False
    for ln in lines:
        if ln.startswith("## "):
            skip = ln.strip() == heading
        if not skip:
            out.append(ln)
    return "\n".join(out)


def drop_paragraphs(text: str, start: str) -> str:
    """Remove every paragraph (up to a blank line) whose first line starts with `start`."""
    out, skip = [], False
    for ln in text.split("\n"):
        if not skip and ln.startswith(start):
            skip = True
        if skip:
            if ln.strip() == "":
                skip = False
            continue
        out.append(ln)
    return "\n".join(out)


NOTE = ("> This page comes from the D2R-XL 2012 repository (<https://github.com/Nugwa628/mxl2012-d2r>), exported by its "
        "`tools/downloader_repo.py`. Other `docs/` pages and `tools/` scripts named here are in that repository.\n")


def transform(path: str, data: bytes, exported: set[str]) -> bytes:
    if not path.endswith(".md") or path.startswith(CURATED):
        return data
    text = data.decode("utf-8")
    if path == "docs/launcher.md":
        text = drop_section(text, "## Testing")
        text = drop_paragraphs(text, "Validation for lane")
        text = re.sub(r"\n{3,}", "\n\n", text).rstrip("\n") + "\n"
        title, _, rest = text.partition("\n")
        text = f"{title}\n\n{NOTE}{rest}"
    if path.startswith("docs/"):
        text = rewrite_links(text, path, exported)
    return text.encode("utf-8")


# ---------------------------------------------------------------- the export

def plan(src: Source) -> dict[str, str]:
    """{destination: source path}; refuses files under ROOTS that are not on ALLOW and missing EXTRA files."""
    names = src.files()
    refused = [n for n in names if n.startswith(ROOTS) and not allowed(n)]
    if refused:
        raise ExportError("not on the downloader export's allow-list (tools/downloader_repo.py ALLOW): " + ", ".join(refused))
    missing = [e for e in EXTRA if e not in names]
    if missing:
        raise ExportError("missing: " + ", ".join(missing))
    out = {}
    for n in names:
        d = dest_of(n)
        if d in out:
            raise ExportError(f"{n} and {out[d]} both export to {d}")
        if not d or d.startswith(".git/") or d == ".git":
            raise ExportError(f"refused destination {d!r}")
        out[d] = n
    return dict(sorted(out.items()))


def scan_text(path: str, data: bytes, extra_deny=()) -> list[tuple]:
    if b"\0" in data[:8192]:
        return []
    hits = []
    for n, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
        found = check_public.scan_line(line) + check_public.scan_mentions(line)
        found += [(name, m.group(0)) for name, rx in [*DENY, *extra_deny] for m in rx.finditer(line)]
        for rule, s in found:
            if not any(match_glob(path, g) and rx.search(line) for g, rx in EXPORT_ALLOW):
                hits.append((f"{path}:{n}", rule, s, line.strip()[:160]))
    return hits


def match_glob(path: str, g: str) -> bool:
    return fnmatch.fnmatch(path, g)


def load_deny_file(path) -> list:
    if not path:
        return []
    out = []
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            out.append(("deny-file", re.compile(ln, re.I)))
    return out


def build(src: Source, extra_deny=()) -> dict[str, bytes]:
    """The exported tree as {destination: bytes}, scanned; raises ExportError on any problem."""
    p = plan(src)
    exported = set(p)
    tree = {d: transform(d, src.read(s), exported) for d, s in p.items()}
    hits = [h for d, data in tree.items() for h in scan_text(d, data, extra_deny)]
    if hits:
        raise ExportError("the export would publish:\n" + "\n".join(f"  {w}  [{r}] {s!r}  {ln}" for w, r, s, ln in hits))
    return tree


def write_tree(tree: dict[str, bytes], out: Path) -> tuple[list[str], list[str]]:
    """Write the tree into out; delete files of an earlier export that are no longer in it. Returns (written, removed)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for d, data in tree.items():
        f = out / d
        if not f.is_file() or f.read_bytes() != data:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
            written.append(d)
    removed = []
    marker = out / ".downloader-export"
    if marker.is_file():
        for d in marker.read_text(encoding="utf-8").splitlines():
            if d and d not in tree and (out / d).is_file():
                (out / d).unlink()
                removed.append(d)
    marker.write_text("".join(d + "\n" for d in tree), encoding="utf-8", newline="\n")
    return written, removed


def export_dir(src: Source, out: Path, extra_deny=()) -> tuple[list[str], list[str]]:
    out = Path(out)
    if out.exists() and any(out.iterdir()) and not (out / ".downloader-export").is_file():
        raise ExportError(f"{out} is not empty and not an earlier export")
    if (out / ".git").exists():
        raise ExportError(f"{out} is a git repository: use commit")
    return write_tree(build(src, extra_deny), out)


def commit_message(src: Source) -> str:
    subject = src.subject
    if scan_text("message", subject.encode("utf-8")):
        subject = "downloader update"
    return (f"Sync from {SOURCE_NAME} {src.sha[:10]}: {subject}\n\n"
            f"Exported by tools/downloader_repo.py from {SOURCE_NAME} commit {src.sha}.\n")


def commit_clone(src: Source, clone: Path, extra_deny=(), author=None) -> str | None:
    """Export into a clone of the downloader repository and commit the change. Returns the new commit or None."""
    if src.rev is None:
        raise ExportError("commit needs a commit to name (--rev), not the working tree")
    clone = Path(clone).resolve()
    top = git(clone, "rev-parse", "--show-toplevel").decode().strip()
    if Path(top).resolve() != clone:
        raise ExportError(f"{clone} is not the top of a git repository")
    if git(clone, "status", "--porcelain", "--untracked-files=all").strip():
        raise ExportError(f"{clone} has uncommitted changes; commit or remove them first")
    tree = build(src, extra_deny)
    tracked = [n for n in git(clone, "ls-files", "-z").decode("utf-8").split("\0") if n]
    gone = [n for n in tracked if n not in tree]
    for i in range(0, len(gone), 100):
        git(clone, "rm", "-q", "--", *gone[i:i + 100])
    for d, data in tree.items():
        f = clone / d
        if not f.is_file() or f.read_bytes() != data:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
    names = list(tree)
    for i in range(0, len(names), 100):
        git(clone, "add", "--", *names[i:i + 100])
    if subprocess.run(["git", "-C", str(clone), "diff", "--cached", "--quiet"]).returncode == 0:
        return None
    args = ["commit", "-q", "-F", "-"]
    if author:
        args[1:1] = ["--author", author]
    git(clone, *args, input=commit_message(src).encode("utf-8"))
    return git(clone, "rev-parse", "HEAD").decode().strip()


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("list", "check", "export", "commit"):
        s = sub.add_parser(name)
        if name == "export":
            s.add_argument("dir", type=Path)
        if name == "commit":
            s.add_argument("clone", type=Path)
            s.add_argument("--author", help='"Name <email>" for the commit (default: the clone\'s git identity)')
        else:
            s.add_argument("--worktree", action="store_true", help="read the working tree instead of a commit")
        s.add_argument("--rev", default="HEAD")
        s.add_argument("--repo", type=Path, default=ROOT)
        s.add_argument("--deny-file", type=Path, help="extra regexes (one per line) the export must not contain")
    a = ap.parse_args(argv)
    try:
        src = Source(a.repo, None if getattr(a, "worktree", False) else a.rev)
        deny = load_deny_file(a.deny_file)
        if a.cmd == "list":
            for d, s in plan(src).items():
                print(d if d == s else f"{d}  <- {s}")
        elif a.cmd == "check":
            tree = build(src, deny)
            print(f"ok: {len(tree)} files, allow-list and scan clean")
        elif a.cmd == "export":
            written, removed = export_dir(src, a.dir, deny)
            print(f"exported to {a.dir}: {len(written)} written, {len(removed)} removed")
        else:
            c = commit_clone(src, a.clone, deny, a.author)
            print(f"committed {c} in {a.clone} (not pushed)" if c else "nothing changed: no commit")
    except ExportError as e:
        print(f"downloader_repo: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""The string keys and ids the plugin uses must exist (docs/strings.md "Plugin keys"), so the game never shows "Missing string".

Checked (called from validate.py, which fails the build on a finding; `python tools/plugin_keys.py` runs it alone):

  keys     every full key written as a string literal in plugin/src (generated headers mxl_npc_actions.h labelKey / promptKey,
           mxl_items.h trophy keys, and the hard-coded ones in strings_logic.h): `mxl2012:<key>` must be a Median-only key of
           work/mod/data/local/lng/strings/mxl2012/median.json, `d2r:<key>` a key of D2R's own string files, and a key
           without a namespace is not allowed (the plugin hands the service full keys).
  ids      the numeric D2R string ids in mxl_npc_actions.h (Slot label / prompt) and the ids the source names as
           `... = 0xd10;  // "Yes" (D2R string 3344)` must be ids of D2R's string files (and, for the annotated ones, carry
           that text).

Comments are ignored; string literals are read as written (keys are plain ASCII identifiers or words).
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import strings_ns  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "plugin" / "src"
MEDIAN_JSON = strings_ns.MOD_STRINGS / strings_ns.NAMESPACE / "median.json"

_TOKEN = re.compile(r'"(?:\\.|[^"\\\n])*"|//[^\n]*|/\*.*?\*/', re.S)
_KEY = re.compile(r'"((?:mxl2012|d2r):[^"]*)"')
_SLOT = re.compile(r"\{(-?\d+), (-?\d+), (\d+), (-?\d+), (-?\d+), (\d+), (\d+), (\d+), (?:true|false), (\"[^\"]*\"|nullptr), (\"[^\"]*\"|nullptr)\}")
_ANNOTATED = re.compile(r'=\s*(0x[0-9a-fA-F]+|\d+);\s*//\s*"([^"]*)"\s*\(D2R string (\d+)\)')


def strip_comments(text: str) -> str:
    """Source without // and /* */ comments (string literals stay)."""
    return _TOKEN.sub(lambda m: m.group(0) if m.group(0).startswith('"') else "", text)


def source_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*") if p.suffix in (".h", ".cpp"))


def d2r_ids() -> dict[int, str]:
    """D2R string id -> enUS text (strings/ folder; the legacy folder uses the same ids)."""
    out: dict[int, str] = {}
    folder = strings_ns.D2R_LNG / "strings"
    for p in folder.glob("*.json"):
        for e in json.loads(p.read_text("utf-8-sig")):
            if isinstance(e, dict) and "id" in e:
                out.setdefault(int(e["id"]), e.get("enUS", ""))
    return out


def check() -> tuple[list[str], dict[str, int]]:
    """(findings, counts). A finding is one line: file:line what."""
    findings: list[str] = []
    counts = {"files": 0, "keys": 0, "ids": 0}
    if not MEDIAN_JSON.exists():
        return [f"{MEDIAN_JSON.relative_to(ROOT)} is missing (run tools/tbl2json.py)"], counts
    median = {e["Key"] for e in json.loads(MEDIAN_JSON.read_text("utf-8-sig"))}
    d2r = strings_ns.d2r_keys()
    ids = d2r_ids()

    def key_finding(where: str, key: str) -> None:
        counts["keys"] += 1
        ns, bare = strings_ns.split_key(key)
        if ns == strings_ns.NAMESPACE:
            if bare not in median:
                findings.append(f"{where}: key '{key}' is not in {MEDIAN_JSON.relative_to(ROOT)}")
        elif ns == "d2r":
            if bare not in d2r:
                findings.append(f"{where}: key '{key}' is not in D2R's string files")
        else:
            findings.append(f"{where}: key '{key}' has no known namespace (mxl2012: / d2r:)")

    def id_finding(where: str, value: int, text: str | None = None) -> None:
        counts["ids"] += 1
        if value not in ids:
            findings.append(f"{where}: string id {value} is not in D2R's string files")
        elif text is not None and ids[value] != text:
            findings.append(f"{where}: string id {value} is \"{ids[value]}\" in D2R, the source says \"{text}\"")

    for path in source_files():
        raw = path.read_text("utf-8", errors="replace")
        text = strip_comments(raw)
        rel = path.relative_to(ROOT).as_posix()
        counts["files"] += 1
        for m in _KEY.finditer(text):
            key_finding(f"{rel}:{text.count(chr(10), 0, m.start()) + 1}", m.group(1))
        for m in _ANNOTATED.finditer(path.read_text("utf-8", errors="replace")):
            line = path.read_text("utf-8", errors="replace").count("\n", 0, m.start()) + 1
            value, label, annotated = int(m.group(1), 0), m.group(2), int(m.group(3))
            if value != annotated:
                findings.append(f"{rel}:{line}: constant {m.group(1)} but the comment says D2R string {annotated}")
            id_finding(f"{rel}:{line}", annotated, label)
        if path.name == "mxl_npc_actions.h":
            for m in _SLOT.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                for name, num, key in (("label", int(m.group(6)), m.group(9)), ("prompt", int(m.group(8)), m.group(10))):
                    if num:
                        id_finding(f"{rel}:{line} {name}", num)
                    elif key != "nullptr" and not key.startswith('"mxl2012:') and not key.startswith('"d2r:'):
                        findings.append(f"{rel}:{line}: {name} key {key} has no known namespace")
        if path.name == "mxl_items.h":
            for m in re.finditer(r'\{0x[0-9a-fA-F]+, ("[^"]*")\}', text):
                if not m.group(1).startswith('"mxl2012:'):
                    findings.append(f"{rel}:{text.count(chr(10), 0, m.start()) + 1}: trophy key {m.group(1)} is not a mxl2012: key")
    return findings, counts


def main() -> int:
    findings, counts = check()
    print(f"plugin string keys: {counts['keys']} keys, {counts['ids']} ids in {counts['files']} source files, "
          f"{len(findings)} findings")
    for f in findings:
        print("  " + f)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())

"""What a Linux game run leaves behind that nobody reads, removed at the end of the run (lane linfix, 2026-11-20; owner:
"if there are any redundant logs ... just have them deleted").

Kept always: report.md, logscan.txt, game_ctl.log (the run's own record), focus.json (the owner focus measurement),
state.json, every other .json / .md / .txt result, the screenshots report.md cites (and those named in `cited` texts, such
as a lane's REPORT.md), and crash reports of real crashes (docs/testing.md: a new crash report is evidence).
Removed always: empty files (proton.out, wctl-stderr.log of a quiet run) and D2R last-resort reports of a KNOWN HANDLED
first-chance exception (KNOWN_HANDLED below: told apart by exception, faulting offset and read address).
Removed when the run PASSED (report.md without a FAIL / BLOCKED / ERROR / TIMEOUT row; a run without report.md passed when
game_ctl.log names no failure): the noise logs (Proton's steam-N.log, xvfb.log, the Battle.net blz-log.txt), the slot logs
copied out before the restore (slot-logs-N/: d2rloader.log, mxl2012-core.log, harness trace / console; logscan.txt keeps
their summary) and screenshots no report cites. A failed run, and a run whose folder name a `cited` text names (a lane report citing
"runs/r13" as evidence), keeps all its logs and shots.

Usage: python tools/run_cleanup.py RUN_DIR ... [--dry-run] [--cited FILE ...]   (game_checks calls clean() itself on Linux;
env MXL_KEEP_RUN_FILES=1 turns that off)."""
import argparse
import os
import re
import sys

NOISE_LOGS = (re.compile(r"^steam-\d+\.log$"), re.compile(r"^xvfb\.log$"), re.compile(r"^blz-log\.txt$"),
              re.compile(r"^proton\.out$"), re.compile(r"^wctl-stderr\.log$"))
KEEP_NAMES = {"report.md", "logscan.txt", "game_ctl.log", "focus.json", "state.json"}
FAIL_ROW = re.compile(r"^\|[^|]*\|\s*(FAIL|BLOCKED|ERROR|TIMEOUT)\b", re.M)
FAIL_LOG = re.compile(r"TIMEOUT|start failed|steps raised|Traceback|DRIVER: done rc=[1-9]|SHARED FILES NOT RESTORED|Unhandled exception")
SHOT = re.compile(r"[\w.+-]+\.(?:png|jpg)", re.I)

# D2R's last-resort handler also records first-chance exceptions that a plugin handles itself (docs/bugs.md #17, #399).
# Each entry: (what it is, exception code, offset of RIP from its module's allocation base, read address limit).
KNOWN_HANDLED = (
    # statbook.dll before lane linfix: the sheet host's child-list scan (FindKids, sheet_host.cpp) read the entries of a
    # (begin, end) pair (0x13, 0x16) of the sheet under SEH, at every game entry (the sheet host set-up; Windows and
    # Wine; builds up to linharness b3, statbook +0x15599). The scan now skips such pairs without a read.
    ("statbook FindKids handled read (fixed in lane linfix)", 0xC0000005, 0x15599, 0x10000),
    # mxl2012-core's harness with the `diag` word only (a diagnostics run): H_CookieRecord's field probe reads the cookie
    # record's fields 6-10 as strings under SEH; a field that is no string pointer faults (lane linharness r13 / r14:
    # build linharness-b2, +0x65FC4, `mov rcx, [rdx+8]` with rdx 0xF). Left as it is: diagnostics only.
    ("harness diag cookie-record field probe (diag word only)", 0xC0000005, 0x65FC4, 0x10000),
)


def known_handled(text):
    """The KNOWN_HANDLED entry a D2R crash report is (its name), or None: a real crash, or anything not listed."""
    if not text.startswith("D2R last-resort crash report") or "First-Chance Exception" not in text:
        return None
    code = re.search(r"Code: 0x([0-9A-Fa-f]+)", text)
    off = re.search(r"Allocation Base: [0-9A-Fa-f]+ \+ 0x([0-9A-Fa-f]+)", text)
    params = re.findall(r"\[(\d\d)\] 0x([0-9A-Fa-f]+)", text)
    if not code or not off or len(params) < 2:
        return None
    kind, addr = int(params[0][1], 16), int(params[1][1], 16)
    for name, want_code, want_off, below in KNOWN_HANDLED:
        if int(code.group(1), 16) == want_code and int(off.group(1), 16) == want_off and kind == 0 and addr < below:
            return name
    return None


def _read(path, limit=200000):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return ""


def run_passed(run_dir):
    """True when the run passed: report.md has no FAIL / BLOCKED / ERROR / TIMEOUT row, or (no report) game_ctl.log names
    no failure. A run folder with neither is treated as failed (nothing is judged, so nothing but the always-rules goes)."""
    report = os.path.join(run_dir, "report.md")
    if os.path.isfile(report):
        return not FAIL_ROW.search(_read(report))
    log = os.path.join(run_dir, "game_ctl.log")
    if os.path.isfile(log):
        return not FAIL_LOG.search(_read(log, 5000000))
    return False


def plan(run_dir, cited_texts=()):
    """[(path, why)] of what clean() removes in run_dir (nothing outside it)."""
    run_dir = os.path.abspath(run_dir)
    name_re = re.compile(r"(?<![\w-])%s(?![\w-])" % re.escape(os.path.basename(run_dir.rstrip(os.sep))))
    cited_run = any(name_re.search(t) for t in cited_texts)  # a report names the run folder: all of it is evidence
    passed = run_passed(run_dir) and not cited_run
    cited = set(SHOT.findall(_read(os.path.join(run_dir, "report.md"))))
    for t in cited_texts:
        cited |= set(SHOT.findall(t))
    out = []
    for root, _dirs, files in os.walk(run_dir):
        rel_root = os.path.relpath(root, run_dir)
        in_slot_logs = rel_root.split(os.sep)[0].startswith("slot-logs-")
        for name in sorted(files):
            p = os.path.join(root, name)
            if os.path.islink(p):
                continue
            crash = "crashes" in rel_root.split(os.sep) or name.startswith("d2r-")
            if crash:
                why = known_handled(_read(p)) if name.endswith(".log") else None
                if why:
                    out.append((p, "crash report of a known handled exception: " + why))
                continue  # any other crash file (real crash, .dmp) is evidence
            if name in KEEP_NAMES and rel_root == ".":
                continue
            if os.path.getsize(p) == 0:
                out.append((p, "empty"))
                continue
            if not passed:
                continue
            if rel_root == "." and any(r.match(name) for r in NOISE_LOGS):
                out.append((p, "noise log of a passed run"))
            elif in_slot_logs:
                out.append((p, "slot log of a passed run (logscan.txt has its summary)"))
            elif rel_root == "." and name.lower().endswith((".png", ".jpg")) and name not in cited:
                out.append((p, "screenshot no report cites, passed run"))
    return out


def clean(run_dir, cited_texts=(), dry_run=False, log=print):
    """Remove plan(run_dir) (files, then the folders that became empty); one log line with the count, size and names.
    Returns (files removed, bytes)."""
    items = plan(run_dir, cited_texts)
    size = 0
    for p, _ in items:
        try:
            size += os.path.getsize(p)
            if not dry_run:
                os.remove(p)
        except OSError:
            pass
    if not dry_run:
        for root, dirs, files in os.walk(os.path.abspath(run_dir), topdown=False):
            if root != os.path.abspath(run_dir) and not os.listdir(root):
                try:
                    os.rmdir(root)
                except OSError:
                    pass
    if items:
        names = ", ".join(sorted({os.path.relpath(p, run_dir) for p, _ in items})[:40])
        kinds = sorted({why.split(":")[0] for _, why in items})
        log("run cleanup%s: %d files, %.1f MB removed from %s (%s): %s" % (" (dry run)" if dry_run else "", len(items),
            size / 1e6, run_dir, "; ".join(kinds), names))
    else:
        log("run cleanup: nothing to remove in %s" % run_dir)
    return len(items), size


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cited", action="append", default=[], help="a text (e.g. a lane REPORT.md) whose shot names are kept")
    a = ap.parse_args(argv)
    texts = [_read(p, 10000000) for p in a.cited]
    total = [0, 0]
    for r in a.runs:
        if os.path.isdir(r):
            n, b = clean(r, texts, a.dry_run)
            total[0] += n
            total[1] += b
    print("total: %d files, %.1f MB%s" % (total[0], total[1] / 1e6, " (dry run)" if a.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

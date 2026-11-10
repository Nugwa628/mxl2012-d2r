"""Reads the drawcap plugin's per-interval stats (d2rloader/logs/drawcap-stats.csv, drawcap/README.md) and sums them up.

The plugin writes one line per graphics mode per interval (default 1 s):
  t_ms,mode,frames,max,mean,over,dropped,cap,view_w,view_h,grid
The file is new at each game start; lines starting with '#' are comments. Read-only: this module never touches the game.

  py -3 tools/drawcap_stats.py CSV [--since T_MS] [--mode legacy|hd]   # one summary per mode
"""
import argparse
import os
import sys

FIELDS = ("t_ms", "mode", "frames", "max", "mean", "over", "dropped", "cap", "view_w", "view_h", "grid")


def parse(text: str) -> list:
    """The data rows of a drawcap-stats.csv text as dicts (numbers as int, mean as float); malformed lines are skipped."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("t_ms"):
            continue
        parts = line.split(",")
        if len(parts) != len(FIELDS):
            continue
        try:
            row = {k: (v if k == "mode" else float(v) if k == "mean" else int(v)) for k, v in zip(FIELDS, parts)}
        except ValueError:
            continue
        rows.append(row)
    return rows


def read(path: str) -> list:
    try:
        with open(path, encoding="ascii", errors="replace") as f:
            return parse(f.read())
    except OSError:
        return []


def summary(rows: list, mode: str = None) -> dict:
    """Max, frame-weighted mean, frames, frames over the cap, entries dropped, the busiest second (its t_ms and max), the cap and
    the view sizes seen, for the rows of one mode (or all). Empty rows give frames 0."""
    rows = [r for r in rows if mode is None or r["mode"] == mode]
    frames = sum(r["frames"] for r in rows)
    out = {"mode": mode, "rows": len(rows), "frames": frames, "max": max((r["max"] for r in rows), default=0),
           "mean": round(sum(r["mean"] * r["frames"] for r in rows) / frames, 1) if frames else 0.0,
           "over": sum(r["over"] for r in rows), "dropped": sum(r["dropped"] for r in rows),
           "cap": max((r["cap"] for r in rows), default=0),
           "views": sorted({(r["view_w"], r["view_h"]) for r in rows}),
           "fps": round(frames * 1000 / (rows[-1]["t_ms"] - rows[0]["t_ms"]), 1) if len(rows) > 1 and rows[-1]["t_ms"] > rows[0]["t_ms"] else None}
    peak = max(rows, key=lambda r: r["max"], default=None)
    out["peak_t_ms"] = peak["t_ms"] if peak else None
    return out


def describe(s: dict) -> str:
    views = " ".join("%dx%d" % v for v in s["views"]) or "-"
    return ("%s: %d frames (%s s), max %d, mean %.1f, %d frames over %d, %d entries not drawn, view %s" % (
        s["mode"] or "all", s["frames"], s["rows"], s["max"], s["mean"], s["over"], s["cap"], s["dropped"], views))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--since", type=int, default=0, help="only rows with t_ms at or after this")
    ap.add_argument("--mode", choices=("legacy", "hd", "unknown"))
    a = ap.parse_args()
    if not os.path.isfile(a.csv):
        print(f"no file {a.csv}")
        return 1
    rows = [r for r in read(a.csv) if r["t_ms"] >= a.since]
    for mode in ([a.mode] if a.mode else sorted({r["mode"] for r in rows})):
        print(describe(summary(rows, mode)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

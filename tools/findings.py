"""Summary of work/mod/validate_findings.json: severity counts, then the problems of one severity by table (default error)."""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
f = json.loads((ROOT / "work" / "mod" / "validate_findings.json").read_text("utf-8"))
sev = sys.argv[1] if len(sys.argv) > 1 else "error"
bank = sys.argv[2] if len(sys.argv) > 2 else "base"
tot = Counter()
rows = []
for k, v in f[bank].items():
    s, table, col, prob = k.split("|", 3)
    tot[s] += len(v)
    if s == sev:
        rows.append((table, col, prob, len(v), v[0]))
print(dict(tot))
for table, col, prob, n, ex in sorted(rows):
    print(f"{table}.{col}: {prob[:90]} x{n}  e.g. {ex[0]!r}: {str(ex[1])[:70]!r}".encode("ascii", "replace").decode())

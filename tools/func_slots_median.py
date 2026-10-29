import sys
from collections import defaultdict
sys.path.insert(0, "tools")
from func_slots import read, vanilla, D2R, SKILL_COLS, MISSILE_COLS, ROOT
named = ROOT / "work" / "named"
for table, cols, key in (("skills.txt", SKILL_COLS, "skill"), ("missiles.txt", MISSILE_COLS, "Missile")):
    vh, vr = vanilla(table); dh, dr = read(D2R / table); mh, mr = read(named / table)
    vn = {r[vh.index(key)] for r in vr}
    for c in cols:
        if c not in mh:
            print(c, "not in median"); continue
        ci = mh.index(c)
        use = defaultdict(list)
        for r in mr:
            if len(r) > ci and r[ci].strip():
                use[r[ci].strip()].append(r[mh.index(key)])
        v_use = defaultdict(list)
        if c in vh:
            for r in vr:
                if r[vh.index(c)].strip(): v_use[r[vh.index(c)].strip()].append(r[vh.index(key)])
        d_use = defaultdict(list)
        if c in dh:
            for r in dr:
                if r[dh.index(c)].strip(): d_use[r[dh.index(c)].strip()].append((r[dh.index(key)], r[dh.index(key)] in vn))
        print(f"### {table} {c}: D2R max {max([int(s) for s in d_use if s.isdigit()] or [0])}, 1.13c max {max([int(s) for s in v_use if s.isdigit()] or [0])}, median max {max([int(s) for s in use if s.isdigit()] or [0])}")
        for s in sorted(use, key=lambda x: int(x) if x.lstrip('-').isdigit() else -1):
            vs = v_use.get(s, []); ds = d_use.get(s, [])
            dnew = [n for n, ov in ds if not ov]; dold = [n for n, ov in ds if ov]
            flag = ""
            if set(vs) != set(dold): flag += f" VANILLA-USERS-DIFFER(1.13c {vs[:4]} / D2R {dold[:4]})"
            if not vs and ds: flag += " NO-1.13c-USER,D2R-USES"
            if dnew: flag += f" D2R-ONLY {dnew[:3]}"
            if not vs and not ds: flag += " (unused both)"
            if flag:
                print(f"  {s:>4}: median {len(use[s]):3d} {use[s][:3]} |{flag}")

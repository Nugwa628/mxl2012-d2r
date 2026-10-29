"""Compare record counts of compiled .bin tables against their .txt rows in an extracted mpq.
Usage: py -3 -I tools/bin_vs_txt.py <extract-root>"""
import os, struct, sys
root = os.path.join(sys.argv[1], 'data', 'global', 'excel')
for name in sorted(os.listdir(root)):
    if not name.endswith('.bin'):
        continue
    t = os.path.join(root, name[:-4] + '.txt')
    b = open(os.path.join(root, name), 'rb').read()
    n = struct.unpack_from('<I', b)[0] if len(b) >= 4 else -1
    if not os.path.exists(t):
        print(f'{name:28} bin={n:6}  (no txt)')
        continue
    rows = [l for l in open(t, encoding='latin-1').read().split('\n')[1:] if l.strip('\r\t ')]
    exp = sum(1 for l in rows if l.split('\t')[0].strip().lower() == 'expansion')
    rs = (len(b) - 4) / n if n > 0 else 0
    flag = '' if n in (len(rows), len(rows) - exp) else '  <-- MISMATCH'
    print(f'{name:28} bin={n:6} txt={len(rows):6} exp={exp} rec={rs:.1f}{flag}')

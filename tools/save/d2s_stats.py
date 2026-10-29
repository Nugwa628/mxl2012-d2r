import csv, sys
ISC = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))), "work", "mod", "data", "global", "excel", "itemstatcost.txt")  # the built table (tools/build.py)
rows = list(csv.DictReader(open(ISC, newline=''), delimiter='\t'))
bits = {}
for r in rows:
    if r.get('*ID','').strip() and r.get('CSvBits','').strip():
        bits[int(r['*ID'])] = (r['Stat'], int(r['CSvBits']), int(r['CSvParam'] or 0))

def read_stats(d):
    start = d.index(b'gf') + 2
    pos = 0
    def rd(n):
        nonlocal pos
        v = 0
        for i in range(n):
            byte = d[start + (pos >> 3)]
            v |= ((byte >> (pos & 7)) & 1) << i
            pos += 1
        return v
    out = []
    while True:
        sid = rd(9)
        if sid == 0x1ff:
            break
        name, n, p = bits[sid]
        par = rd(p) if p else None
        out.append((sid, name, n, p, par, rd(n)))
    return start, out, pos

def write_stats(d, start, stats, end_bits_old):
    bitsout = []
    def wr(v, n):
        for i in range(n):
            bitsout.append((v >> i) & 1)
    for sid, name, n, p, par, val in stats:
        wr(sid, 9)
        if p: wr(par, p)
        wr(val, n)
    wr(0x1ff, 9)
    while len(bitsout) % 8: bitsout.append(0)
    newb = bytes(sum(bitsout[i+j] << j for j in range(8)) for i in range(0, len(bitsout), 8))
    old_len = (end_bits_old + 7) // 8
    return d[:start] + newb + d[start+old_len:]

def checksum(d):
    d = bytearray(d)
    d[8:12] = len(d).to_bytes(4, 'little')
    d[12:16] = b'\0\0\0\0'
    c = 0
    for b in d:
        c = ((c << 1) | (c >> 31)) & 0xffffffff
        c = (c + b) & 0xffffffff
    d[12:16] = c.to_bytes(4, 'little')
    return bytes(d)

if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    s, st, end = read_stats(d)
    for x in st: print(x)
    print('end bits', end, 'next', d[s + (end+7)//8: s + (end+7)//8 + 2])
    print('checksum ok', checksum(d) == d)

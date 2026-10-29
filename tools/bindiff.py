"""Report differing records between two D2 .bin tables (4-byte count header, fixed record size).
Usage: py -3 -I tools/bindiff.py <a.bin> <b.bin>"""
import struct, sys
a = open(sys.argv[1], 'rb').read(); b = open(sys.argv[2], 'rb').read()
na = struct.unpack_from('<I', a)[0]; nb = struct.unpack_from('<I', b)[0]
ra = (len(a) - 4) // max(na, 1); rb = (len(b) - 4) // max(nb, 1)
print('records', na, nb, 'recsize', ra, rb)
for i in range(min(na, nb)):
    x = a[4 + i * ra:4 + (i + 1) * ra]; y = b[4 + i * rb:4 + (i + 1) * rb]
    if x != y:
        offs = [j for j in range(min(len(x), len(y))) if x[j] != y[j]]
        print('rec', i, 'diff bytes at', offs[:40])
        print('  a', [struct.unpack_from('<I', x, o - o % 4)[0] for o in sorted({o - o % 4 for o in offs})][:20])
        print('  b', [struct.unpack_from('<I', y, o - o % 4)[0] for o in sorted({o - o % 4 for o in offs})][:20])

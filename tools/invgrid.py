"""Print gridX/gridY of each record of an inventory.bin. Usage: py -3 -I tools/invgrid.py <inventory.bin>..."""
import struct, sys
for p in sys.argv[1:]:
    d = open(p, 'rb').read(); n = struct.unpack_from('<I', d)[0]
    print(p[-40:], [(i, d[4 + i * 240 + 16], d[4 + i * 240 + 17]) for i in range(n)])

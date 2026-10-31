"""A small FLAC encoder and decoder for 16-bit PCM (tools/sounds_port.py: Median XL 2012's own .wav sounds -> the .flac files
D2R plays). Standard library + numpy only, no audio package needed.

Encoder: fixed-blocksize frames of BLOCK samples, per channel the best of the FIXED predictors of order 0-4 (Rice-coded
residual, partition orders 0-4, 4-bit parameters, escape never used) or VERBATIM when that is not smaller; independent
channels (no stereo decorrelation), STREAMINFO with the MD5 of the samples. Lossless: decode(encode(x)) == x.

Decoder: reads what this encoder writes plus CONSTANT subframes and wasted bits (enough to check a round trip and to read
the STREAMINFO of any FLAC file); not a general decoder (no LPC subframes).
"""
import hashlib
import struct
import wave
from pathlib import Path

import numpy as np

BLOCK = 4096
MAX_ORDER = 4
MAX_PARTITION_ORDER = 4
MAX_RICE = 14  # 15 is the escape code


def _crc8(data: bytes) -> int:
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


_CRC16 = []
for _i in range(256):
    _c = _i << 8
    for _ in range(8):
        _c = ((_c << 1) ^ 0x8005) & 0xFFFF if _c & 0x8000 else (_c << 1) & 0xFFFF
    _CRC16.append(_c)


def _crc16(data: bytes) -> int:
    c = 0
    for b in data:
        c = ((c << 8) & 0xFFFF) ^ _CRC16[(c >> 8) ^ b]
    return c


class _Bits:
    """MSB-first bit writer: pieces of 0/1 uint8 arrays, packed at the end."""

    def __init__(self):
        self.parts: list[np.ndarray] = []
        self.n = 0

    def put(self, value: int, nbits: int) -> None:
        if nbits:
            value &= (1 << nbits) - 1
            self.add(np.array([(value >> (nbits - 1 - i)) & 1 for i in range(nbits)], dtype=np.uint8))

    def add(self, bits: np.ndarray) -> None:
        self.parts.append(bits)
        self.n += len(bits)

    def pad(self) -> None:
        if self.n % 8:
            self.add(np.zeros(8 - self.n % 8, dtype=np.uint8))

    def bytes(self) -> bytes:
        return np.packbits(np.concatenate(self.parts) if self.parts else np.zeros(0, np.uint8)).tobytes()


def _residual(x: np.ndarray, order: int) -> np.ndarray:
    r = x.astype(np.int64)
    for _ in range(order):
        r = np.diff(r)
    return r  # len(x) - order values: the residual of samples order..n-1


def _rice_bits(u: np.ndarray, k: int) -> int:
    return int(np.sum(u >> k)) + len(u) * (k + 1)


def _best_k(u: np.ndarray) -> tuple[int, int]:
    best = None
    for k in range(MAX_RICE + 1):
        b = _rice_bits(u, k)
        if best is None or b < best[1]:
            best = (k, b)
    return best


def _rice_encode(u: np.ndarray, k: int) -> np.ndarray:
    """Bits of the Rice codes of u (unsigned, folded): q zeros, a one, the k low bits."""
    q = u >> k
    lengths = q + 1 + k
    start = np.concatenate(([0], np.cumsum(lengths)[:-1]))
    bits = np.zeros(int(lengths.sum()), dtype=np.uint8)
    stop = start + q
    bits[stop] = 1
    for j in range(k):
        bits[stop + 1 + j] = (u >> (k - 1 - j)) & 1
    return bits


def _partitions(n: int, order: int):
    """Partition orders p usable for a block of n samples and predictor order `order`."""
    for p in range(MAX_PARTITION_ORDER + 1):
        if n % (1 << p) or (n >> p) <= order:
            break
        yield p


def _subframe(x: np.ndarray, bps: int) -> _Bits:
    n = len(x)
    best = None  # (bits, order, p, [k per partition])
    for order in range(min(MAX_ORDER, n - 1) + 1):
        r = _residual(x, order)
        if np.abs(r).max(initial=0) >= 1 << 30:
            continue
        u = np.where(r >= 0, r * 2, -r * 2 - 1)
        for p in _partitions(n, order):
            size = n >> p
            ks, total = [], 6 + order * bps + 2 + 4
            for i in range(1 << p):
                lo = max(0, i * size - order)
                hi = (i + 1) * size - order
                k, b = _best_k(u[lo:hi])
                ks.append(k)
                total += 4 + b
            if best is None or total < best[0]:
                best = (total, order, p, ks, u)
    w = _Bits()
    if best is None or best[0] >= 8 + n * bps:
        w.put(0b00000010, 8)  # pad 0, type VERBATIM 000001, no wasted bits
        for v in x.tolist():
            w.put(int(v), bps)
        return w
    _, order, p, ks, u = best
    w.put(0, 1)
    w.put(0b001000 | order, 6)
    w.put(0, 1)
    for v in x[:order].tolist():
        w.put(int(v), bps)
    w.put(0, 2)  # residual coding method: Rice, 4-bit parameters
    w.put(p, 4)
    size = n >> p
    for i, k in enumerate(ks):
        lo = max(0, i * size - order)
        hi = (i + 1) * size - order
        w.put(k, 4)
        w.add(_rice_encode(u[lo:hi], k))
    return w


def _utf8_number(v: int) -> bytes:
    if v < 0x80:
        return bytes([v])
    for n in range(2, 7):
        if v < 1 << (5 * n + 1):
            out = [0x80 | ((v >> (6 * i)) & 0x3F) for i in range(n - 1)][::-1]
            first = ((0xFF << (8 - n)) & 0xFF) | (v >> (6 * (n - 1)))
            return bytes([first, *out])
    raise ValueError(v)


def encode(samples: np.ndarray, rate: int, bps: int = 16) -> bytes:
    """samples: int array of shape (n,) or (n, channels), values within `bps` bits signed."""
    x = np.asarray(samples)
    if x.ndim == 1:
        x = x[:, None]
    n, ch = x.shape
    if not 1 <= ch <= 8 or bps not in (8, 16, 24) or not 0 < rate < 1 << 20:
        raise ValueError(f"unsupported: {ch} channels, {bps} bits, {rate} Hz")
    x = x.astype(np.int64)
    dt = {8: "<i1", 16: "<i2", 24: None}[bps]
    md5 = hashlib.md5(x.astype(dt).tobytes() if dt else b"".join(int(v).to_bytes(3, "little", signed=True)
                                                                  for v in x.ravel().tolist())).digest()
    bps_code = {8: 0b001, 16: 0b100, 24: 0b110}[bps]
    frames, sizes = [], []
    for fi, start in enumerate(range(0, n, BLOCK)):
        blk = x[start:start + BLOCK]
        hdr = _Bits()
        hdr.put(0b11111111111110, 14)
        hdr.put(0, 1)  # reserved
        hdr.put(0, 1)  # fixed blocksize
        hdr.put(0b0111, 4)  # block size: 16 bits at the end of the header
        hdr.put(0b0000, 4)  # sample rate: from STREAMINFO
        hdr.put(ch - 1, 4)  # independent channels
        hdr.put(bps_code, 3)
        hdr.put(0, 1)
        h = hdr.bytes() + _utf8_number(fi) + struct.pack(">H", len(blk) - 1)
        h += bytes([_crc8(h)])
        body = _Bits()
        for c in range(ch):
            sub = _subframe(blk[:, c], bps)
            body.parts += sub.parts
            body.n += sub.n
        body.pad()
        f = h + body.bytes()
        f += struct.pack(">H", _crc16(f))
        frames.append(f)
        sizes.append(len(f))
    info = struct.pack(">HH", BLOCK if n > BLOCK else max(n, 16), BLOCK if n > BLOCK else max(n, 16))
    info += (min(sizes, default=0)).to_bytes(3, "big") + (max(sizes, default=0)).to_bytes(3, "big")
    packed = (rate << 44) | ((ch - 1) << 41) | ((bps - 1) << 36) | n
    info += packed.to_bytes(8, "big") + md5
    return b"fLaC" + bytes([0x80]) + len(info).to_bytes(3, "big") + info + b"".join(frames)


def read_wav(path: Path) -> tuple[np.ndarray, int, int]:
    """(samples (n, channels) int, rate, bits) of a PCM .wav (8 / 16 bit)."""
    with wave.open(str(path), "rb") as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width == 1:
        x = np.frombuffer(raw, dtype=np.uint8).astype(np.int64) - 128
    elif width == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.int64)
    else:
        raise ValueError(f"{path}: {8 * width}-bit PCM not supported")
    n = len(x) // ch
    return x[:n * ch].reshape(n, ch), rate, 8 * width


def wav_to_flac(src: Path, dst: Path) -> dict:
    x, rate, bits = read_wav(src)
    data = encode(x, rate, bits)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    return {"rate": rate, "channels": x.shape[1], "bits": bits, "samples": len(x), "bytes": len(data)}


# ---- decoder (checks) ----

class _Reader:
    def __init__(self, data: bytes, pos: int = 0):
        self.data, self.bit = data, pos * 8

    def read(self, n: int) -> int:
        v = 0
        for _ in range(n):
            v = (v << 1) | ((self.data[self.bit >> 3] >> (7 - (self.bit & 7))) & 1)
            self.bit += 1
        return v

    def signed(self, n: int) -> int:
        v = self.read(n)
        return v - (1 << n) if n and v >> (n - 1) else v

    def unary(self) -> int:
        q = 0
        while not self.read(1):
            q += 1
        return q

    def align(self) -> None:
        self.bit = (self.bit + 7) & ~7


def streaminfo(data: bytes) -> dict:
    if data[:4] != b"fLaC" or data[4] & 0x7F != 0:
        raise ValueError("not a FLAC stream with STREAMINFO first")
    s = data[8:42]
    packed = int.from_bytes(s[10:18], "big")
    return {"min_block": struct.unpack(">H", s[0:2])[0], "max_block": struct.unpack(">H", s[2:4])[0],
            "rate": packed >> 44, "channels": ((packed >> 41) & 7) + 1, "bits": ((packed >> 36) & 31) + 1,
            "samples": packed & ((1 << 36) - 1), "md5": s[18:34]}


def decode(data: bytes) -> tuple[np.ndarray, int]:
    """(samples (n, channels), rate) of a FLAC stream as this module writes it."""
    info = streaminfo(data)
    pos = 4
    while True:
        last, length = data[pos] & 0x80, int.from_bytes(data[pos + 1:pos + 4], "big")
        pos += 4 + length
        if last:
            break
    ch, bps, total = info["channels"], info["bits"], info["samples"]
    out = []
    while pos < len(data) and sum(len(o) for o in out) < total:
        start = pos
        r = _Reader(data, pos)
        if r.read(14) != 0b11111111111110:
            raise ValueError(f"no frame sync at {pos}")
        r.read(2)
        bs_code, sr_code, chan, _ss, _ = r.read(4), r.read(4), r.read(4), r.read(3), r.read(1)
        if chan > 7:
            raise ValueError("stereo decorrelation not supported")
        first = r.read(8)
        extra = 0
        while first & (0x80 >> extra) and extra < 7:
            extra += 1
        for _ in range(max(0, extra - 1)):
            r.read(8)
        if bs_code == 0b0110:
            n = r.read(8) + 1
        elif bs_code == 0b0111:
            n = r.read(16) + 1
        else:
            n = {1: 192, 2: 576, 3: 1152, 4: 2304, 5: 4608}.get(bs_code) or 256 << (bs_code - 8)
        if sr_code == 0b1100:
            r.read(8)
        elif sr_code in (0b1101, 0b1110):
            r.read(16)
        hlen = (r.bit >> 3) - start
        if r.read(8) != _crc8(data[start:start + hlen]):
            raise ValueError(f"frame header CRC at {start}")
        block = np.zeros((n, ch), dtype=np.int64)
        for c in range(ch):
            r.read(1)
            typ = r.read(6)
            wasted = 0
            if r.read(1):
                wasted = r.unary() + 1
            b = bps - wasted
            if typ == 0:
                block[:, c] = r.signed(b)
            elif typ == 1:
                block[:, c] = [r.signed(b) for _ in range(n)]
            elif 8 <= typ <= 12:
                order = typ - 8
                s = [r.signed(b) for _ in range(order)]
                method, p = r.read(2), r.read(4)
                pbits = 4 if method == 0 else 5
                res = []
                for i in range(1 << p):
                    cnt = (n >> p) - (order if i == 0 else 0)
                    k = r.read(pbits)
                    if k == (1 << pbits) - 1:
                        eb = r.read(5)
                        res += [r.signed(eb) for _ in range(cnt)]
                        continue
                    for _ in range(cnt):
                        u = (r.unary() << k) | r.read(k)
                        res.append(u >> 1 if not u & 1 else -(u >> 1) - 1)
                coef = {0: [], 1: [1], 2: [2, -1], 3: [3, -3, 1], 4: [4, -6, 4, -1]}[order]
                for e in res:
                    s.append(e + sum(a * s[-1 - j] for j, a in enumerate(coef)))
                block[:, c] = s
            else:
                raise ValueError(f"subframe type {typ} not supported")
            block[:, c] <<= wasted
        r.align()
        flen = (r.bit >> 3) - start
        if r.read(16) != _crc16(data[start:start + flen]):
            raise ValueError(f"frame CRC at {start}")
        pos = r.bit >> 3
        out.append(block)
    x = np.concatenate(out) if out else np.zeros((0, ch), np.int64)
    return x, info["rate"]


def check(data: bytes, expected: np.ndarray | None = None) -> None:
    """Decodes the stream and checks the MD5 of STREAMINFO (and the samples, when given)."""
    x, _ = decode(data)
    info = streaminfo(data)
    dt = {8: "<i1", 16: "<i2"}.get(info["bits"])
    if dt and hashlib.md5(x.astype(dt).tobytes()).digest() != info["md5"]:
        raise ValueError("MD5 mismatch")
    if expected is not None:
        e = np.asarray(expected)
        if not np.array_equal(x, e if e.ndim == 2 else e[:, None]):
            raise ValueError("samples differ")


if __name__ == "__main__":
    import sys
    for a in sys.argv[1:]:
        d = Path(a).read_bytes()
        print(a, streaminfo(d))
        check(d)
        print("  decodes, MD5 ok")

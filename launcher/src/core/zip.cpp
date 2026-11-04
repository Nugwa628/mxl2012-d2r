#include "zip.h"

#include <array>
#include <cstring>

namespace mxl {
namespace {

uint32_t Get16(const std::string& s, size_t at) { return uint32_t(uint8_t(s[at])) | uint32_t(uint8_t(s[at + 1])) << 8; }
uint32_t Get32(const std::string& s, size_t at) { return Get16(s, at) | Get16(s, at + 2) << 16; }

// Bit reader and canonical Huffman decoding after zlib's puff.c (RFC 1951 3.2).
struct Bits {
	const uint8_t* p;
	size_t n, pos = 0;
	uint32_t buf = 0;
	int cnt = 0;
	bool err = false;
	int Need(int k) {
		uint32_t v = buf;
		while (cnt < k) {
			if (pos >= n) {
				err = true;
				return 0;
			}
			v |= uint32_t(p[pos++]) << cnt;
			cnt += 8;
		}
		buf = v >> k;
		cnt -= k;
		return int(v & ((1u << k) - 1));
	}
};

struct Huffman {
	std::array<short, 16> count{};
	std::array<short, 288> symbol{};
};

// < 0: over-subscribed (an error); an incomplete code is allowed (puff: a single distance code), a code it lacks fails
// at decode time.
int Build(Huffman& h, const short* length, int n) {
	h.count.fill(0);
	for (int s = 0; s < n; ++s)
		++h.count[length[s]];
	if (h.count[0] == n)
		return 0;
	int left = 1;
	for (int len = 1; len < 16; ++len) {
		left <<= 1;
		left -= h.count[len];
		if (left < 0)
			return left;
	}
	short offs[16];
	offs[1] = 0;
	for (int len = 1; len < 15; ++len)
		offs[len + 1] = short(offs[len] + h.count[len]);
	for (int s = 0; s < n; ++s)
		if (length[s] != 0)
			h.symbol[offs[length[s]]++] = short(s);
	return left;
}

int Decode(Bits& b, const Huffman& h) {
	int code = 0, first = 0, index = 0;
	for (int len = 1; len < 16; ++len) {
		code |= b.Need(1);
		if (b.err)
			return -1;
		int count = h.count[len];
		if (code - count < first)
			return h.symbol[index + (code - first)];
		index += count;
		first += count;
		first <<= 1;
		code <<= 1;
	}
	return -1;
}

constexpr short LBase[29] = {3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258};
constexpr short LExt[29] = {0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0};
constexpr short DBase[30] = {1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025, 1537, 2049, 3073,
                             4097, 6145, 8193, 12289, 16385, 24577};
constexpr short DExt[30] = {0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13};

bool Codes(Bits& b, std::string& out, size_t limit, const Huffman& lencode, const Huffman& distcode, std::string& error) {
	for (;;) {
		int sym = Decode(b, lencode);
		if (sym < 0) {
			error = "damaged deflate data (bad literal/length code)";
			return false;
		}
		if (sym < 256) {
			if (out.size() >= limit) {
				error = "deflate data is larger than the entry";
				return false;
			}
			out.push_back(char(sym));
			continue;
		}
		if (sym == 256)
			return true;
		sym -= 257;
		if (sym >= 29) {
			error = "damaged deflate data (bad length)";
			return false;
		}
		size_t len = size_t(LBase[sym] + b.Need(LExt[sym]));
		int ds = Decode(b, distcode);
		if (ds < 0 || ds >= 30) {
			error = "damaged deflate data (bad distance code)";
			return false;
		}
		size_t dist = size_t(DBase[ds] + b.Need(DExt[ds]));
		if (b.err) {
			error = "deflate data ends early";
			return false;
		}
		if (dist > out.size()) {
			error = "damaged deflate data (distance too far back)";
			return false;
		}
		if (out.size() + len > limit) {
			error = "deflate data is larger than the entry";
			return false;
		}
		size_t from = out.size() - dist;
		for (size_t i = 0; i < len; ++i)
			out.push_back(out[from + i]);
	}
}

}  // namespace

uint32_t Crc32(const void* data, size_t size, uint32_t crc) {
	static const auto table = [] {
		std::array<uint32_t, 256> t{};
		for (uint32_t i = 0; i < 256; ++i) {
			uint32_t c = i;
			for (int k = 0; k < 8; ++k)
				c = c & 1 ? 0xEDB88320u ^ (c >> 1) : c >> 1;
			t[i] = c;
		}
		return t;
	}();
	const uint8_t* p = static_cast<const uint8_t*>(data);
	crc = ~crc;
	for (size_t i = 0; i < size; ++i)
		crc = table[(crc ^ p[i]) & 0xFF] ^ (crc >> 8);
	return ~crc;
}

bool Inflate(const uint8_t* in, size_t size, std::string& out, size_t limit, std::string& error) {
	Bits b{in, size};
	out.clear();
	out.reserve(limit);
	int last;
	do {
		last = b.Need(1);
		int type = b.Need(2);
		if (b.err) {
			error = "deflate data ends early";
			return false;
		}
		if (type == 0) {  // stored: skip to the byte border
			b.buf = 0;
			b.cnt = 0;
			if (b.pos + 4 > b.n) {
				error = "deflate data ends early";
				return false;
			}
			size_t len = size_t(in[b.pos]) | size_t(in[b.pos + 1]) << 8;
			size_t nlen = size_t(in[b.pos + 2]) | size_t(in[b.pos + 3]) << 8;
			b.pos += 4;
			if (len != (~nlen & 0xFFFF)) {
				error = "damaged deflate data (stored block length)";
				return false;
			}
			if (b.pos + len > b.n) {
				error = "deflate data ends early";
				return false;
			}
			if (out.size() + len > limit) {
				error = "deflate data is larger than the entry";
				return false;
			}
			out.append(reinterpret_cast<const char*>(in + b.pos), len);
			b.pos += len;
		} else if (type == 1) {
			static const auto fixed = [] {
				std::pair<Huffman, Huffman> f;
				short lengths[288];
				int s = 0;
				for (; s < 144; ++s) lengths[s] = 8;
				for (; s < 256; ++s) lengths[s] = 9;
				for (; s < 280; ++s) lengths[s] = 7;
				for (; s < 288; ++s) lengths[s] = 8;
				Build(f.first, lengths, 288);
				for (s = 0; s < 30; ++s) lengths[s] = 5;
				Build(f.second, lengths, 30);
				return f;
			}();
			if (!Codes(b, out, limit, fixed.first, fixed.second, error))
				return false;
		} else if (type == 2) {
			static constexpr short order[19] = {16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15};
			int nlen = b.Need(5) + 257, ndist = b.Need(5) + 1, ncode = b.Need(4) + 4;
			if (b.err || nlen > 286 || ndist > 30) {
				error = "damaged deflate data (bad code counts)";
				return false;
			}
			short lengths[320] = {};
			for (int i = 0; i < ncode; ++i)
				lengths[order[i]] = short(b.Need(3));
			Huffman lencode, distcode;
			if (b.err || Build(lencode, lengths, 19) != 0) {
				error = "damaged deflate data (code lengths code)";
				return false;
			}
			for (int i = 0; i < nlen + ndist;) {
				int sym = Decode(b, lencode);
				if (sym < 0) {
					error = "damaged deflate data (code lengths)";
					return false;
				}
				if (sym < 16) {
					lengths[i++] = short(sym);
					continue;
				}
				short len = 0;
				int rep;
				if (sym == 16) {
					if (i == 0) {
						error = "damaged deflate data (repeat without a length)";
						return false;
					}
					len = lengths[i - 1];
					rep = 3 + b.Need(2);
				} else if (sym == 17)
					rep = 3 + b.Need(3);
				else
					rep = 11 + b.Need(7);
				if (b.err || i + rep > nlen + ndist) {
					error = "damaged deflate data (too many code lengths)";
					return false;
				}
				while (rep--)
					lengths[i++] = len;
			}
			if (lengths[256] == 0) {
				error = "damaged deflate data (no end-of-block code)";
				return false;
			}
			int err = Build(lencode, lengths, nlen);
			if (err < 0 || (err > 0 && nlen - lencode.count[0] != 1)) {
				error = "damaged deflate data (literal/length code)";
				return false;
			}
			err = Build(distcode, lengths + nlen, ndist);
			if (err < 0 || (err > 0 && ndist - distcode.count[0] != 1)) {
				error = "damaged deflate data (distance code)";
				return false;
			}
			if (!Codes(b, out, limit, lencode, distcode, error))
				return false;
		} else {
			error = "damaged deflate data (block type 3)";
			return false;
		}
	} while (!last);
	return true;
}

bool ReadZipDirectory(const std::string& zip, std::vector<ZipEntry>& out, std::string& error) {
	out.clear();
	if (zip.size() < 22) {
		error = "not a ZIP file (too short)";
		return false;
	}
	size_t eocd = std::string::npos;
	size_t lowest = zip.size() > 22 + 65535 ? zip.size() - 22 - 65535 : 0;
	for (size_t at = zip.size() - 22 + 1; at-- > lowest;)
		if (Get32(zip, at) == 0x06054b50) {
			eocd = at;
			break;
		}
	if (eocd == std::string::npos) {
		error = "not a ZIP file (no end of central directory)";
		return false;
	}
	uint32_t count = Get16(zip, eocd + 10), dirSize = Get32(zip, eocd + 12), dirOffset = Get32(zip, eocd + 16);
	if (count == 0xFFFF || dirSize == 0xFFFFFFFF || dirOffset == 0xFFFFFFFF) {
		error = "ZIP64 archives are not supported";
		return false;
	}
	if (uint64_t(dirOffset) + dirSize > eocd) {
		error = "damaged ZIP (central directory out of range)";
		return false;
	}
	size_t at = dirOffset;
	for (uint32_t i = 0; i < count; ++i) {
		if (at + 46 > eocd || Get32(zip, at) != 0x02014b50) {
			error = "damaged ZIP (central directory entry " + std::to_string(i) + ")";
			return false;
		}
		ZipEntry e;
		e.flags = uint16_t(Get16(zip, at + 8));
		e.method = uint16_t(Get16(zip, at + 10));
		e.crc = Get32(zip, at + 16);
		e.packedSize = Get32(zip, at + 20);
		e.size = Get32(zip, at + 24);
		uint32_t nameLen = Get16(zip, at + 28), extraLen = Get16(zip, at + 30), commentLen = Get16(zip, at + 32);
		e.localOffset = Get32(zip, at + 42);
		if (at + 46 + nameLen + extraLen + commentLen > eocd) {
			error = "damaged ZIP (central directory entry " + std::to_string(i) + ")";
			return false;
		}
		e.name = zip.substr(at + 46, nameLen);
		if (e.packedSize == 0xFFFFFFFF || e.size == 0xFFFFFFFF || e.localOffset == 0xFFFFFFFF) {
			error = "ZIP64 archives are not supported";
			return false;
		}
		out.push_back(std::move(e));
		at += 46 + nameLen + extraLen + commentLen;
	}
	return true;
}

bool ExtractZipEntry(const std::string& zip, const ZipEntry& e, std::string& out, std::string& error) {
	out.clear();
	if (e.flags & 1) {
		error = e.name + ": encrypted entries are not supported";
		return false;
	}
	size_t at = size_t(e.localOffset);
	if (at + 30 > zip.size() || Get32(zip, at) != 0x04034b50) {
		error = e.name + ": damaged ZIP (local header)";
		return false;
	}
	size_t data = at + 30 + Get16(zip, at + 26) + Get16(zip, at + 28);
	if (data > zip.size() || e.packedSize > zip.size() - data) {
		error = e.name + ": damaged ZIP (data out of range)";
		return false;
	}
	const uint8_t* p = reinterpret_cast<const uint8_t*>(zip.data() + data);
	if (e.method == 0) {
		if (e.packedSize != e.size) {
			error = e.name + ": damaged ZIP (stored sizes differ)";
			return false;
		}
		out.assign(reinterpret_cast<const char*>(p), size_t(e.size));
	} else if (e.method == 8) {
		if (!Inflate(p, size_t(e.packedSize), out, size_t(e.size), error)) {
			error = e.name + ": " + error;
			return false;
		}
	} else {
		error = e.name + ": compression method " + std::to_string(e.method) + " is not supported";
		return false;
	}
	if (out.size() != e.size) {
		error = e.name + ": " + std::to_string(out.size()) + " bytes unpacked, the ZIP says " + std::to_string(e.size);
		return false;
	}
	if (Crc32(out.data(), out.size()) != e.crc) {
		error = e.name + ": CRC-32 does not match (damaged download)";
		return false;
	}
	return true;
}

}  // namespace mxl

// drawcap's pure part: byte signatures, the scans that find every site in the loaded image, the cap raise's edits (PlanPatch),
// the config and the per-second statistics. No Windows headers, no game memory: the unit tests (tests/drawcap_test.cpp) run it on byte arrays.
//
// What it measures: D2R keeps Diablo II's fixed draw list of 3000 entries (TVIEWDATA +0x50, 32 bytes each). Each frame the
// build function resets the entry count and the inserters add tiles and units; an inserter whose index is at or past the cap
// drops the entry silently, but the count is incremented anyway. So the count read just before the next reset is the
// frame's real demand, and count - cap is the number of entries that were not drawn.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace drawcap {

inline constexpr size_t NotFound = static_cast<size_t>(-1);
inline constexpr size_t MaxPattern = 96;

// A byte pattern: hex bytes, "??" for any byte ("48 8b 05 ?? ?? ?? ?? c3").
struct Pattern {
	uint8_t bytes[MaxPattern]{};
	bool any[MaxPattern]{};
	size_t size = 0;
};

constexpr auto HexDigit(char c) noexcept -> int {
	return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
}

// False on a malformed pattern (odd digit, unknown character, longer than MaxPattern, empty).
inline auto Parse(const char* text, Pattern& out) noexcept -> bool {
	out = Pattern{};
	if (text == nullptr) {
		return false;
	}
	for (const char* p = text; *p != '\0';) {
		if (*p == ' ') {
			++p;
			continue;
		}
		if (out.size == MaxPattern || p[1] == '\0') {
			return false;
		}
		if (p[0] == '?' && p[1] == '?') {
			out.any[out.size++] = true;
		} else {
			const int hi = HexDigit(p[0]), lo = HexDigit(p[1]);
			if (hi < 0 || lo < 0) {
				return false;
			}
			out.bytes[out.size++] = static_cast<uint8_t>(hi << 4 | lo);
		}
		p += 2;
		if (*p != '\0' && *p != ' ') {
			return false;
		}
	}
	return out.size > 0;
}

inline auto MatchAt(const uint8_t* data, size_t size, size_t at, const Pattern& p) noexcept -> bool {
	if (at > size || size - at < p.size) {
		return false;
	}
	for (size_t i = 0; i < p.size; ++i) {
		if (!p.any[i] && data[at + i] != p.bytes[i]) {
			return false;
		}
	}
	return true;
}

// First match at or after `from` and before `to` (the match must fit before `to`), or NotFound.
inline auto Find(const uint8_t* data, size_t to, const Pattern& p, size_t from = 0) noexcept -> size_t {
	if (p.size == 0 || p.any[0]) {
		for (size_t i = from; i + p.size <= to; ++i) {
			if (MatchAt(data, to, i, p)) {
				return i;
			}
		}
		return NotFound;
	}
	const uint8_t first = p.bytes[0];
	for (size_t i = from; i + p.size <= to; ++i) {
		if (data[i] == first && MatchAt(data, to, i, p)) {
			return i;
		}
	}
	return NotFound;
}

inline auto Count(const uint8_t* data, size_t to, const Pattern& p, size_t from = 0, size_t* firstAt = nullptr) noexcept -> size_t {
	size_t n = 0;
	for (size_t at = Find(data, to, p, from); at != NotFound; at = Find(data, to, p, at + 1)) {
		if (n++ == 0 && firstAt != nullptr) {
			*firstAt = at;
		}
	}
	return n;
}

inline auto Le32(const uint8_t* b) noexcept -> uint32_t {
	return static_cast<uint32_t>(b[0]) | static_cast<uint32_t>(b[1]) << 8 | static_cast<uint32_t>(b[2]) << 16 |
	       static_cast<uint32_t>(b[3]) << 24;
}

// ---------------------------------------------------------------------------------------------------------------- signatures
// Taken from D2R 3.3 build 93847 (image 0x6ab3782c, RVAs below are that build's) and each unique in its .text.

// The draw list build (1.14d WALL2_BuildSceneDrawList, D2R 0x21bae0 (TVIEWDATA*, int)): prologue, stack cookie, then the
// view rect reads (+0xc - +4 is the width, +0x10 - +8 the height) and the grid side sum W/160 + H/80.
inline constexpr const char* BuildSig =
    "48 89 5c 24 18 48 89 74 24 20 55 57 41 54 41 56 41 57 48 8b ec 48 83 ec 60 48 8b 05 ?? ?? ?? ?? 48 33 c4 48 89 45 f8 "
    "48 8b d9 44 8b e2 8b 49 0c b8 67 66 66 66 2b 4b 04 f7 e9 8b 4b 10 b8 67 66 66 66 2b 4b 08";
inline constexpr size_t HookSize = 25;  // the prologue up to `sub rsp, 0x60`: whole instructions, no RIP-relative operand
inline constexpr uint64_t BuildRva93847 = 0x21bae0;

// The count reset inside the build function (0x21bc08): movups xmm0,[rbp-0x28]; xor edi,edi; mov [rbx+COUNT],edi; ...;
// mov [rbx+0x48],edi (the pass mask). The disp32 at +8 is the count's offset in TVIEWDATA (0x17750 in 93847).
inline constexpr const char* ResetSig = "0f 10 45 d8 33 ff 89 bb ?? ?? ?? ?? 0f 11 05 ?? ?? ?? ?? 89 7b 48";
inline constexpr size_t ResetCountDisp = 8;
inline constexpr size_t ResetWindow = 0x400;  // searched from the build function's start
inline constexpr uint32_t CountOffset93847 = 0x17750;
// The pass mask sits at TVIEWDATA +0x48 and the entries at +0x50; the count follows the array (entries + cap * 32).
inline constexpr uint32_t EntriesOffset = 0x50;
inline constexpr uint32_t EntrySize = 32;

// The HD graphics test (0x846210): `mov rax,[rip+PANELMGR]; test rax,rax; je; movzx eax, byte [rax+0xb9]; ret`, 1 in HD and 0
// in legacy graphics. The probe reads the global and the byte itself (no call).
inline constexpr const char* HdSig = "48 8b 05 ?? ?? ?? ?? 48 85 c0 74 08 0f b6 80 b9 00 00 00 c3";
inline constexpr size_t HdGlobalDisp = 3;   // rel32 of the global, relative to the end of the 7-byte mov
inline constexpr uint32_t HdFlagOffset = 0xb9;

// The cap sites (7 in 93847, all in 0x21be60 .. 0x21cae0): `lea eax,[r+1]; mov [r+COUNT],eax; cmp r,CAP; jae <drop>`.
// COUNT is the count's offset from TVIEWDATA or from the list (TVIEWDATA +0x48); a REX.B prefix may come before the lea and the
// cmp (site C: `41 8d 40 01 89 81 08 77 01 00 41 81 f8 b8 0b 00 00`).
inline constexpr size_t SiteWindow = 0x2000;  // searched from the build function's start
inline constexpr uint32_t ListOffset = 0x48;

struct Site {
	size_t compareAt = 0;    // offset of the cmp (its REX prefix included)
	size_t compareSize = 0;  // 6, or 7 with the REX prefix
	uint32_t cap = 0;
	bool listRelative = false;
};

// Reads one cap site at `at` (the lea, or its REX prefix); 0 when it is none, else the length up to the end of the cmp.
inline auto SiteAt(const uint8_t* data, size_t size, size_t at, uint32_t countOffset, Site* out) noexcept -> size_t {
	size_t i = at;
	if (i < size && data[i] == 0x41) {
		++i;
	}
	if (i + 9 > size || data[i] != 0x8d || data[i + 1] < 0x40 || data[i + 1] > 0x47 || data[i + 2] != 0x01) {
		return 0;
	}
	i += 3;
	if (data[i] != 0x89 || data[i + 1] < 0x80 || data[i + 1] > 0xbf) {
		return 0;
	}
	const uint32_t disp = Le32(data + i + 2);
	if (disp != countOffset && disp != countOffset - ListOffset) {
		return 0;
	}
	i += 6;
	const size_t compareAt = i;
	if (i < size && data[i] == 0x41) {
		++i;
	}
	if (i + 6 > size || data[i] != 0x81 || data[i + 1] < 0xf8) {
		return 0;
	}
	if (out != nullptr) {
		out->compareAt = compareAt;
		out->compareSize = i + 6 - compareAt;
		out->cap = Le32(data + i + 2);
		out->listRelative = disp != countOffset;
	}
	return i + 6 - at;
}

// Every cap site in data[from, to). Returns how many; the first `max` go to `out`.
inline auto FindSites(const uint8_t* data, size_t to, size_t from, uint32_t countOffset, Site* out, size_t max) noexcept -> size_t {
	size_t n = 0;
	for (size_t i = from; i < to; ++i) {
		Site s;
		const size_t len = SiteAt(data, to, i, countOffset, &s);
		if (len != 0) {
			if (n < max) {
				out[n] = s;
			}
			++n;
			i += len - 1;
		}
	}
	return n;
}

// What the scan of the loaded .text found. Offsets are from the start of the scanned buffer (the caller adds the base RVA).
struct ScanResult {
	bool ok = false;
	const char* failed = nullptr;  // which signature did not match (for the log)
	size_t build = NotFound;
	size_t reset = NotFound;
	uint32_t countOffset = 0;
	size_t hd = NotFound;
	size_t hdGlobal = NotFound;  // offset of the panel manager global (may lie past .text: the caller checks the image)
	size_t buildMatches = 0, resetMatches = 0, hdMatches = 0;
	Site sites[16]{};
	size_t siteCount = 0;
	uint32_t cap = 0;
	bool capsAgree = false;
};

// Scans text[0, size): each signature must match exactly once (the count reset once inside the build function), the count
// offset must make sense, and at least one cap site must use it, all with the same cap. Anything else: ok = false, nothing
// may be hooked.
inline auto Scan(const uint8_t* text, size_t size) noexcept -> ScanResult {
	ScanResult r;
	Pattern build, reset, hd;
	if (!Parse(BuildSig, build) || !Parse(ResetSig, reset) || !Parse(HdSig, hd)) {
		r.failed = "pattern table";
		return r;
	}
	r.buildMatches = Count(text, size, build, 0, &r.build);
	if (r.buildMatches != 1) {
		r.failed = "draw list build";
		return r;
	}
	const size_t resetEnd = r.build + ResetWindow < size ? r.build + ResetWindow : size;
	r.resetMatches = Count(text, resetEnd, reset, r.build, &r.reset);
	if (r.resetMatches != 1) {
		r.failed = "count reset";
		return r;
	}
	r.countOffset = Le32(text + r.reset + ResetCountDisp);
	if (r.countOffset < EntriesOffset + EntrySize * 100 || r.countOffset > 0x100000 || (r.countOffset - EntriesOffset) % EntrySize != 0) {
		r.failed = "count offset";
		return r;
	}
	r.hdMatches = Count(text, size, hd, 0, &r.hd);
	if (r.hdMatches != 1) {
		r.failed = "HD graphics test";
		return r;
	}
	const int32_t rel = static_cast<int32_t>(Le32(text + r.hd + HdGlobalDisp));
	r.hdGlobal = static_cast<size_t>(static_cast<int64_t>(r.hd) + 7 + rel);
	const size_t siteEnd = r.build + SiteWindow < size ? r.build + SiteWindow : size;
	r.siteCount = FindSites(text, siteEnd, r.build, r.countOffset, r.sites, sizeof(r.sites) / sizeof(r.sites[0]));
	if (r.siteCount == 0) {
		r.failed = "cap sites";
		return r;
	}
	r.cap = r.sites[0].cap;
	r.capsAgree = true;
	const size_t listed = r.siteCount < 16 ? r.siteCount : 16;
	for (size_t i = 1; i < listed; ++i) {
		r.capsAgree = r.capsAgree && r.sites[i].cap == r.cap;
	}
	// the array runs from +0x50 to the count: cap entries of 32 bytes
	if (!r.capsAgree || EntriesOffset + static_cast<uint64_t>(r.cap) * EntrySize != r.countOffset) {
		r.failed = "cap value";
		return r;
	}
	r.ok = true;
	return r;
}

// ---------------------------------------------------------------------------------------------------------------- the raise
// The entries move out of TVIEWDATA into a buffer of the plugin's, `cap` entries long. Every inserter computes its entry as
// `base + index * 32` with base = TVIEWDATA + 0x50, from one `lea r64, [view + 0x50]` (or `[list + 8]`, list = view + 0x48)
// a few instructions after its cap compare. The patch, per site:
//  - the compare's imm32 becomes the new cap;
//  - the base `lea` (48 8d /r disp8) becomes a `mov` (48 8b /r disp8) of the same operands: the base is then the qword stored
//    at TVIEWDATA + 0x50, the first 8 bytes of the old entry 0, which no code reads once all inserters are moved.
// The build hook stores the view's buffer there before every build. No code is added to the game, so nothing has to be placed
// near the image. Everything else that reads the entries follows the cells' linked pointers (cell +0x10, entry +0x18), so
// entries in the buffer are drawn like entries in the struct (mxl2012-runs/drawcap/PATCH.md for the code reading).

inline constexpr size_t LeaWindow = 0x30;  // from the end of the compare to the base lea (93847: 4 .. 0x1d bytes)
inline constexpr size_t AddWindow = 0x10;  // from the lea to its `add reg, rax`
inline constexpr uint32_t MinPatchCap = 3001;
inline constexpr uint32_t MaxPatchCap = 100000;  // 3.2 MB per view
inline constexpr uint32_t DefaultPatchCap = 12000;

// One change in the code: `expected` must be found at `at` (an offset in the scanned .text), `bytes` is written there.
struct Edit {
	size_t at = 0;
	uint8_t size = 0;
	uint8_t expected[8]{};
	uint8_t bytes[8]{};
};

// The base lea of a site: the first `48 8d /r disp8` after the site's `jae` whose base displacement is the entries' (8 for a
// list-relative site, 0x50 for a view-relative one), whose destination is not rax, followed by `add <dest>, rax`, with
// `shl rax, 5` between the compare and that add. NotFound if any of it is missing.
inline auto BaseLeaAt(const uint8_t* data, size_t size, const Site& s) noexcept -> size_t {
	const size_t end = s.compareAt + s.compareSize;
	if (end + 6 > size || data[end] != 0x0f || data[end + 1] != 0x83) {
		return NotFound;  // the drop branch must follow the compare
	}
	const uint8_t disp = s.listRelative ? static_cast<uint8_t>(EntriesOffset - ListOffset) : static_cast<uint8_t>(EntriesOffset);
	const size_t last = end + LeaWindow < size ? end + LeaWindow : size;
	for (size_t i = end + 6; i + 4 <= last; ++i) {
		const uint8_t modrm = data[i + 2];
		const uint8_t reg = (modrm >> 3) & 7, rm = modrm & 7;
		if (data[i] != 0x48 || data[i + 1] != 0x8d || (modrm >> 6) != 1 || rm == 4 || reg == 0 || data[i + 3] != disp) {
			continue;
		}
		const uint8_t add[3] = {0x48, 0x03, static_cast<uint8_t>(0xc0 | reg << 3)};
		const uint8_t shl[4] = {0x48, 0xc1, 0xe0, 0x05};
		size_t addAt = NotFound;
		for (size_t j = i + 4; j + 3 <= size && j < i + 4 + AddWindow; ++j) {
			if (std::memcmp(data + j, add, 3) == 0) {
				addAt = j;
				break;
			}
		}
		if (addAt == NotFound) {
			return NotFound;
		}
		for (size_t j = end; j + 4 <= addAt; ++j) {
			if (std::memcmp(data + j, shl, 4) == 0) {
				return i;
			}
		}
		return NotFound;
	}
	return NotFound;
}

struct PatchPlan {
	bool ok = false;
	const char* failed = nullptr;  // why there is no patch (for the log)
	size_t failedSite = 0;         // 1-based site number when a site did not match
	Edit edits[32]{};
	size_t editCount = 0;
	size_t leaAt[16]{};
};

// The edits that raise the cap of a scan (ok) to `cap`: two per site, the compare and the base lea, each with the bytes read
// from the code as its expected bytes. Not ok, and no edit, when any site's lea is missing or the cap is out of range.
inline auto PlanPatch(const uint8_t* text, size_t size, const ScanResult& scan, uint32_t cap) noexcept -> PatchPlan {
	PatchPlan p;
	if (!scan.ok || scan.siteCount == 0 || scan.siteCount > 16) {
		p.failed = "the scan did not pass";
		return p;
	}
	if (cap < MinPatchCap || cap > MaxPatchCap || cap <= scan.cap) {
		p.failed = "cap out of range";
		return p;
	}
	for (size_t k = 0; k < scan.siteCount; ++k) {
		const Site& s = scan.sites[k];
		const size_t lea = BaseLeaAt(text, size, s);
		if (lea == NotFound || s.compareSize < 6 || s.compareSize > 7) {
			p.failed = "base lea";
			p.failedSite = k + 1;
			p.editCount = 0;
			return p;
		}
		p.leaAt[k] = lea;
		Edit& cmp = p.edits[p.editCount++];
		cmp.at = s.compareAt;
		cmp.size = static_cast<uint8_t>(s.compareSize);
		std::memcpy(cmp.expected, text + s.compareAt, s.compareSize);
		std::memcpy(cmp.bytes, cmp.expected, s.compareSize);
		uint8_t* imm = cmp.bytes + s.compareSize - 4;
		imm[0] = static_cast<uint8_t>(cap);
		imm[1] = static_cast<uint8_t>(cap >> 8);
		imm[2] = static_cast<uint8_t>(cap >> 16);
		imm[3] = static_cast<uint8_t>(cap >> 24);
		Edit& mov = p.edits[p.editCount++];
		mov.at = lea;
		mov.size = 4;
		std::memcpy(mov.expected, text + lea, 4);
		std::memcpy(mov.bytes, mov.expected, 4);
		mov.bytes[1] = 0x8b;
	}
	p.ok = true;
	return p;
}

// The buffer of each view the build has seen (the game has one; a few more are allowed). Single writer: the build's thread.
template <size_t N>
struct ViewTable {
	const void* view[N]{};
	void* buffer[N]{};
	size_t used = 0;

	auto Find(const void* v) const noexcept -> void* {
		for (size_t i = 0; i < used; ++i) {
			if (view[i] == v) {
				return buffer[i];
			}
		}
		return nullptr;
	}
	auto Add(const void* v, void* b) noexcept -> bool {
		if (used == N || v == nullptr || b == nullptr) {
			return false;
		}
		view[used] = v;
		buffer[used] = b;
		++used;
		return true;
	}
};

// ---------------------------------------------------------------------------------------------------------------- config

struct Config {
	bool probe = false;         // [drawcap] probe = true: measure the list (read-only)
	uint32_t intervalMs = 1000; // [drawcap] interval_ms: one stats line per mode per interval (250 .. 60000)
	bool patch = true;          // [drawcap] patch = true: raise the cap to `cap`
	uint32_t cap = DefaultPatchCap;  // [drawcap] cap: the raised cap, MinPatchCap .. MaxPatchCap (clamped)
};

// The keys of the [drawcap] section of drawcap.toml; everything else is ignored. null or "" gives the defaults.
inline auto ParseConfig(const char* text) noexcept -> Config {
	Config c;
	if (text == nullptr) {
		return c;
	}
	bool inSection = false;
	const char* line = text;
	while (*line != '\0') {
		const char* end = line;
		while (*end != '\0' && *end != '\n') {
			++end;
		}
		const char* p = line;
		while (p < end && (*p == ' ' || *p == '\t')) {
			++p;
		}
		auto starts = [&](const char* word) {
			const size_t n = std::strlen(word);
			return static_cast<size_t>(end - p) >= n && std::strncmp(p, word, n) == 0;
		};
		if (p < end && *p == '[') {
			inSection = starts("[drawcap]");
		} else if (inSection && p < end && *p != '#') {
			const char* eq = p;
			while (eq < end && *eq != '=') {
				++eq;
			}
			if (eq < end) {
				const char* v = eq + 1;
				while (v < end && *v == ' ') {
					++v;
				}
				const auto keyIs = [&](const char* key) {
					const size_t n = std::strlen(key);
					const char* k = p + n;
					while (k < eq && *k == ' ') {
						++k;
					}
					return static_cast<size_t>(eq - p) >= n && std::strncmp(p, key, n) == 0 && k == eq;
				};
				const auto isTrue = [&] { return static_cast<size_t>(end - v) >= 4 && std::strncmp(v, "true", 4) == 0; };
				const auto number = [&](uint32_t* n) {
					*n = 0;
					bool digits = false;
					for (const char* d = v; d < end && *d >= '0' && *d <= '9' && *n < 10000000; ++d) {
						*n = *n * 10 + static_cast<uint32_t>(*d - '0');
						digits = true;
					}
					return digits;
				};
				uint32_t n = 0;
				if (keyIs("probe")) {
					c.probe = isTrue();
				} else if (keyIs("patch")) {
					c.patch = isTrue();
				} else if (keyIs("interval_ms")) {
					if (number(&n)) {
						c.intervalMs = n < 250 ? 250 : n > 60000 ? 60000 : n;
					}
				} else if (keyIs("cap")) {
					if (number(&n)) {
						c.cap = n < MinPatchCap ? MinPatchCap : n > MaxPatchCap ? MaxPatchCap : n;
					}
				}
			}
		}
		line = *end == '\n' ? end + 1 : end;
	}
	return c;
}

// ---------------------------------------------------------------------------------------------------------------- statistics

enum Mode : int { Legacy = 0, Hd = 1, Unknown = 2 };
inline constexpr const char* ModeName[] = {"legacy", "hd", "unknown"};

struct Window {
	uint32_t frames = 0;
	uint32_t max = 0;
	uint32_t over = 0;  // frames whose count was past the cap (entries dropped)
	uint64_t sum = 0;
	uint64_t dropped = 0;  // sum of count - cap over those frames
	int32_t viewW = 0, viewH = 0;
};

struct Totals {
	uint64_t frames = 0, over = 0, dropped = 0;
	uint32_t max = 0;
};

// One interval per mode; Add() per frame, Flush() when the interval is over. Single writer (the frame's thread).
struct Stats {
	Window window[3]{};
	Totals total[3]{};
	uint64_t windowStart = 0;

	void Add(uint32_t count, int mode, uint32_t cap, int32_t viewW, int32_t viewH) noexcept {
		if (mode < 0 || mode > 2) {
			mode = Unknown;
		}
		Window& w = window[mode];
		++w.frames;
		w.sum += count;
		w.max = count > w.max ? count : w.max;
		w.viewW = viewW;
		w.viewH = viewH;
		Totals& t = total[mode];
		++t.frames;
		t.max = count > t.max ? count : t.max;
		if (count > cap) {
			++w.over;
			w.dropped += count - cap;
			++t.over;
			t.dropped += count - cap;
		}
	}
	auto Due(uint64_t nowMs, uint32_t intervalMs) noexcept -> bool {
		if (windowStart == 0) {
			windowStart = nowMs;
			return false;
		}
		return nowMs - windowStart >= intervalMs;
	}
	void Reset(uint64_t nowMs) noexcept {
		for (Window& w : window) {
			w = Window{};
		}
		windowStart = nowMs;
	}
};

// The CSV columns of drawcap-stats.csv.
inline constexpr const char* CsvHeader = "t_ms,mode,frames,max,mean,over,dropped,cap,view_w,view_h,grid";

// The legacy cell grid's side for a view (0x21bae0: S = W/160 + H/80 + 22, rounded toward zero as the code does).
constexpr auto GridSide(int32_t w, int32_t h) noexcept -> int32_t {
	return w / 160 + h / 80 + 22;
}

// One CSV line (with \n) for a mode's window, or "" when that mode had no frame. Returns the length written.
inline auto CsvLine(char* out, size_t size, uint64_t tMs, int mode, const Window& w, uint32_t cap) noexcept -> int {
	if (out == nullptr || size == 0) {
		return 0;
	}
	out[0] = '\0';
	if (w.frames == 0 || mode < 0 || mode > 2) {
		return 0;
	}
	const uint64_t mean10 = (w.sum * 10 + w.frames / 2) / w.frames;
	const int n = std::snprintf(out, size, "%llu,%s,%u,%u,%llu.%llu,%u,%llu,%u,%d,%d,%d\n", static_cast<unsigned long long>(tMs),
	                            ModeName[mode], w.frames, w.max, static_cast<unsigned long long>(mean10 / 10),
	                            static_cast<unsigned long long>(mean10 % 10), w.over, static_cast<unsigned long long>(w.dropped), cap,
	                            w.viewW, w.viewH, GridSide(w.viewW, w.viewH));
	return n < 0 ? 0 : (static_cast<size_t>(n) >= size ? static_cast<int>(size - 1) : n);
}

}  // namespace drawcap

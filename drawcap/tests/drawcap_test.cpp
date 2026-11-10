// Unit tests of drawcap_logic.h: pattern parsing and search, the image scan on a synthetic .text, the config switch and the
// statistics. With env D2R_DUMP set to a memory-layout dump of D2R 93847 (file offset == RVA, tools/dump_image.py) it also
// scans the dump's .text and checks the 93847 places.
#include "../src/drawcap_logic.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

namespace {
int failures = 0;
void Check(bool ok, const char* what) {
	if (!ok) {
		++failures;
		std::printf("FAIL: %s\n", what);
	}
}

// Writes a pattern's bytes at `at` (wildcards as `fill`).
void Put(std::vector<uint8_t>& t, size_t at, const char* pattern, uint8_t fill = 0) {
	drawcap::Pattern p;
	drawcap::Parse(pattern, p);
	for (size_t i = 0; i < p.size; ++i) {
		t[at + i] = p.any[i] ? fill : p.bytes[i];
	}
}

void Put32(std::vector<uint8_t>& t, size_t at, uint32_t v) {
	for (int i = 0; i < 4; ++i) {
		t[at + i] = static_cast<uint8_t>(v >> (8 * i));
	}
}

// The seven cap sites as 93847 has them (lea; mov [r+count]; cmp r, 3000), list-relative (0x17708) or view-relative (0x17750),
// each with the code after it up to the entry address (jae <drop>; ...; lea base; shl rax, 5; add base, rax).
constexpr const char* Sites[] = {
    "8d 42 01 89 81 08 77 01 00 81 fa b8 0b 00 00 0f 83 90 00 00 00 8b c2 48 89 9c 24 80 00 00 00 48 8d 59 08 48 c1 e0 05 48 03 d8",  // A
    "8d 47 01 89 81 08 77 01 00 81 ff b8 0b 00 00 0f 83 35 02 00 00 48 89 6c 24 78 e8 7a 17 ff 00 48 8d a8 f4 01 00 00 8b c7 48 c1 e0 05 "
    "48 8d 7e 08 48 03 f8",  // B
    "41 8d 40 01 89 81 08 77 01 00 41 81 f8 b8 0b 00 00 0f 83 e5 00 00 00 48 89 74 24 48 41 8b c0 33 f6 48 89 7c 24 50 48 c1 e0 05 "
    "48 8d 79 08 48 03 f8",  // C
    "8d 41 01 89 87 50 77 01 00 81 f9 b8 0b 00 00 0f 83 ad 01 00 00 8b c1 48 8d 77 50 48 c1 e0 05 48 8d 55 ff 48 03 f0",  // D
    "8d 41 01 89 87 50 77 01 00 81 f9 b8 0b 00 00 0f 83 c5 00 00 00 8b c1 48 8d 77 50 48 c1 e0 05 48 8d 55 ff 48 03 f0",  // E
    "8d 41 01 89 87 50 77 01 00 81 f9 b8 0b 00 00 0f 83 c1 00 00 00 8b c1 48 8d 77 50 48 c1 e0 05 48 03 f0",  // F
    "8d 41 01 89 87 50 77 01 00 81 f9 b8 0b 00 00 0f 83 e1 00 00 00 8b c1 48 8d 77 50 48 c1 e0 05 48 03 f0",  // G
};
// Where each site's base lea sits from the start of its string.
constexpr size_t LeaFromSite[] = {31, 44, 42, 23, 23, 23, 23};

constexpr size_t BuildAt = 0x1000, HdAt = 0x9000;

// A synthetic .text: the build function, its count reset at +0x128, the seven sites, the HD test.
auto MakeText() -> std::vector<uint8_t> {
	std::vector<uint8_t> t(0x10000, 0xcc);
	Put(t, BuildAt, drawcap::BuildSig, 0x11);
	Put(t, BuildAt + 0x128, drawcap::ResetSig);
	Put32(t, BuildAt + 0x128 + drawcap::ResetCountDisp, 0x17750);
	size_t at = BuildAt + 0x3a0;
	for (const char* s : Sites) {
		Put(t, at, s);
		at += 0xf0;
	}
	Put(t, HdAt, drawcap::HdSig);
	Put32(t, HdAt + drawcap::HdGlobalDisp, 0x1000);  // global at HdAt + 7 + 0x1000
	return t;
}

void TestPattern() {
	drawcap::Pattern p;
	Check(drawcap::Parse("48 8b ?? c3", p) && p.size == 4 && p.any[2] && !p.any[0] && p.bytes[1] == 0x8b, "parse with a wildcard");
	Check(!drawcap::Parse("48 8", p), "odd digit refused");
	Check(!drawcap::Parse("48 zz", p), "bad digit refused");
	Check(!drawcap::Parse("", p), "empty refused");
	Check(!drawcap::Parse("488b", p), "bytes must be spaced");
	const uint8_t data[] = {0x00, 0x48, 0x8b, 0x05, 0xc3, 0x48, 0x8b, 0x99, 0xc3, 0x48, 0x8b};
	drawcap::Parse("48 8b ?? c3", p);
	Check(drawcap::Find(data, sizeof(data), p) == 1, "first match");
	Check(drawcap::Find(data, sizeof(data), p, 2) == 5, "next match");
	Check(drawcap::Count(data, sizeof(data), p) == 2, "two matches; a partial match at the end is none");
	drawcap::Parse("?? 8b", p);
	Check(drawcap::Count(data, sizeof(data), p) == 3, "leading wildcard");
	Check(drawcap::Parse(drawcap::BuildSig, p) && p.size > drawcap::HookSize, "build signature parses, longer than the hook");
	bool fixed = true;
	for (size_t i = 0; i < drawcap::HookSize; ++i) {
		fixed = fixed && !p.any[i];
	}
	Check(fixed, "the hooked bytes are fixed bytes of the signature");
	Check(drawcap::Parse(drawcap::ResetSig, p) && drawcap::Parse(drawcap::HdSig, p), "reset and HD signatures parse");
}

void TestScan() {
	std::vector<uint8_t> t = MakeText();
	drawcap::ScanResult r = drawcap::Scan(t.data(), t.size());
	Check(r.ok, "synthetic text scans");
	Check(r.build == BuildAt && r.reset == BuildAt + 0x128, "build and reset found");
	Check(r.countOffset == 0x17750, "count offset from the reset");
	Check(r.hd == HdAt && r.hdGlobal == HdAt + 7 + 0x1000, "HD test and its global");
	Check(r.siteCount == 7 && r.cap == 3000 && r.capsAgree, "seven sites with cap 3000");
	Check(r.sites[0].compareAt == BuildAt + 0x3a0 + 9 && r.sites[0].listRelative, "site A: cmp after lea and mov, list-relative");
	Check(r.sites[2].compareAt == BuildAt + 0x3a0 + 2 * 0xf0 + 10 && r.sites[2].listRelative, "site C: REX-prefixed cmp");
	Check(!r.sites[3].listRelative, "site D: view-relative");

	std::vector<uint8_t> two = MakeText();
	Put(two, 0xa000, drawcap::BuildSig, 0x22);
	r = drawcap::Scan(two.data(), two.size());
	Check(!r.ok && std::strcmp(r.failed, "draw list build") == 0 && r.buildMatches == 2, "a second build match refuses");

	std::vector<uint8_t> noReset = MakeText();
	noReset[BuildAt + 0x128] = 0x90;
	r = drawcap::Scan(noReset.data(), noReset.size());
	Check(!r.ok && std::strcmp(r.failed, "count reset") == 0, "no count reset refuses");

	std::vector<uint8_t> farReset = MakeText();
	Put(farReset, BuildAt + 0x128, "90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90");
	Put(farReset, BuildAt + drawcap::ResetWindow + 0x10, drawcap::ResetSig);
	r = drawcap::Scan(farReset.data(), farReset.size());
	Check(!r.ok && std::strcmp(r.failed, "count reset") == 0, "a reset outside the build function is not taken");

	std::vector<uint8_t> noHd = MakeText();
	noHd[HdAt + 15] = 0xba;
	r = drawcap::Scan(noHd.data(), noHd.size());
	Check(!r.ok && std::strcmp(r.failed, "HD graphics test") == 0, "no HD test refuses");

	std::vector<uint8_t> otherCap = MakeText();
	Put32(otherCap, BuildAt + 0x3a0 + 3 * 0xf0 + 11, 4000);
	r = drawcap::Scan(otherCap.data(), otherCap.size());
	Check(!r.ok && std::strcmp(r.failed, "cap value") == 0, "sites that disagree refuse");

	std::vector<uint8_t> moved = MakeText();
	Put32(moved, BuildAt + 0x128 + drawcap::ResetCountDisp, 0x17770);  // a whole entry further: no site uses it
	r = drawcap::Scan(moved.data(), moved.size());
	Check(!r.ok && std::strcmp(r.failed, "cap sites") == 0, "sites must use the reset's count offset");

	// A build with the same code but a bigger array: count at 0x50 + 5000 * 32, cap 5000 at every site
	std::vector<uint8_t> bigger = MakeText();
	const uint32_t count = 0x50 + 5000 * 32;
	Put32(bigger, BuildAt + 0x128 + drawcap::ResetCountDisp, count);
	size_t at = BuildAt + 0x3a0;
	for (const char* s : Sites) {
		const bool rex = s[0] == '4';
		const bool list = std::strstr(s, "08 77 01 00") != nullptr;
		Put32(bigger, at + (rex ? 1 : 0) + 5, list ? count - 0x48 : count);
		Put32(bigger, at + (rex ? 1 : 0) + 9 + (rex ? 1 : 0) + 2, 5000);
		at += 0xf0;
	}
	r = drawcap::Scan(bigger.data(), bigger.size());
	Check(r.ok && r.cap == 5000 && r.countOffset == count, "another array size is read from the code");

	std::vector<uint8_t> inconsistent = MakeText();
	Put32(inconsistent, BuildAt + 0x128 + drawcap::ResetCountDisp, 0x17750 + 0x20);
	at = BuildAt + 0x3a0;
	for (const char* s : Sites) {
		const bool rex = s[0] == '4';
		const bool list = std::strstr(s, "08 77 01 00") != nullptr;
		Put32(inconsistent, at + (rex ? 1 : 0) + 5, list ? 0x17750 + 0x20 - 0x48 : 0x17750 + 0x20);
		at += 0xf0;
	}
	r = drawcap::Scan(inconsistent.data(), inconsistent.size());
	Check(!r.ok && std::strcmp(r.failed, "cap value") == 0, "a count that does not follow the array refuses");
}

void TestPatch() {
	std::vector<uint8_t> t = MakeText();
	const drawcap::ScanResult r = drawcap::Scan(t.data(), t.size());
	drawcap::PatchPlan p = drawcap::PlanPatch(t.data(), t.size(), r, 12000);
	Check(p.ok && p.editCount == 14, "a plan of 14 edits for 7 sites");
	bool leas = p.ok;
	for (size_t k = 0; leas && k < 7; ++k) {
		leas = p.leaAt[k] == BuildAt + 0x3a0 + k * 0xf0 + LeaFromSite[k];
	}
	Check(leas, "each site's base lea found, past the other leas of site B and D");
	const drawcap::Edit& a = p.edits[0];
	const uint8_t aCmp[] = {0x81, 0xfa, 0xe0, 0x2e, 0x00, 0x00};
	Check(a.at == r.sites[0].compareAt && a.size == 6 && std::memcmp(a.bytes, aCmp, 6) == 0 && std::memcmp(a.expected, t.data() + a.at, 6) == 0,
	      "site A compare: cmp edx, 12000, expected = the code");
	const drawcap::Edit& aLea = p.edits[1];
	const uint8_t aMov[] = {0x48, 0x8b, 0x59, 0x08}, aOld[] = {0x48, 0x8d, 0x59, 0x08};
	Check(aLea.size == 4 && std::memcmp(aLea.bytes, aMov, 4) == 0 && std::memcmp(aLea.expected, aOld, 4) == 0, "site A: lea rbx,[rcx+8] -> mov rbx,[rcx+8]");
	const drawcap::Edit& c = p.edits[4];
	const uint8_t cCmp[] = {0x41, 0x81, 0xf8, 0xe0, 0x2e, 0x00, 0x00};
	Check(c.size == 7 && std::memcmp(c.bytes, cCmp, 7) == 0, "site C: REX compare keeps its prefix");
	const uint8_t dMov[] = {0x48, 0x8b, 0x77, 0x50};
	Check(std::memcmp(p.edits[7].bytes, dMov, 4) == 0, "site D: lea rsi,[rdi+0x50] -> mov rsi,[rdi+0x50]");

	Check(!drawcap::PlanPatch(t.data(), t.size(), r, 3000).ok, "a cap not above the game's refuses");
	Check(!drawcap::PlanPatch(t.data(), t.size(), r, drawcap::MaxPatchCap + 1).ok, "a cap above the maximum refuses");
	drawcap::ScanResult bad = r;
	bad.ok = false;
	Check(!drawcap::PlanPatch(t.data(), t.size(), bad, 12000).ok, "no plan without a passed scan");

	// Any site that does not look like 93847's: no plan at all, and which site says why
	const auto refuses = [&](size_t site, size_t from, const char* bytes, const char* what) {
		std::vector<uint8_t> m = MakeText();
		Put(m, BuildAt + 0x3a0 + site * 0xf0 + from, bytes);
		const drawcap::ScanResult rm = drawcap::Scan(m.data(), m.size());
		const drawcap::PatchPlan pm = drawcap::PlanPatch(m.data(), m.size(), rm, 12000);
		Check(rm.ok && !pm.ok && pm.editCount == 0 && pm.failedSite == site + 1 && std::strcmp(pm.failed, "base lea") == 0, what);
	};
	refuses(0, 15, "0f 82", "no jae after the compare refuses");
	refuses(3, 26, "48", "a base lea with another displacement refuses");
	refuses(5, 31, "48 03 d8", "an add to another register refuses");
	refuses(6, 27, "90 90 90 90", "no shl rax, 5 refuses");
	refuses(1, 44, "90 90 90 90", "no lea in the window refuses");
	refuses(2, 43, "8d 41", "a lea to rax refuses");
}

void TestViewTable() {
	drawcap::ViewTable<2> v;
	int a = 0, b = 0, c = 0, ba = 0, bb = 0;
	Check(v.Find(&a) == nullptr, "an unknown view has no buffer");
	Check(v.Add(&a, &ba) && v.Add(&b, &bb) && v.Find(&a) == &ba && v.Find(&b) == &bb, "two views, two buffers");
	Check(!v.Add(&c, &ba) && v.Find(&c) == nullptr, "a full table refuses");
	Check(!v.Add(nullptr, &ba), "no null view");
}

void TestConfig() {
	drawcap::Config c = drawcap::ParseConfig(nullptr);
	Check(!c.probe && c.intervalMs == 1000 && c.patch && c.cap == 12000, "defaults: probe off, patch on at 12000");
	c = drawcap::ParseConfig("[drawcap]\npatch = false\ncap = 20000\n");
	Check(!c.patch && c.cap == 20000, "patch off, cap 20000");
	c = drawcap::ParseConfig("[drawcap]\ncap = 100\n");
	Check(c.cap == drawcap::MinPatchCap && c.patch, "cap clamped up");
	c = drawcap::ParseConfig("[drawcap]\ncap = 99999999\npatches = false\ncapacity = 5000\n");
	Check(c.cap == drawcap::MaxPatchCap && c.patch, "cap clamped down; longer keys are not patch or cap");
	c = drawcap::ParseConfig("[drawcap]\nprobe = true\ninterval_ms = 500\n");
	Check(c.probe && c.intervalMs == 500, "probe on, 500 ms");
	c = drawcap::ParseConfig("[other]\nprobe = true\n[drawcap]\n# probe = true\nprobe = false\n");
	Check(!c.probe, "other sections and comments ignored");
	c = drawcap::ParseConfig("[drawcap]\r\nprobe=true\r\ninterval_ms = 10\r\n");
	Check(c.probe && c.intervalMs == 250, "CRLF, no spaces, interval clamped up");
	c = drawcap::ParseConfig("[drawcap]\ninterval_ms = 999999\nprobes = true\n");
	Check(!c.probe && c.intervalMs == 60000, "interval clamped down, a longer key is not probe");
}

void TestStats() {
	drawcap::Stats s;
	Check(!s.Due(5000, 1000), "the first frame starts the window");
	s.Add(2000, drawcap::Legacy, 3000, 800, 600);
	s.Add(3500, drawcap::Legacy, 3000, 800, 600);
	s.Add(3001, drawcap::Legacy, 3000, 800, 600);
	s.Add(100, drawcap::Hd, 3000, 1600, 900);
	s.Add(7, 9, 3000, 0, 0);
	Check(!s.Due(5999, 1000) && s.Due(6000, 1000), "due after the interval");
	const drawcap::Window& w = s.window[drawcap::Legacy];
	Check(w.frames == 3 && w.max == 3500 && w.over == 2 && w.dropped == 501 && w.sum == 8501, "legacy window");
	Check(s.window[drawcap::Unknown].frames == 1, "a bad mode counts as unknown");
	char line[160];
	const int n = drawcap::CsvLine(line, sizeof(line), 6000, drawcap::Legacy, w, 3000);
	Check(n > 0 && std::strcmp(line, "6000,legacy,3,3500,2833.7,2,501,3000,800,600,34\n") == 0, "CSV line");
	Check(drawcap::CsvLine(line, sizeof(line), 6000, drawcap::Legacy, drawcap::Window{}, 3000) == 0 && line[0] == '\0', "no line without frames");
	s.Reset(6000);
	Check(s.window[drawcap::Legacy].frames == 0 && s.total[drawcap::Legacy].frames == 3 && s.total[drawcap::Legacy].max == 3500 &&
	          s.total[drawcap::Legacy].dropped == 501,
	      "reset keeps the totals");
	Check(drawcap::GridSide(800, 600) == 34 && drawcap::GridSide(2560, 1440) == 56, "grid side as STATIC.md section 4");
}

// The real image, when a dump is at hand.
void TestDump() {
	const char* path = std::getenv("D2R_DUMP");
	if (path == nullptr || path[0] == '\0') {
		std::printf("drawcap_tests: D2R_DUMP not set, the dump check is skipped\n");
		return;
	}
	FILE* f = std::fopen(path, "rb");
	if (f == nullptr) {
		std::printf("drawcap_tests: %s not readable, the dump check is skipped\n", path);
		return;
	}
	constexpr size_t TextRva = 0x1000, TextSize = 0x1caf000;  // 93847's .text
	std::vector<uint8_t> text(TextSize);
	const bool read = std::fseek(f, static_cast<long>(TextRva), SEEK_SET) == 0 && std::fread(text.data(), 1, TextSize, f) == TextSize;
	std::fclose(f);
	Check(read, "dump .text read");
	if (!read) {
		return;
	}
	const drawcap::ScanResult r = drawcap::Scan(text.data(), text.size());
	Check(r.ok, "dump scans");
	Check(TextRva + r.build == drawcap::BuildRva93847, "dump: build at 0x21bae0");
	Check(TextRva + r.reset == 0x21bc08 && r.countOffset == drawcap::CountOffset93847, "dump: reset at 0x21bc08, count +0x17750");
	Check(TextRva + r.hd == 0x846210 && TextRva + r.hdGlobal == 0x3440170, "dump: HD test 0x846210, panel manager 0x3440170");
	const uint64_t want[] = {0x21be8f, 0x21bf90, 0x21c273, 0x21c578, 0x21c660, 0x21c904, 0x21c9f5};
	bool same = r.siteCount == 7;
	for (size_t i = 0; same && i < 7; ++i) {
		same = TextRva + r.sites[i].compareAt == want[i];
	}
	Check(same && r.cap == 3000, "dump: the seven cap sites of STATIC.md, cap 3000");
	const drawcap::PatchPlan p = drawcap::PlanPatch(text.data(), text.size(), r, 12000);
	const uint64_t leas[] = {0x21bea5, 0x21bfb3, 0x21c293, 0x21c586, 0x21c66e, 0x21c912, 0x21ca03};
	bool at = p.ok && p.editCount == 14;
	for (size_t i = 0; at && i < 7; ++i) {
		at = TextRva + p.leaAt[i] == leas[i];
	}
	Check(at, "dump: the seven base leas of STATIC.md section 7");
	std::printf("drawcap_tests: dump %s checked\n", path);
}
}  // namespace

int main() {
	TestPattern();
	TestScan();
	TestPatch();
	TestViewTable();
	TestConfig();
	TestStats();
	TestDump();
	if (failures != 0) {
		std::printf("drawcap_tests: %d failures\n", failures);
		return 1;
	}
	std::printf("drawcap_tests: all passed\n");
	return 0;
}

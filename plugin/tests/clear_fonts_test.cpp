// Standalone test of the clear legacy fonts setting (clear_fonts_logic.h; not part of the plugin DLL). Lane fonttoggle.
#include "../src/clear_fonts_logic.h"

#include <cstdio>
#include <cstring>

namespace {
int failures = 0;
void Check(bool ok, const char* what) {
	if (!ok) {
		++failures;
		std::printf("FAIL: %s\n", what);
	}
}

auto Rel32At(const uint8_t* b, uint64_t at) -> uint64_t {
	int32_t rel = 0;
	std::memcpy(&rel, b + 1, 4);
	return at + 5 + static_cast<int64_t>(rel);
}

void Tbl(uint8_t* t, uint8_t lineHeight) {
	std::memset(t, 0, 12 + 256 * 14);
	std::memcpy(t, "Woo!", 4);
	t[4] = 1;
	t[9] = 1;  // 256 glyphs
	t[10] = lineHeight;
}
}  // namespace

int main() {
	using namespace clear_fonts;
	// D2R's bytes: the call goes to the language set-up, the pad ends before the next function, the names' table order
	Check(Rel32At(LangCall, LangCallRva) == LangInitRva, "0x902ff4 calls 0x90da90");
	Check(PadRva + sizeof(Pad) == 0x903010, "the pad is the 14 int3 bytes before 0x903010");
	Check(Rel32At(Unload + 9, UnloadRva + 9) == FreeDc6Rva, "the unload loop frees the DC6 with 0x79d200");
	Check(Unload[3] == 0xf8, "the unload loop reads the DC6 handle at slot +0 (rbx = slot +8)");
	Check(SlotsRva + 8 == 0x34b2a38 && SlotStride == 5 * 8, "slots are 5 qwords from 0x34b2a30");
	for (int id = 1; id < FontIds; ++id) {
		Check(D2RNameRvas[id] > D2RNameRvas[id - 1], "the names follow each other");
	}
	Check(std::strcmp(D2RNames[8], "fontformal11") == 0, "id 8 is formal11");

	// the redirected set: the safe pairs, never the formal fonts or chat
	for (int i = 0; i < Count; ++i) {
		const char* n = D2RNames[Ids[i]];
		Check(std::strstr(n, "formal") == nullptr && std::strcmp(n, "fontingamechat") != 0, "no formal font or chat is redirected");
	}
	Check(Count == 6, "six fonts");

	char name[NameSize];
	NameFor(0, false, name);
	Check(std::strcmp(name, "font8") == 0, "off: D2R's name");
	NameFor(0, true, name);
	Check(std::strcmp(name, "clear\\font8") == 0, "on: the clear folder");
	NameFor(5, true, name);
	Check(std::strcmp(name, "clear\\ReallyTheLastSucker") == 0 && std::strlen(name) < NameSize, "the longest name fits");
	// the path buffers: "data\local\font\" + "latin\" + name + ".tbl" in 0x50 bytes (0x90f070)
	Check(std::strlen("data\\local\\font\\latin\\") + std::strlen(name) + 4 < 0x50, "the TBL path fits D2R's buffer");

	Check(IsLatin("latin\\") && !IsLatin("latin2\\") && !IsLatin("chi\\") && !IsLatin("") && !IsLatin(nullptr), "Latin only");

	uint8_t t[12 + 256 * 14 + 1];
	Tbl(t, 11);
	Check(TblSafe(t, 12 + 256 * 14), "a stock-shaped TBL is safe");
	Tbl(t, 0);
	Check(!TblSafe(t, 12 + 256 * 14), "line height 0 (the repack's formal11) is refused");
	Tbl(t, 11);
	Check(!TblSafe(t, 12 + 256 * 14 + 1) && !TblSafe(t, 100), "a wrong size is refused");
	t[0] = 'X';
	Check(!TblSafe(t, 12 + 256 * 14), "a wrong signature is refused");

	// the setting
	Check(!ParseSetting(nullptr) && !ParseSetting(""), "missing: off");
	Check(ParseSetting("[fonts]\nlegacy_clear_fonts = true\n"), "true: on");
	Check(!ParseSetting("[fonts]\nlegacy_clear_fonts = false # comment\n"), "false: off");
	Check(!ParseSetting("[mapreveal]\nlegacy_clear_fonts = true\n"), "another table: off");
	Check(ParseSetting("[mapreveal]\nthreshold = 70\n\n[fonts]\r\n  legacy_clear_fonts=true\r\n"), "CRLF and spaces");
	Check(!ParseSetting("[fonts]\n# legacy_clear_fonts = true\n"), "a comment: off");

	char out[512];
	Check(WithSetting("[fonts]\nlegacy_clear_fonts = false # keep\nx = 1\n", true, out, sizeof(out)) &&
	          std::strcmp(out, "[fonts]\nlegacy_clear_fonts = true # keep\nx = 1\n") == 0,
	      "an existing value is replaced, its comment kept");
	Check(WithSetting("[mapreveal]\nthreshold = 70\n", true, out, sizeof(out)) && ParseSetting(out) &&
	          std::strncmp(out, "[mapreveal]\nthreshold = 70\n", 27) == 0,
	      "a missing table is added at the end");
	Check(WithSetting("[mapreveal]\nthreshold = 70", false, out, sizeof(out)) && !ParseSetting(out) && std::strstr(out, "70\n\n[fonts]") != nullptr,
	      "a file without a final newline");
	Check(WithSetting("[fonts]\n# about\n[other]\nlegacy_clear_fonts = false\n", true, out, sizeof(out)) && ParseSetting(out) &&
	          std::strstr(out, "[other]\nlegacy_clear_fonts = false") != nullptr,
	      "the key of another table is left alone; it goes under [fonts]");
	Check(WithSetting("", true, out, sizeof(out)) && ParseSetting(out), "an empty file");
	Check(WithSetting("[fonts]\nlegacy_clear_fonts = true\n", false, out, sizeof(out)) && !ParseSetting(out) &&
	          WithSetting(out, true, out + 256, 256) && ParseSetting(out + 256),
	      "round trip");
	Check(!WithSetting("[mapreveal]\nthreshold = 70\n", true, out, 20), "too small: refused");

	// freeing: loaded and not current
	Check(MayFree(0, 1, 0x1234) && !MayFree(0, 0, 0x1234) && !MayFree(0, 1, 0), "only a loaded font that is not current");

	const CallBytes c = CallTo(LangCallRva, PadRva);
	Check(c.bytes[0] == 0xe8 && Rel32At(c.bytes, LangCallRva) == PadRva, "the call goes to the pad");
	const AbsJump j = AbsJumpBytes(0x1122334455667788ull);
	uint64_t to = 0;
	std::memcpy(&to, j.bytes + 6, 8);
	Check(j.bytes[0] == 0xff && j.bytes[1] == 0x25 && to == 0x1122334455667788ull && sizeof(j.bytes) == sizeof(Pad), "the pad's jump fills it");

	if (failures == 0) {
		std::printf("clear_fonts: all checks passed\n");
	}
	return failures == 0 ? 0 : 1;
}

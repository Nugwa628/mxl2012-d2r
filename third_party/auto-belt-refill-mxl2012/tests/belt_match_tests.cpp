// Unit tests for belt_match_logic.h (patches 0003 / 0004) and belt_natives.h (patch 0005), the HUD text of 0006: exact first-slot matching, the counts and where they are drawn, and the
// signatures that find the counts' game data and the refill's routines. With env D2R_DUMP set to a memory-layout dump of D2R 93847 (file offset == RVA,
// tools/dump_image.py) the signatures are also resolved in the real image.
#include "belt_match_logic.h"
#include "belt_natives.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace {

int failures = 0;

void Check(bool ok, const char* what, int line) {
	if (!ok) {
		std::printf("FAIL line %d: %s\n", line, what);
		++failures;
	}
}

#define CHECK(x) Check((x), #x, __LINE__)

constexpr auto Code(const char* text) noexcept -> uint32_t {
	uint32_t code = 0x20202020U;
	for (uint32_t index = 0; index < 4 && text[index] != '\0'; ++index) {
		code = (code & ~(0xFFU << (index * 8))) | (static_cast<uint32_t>(static_cast<unsigned char>(text[index])) << (index * 8));
	}
	return code;
}

bool Near(float a, float b) {
	return std::fabs(a - b) < 0.01F;
}

void Matching() {
	const uint32_t never[] = {Code("ey2"), Code("b@b")};
	// the first slot's exact code, never its family or a bigger potion
	CHECK(BeltMatch::MatchedCode(Code("hp3"), false, Code("hp5"), never, 2) == Code("hp3"));
	CHECK(BeltMatch::MatchedCode(Code("mp1"), false, 0, never, 2) == Code("mp1"));
	CHECK(BeltMatch::MatchedCode(Code("rvs"), false, Code("rvl"), never, 2) == Code("rvs"));
	// a completely empty column refills nothing, whatever it held before (owner, 2026-11-06)
	CHECK(BeltMatch::MatchedCode(0, true, Code("hp4"), never, 2) == 0);
	CHECK(BeltMatch::MatchedCode(0, true, 0, never, 2) == 0);
	// an empty first slot under items still in the column (shifting down after a drink) keeps the code
	CHECK(BeltMatch::MatchedCode(0, false, Code("hp4"), never, 2) == Code("hp4"));
	// an elixir / the Goodberry at the bottom is never learned and the column is not refilled (#541)
	CHECK(BeltMatch::MatchedCode(Code("ey2"), false, Code("hp5"), never, 2) == 0);
	CHECK(BeltMatch::MatchedCode(Code("b@b"), false, 0, never, 2) == 0);
	CHECK(BeltMatch::IsNever(Code("b@b"), never, 2));
	CHECK(!BeltMatch::IsNever(Code("hp5"), never, 2));
	CHECK(!BeltMatch::IsNever(Code("ey2"), never, 0));
}

void Counting() {
	const uint32_t items[] = {Code("hp5"), Code("hp4"), Code("hp5"), Code("mp5"), Code("hp5"), 0};
	CHECK(BeltMatch::CountOf(Code("hp5"), items, 6) == 3);
	CHECK(BeltMatch::CountOf(Code("hp4"), items, 6) == 1);
	CHECK(BeltMatch::CountOf(Code("mp1"), items, 6) == 0);
	CHECK(BeltMatch::CountOf(0, items, 6) == 0);

	char text[4] {};
	CHECK(BeltMatch::CountText(0, text) == 1 && std::strcmp(text, "0") == 0);
	CHECK(BeltMatch::CountText(7, text) == 1 && std::strcmp(text, "7") == 0);
	CHECK(BeltMatch::CountText(42, text) == 2 && std::strcmp(text, "42") == 0);
	CHECK(BeltMatch::CountText(999, text) == 3 && std::strcmp(text, "999") == 0);
	CHECK(BeltMatch::CountText(12345, text) == 3 && std::strcmp(text, "999") == 0);
}

void Geometry() {
	// legacy 800 x 600 in an 800 x 600 window: the classic belt, x 422 + 31 * column, y 561, 29 square
	auto cell = BeltMatch::FirstRowCell(false, 800.0F, 600.0F, 800.0F, 600.0F, 0);
	CHECK(Near(cell.left, 422.0F) && Near(cell.top, 561.0F) && Near(cell.size, 29.0F));
	cell = BeltMatch::FirstRowCell(false, 800.0F, 600.0F, 800.0F, 600.0F, 3);
	CHECK(Near(cell.left, 515.0F));
	// the same screen doubled and letterboxed into 1920 x 1200: scale 2, 160 pixels each side
	cell = BeltMatch::FirstRowCell(false, 1920.0F, 1200.0F, 800.0F, 600.0F, 0);
	CHECK(Near(cell.left, 160.0F + 844.0F) && Near(cell.top, 1122.0F) && Near(cell.size, 58.0F));
	// D2R Legacy 16:9 (1066 x 600) filling a 1920 x 1080 window: the belt moves right with the centred middle part
	cell = BeltMatch::FirstRowCell(false, 1920.0F, 1080.0F, 1066.0F, 600.0F, 0);
	CHECK(Near(cell.left, (0.5F * (1920.0F - 1066.0F * 1.8F)) + 555.0F * 1.8F) && Near(cell.size, 29.0F * 1.8F));
	// HD at 3840 x 2160 (UI units = pixels): HUD left 466, belt 2170, first cell 2182 / 2032, pitch 125
	cell = BeltMatch::FirstRowCell(true, 3840.0F, 2160.0F, 0.0F, 0.0F, 0);
	CHECK(Near(cell.left, 2182.0F) && Near(cell.top, 2032.0F) && Near(cell.size, 98.0F));
	cell = BeltMatch::FirstRowCell(true, 3840.0F, 2160.0F, 0.0F, 0.0F, 2);
	CHECK(Near(cell.left, 2432.0F));
	// HD at 1920 x 1080: everything halved
	cell = BeltMatch::FirstRowCell(true, 1920.0F, 1080.0F, 0.0F, 0.0F, 1);
	CHECK(Near(cell.left, (2182.0F + 125.0F) * 0.5F) && Near(cell.top, 1016.0F) && Near(cell.size, 49.0F));
}

// Writes a little-endian rel32 at `at` that points to `target` (relative to the end of the 4 bytes).
void Rel32(std::vector<uint8_t>& image, std::size_t at, std::size_t target) {
	const auto value = static_cast<uint32_t>(static_cast<int32_t>(static_cast<int64_t>(target) - static_cast<int64_t>(at + 4)));
	for (std::size_t k = 0; k < 4; ++k) {
		image[at + k] = static_cast<uint8_t>(value >> (8 * k));
	}
}

// Copies a signature's bytes (wildcards as 0x00) to `at`.
void Put(std::vector<uint8_t>& image, std::size_t at, const char* pattern) {
	const auto bytes = invtabs::ParsePattern(pattern);
	for (std::size_t k = 0; k < bytes.size(); ++k) {
		image[at + k] = bytes[k] < 0 ? 0x00 : static_cast<uint8_t>(bytes[k]);
	}
}

// A small image: .text at 0x100 (0x400 bytes), the HD test at 0x110, the screen function at 0x180, the panel manager global
// at 0x900, the classic width / height at 0x800 / 0x804.
constexpr std::size_t ImageSize = 0x1000, TextRva = 0x100, TextSize = 0x400, HdAt = 0x110, ScreenAt = 0x180;

auto MakeImage() -> std::vector<uint8_t> {
	std::vector<uint8_t> image(ImageSize, 0xCC);
	Put(image, HdAt, BeltMatch::HdModeNative.pattern);
	Rel32(image, HdAt + BeltMatch::HdModeGlobalDisp, 0x900);
	Put(image, ScreenAt, BeltMatch::ScreenSizeNative.pattern);
	Rel32(image, ScreenAt + BeltMatch::ScreenCallDisp, HdAt);
	Rel32(image, ScreenAt + 0x12, 0x300); // the jmp to the HD size: any code
	Rel32(image, ScreenAt + BeltMatch::ScreenWidthDisp, 0x800);
	Rel32(image, ScreenAt + BeltMatch::ScreenHeightDisp, 0x804);
	return image;
}

auto Resolve(const std::vector<uint8_t>& image) -> BeltMatch::CountNatives {
	return BeltMatch::ResolveCountNatives(image.data(), image.size(), TextRva, TextSize);
}

auto Missing(const BeltMatch::CountNatives& n, const char* name) -> bool {
	return !n.ok() && std::strcmp(n.missing, name) == 0 && n.hdMode == -1 && n.screenWidth == -1 && n.screenHeight == -1;
}

void Signatures() {
	CHECK(!invtabs::ParsePattern(BeltMatch::HdModeNative.pattern).empty());
	CHECK(invtabs::ParsePattern(BeltMatch::ScreenSizeNative.pattern).size() == 0x34);
	auto image = MakeImage();
	auto n = Resolve(image);
	CHECK(n.ok() && n.hdMode == static_cast<int64_t>(HdAt) && n.screenWidth == 0x800 && n.screenHeight == 0x804);
	// no HD test: off, nothing resolved
	image = MakeImage();
	image[HdAt + 15] = 0xBA; // movzx eax, byte [rax+0xba]: another field
	CHECK(Missing(Resolve(image), "hd_mode"));
	// the HD test twice: ambiguous, off
	image = MakeImage();
	Put(image, 0x400, BeltMatch::HdModeNative.pattern);
	Rel32(image, 0x400 + BeltMatch::HdModeGlobalDisp, 0x900);
	CHECK(Missing(Resolve(image), "hd_mode"));
	// the HD test's global outside the image, or in .text
	image = MakeImage();
	Rel32(image, HdAt + BeltMatch::HdModeGlobalDisp, ImageSize + 0x100);
	CHECK(Missing(Resolve(image), "hd_mode"));
	image = MakeImage();
	Rel32(image, HdAt + BeltMatch::HdModeGlobalDisp, 0x200);
	CHECK(Missing(Resolve(image), "hd_mode"));
	// no screen function
	image = MakeImage();
	image[ScreenAt + 0x33] = 0x90;
	CHECK(Missing(Resolve(image), "screen_size"));
	// the screen function calls something else, its height does not follow its width, or its data is code / outside
	image = MakeImage();
	Rel32(image, ScreenAt + BeltMatch::ScreenCallDisp, 0x300);
	CHECK(Missing(Resolve(image), "screen_size"));
	image = MakeImage();
	Rel32(image, ScreenAt + BeltMatch::ScreenHeightDisp, 0x808);
	CHECK(Missing(Resolve(image), "screen_size"));
	image = MakeImage();
	Rel32(image, ScreenAt + BeltMatch::ScreenWidthDisp, 0x200);
	Rel32(image, ScreenAt + BeltMatch::ScreenHeightDisp, 0x204);
	CHECK(Missing(Resolve(image), "screen_size"));
	image = MakeImage();
	Rel32(image, ScreenAt + BeltMatch::ScreenWidthDisp, ImageSize - 4);
	Rel32(image, ScreenAt + BeltMatch::ScreenHeightDisp, ImageSize);
	CHECK(Missing(Resolve(image), "screen_size"));
	// a bad image description
	CHECK(Missing(BeltMatch::ResolveCountNatives(nullptr, ImageSize, TextRva, TextSize), "image"));
	CHECK(Missing(BeltMatch::ResolveCountNatives(image.data(), ImageSize, TextRva, ImageSize), "image"));
}

// ---- 0006 / 0007: the counts as D2R's own HUD text: the column's potions and the inventory reserve ----

void HudText() {
	auto t = BeltMatch::BoxTexts(0, 4, 17); // no code (empty column, elixir): all three boxes empty
	CHECK(t.white[0] == '\0' && t.red[0] == '\0' && t.reserve[0] == '\0');
	t = BeltMatch::BoxTexts(Code("hp3"), 0, 0); // column empty, none left: a red 0 and "+0"
	CHECK(t.white[0] == '\0' && std::strcmp(t.red, "0") == 0 && std::strcmp(t.reserve, "+0") == 0);
	t = BeltMatch::BoxTexts(Code("hp3"), 1, 0); // the last one: red
	CHECK(t.white[0] == '\0' && std::strcmp(t.red, "1") == 0 && std::strcmp(t.reserve, "+0") == 0);
	t = BeltMatch::BoxTexts(Code("hp3"), 2, 0);
	CHECK(std::strcmp(t.white, "2") == 0 && t.red[0] == '\0');
	t = BeltMatch::BoxTexts(Code("hp3"), 4, 17); // a full 4-row column, 17 more in the inventory
	CHECK(std::strcmp(t.white, "4") == 0 && t.red[0] == '\0' && std::strcmp(t.reserve, "+17") == 0);
	t = BeltMatch::BoxTexts(Code("mp5"), 4, 5000);
	CHECK(std::strcmp(t.reserve, "+999") == 0);
	CHECK(BeltMatch::LowCount == 1);
	char name[24] {};
	CHECK(std::strcmp(BeltMatch::BoxName(BeltMatch::BoxKind::Count, 0, name), "MxlBeltCount0") == 0);
	CHECK(std::strcmp(BeltMatch::BoxName(BeltMatch::BoxKind::Low, 3, name), "MxlBeltCountLow3") == 0);
	CHECK(std::strcmp(BeltMatch::BoxName(BeltMatch::BoxKind::Reserve, 2, name), "MxlBeltReserve2") == 0);
	CHECK(BeltMatch::BoxKinds == 3);
	CHECK(std::strcmp(BeltMatch::HudPanelName, "HUDPanel") == 0);
}

// The column's own potions: the belt slots are row * 4 + column.
void ColumnCounts() {
	const int32_t full4[] = {0, 4, 8, 12, 1, 5, 2}; // column 0 full (4 rows), column 1 two, column 2 one, column 3 none
	CHECK(BeltMatch::InColumn(0, full4, 7) == 4);
	CHECK(BeltMatch::InColumn(1, full4, 7) == 2);
	CHECK(BeltMatch::InColumn(2, full4, 7) == 1);
	CHECK(BeltMatch::InColumn(3, full4, 7) == 0);
	CHECK(BeltMatch::InColumn(0, full4, 0) == 0);
	const int32_t bad[] = {-1, 3, 7};
	CHECK(BeltMatch::InColumn(3, bad, 3) == 2);
	CHECK(BeltMatch::InColumn(0, bad, 3) == 0);
}

// A small image: the root load at 0x120 (the root at 0x900), the FindPanel call at 0x180 (to 0x300), FindChild at 0x200,
// SetText at 0x240.
auto MakeTextImage() -> std::vector<uint8_t> {
	namespace S = invtabs::summary;
	std::vector<uint8_t> image(ImageSize, 0xCC);
	Put(image, 0x120, S::SummaryPatterns[S::UiRoot].pattern);
	Rel32(image, 0x123, 0x900);
	Put(image, 0x180, S::SummaryPatterns[S::UiFindPanel].pattern);
	Rel32(image, 0x181, 0x300);
	Put(image, 0x200, S::SummaryPatterns[S::UiFindChild].pattern);
	Put(image, 0x240, S::SummaryPatterns[S::TextBoxSetText].pattern);
	return image;
}

auto TextOff(const BeltMatch::TextNatives& n, const char* name) -> bool {
	return !n.ok() && std::strcmp(n.missing, name) == 0;
}

auto ResolveText(const std::vector<uint8_t>& image) -> BeltMatch::TextNatives {
	return BeltMatch::ResolveTextNatives(image.data(), image.size(), TextRva, TextSize);
}

void TextSignatures() {
	namespace S = invtabs::summary;
	auto image = MakeTextImage();
	auto n = ResolveText(image);
	CHECK(n.ok() && n.uiRoot == 0x900 && n.findPanel == 0x300 && n.findChild == 0x200 && n.setText == 0x240);
	// the root inside .text: not data, off
	Rel32(image, 0x123, 0x350);
	CHECK(TextOff(ResolveText(image), "UiRoot"));
	// the FindPanel call leaves .text
	image = MakeTextImage();
	Rel32(image, 0x181, 0x900);
	CHECK(TextOff(ResolveText(image), "UiFindPanel"));
	// FindChild twice: ambiguous
	image = MakeTextImage();
	Put(image, 0x400, S::SummaryPatterns[S::UiFindChild].pattern);
	CHECK(TextOff(ResolveText(image), "UiFindChild"));
	// no setter
	image = MakeTextImage();
	image[0x241] = 0x54;
	CHECK(TextOff(ResolveText(image), "TextBoxSetText"));
	// the FindPanel call lands on FindChild
	image = MakeTextImage();
	Rel32(image, 0x181, 0x200);
	CHECK(TextOff(ResolveText(image), "UI functions not distinct"));
	CHECK(TextOff(BeltMatch::ResolveTextNatives(nullptr, ImageSize, TextRva, TextSize), "image"));
}

// ---- belt_natives.h: a small image that holds every signature with consistent calls and entries ----

constexpr std::size_t NImageSize = 0x8000, NTextRva = 0x100, NTextSize = 0x6000;

struct NativeImage {
	std::vector<uint8_t> image = std::vector<uint8_t>(NImageSize, 0xCC);
	std::size_t          site[BeltNatives::Count] {};   // where each signature was placed
	std::size_t          target[BeltNatives::Count] {}; // where each routine is
};

auto MakeNativeImage() -> NativeImage {
	NativeImage n;
	std::size_t next = NTextRva + 0x40;
	const auto  take = [&](std::size_t size) {
		const std::size_t at = next;
		next += (size + 0x40) & ~std::size_t {0x1F};
		return at;
	};
	for (const BeltNatives::Sig& sig : BeltNatives::Sigs) {
		// a signature shared with an earlier routine (GetUnitType / GetItemData) is placed once
		std::size_t at = 0;
		for (const BeltNatives::Sig& before : BeltNatives::Sigs) {
			if (before.id == sig.id) {
				break;
			}
			if (std::strcmp(before.pattern, sig.pattern) == 0) {
				at = n.site[before.id];
			}
		}
		if (at == 0) {
			at = take(invtabs::ParsePattern(sig.pattern).size());
			Put(n.image, at, sig.pattern);
		}
		n.site[sig.id] = at;
		if (sig.rip >= 0) {
			const std::size_t entry = take(sig.entry != nullptr ? invtabs::ParsePattern(sig.entry).size() : 8);
			if (sig.entry != nullptr) {
				Put(n.image, entry, sig.entry);
			}
			Rel32(n.image, at + static_cast<std::size_t>(sig.rip), entry);
			n.target[sig.id] = entry;
		} else {
			n.target[sig.id] = at + static_cast<std::size_t>(sig.adjust);
		}
		for (const BeltNatives::CallCheck& call : sig.calls) {
			if (call.offset >= 0) {
				Rel32(n.image, at + static_cast<std::size_t>(call.offset), n.target[call.target]);
			}
		}
	}
	return n;
}

auto ResolveN(const NativeImage& n) -> BeltNatives::Resolved {
	return BeltNatives::Resolve(n.image.data(), n.image.size(), NTextRva, NTextSize);
}

auto Off(const BeltNatives::Resolved& r, const char* name) -> bool {
	if (r.ok() || std::strcmp(r.missing, name) != 0) {
		return false;
	}
	for (const int64_t rva : r.rva) {
		if (rva != -1) {
			return false;
		}
	}
	return true;
}

void Natives() {
	for (const BeltNatives::Sig& sig : BeltNatives::Sigs) {
		Check(!invtabs::ParsePattern(sig.pattern).empty(), sig.name, __LINE__);
		Check(sig.entry == nullptr || !invtabs::ParsePattern(sig.entry).empty(), sig.name, __LINE__);
		Check(sig.id == static_cast<int>(&sig - BeltNatives::Sigs), sig.name, __LINE__);
		for (const BeltNatives::CallCheck& call : sig.calls) {
			Check(call.offset < 0 || call.target < sig.id, sig.name, __LINE__); // calls name routines resolved before
		}
	}
	CHECK(invtabs::ParsePattern(BeltNatives::Sigs[BeltNatives::CanPutInBelt].pattern).size() >= BeltNatives::HookBytes);
	CHECK(invtabs::ParsePattern(BeltNatives::Sigs[BeltNatives::BeltTransfer].pattern).size() >= BeltNatives::HookBytes);

	// all found, each where it was put
	const NativeImage good = MakeNativeImage();
	auto              r    = ResolveN(good);
	CHECK(r.ok());
	for (int id = 0; id < BeltNatives::Count; ++id) {
		Check(r.rva[id] == static_cast<int64_t>(good.target[id]), BeltNatives::Sigs[id].name, __LINE__);
	}

	// each signature missing, or there twice (ambiguous): a required one turns the refill off with nothing resolved,
	// the optional one only stays unresolved
	// (a signature shared by two routines is reported under the first of them: GetUnitType for GetItemData's)
	for (const BeltNatives::Sig& sig : BeltNatives::Sigs) {
		const char* first = sig.name;
		for (const BeltNatives::Sig& before : BeltNatives::Sigs) {
			if (std::strcmp(before.pattern, sig.pattern) == 0) {
				first = before.name;
				break;
			}
		}
		NativeImage n = good;
		n.image[n.site[sig.id]] = 0x90;
		r = ResolveN(n);
		Check(sig.required ? Off(r, first) : (r.ok() && !r.has(sig.id)), sig.name, __LINE__);
		n = good;
		const std::size_t size = invtabs::ParsePattern(sig.pattern).size();
		std::memcpy(&n.image[NTextRva + NTextSize - 0x200], &n.image[n.site[sig.id]], size);
		r = ResolveN(n);
		Check(sig.required ? Off(r, first) : (r.ok() && !r.has(sig.id)), sig.name, __LINE__);
	}
	// GetItemData's own entry check: its target is not an item-data getter
	{
		NativeImage n = good;
		n.image[good.target[BeltNatives::ItemData]] = 0x90;
		CHECK(Off(ResolveN(n), "GetItemData"));
	}

	// GetLocalDataContext's caller does not hand it to GetLocalPlayer
	NativeImage n = good;
	Rel32(n.image, n.site[BeltNatives::LocalDataContext] + 8, NTextRva + 0x10);
	CHECK(Off(ResolveN(n), "GetLocalDataContext"));
	// CanPutInBelt's start does not call GetLocalPlayer
	n = good;
	Rel32(n.image, n.site[BeltNatives::CanPutInBelt] + 26, NTextRva + 0x10);
	CHECK(Off(ResolveN(n), "CanPutInBelt"));
	// GetItemCode's target is not its entry
	n = good;
	n.image[good.target[BeltNatives::ItemCode]] = 0x90;
	CHECK(Off(ResolveN(n), "GetItemCode"));
	// a target outside .text
	n = good;
	Rel32(n.image, n.site[BeltNatives::ItemCode] + 4, NTextRva + NTextSize + 0x100);
	CHECK(Off(ResolveN(n), "GetItemCode"));
	// GetNextItem's call pointing at GetItemData (same entry shape): two routines at one address
	n = good;
	Rel32(n.image, n.site[BeltNatives::NextItem] + 89, good.target[BeltNatives::ItemData]);
	CHECK(Off(ResolveN(n), "GetNextItem"));
	// a bad image description
	CHECK(Off(BeltNatives::Resolve(nullptr, NImageSize, NTextRva, NTextSize), "image"));
	CHECK(Off(BeltNatives::Resolve(good.image.data(), NImageSize, NTextRva, NImageSize), "image"));
}

// The real image, when a dump is at hand: both signatures resolve to the 93847 places.
void Dump() {
	char*       env     = nullptr;
	std::size_t envSize = 0;
	if (_dupenv_s(&env, &envSize, "D2R_DUMP") != 0 || env == nullptr || *env == '\0') {
		std::free(env);
		std::printf("belt_match_tests: D2R_DUMP not set, the dump check is skipped\n");
		return;
	}
	const std::string text(env);
	std::free(env);
	const char* path = text.c_str();
	std::FILE* file = nullptr;
	if (fopen_s(&file, path, "rb") != 0 || file == nullptr) {
		std::printf("belt_match_tests: %s not readable, the dump check is skipped\n", path);
		return;
	}
	std::vector<uint8_t> image;
	uint8_t              chunk[1 << 16];
	for (std::size_t got = 0; (got = std::fread(chunk, 1, sizeof(chunk), file)) != 0;) {
		image.insert(image.end(), chunk, chunk + got);
	}
	std::fclose(file);
	// the dump's PE headers: SizeOfImage and .text
	CHECK(image.size() > 0x1000 && image[0] == 'M' && image[1] == 'Z');
	if (image.size() <= 0x1000) {
		return;
	}
	auto u32 = [&](std::size_t at) {
		return static_cast<uint32_t>(image[at]) | static_cast<uint32_t>(image[at + 1]) << 8 | static_cast<uint32_t>(image[at + 2]) << 16 |
		       static_cast<uint32_t>(image[at + 3]) << 24;
	};
	const std::size_t nt = u32(0x3c);
	const std::size_t sections = static_cast<std::size_t>(image[nt + 6]) | static_cast<std::size_t>(image[nt + 7]) << 8;
	const std::size_t optional = static_cast<std::size_t>(image[nt + 20]) | static_cast<std::size_t>(image[nt + 21]) << 8;
	const std::size_t imageSize = u32(nt + 24 + 56);
	std::size_t       textRva = 0, textSize = 0;
	for (std::size_t s = 0; s < sections; ++s) {
		const std::size_t at = nt + 24 + optional + s * 40;
		if (std::memcmp(&image[at], ".text", 6) == 0) {
			textSize = u32(at + 8);
			textRva = u32(at + 12);
		}
	}
	CHECK(textRva != 0 && imageSize <= image.size());
	if (textRva == 0 || imageSize > image.size()) {
		return;
	}
	const auto n = BeltMatch::ResolveCountNatives(image.data(), imageSize, textRva, textSize);
	CHECK(n.ok());
	CHECK(n.hdMode == 0x846210);
	CHECK(n.screenWidth == 0x22a0d68 && n.screenHeight == 0x22a0d6c);
	std::printf("belt_match_tests: dump %s: hd_mode 0x%llx, screen 0x%llx / 0x%llx\n", path, static_cast<unsigned long long>(n.hdMode),
	            static_cast<unsigned long long>(n.screenWidth), static_cast<unsigned long long>(n.screenHeight));
	// every refill routine at its 93847 address
	const auto natives = BeltNatives::Resolve(image.data(), imageSize, textRva, textSize);
	CHECK(natives.ok());
	for (const BeltNatives::Sig& sig : BeltNatives::Sigs) {
		const bool same = natives.rva[sig.id] == static_cast<int64_t>(sig.rva93847);
		Check(same, sig.name, __LINE__);
		std::printf("belt_match_tests: dump: %-19s 0x%llx (93847 0x%llx)%s\n", sig.name,
		            static_cast<unsigned long long>(natives.rva[sig.id]), static_cast<unsigned long long>(sig.rva93847),
		            same ? "" : "  MISMATCH");
	}
	// the HUD text routines (0006) at their 93847 places
	const auto hud = BeltMatch::ResolveTextNatives(image.data(), imageSize, textRva, textSize);
	CHECK(hud.ok() && hud.uiRoot == 0x3440170 && hud.findPanel == 0x89F760 && hud.findChild == 0x855C90 && hud.setText == 0x86DD50);
	std::printf("belt_match_tests: dump: HUD text %s, root 0x%llx, panel 0x%llx, child 0x%llx, set 0x%llx\n", hud.ok() ? "ok" : hud.missing,
	            static_cast<unsigned long long>(hud.uiRoot), static_cast<unsigned long long>(hud.findPanel),
	            static_cast<unsigned long long>(hud.findChild), static_cast<unsigned long long>(hud.setText));
}

} // namespace

int main() {
	Matching();
	Counting();
	Geometry();
	Signatures();
	HudText();
	ColumnCounts();
	TextSignatures();
	Natives();
	Dump();
	if (failures != 0) {
		std::printf("belt_match_tests: %d failure(s)\n", failures);
		return 1;
	}
	std::printf("belt_match_tests: all passed\n");
	return 0;
}

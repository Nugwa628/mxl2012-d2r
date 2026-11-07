// Unit tests for belt_match_logic.h (patch 0003): exact first-slot matching, the counts and where they are drawn.
#include "belt_match_logic.h"

#include <cmath>
#include <cstdio>
#include <cstring>

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

} // namespace

int main() {
	Matching();
	Counting();
	Geometry();
	if (failures != 0) {
		std::printf("belt_match_tests: %d failure(s)\n", failures);
		return 1;
	}
	std::printf("belt_match_tests: all passed\n");
	return 0;
}

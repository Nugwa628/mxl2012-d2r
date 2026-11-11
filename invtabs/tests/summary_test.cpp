// Unit tests of the charm-tab summary's pure part (src/summary_logic.h, src/summary_natives.h). No game, no Windows headers.
// Build on its own (no CMake change needed): cl /std:c++20 /EHsc /W4 /permissive- /utf-8 invtabs/tests/summary_test.cpp
// or add it to invtabs/tests/CMakeLists.txt next to invtabs_test.cpp (docs/invtabs-summary.md "Tests").
#include "../src/summary_logic.h"
#include "../src/summary_natives.h"

#include <cstdio>
#include <cstring>
#include <set>
#include <string>

namespace {

int failures = 0;

void Check(bool ok, const char* what, int line) {
	if (!ok) {
		++failures;
		std::printf("FAIL line %d: %s\n", line, what);
	}
}
#define CHECK(x) Check((x), #x, __LINE__)

using namespace invtabs::summary;

// Stats used below (itemstatcost ids): 0 strength, 39 fire resist, 43 cold resist, 7 maxhp, 107 item_singleskill
// (param = skill), 83 item_addclassskills (param = class), 216 item_hp_perlevel, 252 item_replenish_durability (hidden
// in this table on purpose), 9999 unknown.
std::optional<StatInfo> Info(std::uint16_t stat) {
	switch (stat) {
	case 0: return StatInfo { 67, true };
	case 7: return StatInfo { 56, true };
	case 39: return StatInfo { 36, true };
	case 43: return StatInfo { 36, true };
	case 83: return StatInfo { 150, true };
	case 107: return StatInfo { 81, true };
	case 216: return StatInfo { 56, true };
	case 252: return StatInfo { 0, false };
	default: return std::nullopt;
	}
}

void Sums() {
	// two charms add up per (stat, param)
	const std::vector<ItemStats> two { { true, { { 0, 0, 5 }, { 39, 0, 10 } } }, { true, { { 0, 0, 3 }, { 43, 0, 7 } } } };
	CHECK(Sum(two) == (std::vector<StatValue> { { 0, 0, 8 }, { 39, 0, 10 }, { 43, 0, 7 } }));
	// an empty tab, items without stats
	CHECK(Sum({}).empty());
	CHECK(Sum({ { true, {} }, { true, {} } }).empty());
}

void Inactive() {
	// a carry1 duplicate that is not the active copy (not merged): left out, its twin counts once
	const ItemStats active { true, { { 7, 0, 20 }, { 39, 0, 15 } } };
	const ItemStats duplicate { false, { { 7, 0, 20 }, { 39, 0, 15 } } };
	CHECK(Sum({ active, duplicate }) == (std::vector<StatValue> { { 7, 0, 20 }, { 39, 0, 15 } }));
	CHECK(Sum({ duplicate, active }) == Sum({ active }));
	// requirements not met: same flag
	CHECK(Sum({ { false, { { 0, 0, 50 } } } }).empty());
}

void Params() {
	// +skill stats are kept apart per skill, +class-skills per class
	const std::vector<ItemStats> items { { true, { { 107, 36, 1 }, { 107, 37, 2 }, { 83, 1, 1 } } },
		                                 { true, { { 107, 36, 2 }, { 83, 2, 1 }, { 83, 1, 2 } } } };
	CHECK(Sum(items) == (std::vector<StatValue> { { 83, 1, 3 }, { 83, 2, 1 }, { 107, 36, 3 }, { 107, 37, 2 } }));
}

void Negatives() {
	// a curse-like charm: negatives add, a total of 0 disappears, a negative total stays
	const std::vector<ItemStats> items { { true, { { 39, 0, 20 }, { 43, 0, -10 }, { 0, 0, 5 } } }, { true, { { 39, 0, -20 }, { 43, 0, -5 } } } };
	CHECK(Sum(items) == (std::vector<StatValue> { { 0, 0, 5 }, { 43, 0, -15 } }));
	// int32 overflow clamps instead of wrapping
	const std::vector<ItemStats> big { { true, { { 7, 0, 2'000'000'000 } } }, { true, { { 7, 0, 2'000'000'000 } } }, { true, { { 0, 0, -2'000'000'000 } } },
		                               { true, { { 0, 0, -2'000'000'000 } } } };
	const auto s = Sum(big);
	CHECK(s.size() == 2 && s[0].stat == 0 && s[0].value == std::numeric_limits<std::int32_t>::min());
	CHECK(s.size() == 2 && s[1].stat == 7 && s[1].value == std::numeric_limits<std::int32_t>::max());
	// per-level stats stay raw (the formatter applies the shift): 3 x 1/8 per level = raw 3
	CHECK(Sum({ { true, { { 216, 0, 1 } } }, { true, { { 216, 0, 2 } } } }) == (std::vector<StatValue> { { 216, 0, 3 } }));
}

void Order() {
	const std::vector<StatValue> totals { { 39, 0, 10 }, { 0, 0, 5 }, { 252, 0, 1 }, { 43, 0, 7 }, { 83, 1, 1 }, { 107, 37, 1 }, { 107, 36, 1 }, { 9999, 0, 1 } };
	const auto ordered = OrderForDisplay(totals, Info);
	// descpriority high first, then stat, then param; hidden (252) and unknown (9999) dropped
	CHECK(ordered == (std::vector<StatValue> { { 83, 1, 1 }, { 107, 36, 1 }, { 107, 37, 1 }, { 0, 0, 5 }, { 39, 0, 10 }, { 43, 0, 7 } }));
	CHECK(OrderForDisplay({ { 252, 0, 5 } }, Info).empty());
}

void Lines() {
	CHECK(SplitLines("") .empty());
	CHECK(SplitLines("a\nb") == (std::vector<std::string> { "a", "b" }));
	CHECK(SplitLines("\r\nFire Resist +10%\r\n\n+5 to Strength\n") == (std::vector<std::string> { "Fire Resist +10%", "+5 to Strength" }));
	CHECK(StripColour("\xC3\xBF" "c3+5 to Strength") == "+5 to Strength");
	CHECK(StripColour("a\xFF" "c1b") == "ab");
	CHECK(StripColour("plain") == "plain");
	// the writer's order (lowest descpriority first) into the tooltip's
	CHECK(TooltipOrder({ "+3 to Strength", "+1 to Sorceress Skill Levels" }) == (std::vector<std::string> { "+1 to Sorceress Skill Levels", "+3 to Strength" }));
	CHECK(TooltipOrder({}).empty());
	CHECK(StripColour("\xC3\xBF" "c") == "\xC3\xBF" "c"); // a cut-off code stays as it is
}

void LongLists() {
	std::vector<std::string> many;
	for (int i = 0; i < 500; ++i) many.push_back("line " + std::to_string(i));
	const auto capped = CapLines(many);
	CHECK(capped.size() == MaxLines);
	CHECK(capped.back() == MoreLine(500 - (MaxLines - 1)));
	CHECK(capped[MaxLines - 2] == "line " + std::to_string(MaxLines - 2));
	CHECK(CapLines(many, 1) == (std::vector<std::string> { MoreLine(500) }));
	CHECK(CapLines(many, 0).empty());
	CHECK(CapLines({ "a", "b" }).size() == 2);

	// classic window: 8 rows over 20 lines
	CHECK(ClampFirst(-3, 20, 8) == 0);
	CHECK(ClampFirst(5, 20, 8) == 5);
	CHECK(ClampFirst(50, 20, 8) == 12);
	CHECK(ClampFirst(4, 6, 8) == 0); // fewer lines than rows: no scrolling
	CHECK(Scroll(0, -1, 20, 8) == 0);
	CHECK(Scroll(11, 3, 20, 8) == 12);
	CHECK(Scroll(12, -1, 20, 8) == 11);
	const std::vector<std::string> l { "a", "b", "c" };
	CHECK(RowText(l, 1, 0) == "b");
	CHECK(RowText(l, 1, 1) == "c");
	CHECK(RowText(l, 1, 2).empty());
}

void Layout() {
	CHECK(VisibleRows(LayoutMode::Hd, 320) == 10);
	CHECK(VisibleRows(LayoutMode::Hd, 0) == 0);
	CHECK(VisibleRows(LayoutMode::Classic, 130) == 10);
	CHECK(LayoutRows(LayoutMode::Hd, 320, 3) == 10);    // at least a screenful
	CHECK(LayoutRows(LayoutMode::Hd, 320, 40) == 40);   // one per line
	CHECK(LayoutRows(LayoutMode::Hd, 320, 9000) == MaxLines);
	CHECK(LayoutRows(LayoutMode::Classic, 130, 40) == 10);
	CHECK(Fits(LayoutMode::Hd, 10, 10));
	CHECK(!Fits(LayoutMode::Hd, 10, 11));
	CHECK(Fits(LayoutMode::Hd, MaxLines, MaxLines + 5));
	CHECK(Fits(LayoutMode::Classic, 10, 50));

	const std::string hd = LayoutFragment(LayoutMode::Hd, { 40, 120, 600, 320 }, 12);
	CHECK(hd.find("\"ScrollViewWidget\", \"name\": \"SummaryView\"") != std::string::npos);
	CHECK(hd.find("\"scrollControllerName\": \"SummaryScroll\"") != std::string::npos);
	CHECK(hd.find("\"viewName\": \"SummaryView\"") != std::string::npos);
	CHECK(hd.find("\"clipChildrenDraw\": true") != std::string::npos);
	CHECK(hd.find("\"name\": \"SummaryLine11\"") != std::string::npos);
	CHECK(hd.find("\"name\": \"SummaryLine12\"") == std::string::npos);
	// the view leaves room for the bar; the bar sits at the right edge of the area
	CHECK(hd.find(JsonRect(40, 120, 600 - HdBarWidth - HdBarGap, 320)) != std::string::npos);
	CHECK(hd.find(JsonRect(40 + 600 - HdBarWidth, 120, HdBarWidth, 320)) != std::string::npos);
	// rows are relative to the view, one pitch apart
	CHECK(hd.find(JsonRect(0, 11 * HdRowPitch, 600 - HdBarWidth - HdBarGap, HdRowHeight)) != std::string::npos);
	// balanced brackets: it splices into a children array as is
	int braces = 0, brackets = 0;
	bool quoted = false;
	for (std::size_t i = 0; i < hd.size(); ++i) {
		const char c = hd[i];
		if (c == '"' && (i == 0 || hd[i - 1] != '\\')) quoted = !quoted;
		if (quoted) continue;
		braces += c == '{' ? 1 : c == '}' ? -1 : 0;
		brackets += c == '[' ? 1 : c == ']' ? -1 : 0;
		CHECK(braces >= 0 && brackets >= 0);
	}
	CHECK(braces == 0 && brackets == 0 && !quoted);
	// no backslash at all: art paths use '/', so no JSON escape can go wrong (D2RLoader rejected "FrontEnd\HD" as an escape)
	CHECK(hd.find('\\') == std::string::npos);
	CHECK(hd.find("\"barFilepath\": \"PauseMenu/VerticalIndicator\"") != std::string::npos);
	CHECK(hd.back() == '}');

	const std::string sd = LayoutFragment(LayoutMode::Classic, { 10, 50, 300, 130 }, 10);
	CHECK(sd.find("ScrollViewWidget") == std::string::npos);
	CHECK(sd.find("\"fontType\": \"8pt\"") != std::string::npos);
	CHECK(sd.find(JsonRect(10, 50 + 9 * ClassicRowPitch, 300, ClassicRowHeight)) != std::string::npos);
	CHECK(LayoutFragment(LayoutMode::Classic, { 0, 0, 10, 10 }, 0).empty());
}

void Patterns() {
	CHECK(ParsePattern("E8 ?? ?? ?? ?? 48") == (std::vector<int> { 0xE8, -1, -1, -1, -1, 0x48 }));
	CHECK(ParsePattern("e8 0f") == (std::vector<int> { 0xE8, 0x0F }));
	CHECK(ParsePattern("?? 8B").empty());
	CHECK(ParsePattern("48 8").empty());
	CHECK(ParsePattern("48 GG").empty());
	CHECK(ParsePattern("488B").empty());
	// a call site: E8 rel32 -> target
	const std::uint8_t code[] { 0x90, 0x90, 0xE8, 0x10, 0x00, 0x00, 0x00, 0x48, 0x8B, 0xF8, 0x90, 0xE8, 0xF0, 0xFF, 0xFF, 0xFF, 0x48, 0x8B, 0xF9 };
	const auto at = FindUnique(code, sizeof(code), "E8 ?? ?? ?? ?? 48 8B F8");
	CHECK(at && *at == 2);
	CHECK(at && RipTarget(code, *at + 1) == 2 + 5 + 0x10);
	const auto back = FindUnique(code, sizeof(code), "E8 ?? ?? ?? ?? 48 8B F9");
	CHECK(back && RipTarget(code, *back + 1) == 11 + 5 - 0x10);
	CHECK(!FindUnique(code, sizeof(code), "E8 ?? ?? ?? ?? 48 8B")); // two matches
	CHECK(!FindUnique(code, sizeof(code), "E8 ?? ?? ?? ?? 49"));    // none

	// the table: every pattern parses, starts with a fixed byte, names are unique, call-site rip points at a rel32
	std::set<std::string> names;
	for (const SummaryPattern& p : SummaryPatterns) {
		const auto parsed = ParsePattern(p.pattern);
		CHECK(!parsed.empty());
		CHECK(parsed.size() >= 16);
		CHECK(names.insert(p.name).second);
		if (p.rip >= 0) {
			CHECK(static_cast<std::size_t>(p.rip) + 4 <= parsed.size());
			for (int k = 0; k < 4 && static_cast<std::size_t>(p.rip + k) < parsed.size(); ++k) CHECK(parsed[static_cast<std::size_t>(p.rip + k)] == -1);
		}
	}
	CHECK(names.size() == SummaryNativeCount);
	CHECK(SummaryNativeOptional(FormatOne) && SummaryNativeOptional(StatRecord) && !SummaryNativeOptional(StatListText));
}

} // namespace

int main() {
	Sums();
	Inactive();
	Params();
	Negatives();
	Order();
	Lines();
	LongLists();
	Layout();
	Patterns();
	if (failures) {
		std::printf("%d check(s) failed\n", failures);
		return 1;
	}
	std::printf("summary_tests: all checks passed\n");
	return 0;
}

// Unit tests of the sheet host's pure part (src/sheet_host_logic.h): widget names, what shows on a tab and a line, the All Stats
// window with its highlight layers and scroll, the typed query, colour codes, the click rectangles and the All Stats lines.
#include "../src/sheet_host_logic.h"

#include <cstdio>
#include <map>
#include <string>

using namespace sheet_host;

namespace {

int g_failed = 0;

void Check(bool ok, const char* what) {
	if (!ok) {
		std::printf("FAIL: %s\n", what);
		++g_failed;
	}
}

const char* const Sample =
	"statbook\t1\n"
	"page\toffense\tOffense\n"
	"section\tDamage\n"
	"row\tEnhanced Damage\t17\t%+d%%\tw\t-\t-\th\n"
	"row\tAttack Rating\t119\t%+d%%\tw\t-\t-\th\n"
	"row\tCrushing Blow\t136\t%d%%\tw\t-\t-\tf\n"
	"page\tresist\tResistances\n"
	"section\tResistances\n"
	"row\tFire Resistance\t39,40\t%d%% (max %d%%)\tr\t75+40<=95\t0,75\tf\n"
	"group\tAdvStatsGroupOffense\tOffense\n"
	"all\tstat\t17\t-\t-\n"
	"all\trange\t48,49\tAdvStatsAddsFire\tAdds %d-%d Fire Damage\n"
	"group\tAdvStatsGroupDefense\tDefense\n"
	"all\tavoid\t338,339,340\t-\t-\n";

void TestNames() {
	Check(Slot("SbLine", 3, "LeftValueGold") == "SbLine03LeftValueGold", "line slot name");
	Check(Slot("SbAll", 21, "Hit") == "SbAll21Hit", "all row name");
	Check(TabName(7, "SelectedLabel") == "SbTab7SelectedLabel", "tab name");
	Check(std::string(ToneNames[static_cast<int>(statbook::Tone::ItemBlue)]) == "ItemBlue", "tone names follow the Tone order");
	Check(ParentOf("SbLine03LeftValueGold") == "SbLine03Left" && ParentOf("SbLine03Left") == "StatBookPage" &&
	          ParentOf("SbLine21HeadingText") == "SbLine21Heading" && ParentOf("SbLine00FullCell") == "SbLine00Full",
	      "line parents");
	Check(ParentOf("SbAll07Hit") == "SbAll07Row" && ParentOf("SbAll07Go") == "SbAll07Row" && ParentOf("SbAll07HeadingRule") == "SbAll07Heading" &&
	          ParentOf("SbAll07Row") == "StatBookAll" && ParentOf("SbAll07Heading") == "StatBookAll",
	      "All Stats parents");
	Check(ParentOf("SbTab3SelectedLabel") == "StatBookTabs" && ParentOf("SbPadPrevLB") == "StatBookTabs" && ParentOf("SbPadAllHintText") == "SbPadAllHint" &&
	          ParentOf("SbPadAllHint").empty() && ParentOf("SbSearchInput") == "StatBookAll" && ParentOf("SbAllScrollThumb") == "StatBookAll" &&
	          ParentOf("StatBookPage").empty() && ParentOf("SbPageBody").empty(),
	      "other parents");
}

void TestShow() {
	statbook::Tabs t;
	t.pages = 6;
	PageShow s = ShowForTab(t);
	Check(s.sheet && !s.body && !s.page && !s.all, "the Character tab shows D2R's sheet only");
	t.Select(3);
	s = ShowForTab(t);
	Check(!s.sheet && s.body && s.page && !s.all, "a themed page");
	t.Select(t.AllStats());
	s = ShowForTab(t);
	Check(!s.sheet && s.body && !s.page && s.all, "All Stats");
	Check(!PlusButtonsEnabled(s, false, false), "the + buttons take no click on All Stats");
	Check(PlusButtonsEnabled(s, true, false), "the side host shows D2R's sheet: + buttons on");
	Check(PlusButtonsEnabled(s, false, true), "plain D2R: the + buttons are D2R's");
	t.Select(3);
	Check(!PlusButtonsEnabled(ShowForTab(t), false, false), "the + buttons take no click on a themed page");
	t.Select(0);
	Check(PlusButtonsEnabled(ShowForTab(t), false, false), "the + buttons take clicks on the Character tab");
	t.Select(t.AllStats());
	statbook::Line l;
	LineShow ls = ShowFor(l);
	Check(!ls.heading && !ls.full && !ls.left && !ls.right, "an empty line shows nothing");
	l.kind = statbook::Line::Kind::Pair;
	ls = ShowFor(l);
	Check(ls.left && !ls.right, "a pair without its right half");
	l.right = true;
	Check(ShowFor(l).right, "a full pair");
	l.kind = statbook::Line::Kind::Heading;
	Check(ShowFor(l).heading && !ShowFor(l).left, "a heading");
}

void TestWindow() {
	std::vector<statbook::ListLine> lines = {{true, "Offense"}, {false, "+20% Enhanced Damage"}, {false, "Adds 1-2 Fire Damage"},
	                                         {true, "Defense"}, {false, "10% Chance to Block"}};
	AllSlot out[3];
	long scroll = 0;
	size_t kept = 0, rows = 0;
	AllWindow(lines, "", &scroll, out, 3, &kept, &rows);
	Check(kept == 5 && rows == 3 && out[0].kind == AllSlot::Kind::Heading && out[1].text == "+20% Enhanced Damage", "no query keeps all");
	Check(out[1].hit.empty() && out[1].pre.empty(), "no highlight without a query");
	scroll = 99;
	AllWindow(lines, "", &scroll, out, 3, &kept, &rows);
	Check(scroll == 2 && out[0].text == "Adds 1-2 Fire Damage" && out[2].text == "10% Chance to Block", "scroll clamped to the end");
	scroll = 0;
	AllWindow(lines, "fire", &scroll, out, 3, &kept, &rows);
	Check(kept == 2 && rows == 1 && out[0].kind == AllSlot::Kind::Heading && out[1].text == "Adds 1-2 Fire Damage" && out[2].kind == AllSlot::Kind::None,
	      "a query keeps its group heading and drops other groups");
	Check(out[1].hit == "Adds 1-2 Fire" && out[1].pre == "Adds 1-2 ", "highlight layers");
	Check(out[1].source == 2, "source index");
	AllWindow(lines, "enhanced", &scroll, out, 3, &kept, &rows);
	Check(out[1].hit == "+20% Enhanced" && out[1].pre == "+20% ", "case-insensitive match");
	AllWindow(lines, "+20", &scroll, out, 3, &kept, &rows);
	Check(out[1].hit == "+20" && out[1].pre.empty(), "a match at 0 has no pre layer");
	Check(RowCount(lines) == 3, "row count");
	Check(ClampScroll(-4, 10, 3) == 0 && ClampScroll(4, 10, 3) == 4 && ClampScroll(9, 10, 3) == 7 && ClampScroll(2, 2, 3) == 0, "clamp");
}

void TestText() {
	Check(Query("  fire  ") == "fire", "query trimmed");
	Check(Query(std::string(40, 'a')).size() == 32, "query at most 32 characters");
	Check(Plain("\xff" "c4Gold\xff" "c0 text") == "Gold text", "colour codes stripped");
	Check(Plain("\xc3\xbf" "c1Red") == "Red", "UTF-8 colour codes stripped");
	Check(Plain("two\nlines") == "two lines", "newlines become spaces");
}

void TestGeometry() {
	const char* json = "{\"pc\": {\"tabs\": [[58, 60, 124, 73], [184, 60, 124, 73]], \"lineRects\": [[63, 318, 1035, 43]], "
	                   "\"allRowRects\": [[63, 398, 990, 40], [63, 438, 990, 40]], \"search\": [300, 330, 500], \"lines\": 22, \"allRows\": 22, "
	                   "\"allColumns\": 1},\n \"pad\": {\"tabs\": [[10, 20, 30, 40]], \"search\": [1, 2, 3, 4], \"lines\": 18, \"allRows\": 20, "
	                   "\"allColumns\": 2}}";
	const Geometry pc = ParseGeometry(json, "pc");
	Check(pc.ok && pc.tabs.size() == 2 && pc.tabs[1].x == 184 && pc.allRowRects.size() == 2 && pc.allRowRects[1].y == 438, "pc rects");
	Check(pc.search.x == 300 && pc.search.w == 500 && pc.search.h == 44 && pc.allRows == 22 && pc.allColumns == 1, "pc search and counts");
	const Geometry pad = ParseGeometry(json, "pad");
	Check(pad.ok && pad.tabs.size() == 1 && pad.search.h == 4 && pad.allColumns == 2 && pad.lineRects.empty(), "pad layout");
	Check(!ParseGeometry(json, "nope").ok && !ParseGeometry("{\"pc\": {\"tabs\": []}}", "pc").ok, "missing layout");
	Check(HitRect(pc.tabs, 60, 61) == 0 && HitRect(pc.tabs, 200, 100) == 1 && HitRect(pc.tabs, 400, 100) == -1 && HitRect(pc.tabs, 184, 61) == 1 &&
	          HitRect(pc.tabs, 182, 61) == -1,
	      "hit rectangles");
	Check(pc.toggle.w == 0 && pad.toggle.w == 0, "no toggle in the layout: none");

	// the side panel: no Character tab (a zero rect), the toggle at the header's right
	const char* side = "{\"side\": {\"tabs\": [[0, 0, 0, 0], [100, 230, 150, 118], [100, 356, 150, 118], [100, 482, 150, 118]], "
	                   "\"allRowRects\": [[262, 306, 890, 40]], \"search\": [262, 228, 890, 70], \"lines\": 22, \"allRows\": 22, "
	                   "\"allColumns\": 1, \"toggle\": [1146, 176, 46, 46]}}";
	const Geometry sg = ParseGeometry(side, "side");
	Check(sg.ok && sg.tabs.size() == 4 && sg.toggle.x == 1146 && sg.toggle.w == 46, "side rects and toggle");
	statbook::Tabs t;
	t.pages = 2;  // tabs 0 (sheet), 1, 2, 3 (All Stats)
	t.current = 1;
	Check(ClickOn(sg, t, 0, 0).kind == ClickHit::Kind::None, "the zero Character tab is never hit");
	Check(ClickOn(sg, t, 110, 360).kind == ClickHit::Kind::Tab && ClickOn(sg, t, 110, 360).index == 2, "side tab 2");
	Check(ClickOn(sg, t, 1150, 180).kind == ClickHit::Kind::Toggle, "toggle");
	Check(ClickOn(sg, t, 300, 310).kind == ClickHit::Kind::None, "rows only on All Stats");
	t.current = 3;
	Check(ClickOn(sg, t, 300, 310).kind == ClickHit::Kind::Row && ClickOn(sg, t, 300, 310).index == 0, "All Stats row");
	Geometry over = sg;
	over.toggle = Rect{100, 230, 20, 20};
	Check(ClickOn(over, t, 105, 235).kind == ClickHit::Kind::Toggle, "the toggle before a tab under it");
	Check(SideTab(0) == 1 && SideTab(-1) == 1 && SideTab(3) == 3, "side tab never 0");
	t.current = 0;
	SideStep(t, 1);
	Check(t.current == 2, "side step from the sheet: from tab 1");
	SideStep(t, 1);
	SideStep(t, 1);
	Check(t.current == 1, "side step wraps past All Stats to tab 1, not the sheet");
	SideStep(t, -1);
	Check(t.current == 3, "side step back wraps to All Stats");
}

// Legacy graphics: the classic layouts' place on the screen and a client pixel in their units.
void TestAdvancedClick() {
	const Geometry g = ParseGeometry("{\"legacy\": {\"tabs\": [[0, 0, 40, 18]], \"lines\": 22, \"allRows\": 21, \"advanced\": [142, 340, 19, 26]}}", "legacy");
	statbook::Tabs t;
	t.pages = 6;
	Check(g.advanced.w == 19 && ClickOn(g, t, 150, 350).kind == ClickHit::Kind::Advanced, "legacy Advanced Stats arrow hit on the Character tab");
	t.current = 2;
	Check(ClickOn(g, t, 150, 350).kind == ClickHit::Kind::None, "no Advanced Stats arrow on a page");
	Check(ClickOn(g, t, 10, 5).kind == ClickHit::Kind::Tab, "tab still hit");
}

void TestShortLabel() {
	Check(ShortLabel("Life Stolen per Hit") == "Life Leech", "short label: leech");
	Check(ShortLabel("Minion Resistances") == "Minion Res.", "short label: whole label, no cut word");
	Check(ShortLabel("Chance to Avoid Damage") == "Avoid Damage", "short label: clean form");
	Check(ShortLabel("Damage to Demons") == "Damage to Demons", "short label: a label that fits is kept");
	Check(ShortLabel("Fire Spell Damage Bonus") == "Fire Spell Damage Bonus", "short label: only whole labels");
}

void TestClassic() {
	const char* json = "{\"legacy\": {\"tabs\": [[0, 0, 40, 24], [40, 0, 60, 24]], \"allRowRects\": [[6, 117, 388, 13]], "
	                   "\"search\": [6, 101, 388, 13], \"lines\": 22, \"allRows\": 21, \"allColumns\": 1, \"toggle\": [34, 54, 22, 22], "
	                   "\"advanced\": [142, 340, 19, 26], \"origin\": [-80, -24]},\n \"legacyside\": {\"tabs\": [[0, 0, 0, 0], [0, 0, 50, 24]], \"lines\": 22, \"allRows\": 21, "
	                   "\"origin\": [320, -24]}}";
	const Geometry lg = ParseGeometry(json, "legacy"), ls = ParseGeometry(json, "legacyside");
	Check(lg.ok && lg.origin.x == -80 && lg.origin.y == -24 && lg.tabs.size() == 2 && lg.toggle.w == 22, "legacy geometry and origin");
	Check(ls.ok && ls.origin.x == 320 && ls.tabs.size() == 2, "legacy side geometry: \"legacy\" does not match \"legacyside\"");
	Check(!ParseGeometry(json, "side").ok, "\"side\" does not match \"legacyside\"");
	Check(ClassicPanelLeft(600) == 80 && ClassicPanelLeft(480) == 0, "the classic left panel's left edge");
	int px = 0, py = 0;
	ClassicPlace(800, 600, lg.origin, &px, &py);
	Check(px == -400 && py == -264, "800 x 600: the wide sheet from x 0, y 36 (the layout's rect)");
	ClassicPlace(1066, 600, lg.origin, &px, &py);
	Check(px == -533 && py == -264, "1066 x 600 (Legacy 16:9): the left panel stays at x 80");
	double ux = 0, uy = 0;
	// 1600 x 900 client, 800 x 600 screen: scale 1.5, 200 pixels of side bar; screen (0, 36) at client (200, 54)
	Check(ClassicUnits(1600, 900, 800, 600, lg.origin, 200, 54, &ux, &uy) && ux > -0.01 && ux < 0.01 && uy > -0.01 && uy < 0.01, "the sheet's corner");
	Check(ClassicUnits(1600, 900, 800, 600, lg.origin, 200 + 45, 54 + 15, &ux, &uy) && HitRect(lg.tabs, ux, uy) == 0, "a tab at 900p");
	Check(ClassicUnits(1920, 1080, 800, 600, lg.origin, 240 + 60 * 9 / 5, 65 + 10 * 9 / 5, &ux, &uy) && HitRect(lg.tabs, ux, uy) == 1, "a tab at 1080p");
	// 2560 x 1440: scale 2.4, 320 of side bar; the side panel's tab 1 (x 400 + 10 of the screen)
	Check(ClassicUnits(2560, 1440, 800, 600, ls.origin, 320 + 410 * 12 / 5, (36 + 10) * 12 / 5, &ux, &uy) && HitRect(ls.tabs, ux, uy) == 1, "a side tab at 1440p");
	// Legacy 16:9 at 1920 x 1080: scale 1.8 (1066 wide fills it), the sheet from screen x 0
	Check(ClassicUnits(1920, 1080, 1066, 600, lg.origin, 5, 65, &ux, &uy) && HitRect(lg.tabs, ux, uy) == 0, "Legacy 16:9: tab 0");
	Check(!ClassicUnits(0, 900, 800, 600, lg.origin, 1, 1, &ux, &uy) && !ClassicUnits(1600, 900, 0, 0, lg.origin, 1, 1, &ux, &uy), "no client or screen");
}

void TestAll() {
	const statbook::Book b = statbook::ParseBook(Sample);
	Check(b.error.empty(), "sample parses");
	Check(TabOfStat(b, 136) == 1 && TabOfStat(b, 40) == 2 && TabOfStat(b, 9999) == -1, "the tab of a stat");
	std::map<int, int> v = {{17, 20}, {338, 0}};
	auto value = [&](uint16_t id) -> int32_t { return v.count(id) ? v[id] : 0; };
	auto statText = [](uint16_t stat, int32_t x) -> std::string { return stat == 17 ? "\xff" "c3+" + std::to_string(x) + "% Enhanced Damage" : ""; };
	auto text = [](const std::string& key, const std::string& english) { return key == "AdvStatsGroupOffense" ? std::string("Angriff") : english; };
	std::vector<statbook::ListLine> lines;
	std::vector<uint16_t> stats;
	AllLines(b, value, statText, text, &lines, &stats);
	Check(lines.size() == 2 && lines[0].heading && lines[0].text == "Angriff" && lines[1].text == "+20% Enhanced Damage", "zero rows and empty groups dropped");
	Check(stats.size() == 2 && stats[1] == 17, "stat per line");
	v[48] = 3;
	v[49] = 7;
	v[17] = 0;
	AllLines(b, value, statText, text, &lines, &stats);
	Check(lines.size() == 2 && lines[1].text == "Adds 3-7 Fire Damage" && stats[1] == 48, "a range row");
	auto noText = [](uint16_t, int32_t) -> std::string { return ""; };
	v[17] = 5;
	AllLines(b, value, noText, text, &lines, &stats);
	Check(lines.size() == 3 && lines[1].text == "stat 17: 5", "fallback text");
}

}  // namespace

int main() {
	TestNames();
	TestShow();
	TestWindow();
	TestText();
	TestGeometry();
	TestClassic();
	TestShortLabel();
	TestAdvancedClick();
	TestAll();
	if (g_failed != 0) {
		std::printf("%d failed\n", g_failed);
		return 1;
	}
	std::printf("sheet host tests passed\n");
	return 0;
}

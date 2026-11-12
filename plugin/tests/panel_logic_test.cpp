// Unit tests of plugin/src/panel_logic.h (the rules the developer menu and the wiki panel share). The search, paging and wrapping are also
// tested through devmenu_test.cpp, which uses them under the developer menu's names.
#include "../src/panel_logic.h"

#include <cstdio>
#include <string>

using namespace panel_logic;

namespace {
int g_fails = 0;

void Check(bool ok, const char* what) {
	if (!ok) {
		std::printf("FAIL: %s\n", what);
		++g_fails;
	}
}

void TestUnits() {
	// HD: 2160 units high whatever the window; a panel at (-1400, -1000) from the centre
	Check(UnitScale(true, 1600, 900) == 900 / 2160.0 && UnitScale(true, 1280, 720) == 720 / 2160.0, "HD scale follows the height");
	Check(UnitScale(false, 1600, 900) == 1.5 && UnitScale(false, 800, 900) == 1.0, "classic: 800 x 600 scaled to fit");
	double x = 0.0, y = 0.0;
	Check(ToPanelUnits(true, 1600, 900, -1400, -1000, 800, 450, &x, &y) && x == 1400.0 && y == 1000.0, "the window's centre is the panel's (1400, 1000)");
	Check(ToPanelUnits(true, 1280, 720, -1400, -1000, 640, 360, &x, &y) && x == 1400.0 && y == 1000.0, "the same at 1280 x 720");
	Check(ToPanelUnits(true, 2160 * 16 / 9, 2160, -1400, -1000, 1920 - 1400, 1080 - 1000, &x, &y) && x == 0.0 && y == 0.0, "the panel's corner at scale 1");
	Check(!ToPanelUnits(true, 0, 900, 0, 0, 1, 1, &x, &y) && !ToPanelUnits(true, 1600, 0, 0, 0, 1, 1, &x, &y), "no client area: no answer");
	// OnBox and ToPanelUnits agree
	Check(OnBox(true, 1600, 900, -1400, -1000, 1300, 900, 200, 200, 800, 450, 0) && !OnBox(true, 1600, 900, -1400, -1000, 0, 0, 100, 100, 800, 450, 0), "OnBox");
}

void TestRectAt() {
	const UnitRect rects[] = {{10, 10, 48, 48}, {10, 62, 48, 48}, {500, 10, 242, 46}};
	Check(RectAt(rects, 3, 20.0, 20.0) == 0 && RectAt(rects, 3, 20.0, 70.0) == 1 && RectAt(rects, 3, 600.0, 30.0) == 2, "inside a rectangle");
	Check(RectAt(rects, 3, 9.0, 20.0) == 0 && RectAt(rects, 3, 20.0, 113.0) == 1, "just outside counts for the nearest");
	Check(RectAt(rects, 3, 20.0, 62.0) == 1, "the top edge of the second is the second's, not the first's margin");
	Check(RectAt(rects, 3, 20.0, 59.0) == 0, "the gap between two goes to the first that reaches it");
	Check(RectAt(rects, 3, 300.0, 300.0) == -1 && RectAt(rects, 0, 20.0, 20.0) == -1, "nowhere");
	Check(RectAt(rects, 3, 3.0, 20.0, 4) == -1 && RectAt(rects, 3, 3.0, 20.0, 8) == 0, "the margin is the caller's");
}

void TestSharedRules() {
	Check(Matches("Staff of Kings", "king STAFF") && !Matches("Staff of Kings", "queen") && Matches("anything", "  "), "word search");
	const Page p = PageOf(45, 9, 22);
	Check(p.pages == 3 && p.page == 2 && p.first == 44 && p.count == 1, "the last page clamps");
	Check(PageOf(0, 0, 22).pages == 1 && PageOf(0, 0, 22).count == 0, "an empty list is one empty page");
	Check(Ellipsize("abcdefghij", 8) == "abcde..." && Ellipsize("abc", 8) == "abc", "a cut line ends in dots");
	Check(TypedKey('A') && TypedKey(0x20) && !TypedKey(0x1B) && !TypedKey(0x7B) && EditingKey(0x08) && !EditingKey('A'), "typed and editing keys");
	const auto f = SplitTabs("a\t\tb");
	Check(f.size() == 3 && f[1].empty() && ToInt("42") == 42 && ToInt("4x", -1) == -1, "tabs and numbers");
}
}  // namespace

int main() {
	TestUnits();
	TestRectAt();
	TestSharedRules();
	if (g_fails == 0) {
		std::printf("panel_logic tests passed\n");
	}
	return g_fails == 0 ? 0 : 1;
}

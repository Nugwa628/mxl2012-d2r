// Unit tests of plugin/src/devmenu_logic.h.
#include "../src/devmenu_logic.h"

#include <cstdio>
#include <string>

using namespace devmenu;

namespace {
int g_fails = 0;

void Check(bool ok, const char* what) {
	if (!ok) {
		std::printf("FAIL: %s\n", what);
		++g_fails;
	}
}

std::string Xline(int cls) {
	std::string s = "X\t" + std::to_string(cls);
	for (int i = 0; i < MaxLevel; ++i) {
		s += "\t" + std::to_string(i * 1000);
	}
	return s;
}

std::string Sample() {
	return "#devmenu\t1\tabc\n"
	       "I\tU\tvip\t7\t0\tAmulet of the Viper\n"
	       "I\tC\ta56\t7\t180\tAzmodan's Heart\tretired row\n"
	       "I\tS\tlrg\t5\t0\tCiverb's Ward (Civerb's Vestments)\n"
	       "I\tQ\tbox\t0\t-1\tHoradric Cube\n"
	       "I\tB\tswd\t0\t-1\tShort Sword\n"
	       "K\tcrs\t2\tr01,r02\tWhite Noise\n"
	       "L\t1\t0\t0\t0\tRogue Encampment\n"
	       "L\t59\t1\t0\t255\tFauztinville\n"
	       "L\t125\t4\t1\t255\tWelcome to Toraja\n" +
	       Xline(0) + "\n" + Xline(4) + "\n";
}
}  // namespace

void TestWrap() {
	const auto chars = [](const std::string& s) { return static_cast<float>(s.size()); };
	Check(Ellipsize("short", 10) == "short", "ellipsize: fits");
	Check(Ellipsize("0123456789", 10) == "0123456789", "ellipsize: exactly fits");
	Check(Ellipsize("0123456789a", 10) == "0123456...", "ellipsize: cut");
	Check(Ellipsize("abc\xC3\xA9" "defgh", 8) == "abc\xC3\xA9" "...", "ellipsize: keeps a whole sequence");
	Check(Ellipsize("ab\xC3\xA9" "defgh", 6) == "ab...", "ellipsize: never inside a sequence");
	Check(WrapText("", 10.0F, 3, chars).empty(), "wrap: empty");
	const auto two = WrapText("aaaa bbbb cccc", 9.0F, 3, chars);
	Check(two.size() == 2 && two[0] == "aaaa bbbb" && two[1] == "cccc", "wrap: two lines");
	const auto cut = WrapText("aaaa bbbb cccc dddd", 4.0F, 2, chars);
	Check(cut.size() == 2 && cut[0] == "aaaa" && cut[1] == "bbbb...", "wrap: cut marks the last line");
	const auto wide = WrapText("aaaaaaaaaa b", 4.0F, 3, chars);
	Check(wide.size() == 2 && wide[0] == "aaaaaaaaaa" && wide[1] == "b", "wrap: a long word keeps its own line");
}

int main() {
	TestWrap();
	const Catalog c = ParseCatalog(Sample());
	Check(c.ok, "catalog parses");
	Check(c.items.size() == 5, "five items");
	Check(c.kits.size() == 1 && c.kits[0].sockets == 2 && c.kits[0].runes.size() == 2, "kit runes");
	Check(c.kits[0].runes[0] == MakeCode("r01", 3), "kit code padded");
	Check(c.levels.size() == 3, "levels");
	Check(c.items[1].tag == "retired row", "tag kept");
	Check(c.items[0].quality == QualityUnique && c.items[0].row == 0, "unique row");
	Check(c.items[2].quality == QualitySet, "set quality");
	Check(c.items[4].quality == QualityNormal && c.items[4].row == -1, "base");
	Check(c.thresholds[0][49] == 49000 && c.thresholds[4][1] == 1000, "experience");
	Check(c.levels[2].note == 1, "map only note");

	Check(!ParseCatalog("").ok, "empty text");
	Check(!ParseCatalog("garbage\n").ok, "no header");
	Check(!ParseCatalog("#devmenu\t9\tabc\nL\t1\t0\t0\t0\tx\nI\tU\tab\t7\t0\ty\n").ok, "wrong format");

	Check(Matches("Horadric Cube", "cube"), "single word");
	Check(Matches("Horadric Cube", "CUBE hor"), "words any order, case");
	Check(!Matches("Horadric Cube", "stone"), "absent word");
	Check(Matches("Horadric Cube", "   "), "blank matches all");

	auto charms = SearchItems(c, Category::Charm, "");
	Check(charms.size() == 1 && !charms[0].kit, "charm filter");
	auto all = SearchItems(c, Category::All, "ward");
	Check(all.size() == 1 && c.items[static_cast<size_t>(all[0].index)].cat == Category::Set, "search in all");
	auto kits = SearchItems(c, Category::Runeword, "white");
	Check(kits.size() == 1 && kits[0].kit, "runeword filter");
	Check(SearchItems(c, Category::All, "").size() == 6, "all rows with kits");
	auto levels = SearchLevels(c, "fauz");
	Check(levels.size() == 1 && c.levels[static_cast<size_t>(levels[0])].id == 59, "level search");
	Check(FindLevel(c, 125) != nullptr && FindLevel(c, 999) == nullptr, "find level");

	Page p = PageOf(25, 0, 12);
	Check(p.pages == 3 && p.count == 12 && p.first == 0, "first page");
	p = PageOf(25, 2, 12);
	Check(p.first == 24 && p.count == 1, "last page");
	p = PageOf(25, 99, 12);
	Check(p.page == 2, "page clamps");
	p = PageOf(0, 0, 12);
	Check(p.pages == 1 && p.count == 0, "empty list");

	GateState g;
	Check(Gate(g) == Refusal::NoCatalog, "no catalog");
	g.catalogOk = true;
	Check(Gate(g) == Refusal::NotInGame, "no game");
	g.inGame = true;
	Check(Gate(g) == Refusal::Joined, "joined client: no local server");
	g.localServer = true;
	Check(Gate(g) == Refusal::Networked, "default: listening assumed, refused");
	g.listening = false;
	Check(Gate(g) == Refusal::Networked, "clients 0: refused");
	g.clients = 2;
	Check(Gate(g) == Refusal::Networked, "two clients: refused");
	g.clients = 1;
	Check(Gate(g) == Refusal::None, "single player passes");
	g.listening = true;
	Check(Gate(g) == Refusal::Networked, "listening socket: refused");
	g.listening = false;
	g.busy = true;
	Check(Gate(g) == Refusal::Busy, "busy");

	Check(CheckRaise(1, 50, 120, true) == Raise::Ok, "raise ok");
	Check(CheckRaise(50, 50, 120, true) == Raise::NotHigher, "same level");
	Check(CheckRaise(60, 50, 120, true) == Raise::NotHigher, "lower refused");
	Check(CheckRaise(1, 121, 120, true) == Raise::TooHigh, "above cap");
	Check(CheckRaise(1, 50, 120, false) == Raise::NoTable, "no table");
	int table[MaxLevel];
	for (int i = 0; i < MaxLevel; ++i) {
		table[i] = i * 1000;
	}
	Check(XpToReach(table, 50, 0) == 49000, "xp from zero");
	Check(XpToReach(table, 50, 49000) == 0, "already there");
	Check(XpToReach(table, 50, 60000) == 0, "past it");
	Check(XpToReach(table, 121, 0) == 0 && XpToReach(table, 0, 0) == 0, "out of range");

	Check(UseNpcTravel(0, 1) && !UseNpcTravel(1, 1), "route");
	Check(ClassOk(0) && ClassOk(7) && !ClassOk(8) && !ClassOk(-1), "class range");

	const auto numbers = WaypointNumbers(c);
	Check(numbers.size() == 1 && numbers[0] == 0, "waypoint numbers skip 255 and duplicates");

	if (g_fails == 0) {
		std::printf("devmenu tests passed\n");
	}
	return g_fails == 0 ? 0 : 1;
}

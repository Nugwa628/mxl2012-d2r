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
	return "#devmenu\t3\tabc\n"
	       "I\tU\tvip\t7\t0\t0\tAmulet of the Viper\n"
	       "I\tC\ta56\t7\t180\t0\tAzmodan's Heart\tretired row\n"
	       "I\tS\tlrg\t5\t0\t0\tCiverb's Ward (Civerb's Vestments)\n"
	       "I\tQ\tbox\t0\t-1\t0\tHoradric Cube\n"
	       "I\tB\tswd\t0\t-1\t2\tShort Sword\n"
	       "K\tcrs\t2\tr01,r02\tWhite Noise\n"
	       "I\tU\tjew\t7\t1803\t0\tCornerstone of the World: Ghost Arrow (Amazon)\n"
	       "I\tU\tjew\t7\t1804\t0\tCornerstone of the World: Barrage (Amazon)\n"
	       "I\tU\tjew\t7\t1960\t0\tCornerstone of the World: Frost Nova (Sorceress)\n"
	       "I\tB\tlrg\t0\t-1\t4\tLarge Shield\n"
	       "I\tU\tswd\t7\t12\t0\tGull\n"
	       "L\t1\t0\t0\t0\tRogue Encampment\n"
	       "L\t59\t1\t0\t255\tFauztinville\n"
	       "L\t125\t4\t1\t255\tWelcome to Toraja\n"
	       "L\t55\t1\t0\t255\tStony Tomb Level 1\n"
	       "L\t111\t4\t0\t31\tFrigid Highlands\n"
	       "L\t115\t4\t0\t34\tGlacial Trail\n"
	       "U\t59\t55\t0\tFauztinville\n"
	       "U\t116\t115\t0\tIsland of the Sunless Sea\n"
	       "U\t125\t111\t1\tWelcome to Toraja\n" +
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
	Check(c.items.size() == 10, "ten items");
	Check(c.kits.size() == 1 && c.kits[0].sockets == 2 && c.kits[0].runes.size() == 2, "kit runes");
	Check(c.kits[0].runes[0] == MakeCode("r01", 3), "kit code padded");
	Check(c.levels.size() == 6, "levels");
	Check(c.ubers.size() == 3 && c.ubers[0].id == 59 && c.ubers[0].entry == 55 && c.ubers[2].how == 1, "uber levels and their entry areas");
	Check(c.items[1].tag == "retired row", "tag kept");
	Check(c.items[0].quality == QualityUnique && c.items[0].row == 0, "unique row");
	Check(c.items[2].quality == QualitySet, "set quality");
	Check(c.items[4].quality == QualityNormal && c.items[4].row == -1, "base");
	Check(c.thresholds[0][49] == 49000 && c.thresholds[4][1] == 1000, "experience");
	Check(c.levels[2].note == 1, "map only note");

	Check(!ParseCatalog("").ok, "empty text");
	Check(!ParseCatalog("garbage\n").ok, "no header");
	Check(!ParseCatalog("#devmenu\t9\tabc\nL\t1\t0\t0\t0\tx\nI\tU\tab\t7\t0\t0\ty\n").ok, "wrong format");
	Check(!ParseCatalog("#devmenu\t1\tabc\nI\tU\tvip\t7\t0\tAmulet of the Viper\nL\t1\t0\t0\t0\tx\n").ok, "format 1 (no socket column) refused");

	// sockets per sample item: a normal weapon and shield get their maximum, a normal item that cannot have sockets none, uniques and sets none
	// asked (their row's own `sock` property decides)
	Check(c.items[4].name == "Short Sword" && c.items[4].sockets == 2 && SpawnSockets(c.items[4]) == 2, "sockets: a normal weapon gets its maximum");
	Check(c.items[8].name == "Large Shield" && SpawnSockets(c.items[8]) == 4, "sockets: a normal armour gets its maximum");
	Check(c.items[3].name == "Horadric Cube" && SpawnSockets(c.items[3]) == 0, "sockets: an item without sockets stays without");
	Check(SpawnSockets(c.items[0]) == 0 && SpawnSockets(c.items[9]) == 0, "sockets: a unique keeps its row's sockets");
	Check(SpawnSockets(c.items[2]) == 0, "sockets: a set item keeps its row's sockets");
	Item odd;
	odd.quality = QualityUnique;
	odd.sockets = 6;
	Check(SpawnSockets(odd) == 0, "sockets: never asked for a unique, whatever the line says");

	// real sockets: identified (an unidentified item's tooltip says "Max Sockets: N"), a count and the socketed flag
	for (uint32_t q : {QualityNormal, QualitySet, QualityUnique}) {
		Check(SpawnIdentified(q), "sockets: every spawned item is created identified");
	}
	Check(SocketsReal(4, 0x82810, 4), "sockets: count, flag and identified (the flag word the item service gave, 0x82800, identified)");
	Check(!SocketsReal(4, 0x82800, 4), "sockets: unidentified is not usable sockets (lane devmenu3's \"Max Sockets: 4\")");
	Check(!SocketsReal(4, ItemFlagIdentified, 4), "sockets: a count without the socketed flag");
	Check(!SocketsReal(4, ItemFlagSocketed | ItemFlagIdentified, 0), "sockets: a flag without a count");
	Check(SocketsReal(6, ItemFlagSocketed | ItemFlagIdentified, 4), "sockets: fewer than asked (capped by the game) still real; the status says n of m");
	Check(SocketsReal(0, 0, 0), "sockets: nothing asked, nothing to check");
	Check(ItemFlagSocketed == 0x800 && ItemFlagIdentified == 0x10 && StatNumSockets == 194, "sockets: D2's flag bits and stat");

	// keys of the focused box
	Check(TypedKey('A') && TypedKey('Z') && TypedKey('0') && TypedKey('9') && TypedKey(0x20), "typed: letters, digits, space");
	Check(TypedKey(0xBD) && TypedKey(0xBE) && TypedKey(0xBF) && TypedKey(0xDE) && TypedKey(0x60) && TypedKey(0x69), "typed: punctuation, numpad digits");
	Check(!TypedKey(0x1B) && !TypedKey(0x7B) && !TypedKey(0x70) && !TypedKey(0x09) && !TypedKey(0x11) && !TypedKey(0x10) && !TypedKey(0x12),
	      "not typed: Esc, F12, F1, Tab, Ctrl, Shift, Alt");
	Check(!TypedKey(0x08) && !TypedKey(0x0D) && !TypedKey(0x25), "not typed: the editing keys go to D2R as keys");
	Check(EditingKey(0x08) && EditingKey(0x0D) && EditingKey(0x25) && EditingKey(0x28) && EditingKey(0x24) && EditingKey(0x23) && EditingKey(0x2E),
	      "editing: Backspace, Enter, arrows, Home, End, Delete");
	Check(!EditingKey(0x1B) && !EditingKey('A') && !EditingKey(0x7B), "not editing: Esc, letters, F12");
	Check(!TypedKey(StandInKey) && !EditingKey(StandInKey), "the stand-in key is neither typed nor editing");

	// a click on the box: HD panel 1162 x 1507 centred, box at (336, 226) 490 x 54; 1600 x 900 client: scale 900 / 2160
	Check(OnBox(true, 1600, 900, -581, -753, 336, 226, 490, 54, 800, 241), "box: the centre of the HD box");
	Check(!OnBox(true, 1600, 900, -581, -753, 336, 226, 490, 54, 800, 300), "box: below it");
	Check(!OnBox(true, 1600, 900, -581, -753, 336, 226, 490, 54, 1200, 241), "box: right of the panel");
	Check(OnBox(true, 2560, 1440, -581, -753, 336, 226, 490, 54, 1280, 386), "box: the centre at 2560 x 1440");
	// classic: panel 640 x 502 at the top of the 800 x 600 screen; a 1600 x 900 client shows it 1.5 times, centred
	Check(OnBox(false, 1600, 900, -320, -298, 104, 64, 300, 26, 800, 3 + 77 * 3 / 2 + 1), "box: the centre of the classic box");
	Check(!OnBox(false, 1600, 900, -320, -298, 104, 64, 300, 26, 800, 450), "box: the classic rows");
	Check(!OnBox(true, 0, 0, -581, -753, 336, 226, 490, 54, 0, 0), "box: no client area");

	Check(Matches("Horadric Cube", "cube"), "single word");
	Check(Matches("Horadric Cube", "CUBE hor"), "words any order, case");
	Check(!Matches("Horadric Cube", "stone"), "absent word");
	Check(Matches("Horadric Cube", "   "), "blank matches all");

	auto charms = SearchItems(c, Category::Charm, "");
	Check(charms.size() == 1 && !charms[0].kit, "charm filter");
	auto all = SearchItems(c, Category::All, "ward");
	Check(all.size() == 1 && c.items[static_cast<size_t>(all[0].index)].cat == Category::Set, "search in all");
	Check(c.items[1].tag == "retired row" && c.items[1].sockets == 0, "tag after the socket column");
	auto kits = SearchItems(c, Category::Runeword, "white");
	Check(kits.size() == 1 && kits[0].kit, "runeword filter");
	Check(SearchItems(c, Category::All, "").size() == 11, "all rows with kits");

	// Cornerstone of the World: one unique row per skill, each listed and found by its skill
	const auto stones = SearchItems(c, Category::All, "cornerstone");
	Check(stones.size() == 3, "cornerstone: one row per skill");
	Check(stones.size() == 3 && c.items[static_cast<size_t>(stones[0].index)].row == 1803 && c.items[static_cast<size_t>(stones[2].index)].row == 1960,
	      "cornerstone: rows keep their own unique row ids");
	const auto bySkill = SearchItems(c, Category::Unique, "frost nova");
	Check(bySkill.size() == 1 && c.items[static_cast<size_t>(bySkill[0].index)].row == 1960, "cornerstone: found by the skill name");
	Check(SearchItems(c, Category::All, "cornerstone amazon").size() == 2, "cornerstone: by class");
	Check(SearchItems(c, Category::All, "barrage cornerstone").size() == 1, "cornerstone: skill and name in any order");
	Check(bySkill.size() == 1 && c.items[static_cast<size_t>(bySkill[0].index)].quality == QualityUnique &&
	          c.items[static_cast<size_t>(bySkill[0].index)].code == MakeCode("jew", 3),
	      "cornerstone: a unique jewel");
	auto levels = SearchLevels(c, "fauz");
	Check(levels.size() == 1 && c.levels[static_cast<size_t>(levels[0])].id == 59, "level search");
	Check(FindLevel(c, 125) != nullptr && FindLevel(c, 999) == nullptr, "find level");

	// uber levels: under their heading, found by name, an arrow goes to the area right before each; the areas follow as before
	const auto fauz = SearchTravel(c, "fauztinville");
	Check(fauz.size() == 4 && fauz[0].kind == TravelRow::Heading && fauz[0].index == 0 && fauz[1].kind == TravelRow::UberLevel &&
	          fauz[2].kind == TravelRow::Heading && fauz[2].index == 1 && fauz[3].kind == TravelRow::Area,
	      "travel: uber heading, uber row, areas heading, the area itself");
	Check(fauz.size() == 4 && c.ubers[static_cast<size_t>(fauz[1].index)].entry == 55, "travel: the uber row goes to Stony Tomb Level 1");
	const auto ubers = SearchTravel(c, "uber");
	Check(ubers.size() == 4 && ubers[0].kind == TravelRow::Heading && ubers[3].kind == TravelRow::UberLevel, "travel: \"uber\" lists them all, no areas");
	const auto sunless = SearchTravel(c, "sunless");
	Check(sunless.size() == 2 && sunless[1].kind == TravelRow::UberLevel, "travel: an uber level found by a word of its name");
	const auto plain = SearchTravel(c, "rogue");
	Check(plain.size() == 1 && plain[0].kind == TravelRow::Area, "travel: no heading without an uber level");
	Check(SearchTravel(c, "").size() == 1 + 3 + 1 + 6, "travel: everything with both headings");
	Check(UberRowText(c, c.ubers[0]) == "Fauztinville (Stony Tomb Level 1)", "uber row: the area in brackets");
	Check(UberRowText(c, c.ubers[2]) == "Welcome to Toraja (Frigid Highlands portal)", "uber row: a red portal");
	Check(UberRowText(c, c.ubers[1]).size() <= 52, "uber row: the longest fits an HD row");
	Check(UberArrivalText(c, c.ubers[0]) == "You arrived in Stony Tomb Level 1, right before Fauztinville: its entrance is in this area.",
	      "uber arrival text");
	Check(UberArrivalText(c, c.ubers[2]).find("red portal") != std::string::npos, "uber arrival: red portal");
	Check(!ParseCatalog("#devmenu\t2\tabc\nI\tU\tvip\t7\t0\t0\tAmulet of the Viper\nL\t1\t0\t0\t0\tx\n").ok, "format 2 refused");

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
	Check(numbers.size() == 3 && numbers[0] == 0 && numbers[1] == 31 && numbers[2] == 34, "waypoint numbers skip 255 and duplicates");

	if (g_fails == 0) {
		std::printf("devmenu tests passed\n");
	}
	return g_fails == 0 ? 0 : 1;
}

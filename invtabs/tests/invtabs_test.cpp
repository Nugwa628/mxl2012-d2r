// Unit tests of invtabs' pure part (src/invtabs_logic.h, src/invtabs_natives.h). No game, no Windows headers.
#include "../src/invtabs_logic.h"
#include "../src/invtabs_natives.h"
#include "../src/layouts.h"

#include <cstdio>
#include <cstring>

namespace {

int failures = 0;

void Check(bool ok, const char* what, int line) {
	if (!ok) {
		++failures;
		std::printf("FAIL line %d: %s\n", line, what);
	}
}
#define CHECK(x) Check((x), #x, __LINE__)

using namespace invtabs;

void Patterns() {
	CHECK(ParsePattern("48 8B ?? 05") == (std::vector<int> { 0x48, 0x8B, -1, 0x05 }));
	CHECK(ParsePattern("48 8b") == (std::vector<int> { 0x48, 0x8B }));
	CHECK(ParsePattern("48 8").empty());
	CHECK(ParsePattern("48 GG").empty());
	CHECK(ParsePattern("488B").empty());
	CHECK(ParsePattern("?? 8B").empty()); // must start with a fixed byte
	const std::uint8_t data[] { 0x90, 0x48, 0x8B, 0x01, 0x05, 0x48, 0x8B, 0x02, 0x06, 0x48, 0x8B, 0x03, 0x05 };
	CHECK(FindPattern(data, sizeof(data), ParsePattern("48 8B ?? 05"), 8) == (std::vector<std::size_t> { 1, 9 }));
	CHECK(!FindUnique(data, sizeof(data), "48 8B ?? 05")); // two matches: not unique
	CHECK(FindUnique(data, sizeof(data), "48 8B ?? 06") == std::optional<std::size_t> { 5 });
	CHECK(!FindUnique(data, sizeof(data), "48 8B ?? 07"));
	CHECK(!FindUnique(data, 4, "48 8B ?? 05")); // runs off the end
	// lea rax, [rip + 0x10] at offset 2: disp at 5, target = 5 + 4 + 0x10
	const std::uint8_t lea[] { 0, 0, 0x48, 0x8D, 0x05, 0x10, 0x00, 0x00, 0x00 };
	CHECK(RipTarget(lea, 5) == 0x19);
	const std::uint8_t back[] { 0x48, 0x8D, 0x05, 0xF0, 0xFF, 0xFF, 0xFF };
	CHECK(RipTarget(back, 3) == 7 - 0x10);
	// every native pattern parses and is long enough to mean something
	for (const auto& native : NativePatterns) {
		const auto p = ParsePattern(native.pattern);
		CHECK(p.size() >= 8);
		CHECK(native.rip < 0 || (native.rip + 4 <= static_cast<int>(p.size()) && p[native.rip] < 0));
	}
}

void Areas() {
	const Area a { 2, 3, 10, 6 };
	CHECK(Inside(a, 2, 3) && Inside(a, 11, 8) && !Inside(a, 12, 8) && !Inside(a, 1, 3));
	CHECK(Inside(a, 10, 7, 2, 2) && !Inside(a, 11, 7, 2, 2));
	CHECK(!Inside(Area {}, 0, 0));
	CHECK(PageToWidget(a, PackCell(4, 5)) == PackCell(2, 2));
	CHECK(PageToWidget(a, PackCell(0, 0)) == PackCell(0, 0)); // outside: unchanged
	CHECK(PageToWidget(a, NoCell) == NoCell);
	CHECK(WidgetToPage(a, PackCell(0, 0), 1, 1) == PackCell(2, 3));
	CHECK(WidgetToPage(a, PackCell(9, 5), 1, 1) == PackCell(11, 8));
	CHECK(WidgetToPage(a, PackCell(9, 5), 1, 2) == NoCell); // a 1 x 2 item would leave the area
	CHECK(WidgetToPage(a, PackCell(10, 0), 1, 1) == NoCell);
	CHECK(CellX(PackCell(7, 13)) == 7 && CellY(PackCell(7, 13)) == 13);

	// The charm tab pinned at 0,0; the others packed around it, largest first.
	std::vector<Area> tabs { { 0, 0, 10, 6 }, { -1, -1, 6, 6 }, { -1, -1, 4, 2 }, { -1, -1, 6, 10 } };
	CHECK(PackAreas(tabs));
	CHECK(tabs[0].x == 0 && tabs[0].y == 0);
	CHECK(tabs[3].x == 10 && tabs[3].y == 0);  // 60 cells, goes first: right of the charms
	CHECK(tabs[1].x == 0 && tabs[1].y == 6);   // 36 cells: under the charms
	CHECK(tabs[2].x == 6 && tabs[2].y == 6);   // 8 cells: next free spot in row 6
	for (std::size_t i = 0; i < tabs.size(); ++i)
		for (std::size_t j = i + 1; j < tabs.size(); ++j) CHECK(!Overlap(tabs[i], tabs[j]));
	CHECK(AreaAt(tabs, 9, 5) == 0 && AreaAt(tabs, 10, 5) == 3 && AreaAt(tabs, 15, 15) == -1);

	// Same input, same places (no saved state needed).
	std::vector<Area> again { { 0, 0, 10, 6 }, { -1, -1, 6, 6 }, { -1, -1, 4, 2 }, { -1, -1, 6, 10 } };
	CHECK(PackAreas(again));
	for (std::size_t i = 0; i < tabs.size(); ++i) CHECK(again[i].x == tabs[i].x && again[i].y == tabs[i].y);

	// Equal size: taller first, then config order.
	std::vector<Area> ties { { -1, -1, 4, 2 }, { -1, -1, 2, 4 }, { -1, -1, 4, 2 } };
	CHECK(PackAreas(ties));
	CHECK(ties[1].x == 0 && ties[1].y == 0 && ties[0].x == 2 && ties[0].y == 0 && ties[2].x == 6 && ties[2].y == 0);

	std::vector<Area> full { { 0, 0, 16, 16 }, { -1, -1, 1, 1 } };
	CHECK(!PackAreas(full));
	std::vector<Area> clash { { 0, 0, 10, 6 }, { 9, 5, 2, 2 } };
	CHECK(!PackAreas(clash));
	std::vector<Area> big { { -1, -1, 17, 1 } };
	CHECK(!PackAreas(big));
	std::vector<Area> offPage { { 10, 0, 10, 6 } };
	CHECK(!PackAreas(offPage));

	// CharmInv 1.0.1's 10 x 4 items all lie in a 10 x 6 charm tab at 0,0.
	const Area charms { 0, 0, 10, 6 };
	for (int y = 0; y < 4; ++y)
		for (int x = 0; x < 10; ++x) CHECK(Inside(charms, x, y));
	CHECK(Inside(charms, 9, 3, 1, 3)); // a grand charm in CharmInv's last column
}

void Marker() {
	CHECK(SlotOfMarker(7400.0f, 7400.0f) == 0);
	CHECK(SlotOfMarker(7405.0f, 7400.0f) == 5);
	CHECK(SlotOfMarker(7412.0f, 7400.0f) == AllSlot);
	CHECK(SlotOfMarker(7413.0f, 7400.0f) == -1);
	CHECK(SlotOfMarker(7402.5f, 7400.0f) == -1);
	CHECK(SlotOfMarker(7302.0f, 7300.0f) == -1); // wild-healer's host marker: not ours
	CHECK(SlotOfMarker(0.0f, 0.0f) == -1);       // a stock grid
}

void Types() {
	const char padded[4] { 'c', 'h', 'a', 'r' };
	const char shortCode[4] { 'm', 'c', 'h', ' ' };
	const char nul[4] { 'a', 'r', 'a', '\0' };
	CHECK(TrimCode(padded) == "char" && TrimCode(shortCode) == "mch" && TrimCode(nul) == "ara");
	const auto charms = CharmFallbackTypes();
	// D2RLoader gives the item's type plus its Equiv parents: a Median grand charm (gcha? -> lcha -> char).
	CHECK(Accepts(charms, { "lcha", "char", "misc" }));
	CHECK(Accepts(charms, { "araa", "char" }));
	CHECK(!Accepts(charms, { "rune", "misc" }));
	CHECK(!Accepts(charms, {}));
	CHECK(Accepts({ "rune", "gem" }, { "gema", "gem" }));
}

void ConfigReader() {
	const auto d = ParseConfig("");
	CHECK(d.enabled && d.inventoryCharms && d.openButton && d.tabs.empty() && d.problems.empty());
	const auto c = ParseConfig("# x\n[invtabs]\nenabled = false # off\ninventory_charms=false\r\nopen_button = true\n\n[tabs.charms]\ncolumns = 12\nrows = 8\nlabel = \"Charms # 1\"\n"
	                           "[tabs.potions]\ncolumns = 4\nrows = 3\nitem_types = [\"hpot\", \"mpot\"]\n[tabs.maps]\ncolumns=2\nrows=2\nx=14\ny=14\n");
	CHECK(!c.enabled && !c.inventoryCharms && c.openButton && c.tabs.size() == 3);
	CHECK(c.tabs[0].name == "charms" && c.tabs[0].columns == 12 && c.tabs[0].rows == 8 && c.tabs[0].label == "Charms # 1" && c.tabs[0].typesFile == "types_charms.txt");
	CHECK(c.tabs[1].types == (std::vector<std::string> { "hpot", "mpot" }) && c.tabs[1].typesFile.empty() && c.tabs[1].label == "potions");
	CHECK(c.tabs[2].x == 14 && c.tabs[2].y == 14 && c.tabs[2].typesFile == "types_maps.txt");
	const auto junk = ParseConfig("[tabs.charms]\ncolumns = ten\nrows = 7x\nenabled\nlabel = Charms\n");
	CHECK(junk.tabs.size() == 1 && junk.tabs[0].columns == 10 && junk.tabs[0].rows == 6 && junk.problems.size() == 3);
	CHECK(!QuotedList("[\"a\", b]") && QuotedList("[]")->empty());
	// the shipped default: the charm tab only
	CHECK(ParseConfig("[tabs.charms]\ncolumns = 10\nrows = 6\ntypes = \"types_charms.txt\"\nlabel = \"Charms\"\n# [tabs.consumables]\n# columns = 6\n").tabs.size() == 1);
}

std::vector<Tab> Wanted(const char* toml) { return ParseConfig(toml).tabs; }

void TabPlan() {
	// fresh: the charm tab first at 0,0 whatever the order, the others packed around it
	auto p = PlanTabs(Wanted("[tabs.potions]\ncolumns=4\nrows=3\nitem_types=[\"hpot\"]\n[tabs.charms]\ncolumns=10\nrows=6\n"), {});
	CHECK(!p.refused && p.tabs.size() == 2 && p.tabs[0].name == "charms" && p.areas[0].x == 0 && p.areas[0].y == 0 && p.areas[0].w == 10);
	CHECK(p.areas[1].x == 10 && p.areas[1].y == 0 && p.areas[1].w == 4 && p.areas[1].h == 3 && p.tabs[1].x == 10);
	// no charm tab given: added; too small: raised to 10 x 4; a big other tab does not take 0,0
	p = PlanTabs(Wanted("[tabs.big]\ncolumns=16\nrows=10\n"), {});
	CHECK(!p.refused && p.tabs[0].name == "charms" && p.areas[0].x == 0 && p.areas[1].y == 6 && p.areas[1].h == 10);
	p = PlanTabs(Wanted("[tabs.charms]\ncolumns=3\nrows=2\n"), {});
	CHECK(!p.refused && p.areas[0].w == 10 && p.areas[0].h == 4);
	// invalid configs fall back to the charm tab alone when nothing is remembered
	for (const char* bad : { "[tabs.charms]\ncolumns=17\n", "[tabs.a]\ncolumns=0\nrows=1\n", "[tabs.a]\ncolumns=1\nrows=1\nx=3\n", "[tabs.a b]\ncolumns=1\nrows=1\n",
	                         "[tabs.a]\ncolumns=1\nrows=1\ntypes=\"../x.txt\"\n", "[tabs.a]\ncolumns=1\nrows=1\nitem_types=[\"toolong\"]\n" }) {
		p = PlanTabs(Wanted(bad), {});
		CHECK(p.refused && p.tabs.size() == 1 && p.tabs[0].name == "charms" && p.areas[0].w == 10 && p.areas[0].h == 6);
	}
	// overlap of explicit places (charm tab 0,0 to 9,5): refused; next to it: fine
	p = PlanTabs(Wanted("[tabs.charms]\n[tabs.a]\ncolumns=2\nrows=2\nx=9\ny=5\n"), {});
	CHECK(p.refused);
	p = PlanTabs(Wanted("[tabs.charms]\n[tabs.a]\ncolumns=2\nrows=2\nx=10\ny=5\n"), {});
	CHECK(!p.refused && p.areas[1].x == 10 && p.areas[1].y == 5);
	// does not fit
	p = PlanTabs(Wanted("[tabs.charms]\ncolumns=16\nrows=16\n[tabs.a]\ncolumns=1\nrows=1\n"), {});
	CHECK(p.refused);

	// remembered: charm tab 10 x 6 with items up to 9,3; potions 4 x 3 at 10,0 with an item at 11,1
	const std::vector<Remembered> mem { { "charms", { 0, 0, 10, 6 }, { 0, 0, 10, 4 } }, { "potions", { 10, 0, 4, 3 }, { 11, 1, 1, 1 } } };
	const auto round = ParseMemory(FormatMemory(mem));
	CHECK(round.size() == 2 && round[1].used.x == 11 && round[1].area.w == 4 && round[0].used.h == 4);
	CHECK(ParseMemory("charms 0 0 10 6 -1 -1 0 0\nbad line\nx 0 0 17 1 -1 -1 0 0\n").size() == 1 && !ParseMemory("charms 0 0 10 6 -1 -1 0 0\n")[0].used.placed());
	// grow: fine, places kept
	p = PlanTabs(Wanted("[tabs.charms]\ncolumns=10\nrows=8\n[tabs.potions]\ncolumns=5\nrows=4\nitem_types=[\"hpot\"]\n"), mem);
	CHECK(!p.refused && p.areas[0].h == 8 && p.areas[1].x == 10 && p.areas[1].w == 5);
	// the charm tab down to 10 x 4: its items (to 9,3) still inside
	p = PlanTabs(Wanted("[tabs.charms]\ncolumns=10\nrows=4\n[tabs.potions]\ncolumns=4\nrows=3\n"), mem);
	CHECK(!p.refused && p.areas[0].h == 4);
	// potions shrunk so 11,1 falls outside: refused, the remembered layout stays (labels from the config)
	p = PlanTabs(Wanted("[tabs.charms]\ncolumns=12\nrows=6\n[tabs.potions]\ncolumns=1\nrows=3\nlabel=\"Pots\"\n"), mem);
	CHECK(p.refused && p.tabs.size() == 2 && p.areas[0].w == 10 && p.areas[1].x == 10 && p.areas[1].w == 4 && p.tabs[1].label == "Pots" && p.tabs[1].columns == 4);
	// a tab that held items removed: refused; an empty one removed: fine
	p = PlanTabs(Wanted("[tabs.charms]\n"), mem);
	CHECK(p.refused && p.tabs.size() == 2 && p.tabs[1].name == "potions" && p.tabs[1].typesFile == "types_potions.txt");
	const std::vector<Remembered> empty2 { { "charms", { 0, 0, 10, 6 }, {} }, { "potions", { 10, 0, 4, 3 }, {} } };
	p = PlanTabs(Wanted("[tabs.charms]\n"), empty2);
	CHECK(!p.refused && p.tabs.size() == 1);
	// a remembered tab keeps its place (toml x, y ignored); growing into a neighbour is refused
	p = PlanTabs(Wanted("[tabs.charms]\n[tabs.potions]\ncolumns=4\nrows=3\nx=0\ny=12\n"), empty2);
	CHECK(!p.refused && p.areas[1].x == 10 && p.areas[1].y == 0);
	p = PlanTabs(Wanted("[tabs.charms]\ncolumns=11\nrows=6\n[tabs.potions]\ncolumns=4\nrows=3\n"), mem);
	CHECK(p.refused && p.areas[0].w == 10);
	// memory after a plan keeps the item boxes by name
	p = PlanTabs(Wanted("[tabs.charms]\n[tabs.potions]\ncolumns=4\nrows=3\n[tabs.maps]\ncolumns=2\nrows=2\n"), mem);
	const auto next = MemoryOf(p, mem);
	CHECK(!p.refused && next.size() == 3 && next[1].used.x == 11 && !next[2].used.placed());
	Area u {};
	AddUsed(u, 3, 2, 1, 1);
	AddUsed(u, 0, 4, 2, 2);
	CHECK(u.x == 0 && u.y == 2 && u.w == 4 && u.h == 4);
}

// What any plan must be, whatever the memory file held: the charm tab first at 0,0 and at least 10 x 4, every tab on the
// page, no two overlapping, at most MaxTabs. (A plan only places tabs: it has no way to move an item.)
bool SafePlan(const Plan& p) {
	if (p.tabs.empty() || p.tabs.size() != p.areas.size() || p.tabs.size() > static_cast<std::size_t>(MaxTabs)) return false;
	if (p.tabs[0].name != CharmTabName || p.areas[0].x != 0 || p.areas[0].y != 0 || p.areas[0].w < MinCharmColumns || p.areas[0].h < MinCharmRows) return false;
	for (std::size_t i = 0; i < p.areas.size(); ++i) {
		const Area& a = p.areas[i];
		if (!a.placed() || a.x < 0 || a.y < 0 || a.x + a.w > PageSize || a.y + a.h > PageSize) return false;
		for (std::size_t j = 0; j < i; ++j) {
			const Area& b = p.areas[j];
			if (a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h) return false;
		}
	}
	return true;
}

// The layout memory file (invtabs-layout.txt): missing, stale, corrupt or written by another character's play can only
// make a config be refused; the plan stays safe either way.
void MemoryFile() {
	const char* configs[] = { "[tabs.charms]\n", "[tabs.charms]\ncolumns=10\nrows=4\n", "[tabs.charms]\n[tabs.potions]\ncolumns=4\nrows=3\n",
		                      "[tabs.potions]\ncolumns=6\nrows=6\n[tabs.maps]\ncolumns=6\nrows=10\n", "[tabs.charms]\ncolumns=16\nrows=16\n", "" };
	const char* files[] = {
		"",                                                                     // missing
		"charms 0 0 10 6 0 0 10 6\npotions 10 0 4 3 10 0 4 3\n",                 // stale: another character filled both
		"\x01\x02garbage\nnot a line\n\n#\n",                                   // corrupt
		"charms 0 0 10 6 0 0 1 1\ncharms 0 0 10 6 9 5 1 1\n",                    // the same tab twice
		"charms 3 3 10 6 -1 -1 0 0\n",                                          // charm tab not at 0,0
		"charms 0 0 10 6 -1 -1 0 0\na 8 0 4 4 8 0 1 1\n",                       // overlapping
		"charms 0 0 10 6 12 12 1 1\n",                                          // a reach outside its tab
		"charms 0 0 10 6 0 0 1 1\nx 0 0 99 99 0 0 1 1\ny -5 0 1 1 -1 -1 0 0\nz 0 0 0 0 0 0 0 0\n", // out of range
		"charms 0 0 10 6 0 0 1 1\na 10 0 1 1 10 0 1 1\nb 11 0 1 1 11 0 1 1\nc 12 0 1 1 12 0 1 1\nd 13 0 1 1 13 0 1 1\ne 14 0 1 1 14 0 1 1\n"
		"f 15 0 1 1 15 0 1 1\ng 10 1 1 1 10 1 1 1\nh 11 1 1 1 11 1 1 1\ni 12 1 1 1 12 1 1 1\nj 13 1 1 1 13 1 1 1\nk 14 1 1 1 14 1 1 1\nl 15 1 1 1 15 1 1 1\n", // 13 tabs
	};
	for (const char* file : files)
		for (const char* config : configs) {
			const auto memory = ParseMemory(file);
			const auto p      = PlanTabs(Wanted(config), memory);
			CHECK(SafePlan(p));
			CHECK(SafePlan(PlanTabs(Wanted(config), MemoryOf(p, memory)))); // and once more from what it would write
		}
	// missing: the config as it is
	auto p = PlanTabs(Wanted("[tabs.charms]\ncolumns=10\nrows=4\n"), ParseMemory(""));
	CHECK(!p.refused && p.areas[0].h == 4);
	// stale or another character's reach: the shrink is refused, nothing else changes
	p = PlanTabs(Wanted("[tabs.charms]\ncolumns=10\nrows=4\n"), ParseMemory("charms 0 0 10 6 0 0 1 6\n"));
	CHECK(p.refused && p.areas[0].h == 6);
	// reach only grows: two characters' items add up, neither can take the other's out
	Area reach {};
	AddUsed(reach, 0, 5, 1, 1); // character A (save folder 1)
	AddUsed(reach, 0, 0, 1, 1); // character B of the same name (save folder 2)
	CHECK(reach.y == 0 && reach.h == 6);
	// garbage lines are dropped one by one; a usable remembered layout survives them
	CHECK(ParseMemory("charms 0 0 10 6 -1 -1 0 0\n\x7f\xff\npotions 10 0 4 3 -1 -1 0 0 extra\n").size() == 1);
	CHECK(ParseMemory("charms 0 0 10 6 12 12 1 1\n")[0].used.placed()); // kept: it refuses, never moves
}

} // namespace

bool Balanced(const std::string& j) {
	int  depth = 0;
	bool str   = false;
	for (std::size_t i = 0; i < j.size(); ++i) {
		const char c = j[i];
		if (str) {
			if (c == '\\') ++i;
			else if (c == '"') str = false;
			continue;
		}
		if (c == '"') str = true;
		else if (c == '{' || c == '[') ++depth;
		else if (c == '}' || c == ']') {
			if (--depth < 0) return false;
		}
	}
	return depth == 0 && !str;
}

void Layouts() {
	namespace L = invtabs::layout;
	CHECK(ClassicMarker(7401.0f) && !ClassicMarker(7400.0f) && SlotOfMarker(7403.0f, 7401.0f) == 3 && SlotOfMarker(7403.0f, 7402.0f) == -1);
	// sprite round trip
	L::Picture p = L::Blank(3, 2);
	for (std::size_t i = 0; i < p.rgba.size(); ++i) p.rgba[i] = static_cast<unsigned char>(i * 7);
	const auto back = L::ParseSprite(L::SpriteFile({ p, p }));
	CHECK(back && back->width == 3 && back->height == 2 && back->rgba == p.rgba);
	CHECK(!L::ParseSprite("SpA1") && !L::ParseSprite(std::string(64, 'x')));
	CHECK(L::Resize(p, 3, 2).rgba == p.rgba && L::Half(L::Blank(10, 6)).width == 5);
	// the stock grid: 10 x 10 re-tiled is the stock itself; a smaller grid takes the stock's edges
	L::Picture stock = L::Blank(L::StockSize, L::StockSize);
	for (int y = 0; y < stock.height; ++y)
		for (int x = 0; x < stock.width; ++x) stock.at(x, y)[0] = static_cast<unsigned char>(x * 3 + y), stock.at(x, y)[1] = static_cast<unsigned char>(y), stock.at(x, y)[3] = 255;
	CHECK(L::TileStockGrid(stock, 10, 10).rgba == stock.rgba);
	const auto small = L::TileStockGrid(stock, 4, 3);
	CHECK(small.width == 4 * 98 + 16 && small.height == 3 * 98 + 16);
	CHECK(std::memcmp(small.at(0, 0), stock.at(0, 0), 4) == 0);                                   // top-left frame
	CHECK(std::memcmp(small.at(small.width - 1, small.height - 1), stock.at(L::StockSize - 1, L::StockSize - 1), 4) == 0); // bottom-right frame
	CHECK(std::memcmp(small.at(8 + 3 * 98 + 5, 8 + 2 * 98 + 5), stock.at(8 + 9 * 98 + 5, 8 + 9 * 98 + 5), 4) == 0);         // last cell = the stock's last
	CHECK(std::memcmp(small.at(8 + 98 + 5, 8 + 5), stock.at(8 + 98 + 5, 8 + 5), 4) == 0);                                  // an inner cell
	const auto wide = L::TileStockGrid(stock, 16, 2);
	CHECK(std::memcmp(wide.at(8 + 10 * 98 + 7, 8 + 7), stock.at(8 + 2 * 98 + 7, 8 + 7), 4) == 0); // columns past the stock repeat its inner ones
	CHECK(L::GridPicture(nullptr, 2, 2, 98).width == 2 * 98 + 16 && L::GridPicture(&stock, 16, 16, 61).width == 16 * 61 + 2 * 4);
	// HD geometry: the stock 10 x 6 charm tab keeps D2R's 98 px cells under the stash's columns, the summary band above
	auto g = L::HdLayoutOf(10, 6, 1, true);
	CHECK(g.cell == 98 && g.grid.x == 89 && g.grid.w == 980 && g.grid.y + g.grid.h == L::HdGridBottom && g.tabRows == 0);
	CHECK(g.band.y == L::HdContentTop && g.band.h >= L::HdSummaryMin && g.band.y + g.band.h + L::HdBandGap + g.frame == g.grid.y);
	g = L::HdLayoutOf(4, 3, 2, false);
	CHECK(g.cell == 98 && g.tabRows == 1 && g.grid.x == 89 + (980 - 392) / 2 && g.band.h == 0);
	g = L::HdLayoutOf(16, 16, 1, false);
	CHECK(g.cell == 61 && g.grid.w == 976 && g.grid.y >= L::HdContentTop);
	g = L::HdLayoutOf(10, 12, 12, true);
	CHECK(g.tabRows == 3 && g.band.h >= L::HdSummaryMin && g.grid.y - g.frame - L::HdBandGap - g.band.h == g.band.y);
	const std::vector<L::TabRef> refs { { "invtabs/Charms", "Charms" }, { "invtabs/Potions", "Pots \"x\"" } };
	const auto hd = L::HdPanel(refs, 1, 1, 4, 3, L::HdLayoutOf(4, 3, 2, false), "d2rloader\\invtabs\\cells1", "", "Pots");
	CHECK(Balanced(hd) && hd.find("\"invtabs/Potions\"") != std::string::npos && hd.find("PANEL\\\\panel_bg") != std::string::npos);
	CHECK(hd.find("PanelManager:OpenPanel:invtabs/Charms") != std::string::npos && hd.find("PanelManager:OpenPanel:invtabs/Potions") == std::string::npos);
	// D2RLoader refuses a plugin layout whose text references have no namespace (@d2r: or @invtabs:)
	for (std::size_t at = hd.find("\"@"); at != std::string::npos; at = hd.find("\"@", at + 1))
		CHECK(hd.compare(at + 2, 4, "d2r:") == 0 || hd.compare(at + 2, 8, "invtabs:") == 0);
	CHECK(hd.find("\"x\": 7401, \"y\": 7400") != std::string::npos && hd.find("Pots \\\"x\\\"") != std::string::npos);
	// the cell size is a struct field of the grid: the stock size by its profile name, any other size as x / y (a bare
	// number made the game assert and the whole-page view did not open)
	CHECK(hd.find("\"cellSize\": \"$ItemCellSize\"") != std::string::npos);
	const auto all = L::HdPanel({ { "invtabs/All", "Player page" } }, 0, 99, 16, 16, L::HdLayoutOf(16, 16, 1, false), "d2rloader\\invtabs\\cells99", "", "All");
	CHECK(Balanced(all) && all.find("\"cellSize\": {\"x\": 61, \"y\": 61}") != std::string::npos);
	// classic geometry = tools/invtabs_legacy.py geometry --grid 10x6
	const auto cg = L::ClassicGrid(10, 6);
	CHECK(cg.x == 16 && cg.y == 198 && L::ClassicTabRowY(6) == 168);
	const auto box = L::ClassicSummaryBox(6), text = L::ClassicSummaryText(6);
	CHECK(box.x == 20 && box.y == 86 && box.x + box.w == 302 && box.y + box.h == 164 && text.h == 5 * 12);
	CHECK(L::ClassicFits(10, 7) && !L::ClassicFits(10, 8) && !L::ClassicFits(11, 2) && L::ClassicFits(4, 3));
	const auto classic = L::ClassicPanel({ { "invtabs/Charms", "Charms", "charms" } }, 0, 0, 10, 6, "");
	CHECK(Balanced(classic) && classic.find("PANEL\\\\invtabs_charms") != std::string::npos && classic.find("\"x\": 7400, \"y\": 7401") != std::string::npos);
}

int main() {
	Patterns();
	Areas();
	Marker();
	Types();
	ConfigReader();
	TabPlan();
	MemoryFile();
	Layouts();
	if (failures) {
		std::printf("%d check(s) failed\n", failures);
		return 1;
	}
	std::printf("invtabs_tests: all checks passed\n");
	return 0;
}

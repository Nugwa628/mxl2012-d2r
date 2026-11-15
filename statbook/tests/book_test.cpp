// Unit tests of the Stat Book's pure part (src/book_logic.h) and of the plain D2R book compiled into the plugin.
#include "../src/book_logic.h"

#include <cstdio>
#include <map>
#include <string>
#include <utility>

using namespace statbook;

namespace {

int g_failed = 0;

void Check(bool ok, const char* what) {
	if (!ok) {
		std::printf("FAIL: %s\n", what);
		++g_failed;
	}
}

constexpr const char* DefaultBook =
#include "../src/default_book.inc"
	;

const char* const Sample =
	"statbook\t1\n"
	"page\toffense\tOffense\n"
	"section\tDamage\n"
	"row\tEnhanced Damage\t17\t%+d%%\tw\t-\t-\th\n"
	"row\tAttack Rating\t119\t%+d%%\tw\t-\t-\th\n"
	"row\tAdds Fire Damage\t48,49\t%d-%d\tr\t-\t-\tf\n"
	"row\tCrushing Blow\t136\t%d%%\tw\t-\t-\th\n"
	"section\tOther\n"
	"row\tIgnore Target's Defense\t115\tyesno\tw\t-\t-\th\n"
	"page\tresist\tResistances\n"
	"section\tResistances\n"
	"row\tFire Resistance\t39,40\t%d%% (max %d%%)\tr\t75+40<=95\t0,75\tf\n"
	"row\tPhysical Resistance\t36\t%d%% (max 50%%)\tw\t50\t-\tf\n"
	"row\tClass Skill Levels\t83:c\t%+d\tblue\t-\t-\th\n"
	"group\tAdvStatsGroupOffense\tOffense\n"
	"all\tstat\t17\t-\t-\n"
	"all\trange\t48,49\tAdvStatsAddsFire\tAdds %d-%d Fire Damage\n"
	"group\tAdvStatsGroupDefense\tDefense\n"
	"all\tavoid\t338,339,340\t-\t-\n";

struct Stats {
	std::map<std::pair<int, bool>, int> v;
	auto operator()(uint16_t id, bool cls) const -> int32_t {
		auto it = v.find({id, cls});
		return it == v.end() ? 0 : it->second;
	}
};

void TestParse() {
	const Book b = ParseBook(Sample);
	Check(b.error.empty(), "sample parses");
	Check(b.pages.size() == 2 && b.pages[0].title == "Offense" && b.pages[1].id == "resist", "two pages");
	Check(b.pages[0].sections.size() == 2 && b.pages[0].sections[0].rows.size() == 4, "sections and rows");
	const Row& fire = b.pages[1].sections[0].rows[0];
	Check(fire.stats == 2 && fire.stat[0].id == 39 && fire.stat[1].id == 40 && fire.base[1] == 75, "range row with base");
	Check(fire.capBase == 75 && fire.capStat == 40 && fire.capMax == 95, "cap with a stat");
	Check(b.pages[1].sections[0].rows[2].stat[0].classParam, "class param");
	Check(b.all.size() == 2 && b.all[0].rows.size() == 2 && b.all[1].rows[0].kind == AllKind::Avoid && b.all[1].rows[0].stats == 3,
	      "all stats groups");
	Check(!ParseBook("nope\n").error.empty(), "not a book");
	Check(!ParseBook("statbook\t1\nrow\ta\t1\t%d\tw\t-\t-\th\n").error.empty(), "row before a section");
	Check(!ParseBook("statbook\t1\npage\ta\tA\nsection\tS\nrow\ta\t1\t%d\tpink\t-\t-\th\n").error.empty(), "bad colour");
	Check(!ParseBook("statbook\t1\npage\ta\tA\nsection\tS\nrow\ta\t1,2,3\t%d\tw\t-\t-\th\n").error.empty(), "three stats");
	Check(ParseBook("statbook\t1\r\npage\ta\tA\r\n").error.empty(), "CRLF lines");
}

void TestFill() {
	const int32_t v[2] = {12, -3};
	Check(Fill("%+d%%", v, 1) == "+12%", "plus percent");
	Check(Fill("%d-%d", v, 2) == "12--3", "two values");
	Check(Fill("%+d", v + 1, 1) == "-3", "negative with plus");
	Check(Fill("%d %d", v, 1) == "12 0", "missing value is 0");
	Check(Fill("%s %x %", v, 1) == "%s %x %", "other tokens stay text");
}

void TestRows() {
	const Book b = ParseBook(Sample);
	Stats s;
	const Row& ed = b.pages[0].sections[0].rows[0];
	Check(FillRow(ed, s).value == "+0%" && FillRow(ed, s).tone == Tone::Grey, "zero is grey");
	s.v[{17, false}] = 486;
	Check(FillRow(ed, s).value == "+486%" && FillRow(ed, s).tone == Tone::White, "value in its colour");
	s.v[{17, false}] = -20;
	Check(FillRow(ed, s).tone == Tone::Red, "negative is red");
	const Row& fire = b.pages[1].sections[0].rows[0];
	s.v[{39, false}] = 80;
	Check(FillRow(fire, s).value == "80% (max 75%)" && FillRow(fire, s).tone == Tone::Gold, "at the cap: gold");
	s.v[{40, false}] = 10;
	Check(FillRow(fire, s).value == "80% (max 85%)" && FillRow(fire, s).tone == Tone::Red,
	      "under a raised cap: its colour");
	s.v[{40, false}] = 40;  // 75 + 40 is over 95: the cap stays 95
	s.v[{39, false}] = 95;
	Check(FillRow(fire, s).tone == Tone::Gold, "cap at most 95");
	const Row& phys = b.pages[1].sections[0].rows[1];
	s.v[{36, false}] = 50;
	Check(FillRow(phys, s).value == "50% (max 50%)" && FillRow(phys, s).tone == Tone::Gold, "physical cap 50");
	s.v[{36, false}] = -5;
	Check(FillRow(phys, s).tone == Tone::Red, "negative resistance red");
	const Row& cls = b.pages[1].sections[0].rows[2];
	s.v[{83, true}] = 2;
	Check(FillRow(cls, s).value == "+2" && FillRow(cls, s).tone == Tone::ItemBlue, "class param asked as such");
	const Row& yes = b.pages[0].sections[1].rows[0];
	Check(FillRow(yes, s).value == "no", "yesno: no");
	s.v[{115, false}] = 1;
	Check(FillRow(yes, s).value == "yes", "yesno: yes");
	const Book blockBook = ParseBook("statbook\t1\npage\td\tD\nsection\tS\nrow\tChance to Block\t20\tblock\tw\t-\t-\th\n");
	Check(blockBook.error.empty(), "block row parses");
	s.v[{20, false}] = 40;
	s.v[{BlockRateStat, false}] = 61;
	Check(FillRow(blockBook.pages[0].sections[0].rows[0], s).value == "61%", "block: the host's rate, not the stat");
}

void TestLines() {
	const Book b = ParseBook(Sample);
	Stats s;
	Line lines[20];
	const size_t n = PageLines(b.pages[0], s, 0, lines, 20);
	// Damage heading, ED|AR pair, Adds Fire full, Crushing Blow half alone, Other heading, Ignore half alone
	Check(n == 6, "line count");
	Check(lines[0].kind == Line::Kind::Heading && lines[0].heading == "Damage", "heading first");
	Check(lines[1].kind == Line::Kind::Pair && lines[1].right && lines[1].cell[1].label == "Attack Rating", "two halves on a line");
	Check(lines[2].kind == Line::Kind::Full && lines[2].cell[0].label == "Adds Fire Damage", "full line");
	Check(lines[3].kind == Line::Kind::Pair && !lines[3].right, "a half alone before a heading");
	Check(lines[6].kind == Line::Kind::Empty, "lines past the page are empty");
	Line two[2];
	Check(PageLines(b.pages[0], s, 4, two, 2) == 6 && two[0].heading == "Other", "scrolled view");
}

void TestSearch() {
	const std::vector<ListLine> list = {{true, "- Offense -"},        {false, "+486% Enhanced Damage"}, {false, "Adds 1-20 Fire Damage"},
	                                    {true, "- Resistances -"},    {false, "Fire Resist +40%"},      {false, "Cold Resist +10%"},
	                                    {true, "- Other -"},          {false, "Magic Find 100%"}};
	Shown s[16];
	size_t n = Search(list, "", s, 16);
	Check(n == list.size(), "empty query keeps all");
	n = Search(list, "FIRE", s, 16);
	Check(n == 4 && s[0].index == 0 && s[1].index == 2 && s[2].index == 3 && s[3].index == 4, "matches under their headings");
	Check(s[1].match == 10 && s[1].length == 4, "match position, case ignored");
	n = Search(list, "resist", s, 16);
	Check(n == 3 && s[1].index == 4 && s[2].index == 5, "a group by its rows");
	n = Search(list, "other", s, 16);
	Check(n == 2 && s[1].index == 7 && s[1].match == std::string::npos, "a heading keeps its group");
	Check(Search(list, "zzz", s, 16) == 0, "nothing found");
	Check(Search(list, "", s, 3) == 3, "capped");
}

void TestTabs() {
	Tabs t;
	t.pages = 6;
	Check(t.Count() == 8 && t.AllStats() == 7 && t.IsSheet() && t.Page() == -1, "sheet first");
	t.Select(3);
	Check(t.Page() == 2, "page index");
	t.Step(5);
	Check(t.current == 0, "wraps forward");
	t.Step(-1);
	Check(t.current == 7 && t.Page() == -1, "wraps back to All Stats");
	t.Select(99);
	Check(t.current == 7, "out of range ignored");
}

void TestDefaultBook() {
	const Book b = ParseBook(DefaultBook);
	Check(b.error.empty(), "the plain D2R book parses");
	Check(b.pages.size() >= 5 && !b.all.empty(), "the plain D2R book has pages and All Stats");
	for (const Page& p : b.pages) {
		for (const Section& s : p.sections) {
			Check(!s.rows.empty(), "no empty section");
			for (const Row& r : s.rows) {
				Check(r.stat[0].id < 359, "plain D2R book holds D2R stats only");
			}
		}
	}
}

}  // namespace

int main() {
	TestParse();
	TestFill();
	TestRows();
	TestLines();
	TestSearch();
	TestTabs();
	TestDefaultBook();
	if (g_failed == 0) {
		std::printf("statbook book tests: all passed\n");
	}
	return g_failed == 0 ? 0 : 1;
}

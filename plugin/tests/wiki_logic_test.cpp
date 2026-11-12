// Unit tests of plugin/src/wiki_logic.h.
#include "../src/wiki_logic.h"

#include <chrono>
#include <cstdio>
#include <string>

using namespace wiki_logic;

namespace {
int g_fails = 0;

void Check(bool ok, const char* what) {
	if (!ok) {
		std::printf("FAIL: %s\n", what);
		++g_fails;
	}
}

// Invented content: three categories, six entries.
std::string Sample() {
	return "V\t1\n"
	       "C\tuniq\tUniques\n"
	       "C\tset\tSets\n"
	       "C\tpage\tPages\n"
	       "E\tuniq\tFrost Lantern\tUnique Charm, level 40\tfrost lantern charm +5 to cold skills cold resist\n"
	       "L\tgold\tFrost Lantern\n"
	       "L\tgrey\tCharm\n"
	       "L\tblue\t+5 to Cold Skills\n"
	       "L\twhite\t\n"
	       "L\tblue\tCold Resist +20%\n"
	       "K\tWinter Garb\n"
	       "K\tnobody here\n"
	       "K\tfrost lantern\n"
	       "E\tuniq\tLantern of Embers\tUnique Lamp, level 12\tlantern of embers lamp fire damage\n"
	       "L\tgold\tLantern of Embers\n"
	       "E\tuniq\tAshen Crown\tUnique Helm, level 70\tashen crown helm frost lantern socket\n"
	       "L\tgold\tAshen Crown\n"
	       "E\tset\tWinter Garb\tSet Armor, level 30\twinter garb armor frost cold\n"
	       "L\tgreen\tWinter Garb\n"
	       "K\tFrost Lantern\n"
	       "E\tset\twinter garb\tSet Gloves, level 31\twinter garb gloves\n"
	       "L\tgreen\twinter garb\n"
	       "E\tpage\tGetting Going\tPage\tgetting going first steps caf\xC3\xA9 r\xC3\xA9sum\xC3\xA9\n"
	       "L\tgold\tFirst steps\n"
	       "L\twhite\tA caf\xC3\xA9 r\xC3\xA9sum\xC3\xA9 with words to wrap.\n";
}

void TestParse() {
	const Table t = ParseTable(Sample());
	Check(t.ok && t.error.empty(), "sample parses");
	Check(t.format == 1, "format number");
	Check(t.categories.size() == 3 && t.categories[1].id == "set" && t.categories[1].label == "Sets", "categories in order");
	Check(t.entries.size() == 6, "six entries");
	Check(t.unknownKinds == 0 && t.badLines == 0 && t.unknownColours == 0 && t.problem.empty(), "a clean table has no problems");
	const Entry& e = t.entries[0];
	Check(e.name == "Frost Lantern" && e.subtitle == "Unique Charm, level 40" && e.category == 0, "entry fields");
	Check(e.folded == "frost lantern", "folded name");
	Check(e.lines.size() == 5 && e.lines[0].colour == Colour::Gold && e.lines[1].colour == Colour::Grey && e.lines[2].colour == Colour::Blue,
	      "line colours");
	Check(e.lines[3].text.empty() && e.lines[3].colour == Colour::White, "empty L text is a blank line");
	Check(e.links.size() == 3 && e.links[0] == "Winter Garb", "links");
	Check(t.entries[3].category == 1 && t.entries[5].category == 2, "entry categories");
	Check(CategoryIndex(t, "page") == 2 && CategoryIndex(t, "nope") == NotFound, "category index");

	// byte order mark and CRLF
	std::string crlf = "\xEF\xBB\xBF";
	for (char ch : Sample()) {
		if (ch == '\n') {
			crlf += '\r';
		}
		crlf += ch;
	}
	const Table c = ParseTable(crlf);
	Check(c.ok && c.entries.size() == 6 && c.badLines == 0 && c.unknownKinds == 0, "BOM and CRLF");
	Check(c.entries[0].lines[4].text == "Cold Resist +20%" && c.entries[0].links[2] == "frost lantern", "CRLF: no stray carriage return");
	Check(ParseTable("V\t1\nC\ta\tA\nE\ta\tX\tx\tx\nL\tgold\tlast line without LF").entries[0].lines[0].text == "last line without LF",
	      "last line without a line feed");

	// the format line
	Check(!ParseTable("").ok && ParseTable("").error == "no format line", "empty text");
	Check(!ParseTable("\n\n").ok, "blank lines only");
	Check(ParseTable("C\ta\tA\nV\t1\n").error == "no format line", "V must come first");
	Check(ParseTable("V\t2\nC\ta\tA\nE\ta\tX\tx\tx\n").error == "unknown table format 2", "format 2 refused");
	Check(!ParseTable("V\tone\nC\ta\tA\nE\ta\tX\tx\tx\n").ok, "format not a number");
	Check(!ParseTable("V\t1\textra\nC\ta\tA\nE\ta\tX\tx\tx\n").ok, "V field count");
	Check(ParseTable("\n\xEF\xBB\xBFV\t1\n").error == "no format line", "a BOM only counts at the very start");

	// unusable tables
	Check(ParseTable("V\t1\n").error == "no categories", "no categories");
	Check(ParseTable("V\t1\nC\ta\tA\n").error == "no entries", "no entries");
	Check(ParseTable("V\t1\nE\ta\tX\tx\tx\n").error == "no categories", "entries without categories");

	// malformed lines: skipped, counted, the first one named
	const Table m = ParseTable("V\t1\n"
	                           "L\tgold\tbefore any entry\n"      // 2: L before E
	                           "K\tSomewhere\n"                   // 3: K before E
	                           "C\ta\tAlpha\n"
	                           "C\ta\tAgain\n"                    // 5: duplicate category
	                           "C\tb\n"                           // 6: C field count
	                           "Z\twhat\n"                        // 7: unknown kind
	                           "E\ta\tOne\tsub\tone\n"
	                           "L\tmauve\tOdd colour\n"           // unknown colour, kept as white
	                           "L\tgold\ttoo\tmany\n"             // 10: L field count
	                           "L\tgold\n"                        // 11: L without its text field
	                           "E\tzz\tTwo\tsub\ttwo\n"           // 12: undeclared category
	                           "L\tgold\tbelongs to Two\n"        // 13: no entry (Two was skipped)
	                           "K\tOne\n"                         // 14: no entry
	                           "E\ta\tThree\tsub\n"               // 15: E field count
	                           "E\ta\t\tsub\tempty name\n"        // 16: empty name
	                           "#\tcomment\n"                     // 17: unknown kind
	                           "V\t1\n"                           // 18: second V
	                           "E\ta\tFour\tsub\tfour\n"
	                           "K\t\n"                            // 20: empty K target
	                           "K\tOne\textra\n"                  // 21: K field count
	                           "K\tOne\n");
	Check(m.ok, "malformed lines do not make a usable table unusable");
	Check(m.entries.size() == 2 && m.entries[0].name == "One" && m.entries[1].name == "Four", "only the good entries");
	Check(m.categories.size() == 1, "a duplicate or broken C is skipped");
	Check(m.unknownKinds == 2, "unknown kinds counted");
	Check(m.badLines == 14, "bad lines counted");
	Check(m.unknownColours == 1, "unknown colour counted");
	Check(m.problem == "line 2: L without an entry", "the first problem with its line number");
	Check(m.entries[0].lines.size() == 1 && m.entries[0].lines[0].colour == Colour::White && m.entries[0].lines[0].text == "Odd colour",
	      "unknown colour reads as white");
	Check(m.entries[1].links.size() == 1 && m.entries[1].links[0] == "One", "a good K after bad ones");
	Check(ParseTable("V\t1\nC\ta\tA\nE\ta\tX\tx\tx\nL\tpink\ty\n").problem == "line 4: unknown colour", "unknown colour is the first problem");
	Check(ParseTable("V\t1\nC\ta\tA\nQ\nE\ta\tX\tx\tx\n").problem == "line 3: unknown line kind", "unknown kind problem text");
	Check(ParseTable("V\t1\nC\ta\tA\nE\tb\tX\tx\tx\n").error == "no entries", "only bad entries: unusable");

	// garbage never crashes
	std::string junk;
	for (int i = 0; i < 4000; ++i) {
		junk += static_cast<char>((i * 7919 + 13) % 256);
	}
	const Table g = ParseTable(junk);
	Check(!g.ok, "garbage is unusable");
	Check(!ParseTable("V\t1\n\t\t\t\n\t\nE\nL\nK\nC\n").ok, "empty fields everywhere");
}

void TestColours() {
	const char* names[] = {"white", "grey", "blue", "gold", "green", "orange", "red", "yellow", "purple", "tan"};
	for (int i = 0; i < ColourCount; ++i) {
		bool known = false;
		Check(ColourOf(names[i], &known) == static_cast<Colour>(i) && known, "every colour name");
	}
	bool known = true;
	Check(ColourOf("Gold", &known) == Colour::White && !known, "colour names are lower case");
	Check(ColourOf("", &known) == Colour::White && !known, "empty colour");
	Check(ColourOf("tan") == Colour::Tan, "without the known flag");
}

void TestSearch() {
	const Table t = ParseTable(Sample());
	const auto ids = [&](std::string_view q, int cat = AllCategories) { return Search(t, q, cat); };
	Check(ids("").size() == 6, "empty query lists everything");
	Check(ids("   ").size() == 6, "blank query lists everything");
	Check(ids("", 1) == std::vector<int>({3, 4}), "empty query lists the category");
	Check(ids("dragon").empty(), "no match");
	Check(ids("COLD skills") == std::vector<int>({0}), "query is lower cased, words in any order");
	Check(ids("skills cold") == std::vector<int>({0}), "words in any order");
	Check(ids("cold\tresist") == std::vector<int>({0}), "tab separates words");
	Check(ids("cold", 1) == std::vector<int>({3}), "category filter");
	Check(ids("cold", 2).empty(), "category filter, no match");
	Check(ids("caf\xC3\xA9") == std::vector<int>({5}), "UTF-8 bytes compare as they are");
	Check(ids("CAF\xC3\xA9") == std::vector<int>({5}), "ASCII lowered next to UTF-8");
	Check(ids("caf\xC3\x89").empty(), "non-ASCII letters are not case folded");
	// ranking: "lantern": Lantern of Embers starts with it; Frost Lantern holds it in its name; Ashen Crown only in its search text
	Check(ids("lantern") == std::vector<int>({1, 0, 2}), "ranking: starts with, contains, rest");
	Check(ids("frost") == std::vector<int>({0, 2, 3}), "ranking: starts with, then the rest in table order");
	Check(ids("lantern frost") == std::vector<int>({0, 2}), "ranking: every word in the name before the rest");
	Check(ids("frost lantern") == std::vector<int>({0, 2}), "ranking: the whole query starts the name");
	Check(ids("  Frost   LANTERN ") == std::vector<int>({0, 2}), "ranking: spaces folded in the joined query");
	Check(ids("winter garb") == std::vector<int>({3, 4}), "ranking: equal ranks keep the table's order");
	Check(ids("garb") == std::vector<int>({3, 4}), "ranking: contains in name");
	Check(ids("lantern", 0) == std::vector<int>({1, 0, 2}), "ranking inside a category");
	const Query q = ParseQuery(" A  bC ");
	Check(q.words.size() == 2 && q.words[0] == "a" && q.words[1] == "bc" && q.joined == "a bc", "query words");
}

void TestPaging() {
	Page p = PageOf(25, 0, 10);
	Check(p.pages == 3 && p.first == 0 && p.count == 10, "first page");
	p = PageOf(25, 2, 10);
	Check(p.first == 20 && p.count == 5, "last page is short");
	p = PageOf(25, 9, 10);
	Check(p.page == 2 && p.first == 20, "past the end clamps");
	p = PageOf(25, -3, 10);
	Check(p.page == 0, "before the start clamps");
	p = PageOf(20, 1, 10);
	Check(p.pages == 2 && p.count == 10, "exact pages");
	p = PageOf(0, 0, 10);
	Check(p.pages == 1 && p.count == 0 && PageText(p) == "Page 1 of 1", "empty list");
	p = PageOf(5, 0, 0);
	Check(p.pages == 5 && p.count == 1, "zero rows per page reads as one");
	Check(PageText(PageOf(25, 1, 10)) == "Page 2 of 3", "page text");
}

void TestWrap() {
	Check(Utf8Length("abc") == 3 && Utf8Length("caf\xC3\xA9") == 4 && Utf8Length("\xE2\x82\xAC\xF0\x9F\x98\x80") == 2, "UTF-8 length");
	Check(WrapLine("", 10) == std::vector<std::string>({""}), "empty line stays one line");
	Check(WrapLine("   ", 10) == std::vector<std::string>({""}), "spaces only: one empty line");
	Check(WrapLine("short", 10) == std::vector<std::string>({"short"}), "fits");
	Check(WrapLine("aaaa bbbb cccc", 9) == std::vector<std::string>({"aaaa bbbb", "cccc"}), "breaks at spaces");
	Check(WrapLine("aaaa bbbb", 9) == std::vector<std::string>({"aaaa bbbb"}), "exactly fits");
	Check(WrapLine("aa   bb", 10) == std::vector<std::string>({"aa bb"}), "runs of spaces fold");
	Check(WrapLine("aaaaaaaaaa b", 4) == std::vector<std::string>({"aaaa", "aaaa", "aa b"}), "a long word is split");
	Check(WrapLine("x aaaaaaaa", 4) == std::vector<std::string>({"x", "aaaa", "aaaa"}), "a long word starts its own line");
	Check(WrapLine("abc", 1) == std::vector<std::string>({"a", "b", "c"}), "width 1");
	Check(WrapLine("a b", 1) == std::vector<std::string>({"a", "b"}), "width 1 with spaces");
	Check(WrapLine("ab", 0) == std::vector<std::string>({"a", "b"}), "width 0 reads as 1");
	// "café" is 4 characters but 5 bytes
	Check(WrapLine("caf\xC3\xA9 caf\xC3\xA9", 9) == std::vector<std::string>({"caf\xC3\xA9 caf\xC3\xA9"}), "characters, not bytes");
	Check(WrapLine("caf\xC3\xA9 caf\xC3\xA9", 8) == std::vector<std::string>({"caf\xC3\xA9", "caf\xC3\xA9"}), "characters, not bytes: break");
	Check(WrapLine("\xC3\xA9\xC3\xA9\xC3\xA9", 2) == std::vector<std::string>({"\xC3\xA9\xC3\xA9", "\xC3\xA9"}), "a split never cuts a sequence");
	Check(WrapLine("\xF0\x9F\x98\x80\xF0\x9F\x98\x80", 1) == std::vector<std::string>({"\xF0\x9F\x98\x80", "\xF0\x9F\x98\x80"}),
	      "four-byte characters at width 1");

	const Table t = ParseTable(Sample());
	const auto w = WrapEntry(t.entries[0], 10);
	// Frost Lantern | Charm | +5 to Cold Skills -> "+5 to Cold" "Skills" | "" | Cold Resist +20% -> "Cold" "Resist" "+20%"
	Check(w.size() == 9, "wrapped entry line count");
	Check(w.size() == 9 && w[0].text == "Frost" && w[1].text == "Lantern" && w[0].colour == Colour::Gold && w[1].colour == Colour::Gold,
	      "a wrapped line keeps its colour");
	Check(w.size() == 9 && w[3].text == "+5 to Cold" && w[4].text == "Skills" && w[4].colour == Colour::Blue, "stat line wraps blue");
	Check(w.size() == 9 && w[5].text.empty() && w[5].colour == Colour::White, "blank line kept");
}

void TestScroll() {
	Check(ClampScroll(5, 30, 10) == 5, "inside");
	Check(ClampScroll(-2, 30, 10) == 0, "clamps at the top");
	Check(ClampScroll(25, 30, 10) == 20, "clamps at the bottom");
	Check(ClampScroll(3, 5, 10) == 0, "shorter than the pane");
	Check(ScrollLines(0, 3, 30, 10) == 3 && ScrollLines(19, 3, 30, 10) == 20 && ScrollLines(2, -5, 30, 10) == 0, "scroll by lines");
	Check(ScrollPages(0, 1, 30, 10) == 10 && ScrollPages(10, 2, 30, 10) == 20 && ScrollPages(15, -1, 30, 10) == 5 && ScrollPages(5, -1, 30, 10) == 0,
	      "scroll by pages");
	Check(LinesText(0, 30, 10) == "Lines 1-10 of 30", "lines text");
	Check(LinesText(20, 30, 10) == "Lines 21-30 of 30", "lines text at the end");
	Check(LinesText(0, 4, 10) == "Lines 1-4 of 4", "lines text, short entry");
	Check(LinesText(0, 0, 10) == "Lines 0-0 of 0", "lines text, no lines");
}

void TestLinks() {
	const Table t = ParseTable(Sample());
	Check(FindEntry(t, "Winter Garb") == 3, "exact name");
	Check(FindEntry(t, "winter garb") == 4, "exact match wins over a case-insensitive one");
	Check(FindEntry(t, "WINTER GARB") == 3, "case-insensitive: the first");
	Check(FindEntry(t, "frost lantern") == 0, "case-insensitive");
	Check(FindEntry(t, "nobody here") == NotFound && FindEntry(t, "") == NotFound, "not found");
}

void TestMatchingLine() {
	const std::vector<Line> lines = {{Colour::Gold, "Mystic Orbs"},
	                                 {Colour::White, "Orb of Fire: +5% Fire Spell Damage"},
	                                 {Colour::White, "Orb of Frost: +5% Cold Spell Damage"},
	                                 {Colour::White, "Orb of Winter: +10 Cold Resist, +2% Cold Spell Damage"}};
	bool all = false;
	Check(FirstMatchingLine(lines, ParseQuery("cold spell damage"), &all) == 2 && all, "the first line with every word");
	Check(FirstMatchingLine(lines, ParseQuery("COLD  Damage"), &all) == 2 && all, "case and spaces do not matter");
	Check(FirstMatchingLine(lines, ParseQuery("mystic cold"), &all) == 0 && !all, "no line has every word: the first with any");
	Check(FirstMatchingLine(lines, ParseQuery("winter"), &all) == 3 && all, "one word");
	Check(FirstMatchingLine(lines, ParseQuery("lightning"), &all) == NotFound && !all, "no line holds a word");
	Check(FirstMatchingLine(lines, ParseQuery("  "), &all) == NotFound && FirstMatchingLine(lines, ParseQuery("")) == NotFound, "an empty query marks nothing");
	Check(FirstMatchingLine({}, ParseQuery("cold")) == NotFound, "no lines");
	Check(HasAnyWord("cold spell damage", ParseQuery("fire cold")) && !HasAnyWord("cold", ParseQuery("")), "any word");
}

void TestHistory() {
	History h;
	Visit v;
	Check(h.Empty() && !h.Pop(v), "empty history");
	h.Push({1, 5});
	h.Push({2, 0});
	Check(h.Pop(v) && v.entry == 2 && v.scroll == 0 && h.Pop(v) && v.entry == 1 && v.scroll == 5 && h.Empty(), "last in, first out");
	for (int i = 0; i < HistoryDepth + 3; ++i) {
		h.Push({i, i});
	}
	Check(h.count == HistoryDepth, "full history stays at its depth");
	int popped = 0, last = -1;
	while (h.Pop(v)) {
		++popped;
		last = v.entry;
	}
	Check(popped == HistoryDepth && last == 3, "the oldest visits were dropped");
	h.Push({7, 0});
	h.Clear();
	Check(h.Empty(), "clear");
}

void TestView() {
	const Table t = ParseTable(Sample());
	View v;
	Check(Init(v, t, 2, 10, 3) == (ChangeCategory | ChangeQuery | ChangeResults | ChangePage | ChangeDetail | ChangeScroll | ChangeBack), "init: everything");
	Check(v.results.size() == 6 && v.selected == NotFound && ViewPageText(v) == "Page 1 of 3", "init: the whole table");
	Check(SetQuery(v, t, "") == ChangeNone, "same query: nothing");

	Check(NextPage(v) == (ChangeResults | ChangePage) && v.page == 1, "next page");
	Check(NextPage(v) == (ChangeResults | ChangePage) && NextPage(v) == ChangeNone && v.page == 2, "next page stops at the end");
	Check(PreviousPage(v) == (ChangeResults | ChangePage) && PreviousPage(v) == (ChangeResults | ChangePage) && PreviousPage(v) == ChangeNone,
	      "previous page stops at the start");

	// select row 1 of the first page: entry 1 (Lantern of Embers)
	Check(RowEntry(v, 1) == 1 && RowEntry(v, 2) == NotFound && RowEntry(v, -1) == NotFound, "row entries");
	Check(SelectRow(v, t, 1) == (ChangeResults | ChangeDetail | ChangeScroll) && v.selected == 1 && SelectedRow(v) == 1, "select a row");
	Check(SelectRow(v, t, 1) == ChangeNone, "select the same row again: nothing");
	Check(SelectRow(v, t, 5) == ChangeNone, "select an empty row: nothing");
	Check(SelectRow(v, t, 0) == (ChangeResults | ChangeDetail | ChangeScroll) && v.selected == 0 && v.detail.size() == 9, "select Frost Lantern");
	Check(ViewLinesText(v) == "Lines 1-3 of 9", "detail lines text");

	// scrolling
	Check(ScrollBy(v, 2) == ChangeScroll && v.scroll == 2, "scroll by lines");
	Check(ScrollByPages(v, 5) == ChangeScroll && v.scroll == 6 && ViewLinesText(v) == "Lines 7-9 of 9", "scroll to the end");
	Check(ScrollBy(v, 1) == ChangeNone, "scroll stops at the end");
	int first = 0, count = 0;
	VisibleDetail(v, first, count);
	Check(first == 6 && count == 3, "visible detail");
	Check(ScrollByPages(v, -9) == ChangeScroll && v.scroll == 0 && ScrollBy(v, -1) == ChangeNone, "scroll stops at the top");

	// links: 0 Winter Garb, 1 not found, 2 itself (case-insensitive "frost lantern")
	ScrollBy(v, 4);
	Check(FollowLink(v, t, 1) == LinkNotFound && v.selected == 0, "a link to nothing changes nothing");
	Check(FollowLink(v, t, 2) == ChangeNone, "a link to the entry itself changes nothing");
	Check(FollowLink(v, t, 9) == ChangeNone && FollowLink(v, t, -1) == ChangeNone, "no such link");
	// Frost Lantern is on page 1, row 0; Winter Garb is not on the page: the highlight goes away
	Check(FollowLink(v, t, 0) == (ChangeResults | ChangeDetail | ChangeScroll | ChangeBack) && v.selected == 3 && v.scroll == 0, "follow a link");
	Check(v.history.count == 1 && SelectedRow(v) == -1, "history holds the old entry");
	Check(FollowLink(v, t, 0) == (ChangeResults | ChangeDetail | ChangeScroll) && v.selected == 0 && v.history.count == 2, "follow back to Frost Lantern");
	Check(Back(v, t) == (ChangeResults | ChangeDetail | ChangeScroll) && v.selected == 3, "back to Winter Garb");
	Check(Back(v, t) == (ChangeResults | ChangeDetail | ChangeScroll | ChangeBack) && v.selected == 0 && v.scroll == 4, "back restores the scroll");
	Check(Back(v, t) == ChangeNone, "back with an empty history");

	// selecting from the list starts a new trail
	FollowLink(v, t, 0);
	Check(SelectRow(v, t, 1) == (ChangeResults | ChangeDetail | ChangeScroll | ChangeBack) && v.history.Empty(), "select clears Back");

	// query and category
	Check(SetQuery(v, t, "lantern") == (ChangeQuery | ChangeResults | ChangePage) && v.results == std::vector<int>({1, 0, 2}), "set a query");
	Check(v.page == 0 && ViewPageText(v) == "Page 1 of 2", "query: first page");
	NextPage(v);
	Check(SetQuery(v, t, "Lantern") == (ChangeQuery | ChangeResults | ChangePage) && v.page == 0, "same results, but back on page 1");
	Check(SetQuery(v, t, "lantern") == (ChangeQuery), "same results on the same page: only the query");
	Check(SetCategory(v, t, 1) == (ChangeCategory | ChangeResults | ChangePage) && v.results.empty(), "category without hits");
	Check(SetCategory(v, t, 1) == ChangeNone, "same category: nothing");
	Check(SetCategory(v, t, 7) == ChangeNone && SetCategory(v, t, -5) == ChangeNone, "unknown category: nothing");
	Check(SetQuery(v, t, "") == (ChangeQuery | ChangeResults) && v.results == std::vector<int>({3, 4}), "empty query lists the category");
	Check(SetCategory(v, t, AllCategories) == (ChangeCategory | ChangeResults | ChangePage) && v.results.size() == 6, "back to all categories");
	Check(v.selected == 1, "the detail stays while the list changes");

	// layout change: the detail is re-wrapped, the scroll clamped
	SelectRow(v, t, 0);
	ScrollByPages(v, 9);
	Check(v.scroll == 6, "scrolled to the end");
	SetLayout(v, t, 4, 40, 3);
	Check(v.detail.size() == 5 && v.scroll == 2 && ViewPageText(v) == "Page 1 of 2", "layout: re-wrapped and clamped");
	Check(SelectedRow(v) == 0, "layout: selection kept");
}

// Search over 10,000 entries with about 300 bytes of search text each (the size the wiki may reach): time one query per keystroke.
void TestSpeed() {
	std::string text = "V\t1\nC\tuniq\tUniques\nC\tpage\tPages\n";
	uint32_t seed = 12345;
	const auto next = [&seed]() {
		seed = seed * 1103515245U + 12345U;
		return (seed >> 16) & 0x7FFF;
	};
	const auto word = [&]() {
		std::string w;
		const int n = 3 + static_cast<int>(next() % 7);
		for (int i = 0; i < n; ++i) {
			w += static_cast<char>('a' + next() % 26);
		}
		return w;
	};
	for (int i = 0; i < 10000; ++i) {
		const std::string name = word() + " " + word();
		std::string search = Fold(name);
		while (search.size() < 300) {
			search += " " + word();
		}
		text += std::string("E\t") + (i % 5 == 0 ? "page" : "uniq") + "\t" + name + "\tsub\t" + search + "\nL\tgold\t" + name + "\nL\tblue\t" + search + "\n";
	}
	const auto t0 = std::chrono::steady_clock::now();
	const Table t = ParseTable(text);
	const auto t1 = std::chrono::steady_clock::now();
	Check(t.ok && t.entries.size() == 10000, "speed: big table parses");
	const char* queries[] = {"a", "e", "ab", "re", "abc", "qu", "the", "zzqx", "a e i", "ma ri", "o u", "xyzzy"};
	size_t hits = 0;
	int runs = 0;
	double worst = 0;
	for (int rep = 0; rep < 5; ++rep) {
		for (const char* q : queries) {
			const auto s0 = std::chrono::steady_clock::now();
			hits += Search(t, q, rep % 2 == 0 ? AllCategories : 0).size();
			const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - s0).count();
			worst = ms > worst ? ms : worst;
			++runs;
		}
	}
	const auto t2 = std::chrono::steady_clock::now();
	const double parseMs = std::chrono::duration<double, std::milli>(t1 - t0).count();
	const double avgMs = std::chrono::duration<double, std::milli>(t2 - t1).count() / runs;
	std::printf("wiki search: 10000 entries, %zu bytes of table; parse %.1f ms; search %.2f ms average, %.2f ms worst over %d queries (%zu hits)\n",
	            text.size(), parseMs, avgMs, worst, runs, hits);
	// a keystroke budget with room for an unoptimised CI build on a busy machine
	Check(avgMs < 100.0, "speed: a search fits a keystroke");
}
}  // namespace

int main() {
	TestParse();
	TestColours();
	TestSearch();
	TestPaging();
	TestWrap();
	TestScroll();
	TestLinks();
	TestMatchingLine();
	TestHistory();
	TestView();
	TestSpeed();
	if (g_fails == 0) {
		std::printf("wiki_logic tests passed\n");
	}
	return g_fails == 0 ? 0 : 1;
}

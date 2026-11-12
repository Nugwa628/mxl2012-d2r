// Pure part of the in-game wiki panel (plugin part `wiki`; unit test plugin/tests/wiki_logic_test.cpp). No Windows headers, no game calls,
// no game state: the content table's parser (data/mxl2012-wiki/wiki.tsv in the mod, written by tools/wikipanel_export.py), the search and
// its ranking, result pages, the detail view's wrapping and scrolling, "see also" links, the Back history, and the view state that ties
// them together and says which parts of the panel changed after each user action.
#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>
#include <string_view>
#include <vector>

#include "panel_logic.h"

namespace wiki_logic {

// --- content table ------------------------------------------------------------------------------------------------------------------------
//   V <format>                                   first line
//   C <category id> <label>                      one per category, in display order, before its entries
//   E <category id> <name> <subtitle> <search>   starts an entry (search text is lower case)
//   L <colour> <text>                            a display line of the entry above; empty text = blank line
//   K <target name>                              a "see also" link of the entry above
// Tab-separated, UTF-8, LF (CRLF and a byte order mark are tolerated), blank lines ignored.
inline constexpr int TableFormat = 1;
inline constexpr int AllCategories = -1;
inline constexpr int NotFound = -1;

enum class Colour : uint8_t { White, Grey, Blue, Gold, Green, Orange, Red, Yellow, Purple, Tan };
inline constexpr int ColourCount = 10;
inline constexpr const char* const ColourNames[ColourCount] = {"white", "grey", "blue", "gold", "green", "orange", "red", "yellow", "purple", "tan"};

// A colour by its table name; an unknown name reads as white and clears *known.
inline auto ColourOf(std::string_view name, bool* known = nullptr) -> Colour {
	for (int i = 0; i < ColourCount; ++i) {
		if (name == ColourNames[i]) {
			if (known != nullptr) {
				*known = true;
			}
			return static_cast<Colour>(i);
		}
	}
	if (known != nullptr) {
		*known = false;
	}
	return Colour::White;
}

struct Line {
	Colour colour = Colour::White;
	std::string text;
};

struct Category {
	std::string id;
	std::string label;
};

struct Entry {
	int category = 0;  // index into Table::categories
	std::string name;
	std::string subtitle;
	std::string search;  // the table's lower-case search text
	std::string folded;  // the name, ASCII lower case (ranking, link lookup)
	std::vector<Line> lines;
	std::vector<std::string> links;  // K target names, in the table's order
};

struct Table {
	bool ok = false;     // usable: format 1, at least one category and one entry
	int format = 0;      // the V line's number (0 when there was none)
	std::string error;   // why the table is unusable (empty when ok)
	std::string problem; // the first skipped line or unknown colour, as "line n: reason" (empty when none)
	int unknownKinds = 0;    // lines of an unknown kind, skipped
	int badLines = 0;        // lines skipped for a wrong field count, an L or K without an entry, an undeclared category, ...
	int unknownColours = 0;  // L lines whose colour was unknown (kept, as white)
	std::vector<Category> categories;
	std::vector<Entry> entries;
};

// ASCII lower case; bytes above 127 (UTF-8 sequences) stay as they are.
constexpr auto LowerAscii(char ch) noexcept -> char {
	return ch >= 'A' && ch <= 'Z' ? static_cast<char>(ch - 'A' + 'a') : ch;
}

inline auto Fold(std::string_view s) -> std::string {
	std::string out(s);
	for (char& ch : out) {
		ch = LowerAscii(ch);
	}
	return out;
}

// Tab-separated fields and whole numbers: the rules every table of the plugin's panels is read with (panel_logic.h).
using panel_logic::SplitTabs;
using panel_logic::ToInt;

// The category with that id, or NotFound.
inline auto CategoryIndex(const Table& t, std::string_view id) -> int {
	for (size_t i = 0; i < t.categories.size(); ++i) {
		if (t.categories[i].id == id) {
			return static_cast<int>(i);
		}
	}
	return NotFound;
}

// Parses the table's text. Never fails hard: a bad line is skipped and counted, `problem` names the first one. The table is unusable
// (`ok` false, `error` says why) without a V line of format 1 as its first line, or with no category or no entry.
inline auto ParseTable(std::string_view text) -> Table {
	Table t;
	if (text.size() >= 3 && static_cast<unsigned char>(text[0]) == 0xEF && static_cast<unsigned char>(text[1]) == 0xBB &&
	    static_cast<unsigned char>(text[2]) == 0xBF) {
		text.remove_prefix(3);
	}
	bool header = false;
	int current = -1;  // the entry L and K lines belong to; -1 before any E and after a skipped E
	int lineNo = 0;
	size_t from = 0;
	const auto note = [&](int& counter, const char* reason) {
		++counter;
		if (t.problem.empty()) {
			t.problem = "line " + std::to_string(lineNo) + ": " + reason;
		}
	};
	while (from < text.size()) {
		size_t nl = text.find('\n', from);
		if (nl == std::string_view::npos) {
			nl = text.size();
		}
		std::string_view line = text.substr(from, nl - from);
		from = nl + 1;
		++lineNo;
		if (!line.empty() && line.back() == '\r') {
			line.remove_suffix(1);
		}
		if (line.empty()) {
			continue;
		}
		const auto f = SplitTabs(line);
		const std::string_view kind = f[0];
		if (!header) {
			if (kind != "V" || f.size() != 2) {
				t.error = "no format line";
				return t;
			}
			t.format = ToInt(f[1], 0);
			if (t.format != TableFormat) {
				t.error = "unknown table format " + std::string(f[1]);
				return t;
			}
			header = true;
			continue;
		}
		if (kind == "C") {
			if (f.size() != 3 || f[1].empty()) {
				note(t.badLines, "C needs an id and a label");
			} else if (CategoryIndex(t, f[1]) != NotFound) {
				note(t.badLines, "category declared twice");
			} else {
				t.categories.push_back({std::string(f[1]), std::string(f[2])});
			}
		} else if (kind == "E") {
			current = -1;
			if (f.size() != 5 || f[2].empty()) {
				note(t.badLines, "E needs a category, a name, a subtitle and a search text");
				continue;
			}
			const int cat = CategoryIndex(t, f[1]);
			if (cat == NotFound) {
				note(t.badLines, "E with an undeclared category");
				continue;
			}
			Entry e;
			e.category = cat;
			e.name = std::string(f[2]);
			e.subtitle = std::string(f[3]);
			e.search = std::string(f[4]);
			e.folded = Fold(e.name);
			t.entries.push_back(std::move(e));
			current = static_cast<int>(t.entries.size()) - 1;
		} else if (kind == "L") {
			if (f.size() != 3) {
				note(t.badLines, "L needs a colour and a text");
			} else if (current < 0) {
				note(t.badLines, "L without an entry");
			} else {
				bool known = true;
				const Colour c = ColourOf(f[1], &known);
				if (!known) {
					note(t.unknownColours, "unknown colour");
				}
				t.entries[static_cast<size_t>(current)].lines.push_back({c, std::string(f[2])});
			}
		} else if (kind == "K") {
			if (f.size() != 2 || f[1].empty()) {
				note(t.badLines, "K needs a target name");
			} else if (current < 0) {
				note(t.badLines, "K without an entry");
			} else {
				t.entries[static_cast<size_t>(current)].links.emplace_back(f[1]);
			}
		} else if (kind == "V") {
			note(t.badLines, "a second V line");
		} else {
			note(t.unknownKinds, "unknown line kind");
		}
	}
	if (!header) {
		t.error = "no format line";
	} else if (t.categories.empty()) {
		t.error = "no categories";
	} else if (t.entries.empty()) {
		t.error = "no entries";
	} else {
		t.ok = true;
	}
	return t;
}

// --- search ---------------------------------------------------------------------------------------------------------------------------------
// The typed query: its words (ASCII lower case, split at spaces and tabs) and the words joined by one space (for "name starts with").
struct Query {
	std::vector<std::string> words;
	std::string joined;
};

inline auto ParseQuery(std::string_view q) -> Query {
	Query out;
	size_t pos = 0;
	while (pos < q.size()) {
		while (pos < q.size() && (q[pos] == ' ' || q[pos] == '\t')) {
			++pos;
		}
		size_t end = pos;
		while (end < q.size() && q[end] != ' ' && q[end] != '\t') {
			++end;
		}
		if (end > pos) {
			out.words.push_back(Fold(q.substr(pos, end - pos)));
			if (!out.joined.empty()) {
				out.joined += ' ';
			}
			out.joined += out.words.back();
		}
		pos = end;
	}
	return out;
}

// Every word occurs in the text (an empty query matches everything).
inline auto HasAllWords(std::string_view text, const Query& q) -> bool {
	for (const std::string& w : q.words) {
		if (text.find(w) == std::string_view::npos) {
			return false;
		}
	}
	return true;
}

// Some word occurs in the text (false for an empty query).
inline auto HasAnyWord(std::string_view text, const Query& q) -> bool {
	for (const std::string& w : q.words) {
		if (text.find(w) != std::string_view::npos) {
			return true;
		}
	}
	return false;
}

// Where a search hit is inside an entry's lines (the table's or the wrapped ones): the first line that holds every word of the query; when
// no single line does, the first that holds any of them. `all` (optional) says which of the two it was. NotFound for an empty query or when
// no line holds a word. The panel scrolls an entry opened from a search to this line and marks the lines that match the same way.
inline auto FirstMatchingLine(const std::vector<Line>& lines, const Query& q, bool* all = nullptr) -> int {
	if (all != nullptr) {
		*all = false;
	}
	if (q.words.empty()) {
		return NotFound;
	}
	int any = NotFound;
	for (size_t i = 0; i < lines.size(); ++i) {
		const std::string folded = Fold(lines[i].text);
		if (HasAllWords(folded, q)) {
			if (all != nullptr) {
				*all = true;
			}
			return static_cast<int>(i);
		}
		if (any == NotFound && HasAnyWord(folded, q)) {
			any = static_cast<int>(i);
		}
	}
	return any;
}

// The entries matching the query, as indexes into Table::entries. Every word must occur in the search text; within the optional category
// (AllCategories for every one). Ranked: names starting with the query, then names holding every word, then the rest; each rank keeps the
// table's order. An empty query lists the whole category (or the whole table) in the table's order.
inline auto Search(const Table& t, std::string_view query, int category = AllCategories) -> std::vector<int> {
	const Query q = ParseQuery(query);
	std::vector<int> starts, inName, rest;
	for (size_t i = 0; i < t.entries.size(); ++i) {
		const Entry& e = t.entries[i];
		if (category != AllCategories && e.category != category) {
			continue;
		}
		if (q.words.empty()) {
			starts.push_back(static_cast<int>(i));
			continue;
		}
		if (!HasAllWords(e.search, q)) {
			continue;
		}
		if (e.folded.compare(0, q.joined.size(), q.joined) == 0) {
			starts.push_back(static_cast<int>(i));
		} else if (HasAllWords(e.folded, q)) {
			inName.push_back(static_cast<int>(i));
		} else {
			rest.push_back(static_cast<int>(i));
		}
	}
	starts.insert(starts.end(), inName.begin(), inName.end());
	starts.insert(starts.end(), rest.begin(), rest.end());
	return starts;
}

// --- result pages ---------------------------------------------------------------------------------------------------------------------------
// `page` is zero-based; a page past either end clamps. The result rows of the page are results[first .. first + count).
struct Page {
	int first = 0, count = 0, page = 0, pages = 1;
};

inline auto PageOf(int total, int page, int perPage) noexcept -> Page {
	perPage = std::max(perPage, 1);
	total = std::max(total, 0);
	Page p;
	p.pages = total == 0 ? 1 : (total + perPage - 1) / perPage;
	p.page = std::clamp(page, 0, p.pages - 1);
	p.first = p.page * perPage;
	p.count = std::max(0, std::min(perPage, total - p.first));
	return p;
}

inline auto PageText(const Page& p) -> std::string {
	return "Page " + std::to_string(p.page + 1) + " of " + std::to_string(p.pages);
}

// --- detail view: wrapping ------------------------------------------------------------------------------------------------------------------
// UTF-8 characters (bytes that do not continue a sequence).
inline auto Utf8Length(std::string_view s) noexcept -> size_t {
	size_t n = 0;
	for (char ch : s) {
		n += (static_cast<unsigned char>(ch) & 0xC0) != 0x80 ? 1 : 0;
	}
	return n;
}

// The byte offset `chars` characters after `pos`, never inside a sequence (the end of `s` at most).
inline auto Utf8Advance(std::string_view s, size_t pos, size_t chars) noexcept -> size_t {
	while (chars > 0 && pos < s.size()) {
		++pos;
		while (pos < s.size() && (static_cast<unsigned char>(s[pos]) & 0xC0) == 0x80) {
			++pos;
		}
		--chars;
	}
	return pos;
}

// Wraps a text to lines of at most `width` characters (0 reads as 1). Breaks at spaces (runs of spaces fold into one); a word longer than a
// line is split; an empty text stays one empty line. Mirrors devmenu::WrapText with a character count as width and no line limit.
inline auto WrapLine(std::string_view text, size_t width) -> std::vector<std::string> {
	width = std::max<size_t>(width, 1);
	std::vector<std::string> out;
	std::string current;
	size_t currentChars = 0;
	size_t pos = 0;
	while (pos < text.size()) {
		size_t end = text.find(' ', pos);
		end = end == std::string_view::npos ? text.size() : end;
		std::string_view word = text.substr(pos, end - pos);
		pos = end + 1;
		if (word.empty()) {
			continue;
		}
		size_t chars = Utf8Length(word);
		if (!current.empty() && currentChars + 1 + chars <= width) {
			current += ' ';
			current.append(word);
			currentChars += 1 + chars;
			continue;
		}
		if (!current.empty()) {
			out.push_back(std::move(current));
			current.clear();
		}
		while (chars > width) {
			const size_t cut = Utf8Advance(word, 0, width);
			out.emplace_back(word.substr(0, cut));
			word.remove_prefix(cut);
			chars -= width;
		}
		current.assign(word);
		currentChars = chars;
	}
	if (!current.empty() || out.empty()) {
		out.push_back(std::move(current));
	}
	return out;
}

// An entry's lines wrapped to `width` characters; each wrapped line keeps the colour of its table line.
inline auto WrapEntry(const Entry& e, size_t width) -> std::vector<Line> {
	std::vector<Line> out;
	for (const Line& l : e.lines) {
		for (std::string& s : WrapLine(l.text, width)) {
			out.push_back({l.colour, std::move(s)});
		}
	}
	return out;
}

// --- detail view: scrolling -----------------------------------------------------------------------------------------------------------------
// `first` is the first visible wrapped line; `visible` lines fit the pane. Clamped so the pane never starts past the last full page.
inline auto ClampScroll(int first, int total, int visible) noexcept -> int {
	return std::clamp(first, 0, std::max(0, total - std::max(visible, 1)));
}

inline auto ScrollLines(int first, int delta, int total, int visible) noexcept -> int {
	return ClampScroll(first + delta, total, visible);
}

inline auto ScrollPages(int first, int pages, int total, int visible) noexcept -> int {
	return ClampScroll(first + pages * std::max(visible, 1), total, visible);
}

// "Lines a-b of n" (one-based, inclusive); "Lines 0-0 of 0" for an entry without lines.
inline auto LinesText(int first, int total, int visible) -> std::string {
	if (total <= 0) {
		return "Lines 0-0 of 0";
	}
	first = ClampScroll(first, total, visible);
	const int last = std::min(total, first + std::max(visible, 1));
	return "Lines " + std::to_string(first + 1) + "-" + std::to_string(last) + " of " + std::to_string(total);
}

// --- links ----------------------------------------------------------------------------------------------------------------------------------
// The entry a K target names: the first exact name match, else the first ASCII case-insensitive one, else NotFound.
inline auto FindEntry(const Table& t, std::string_view name) -> int {
	for (size_t i = 0; i < t.entries.size(); ++i) {
		if (t.entries[i].name == name) {
			return static_cast<int>(i);
		}
	}
	const std::string folded = Fold(name);
	for (size_t i = 0; i < t.entries.size(); ++i) {
		if (t.entries[i].folded == folded) {
			return static_cast<int>(i);
		}
	}
	return NotFound;
}

// --- history (Back) -------------------------------------------------------------------------------------------------------------------------
inline constexpr int HistoryDepth = 16;

struct Visit {
	int entry = NotFound;
	int scroll = 0;
};

// A fixed-size stack of visited entries: Push on following a link, Pop on Back; when full, the oldest visit is dropped.
struct History {
	Visit items[HistoryDepth];
	int count = 0;

	void Push(Visit v) noexcept {
		if (count == HistoryDepth) {
			std::copy(items + 1, items + HistoryDepth, items);
			--count;
		}
		items[count++] = v;
	}
	auto Pop(Visit& v) noexcept -> bool {
		if (count == 0) {
			return false;
		}
		v = items[--count];
		return true;
	}
	auto Empty() const noexcept -> bool {
		return count == 0;
	}
	void Clear() noexcept {
		count = 0;
	}
};

// --- view state -----------------------------------------------------------------------------------------------------------------------------
// What an action changed, so the panel resets only those text boxes and buttons.
enum Change : uint32_t {
	ChangeNone = 0,
	ChangeCategory = 1U << 0,  // the current category (its button or label)
	ChangeQuery = 1U << 1,     // the query text
	ChangeResults = 1U << 2,   // the result rows on screen (their entries or which row is highlighted)
	ChangePage = 1U << 3,      // "Page a of b" and the previous / next buttons
	ChangeDetail = 1U << 4,    // the detail pane's entry: its name, subtitle and lines
	ChangeScroll = 1U << 5,    // the visible detail lines and "Lines a-b of n"
	ChangeBack = 1U << 6,      // whether Back can go anywhere
	LinkNotFound = 1U << 7,    // a followed link names no entry (nothing else changed): the panel may say so
};

struct View {
	int category = AllCategories;
	std::string query;
	std::vector<int> results;  // entry indexes, ranked
	int page = 0;
	int selected = NotFound;  // the entry in the detail pane
	int scroll = 0;           // its first visible wrapped line
	std::vector<Line> detail; // the selected entry wrapped to `wrapWidth`
	History history;
	int rowsPerPage = 10;
	int wrapWidth = 60;
	int visibleLines = 20;
};

inline auto CurrentPage(const View& v) noexcept -> Page {
	return PageOf(static_cast<int>(v.results.size()), v.page, v.rowsPerPage);
}

// The entry shown in row `row` of the current page, or NotFound.
inline auto RowEntry(const View& v, int row) noexcept -> int {
	const Page p = CurrentPage(v);
	return row >= 0 && row < p.count ? v.results[static_cast<size_t>(p.first + row)] : NotFound;
}

// The row of the current page that shows the selected entry (highlighted), or -1.
inline auto SelectedRow(const View& v) noexcept -> int {
	const Page p = CurrentPage(v);
	for (int r = 0; r < p.count; ++r) {
		if (v.results[static_cast<size_t>(p.first + r)] == v.selected) {
			return r;
		}
	}
	return -1;
}

inline auto ViewPageText(const View& v) -> std::string {
	return PageText(CurrentPage(v));
}

inline auto ViewLinesText(const View& v) -> std::string {
	return LinesText(v.scroll, static_cast<int>(v.detail.size()), v.visibleLines);
}

// The visible detail lines: detail[first .. first + count).
inline auto VisibleDetail(const View& v, int& first, int& count) noexcept -> void {
	const int total = static_cast<int>(v.detail.size());
	first = ClampScroll(v.scroll, total, v.visibleLines);
	count = std::min(total - first, std::max(v.visibleLines, 1));
}

namespace internal {
// Re-runs the search; the page goes back to the first. Returns ChangeResults / ChangePage for what differs on screen.
inline auto Refresh(View& v, const Table& t) -> uint32_t {
	const Page before = CurrentPage(v);
	std::vector<int> found = Search(t, v.query, v.category);
	const bool same = found == v.results && before.page == 0;
	v.results = std::move(found);
	v.page = 0;
	const Page after = CurrentPage(v);
	uint32_t c = same ? ChangeNone : ChangeResults;
	if (before.page != after.page || before.pages != after.pages) {
		c |= ChangePage;
	}
	return c;
}

// Shows `entry` scrolled to `scroll` (clamped). Returns what changed: the detail, the scroll, the highlighted row.
inline auto Show(View& v, const Table& t, int entry, int scroll) -> uint32_t {
	const int rowBefore = SelectedRow(v);
	uint32_t c = ChangeNone;
	if (entry != v.selected) {
		v.selected = entry;
		v.detail = entry >= 0 && entry < static_cast<int>(t.entries.size())
		               ? WrapEntry(t.entries[static_cast<size_t>(entry)], static_cast<size_t>(std::max(v.wrapWidth, 1)))
		               : std::vector<Line>{};
		c |= ChangeDetail | ChangeScroll;
	}
	scroll = ClampScroll(scroll, static_cast<int>(v.detail.size()), v.visibleLines);
	if (scroll != v.scroll) {
		v.scroll = scroll;
		c |= ChangeScroll;
	}
	if (SelectedRow(v) != rowBefore) {
		c |= ChangeResults;
	}
	return c;
}
}  // namespace internal

// Sets the sizes the panel's layout gives (result rows per page, detail characters per line and visible lines) and fills the view: the whole
// table, nothing selected. Call again when the layout changes (the selected entry is re-wrapped, its scroll clamped).
inline auto Init(View& v, const Table& t, int rowsPerPage, int wrapWidth, int visibleLines) -> uint32_t {
	v.rowsPerPage = std::max(rowsPerPage, 1);
	v.wrapWidth = std::max(wrapWidth, 1);
	v.visibleLines = std::max(visibleLines, 1);
	v.category = AllCategories;
	v.query.clear();
	v.results = Search(t, v.query, v.category);
	v.page = 0;
	v.selected = NotFound;
	v.scroll = 0;
	v.detail.clear();
	v.history.Clear();
	return ChangeCategory | ChangeQuery | ChangeResults | ChangePage | ChangeDetail | ChangeScroll | ChangeBack;
}

inline auto SetLayout(View& v, const Table& t, int rowsPerPage, int wrapWidth, int visibleLines) -> uint32_t {
	const int topResult = CurrentPage(v).first;
	v.rowsPerPage = std::max(rowsPerPage, 1);
	v.wrapWidth = std::max(wrapWidth, 1);
	v.visibleLines = std::max(visibleLines, 1);
	v.page = topResult / v.rowsPerPage;  // the page that holds the old first row
	const int entry = v.selected;
	v.selected = NotFound;
	internal::Show(v, t, entry, v.scroll);
	return ChangeResults | ChangePage | ChangeDetail | ChangeScroll;
}

// The query typed into the search box. The results go back to the first page.
inline auto SetQuery(View& v, const Table& t, std::string_view query) -> uint32_t {
	if (query == v.query) {
		return ChangeNone;
	}
	v.query = std::string(query);
	return ChangeQuery | internal::Refresh(v, t);
}

// A category (AllCategories for all). The query stays; the results go back to the first page.
inline auto SetCategory(View& v, const Table& t, int category) -> uint32_t {
	if (category != AllCategories && (category < 0 || category >= static_cast<int>(t.categories.size()))) {
		return ChangeNone;
	}
	if (category == v.category) {
		return ChangeNone;
	}
	v.category = category;
	return ChangeCategory | internal::Refresh(v, t);
}

// Next (+1) or previous (-1) result page, clamped at both ends.
inline auto TurnPage(View& v, int delta) -> uint32_t {
	const Page before = CurrentPage(v);
	v.page = PageOf(static_cast<int>(v.results.size()), before.page + delta, v.rowsPerPage).page;
	return v.page == before.page ? ChangeNone : ChangeResults | ChangePage;
}

inline auto NextPage(View& v) -> uint32_t {
	return TurnPage(v, 1);
}

inline auto PreviousPage(View& v) -> uint32_t {
	return TurnPage(v, -1);
}

// A click on row `row` of the current page: that entry fills the detail pane from its top. Starts a new trail, so Back is emptied.
inline auto SelectRow(View& v, const Table& t, int row) -> uint32_t {
	const int entry = RowEntry(v, row);
	if (entry == NotFound || entry == v.selected) {
		return ChangeNone;
	}
	uint32_t c = internal::Show(v, t, entry, 0);
	if (!v.history.Empty()) {
		v.history.Clear();
		c |= ChangeBack;
	}
	return c;
}

// Scrolls the detail pane by lines (wheel, arrows) or by pages, clamped at both ends.
inline auto ScrollBy(View& v, int lines) -> uint32_t {
	const int s = ScrollLines(v.scroll, lines, static_cast<int>(v.detail.size()), v.visibleLines);
	if (s == v.scroll) {
		return ChangeNone;
	}
	v.scroll = s;
	return ChangeScroll;
}

inline auto ScrollByPages(View& v, int pages) -> uint32_t {
	const int s = ScrollPages(v.scroll, pages, static_cast<int>(v.detail.size()), v.visibleLines);
	if (s == v.scroll) {
		return ChangeNone;
	}
	v.scroll = s;
	return ChangeScroll;
}

// Follows the selected entry's link `n` (its n-th K line): the current entry and scroll go on the Back stack, the target shows from its
// top. A link naming no entry changes nothing and returns LinkNotFound; a link to the entry itself changes nothing.
inline auto FollowLink(View& v, const Table& t, int n) -> uint32_t {
	if (v.selected < 0 || v.selected >= static_cast<int>(t.entries.size())) {
		return ChangeNone;
	}
	const Entry& e = t.entries[static_cast<size_t>(v.selected)];
	if (n < 0 || n >= static_cast<int>(e.links.size())) {
		return ChangeNone;
	}
	const int target = FindEntry(t, e.links[static_cast<size_t>(n)]);
	if (target == NotFound) {
		return LinkNotFound;
	}
	if (target == v.selected) {
		return ChangeNone;
	}
	const bool wasEmpty = v.history.Empty();
	v.history.Push({v.selected, v.scroll});
	return internal::Show(v, t, target, 0) | (wasEmpty ? ChangeBack : ChangeNone);
}

// Back: the entry before the last followed link, at its old scroll position.
inline auto Back(View& v, const Table& t) -> uint32_t {
	Visit prev;
	if (!v.history.Pop(prev)) {
		return ChangeNone;
	}
	const int scroll = prev.scroll;
	uint32_t c = internal::Show(v, t, prev.entry, scroll);
	return c | (v.history.Empty() ? ChangeBack : ChangeNone);
}

}  // namespace wiki_logic

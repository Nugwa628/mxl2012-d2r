// The character sheet host's pure part (sheet_host.cpp; widget names: docs/statbook-layout.md). What each widget of the
// contract shows for a tab, a page's lines and the All Stats list, the click rectangles of
// hd/global/ui/panel/statbook/statbook-layout.json, and the All Stats window over book_logic.h's Search. No Windows headers.
#pragma once

#include "book_logic.h"

#include <cstdio>
#include <string>
#include <string_view>
#include <vector>

namespace sheet_host {

inline constexpr const char* ToneNames[10] = {"White", "Grey", "Red", "Blue", "Yellow", "Purple", "Magic", "Gold", "ItemBlue", "Green"};
inline constexpr int ToneCount = 10;
inline constexpr int MaxTabs = 16;
inline constexpr int MaxLines = 22;   // line slots SbLine00 .. SbLine21
inline constexpr int MaxAllRows = 22; // All Stats rows SbAll00 .. SbAll21 (PC; the gamepad has 20)

// "SbLine07" + suffix and the like: a two-digit slot name
inline auto Slot(const char* prefix, int i, const char* suffix) -> std::string {
	char b[64];
	std::snprintf(b, sizeof(b), "%s%02d%s", prefix, i, suffix);
	return b;
}

inline auto TabName(int i, const char* suffix) -> std::string {
	char b[48];
	std::snprintf(b, sizeof(b), "SbTab%d%s", i, suffix);
	return b;
}

// The group a contract widget sits in (docs/statbook-layout.md); "" for the sheet's top level. WidgetService finds a widget
// by name below one parent only, so a leaf is looked up in its group.
inline auto ParentOf(std::string_view name) -> std::string {
	auto digits = [&](size_t at) { return name.size() >= at + 2 && name[at] >= '0' && name[at] <= '9' && name[at + 1] >= '0' && name[at + 1] <= '9'; };
	auto starts = [&](std::string_view s, std::string_view p) { return s.substr(0, p.size()) == p; };
	if (starts(name, "SbLine") && digits(6)) {
		const std::string_view rest = name.substr(8);
		for (std::string_view part : {"Heading", "Full", "Left", "Right"}) {
			if (rest == part) {
				return "StatBookPage";
			}
			if (starts(rest, part)) {
				return std::string(name.substr(0, 8)) + std::string(part);
			}
		}
		return "StatBookPage";
	}
	if (starts(name, "SbAll") && digits(5)) {
		const std::string_view rest = name.substr(7);
		if (rest == "Heading" || rest == "Row") {
			return "StatBookAll";
		}
		return std::string(name.substr(0, 7)) + (starts(rest, "Heading") ? "Heading" : "Row");
	}
	if (starts(name, "SbTab") || starts(name, "SbPadPrev") || starts(name, "SbPadNext")) {
		return "StatBookTabs";
	}
	if (starts(name, "SbPadAllHint") && name != "SbPadAllHint") {
		return "SbPadAllHint";
	}
	if (starts(name, "SbSearch") || name == "SbPreviewQuery" || starts(name, "SbAllScroll")) {
		return "StatBookAll";
	}
	return "";
}

// Which of a line slot's four groups shows (an Empty line: none).
struct LineShow {
	bool heading = false, full = false, left = false, right = false;
};

inline auto ShowFor(const statbook::Line& l) -> LineShow {
	LineShow s;
	s.heading = l.kind == statbook::Line::Kind::Heading;
	s.full = l.kind == statbook::Line::Kind::Full;
	s.left = l.kind == statbook::Line::Kind::Pair;
	s.right = l.kind == statbook::Line::Kind::Pair && l.right;
	return s;
}

// What the page-level groups show on a tab (StatBookPage, SbPageBody, StatBookAll, D2R's own page-1 widgets).
struct PageShow {
	bool sheet = true, body = false, page = false, all = false;
};

inline auto ShowForTab(const statbook::Tabs& t) -> PageShow {
	PageShow s;
	s.sheet = t.IsSheet();
	s.page = t.Page() >= 0;
	s.all = t.current == t.AllStats();
	s.body = s.page || s.all;
	return s;
}

// ---- All Stats ---------------------------------------------------------------------------------------------------------

// One list row slot: a group heading, a stat line with its highlight layers, or nothing (past the end).
struct AllSlot {
	enum class Kind : uint8_t { None, Heading, Row } kind = Kind::None;
	std::string text, hit, pre;
	size_t source = 0;  // index into the ListLine list
};

// The highlight layers of a row (docs/statbook-layout.md "All Stats"): `hit` the text up to the end of the match (drawn gold over
// the white line), `pre` the text before the match (white over that). Both empty without a match; `pre` empty at a match at 0.
inline void Highlight(const std::string& text, size_t match, size_t length, std::string& hit, std::string& pre) {
	hit.clear();
	pre.clear();
	if (match == std::string::npos || length == 0 || match >= text.size()) {
		return;
	}
	hit = text.substr(0, match + length);
	if (match > 0) {
		pre = text.substr(0, match);
	}
}

// The scroll position kept inside the list: at most total - rows, at least 0.
inline auto ClampScroll(long scroll, size_t total, size_t rows) -> long {
	const long last = total > rows ? static_cast<long>(total - rows) : 0;
	return scroll < 0 ? 0 : scroll > last ? last : scroll;
}

// The rows the list shows from `scroll` on (`rows` slots; `*scroll` kept inside the list), the count of list lines the search
// keeps (`*kept`, headings included: the scroll range) and of stat rows among them (`*keptRows`, the "shown" of "shown/total").
inline void AllWindow(const std::vector<statbook::ListLine>& lines, std::string_view query, long* scroll, AllSlot* out, size_t rows, size_t* kept,
                      size_t* keptRows) {
	std::vector<statbook::Shown> shown(lines.size() + 1);
	const size_t n = statbook::Search(lines, query, shown.data(), shown.size());
	*kept = n;
	*keptRows = 0;
	for (size_t i = 0; i < n; ++i) {
		*keptRows += lines[shown[i].index].heading ? 0 : 1;
	}
	const long first = ClampScroll(*scroll, n, rows);
	*scroll = first;
	for (size_t i = 0; i < rows; ++i) {
		AllSlot& s = out[i];
		s = AllSlot{};
		const size_t at = static_cast<size_t>(first) + i;
		if (at >= n) {
			continue;
		}
		const statbook::Shown& sh = shown[at];
		const statbook::ListLine& l = lines[sh.index];
		s.source = sh.index;
		s.text = l.text;
		s.kind = l.heading ? AllSlot::Kind::Heading : AllSlot::Kind::Row;
		if (!l.heading) {
			Highlight(l.text, sh.match, sh.length, s.hit, s.pre);
		}
	}
}

// The count of rows (not headings) among the lines: the "total" of "shown/total".
inline auto RowCount(const std::vector<statbook::ListLine>& lines) -> size_t {
	size_t n = 0;
	for (const auto& l : lines) {
		n += l.heading ? 0 : 1;
	}
	return n;
}

// The search box's text as the list takes it: trimmed, at most 32 characters.
inline auto Query(std::string_view typed) -> std::string {
	while (!typed.empty() && (typed.front() == ' ' || typed.front() == '\t')) {
		typed.remove_prefix(1);
	}
	while (!typed.empty() && (typed.back() == ' ' || typed.back() == '\t')) {
		typed.remove_suffix(1);
	}
	return std::string(typed.substr(0, 32));
}

// A text without D2R's colour codes (the byte 0xff, "ÿ" in UTF-8, then 'c' and one character) and with line breaks as spaces.
inline auto Plain(std::string_view s) -> std::string {
	std::string out;
	for (size_t i = 0; i < s.size(); ++i) {
		const auto c = static_cast<unsigned char>(s[i]);
		if (c == 0xff && i + 2 < s.size() + 1 && i + 1 < s.size() && s[i + 1] == 'c') {
			i += 2;
			continue;
		}
		if (c == 0xc3 && i + 2 < s.size() && static_cast<unsigned char>(s[i + 1]) == 0xbf && s[i + 2] == 'c') {
			i += 3;
			continue;
		}
		out += c == '\n' || c == '\r' ? ' ' : static_cast<char>(c);
	}
	return out;
}

// ---- the click rectangles (hd/global/ui/panel/statbook/statbook-layout.json) ------------------------------------------

struct Rect {
	int x = 0, y = 0, w = 0, h = 0;
};

struct Geometry {
	bool ok = false;
	std::vector<Rect> tabs, lineRects, allRowRects;
	Rect search;
	Rect toggle;  // the top / side toggle (w 0: none, the gamepad layout)
	int lines = 0, allRows = 0, allColumns = 0;
};

namespace detail {

// The text of the JSON value after `"key":` inside [from, to); npos when not there.
inline auto ValueAt(std::string_view s, std::string_view key, size_t from, size_t to) -> size_t {
	const std::string quoted = "\"" + std::string(key) + "\"";
	size_t at = s.find(quoted, from);
	if (at == std::string_view::npos || at >= to) {
		return std::string_view::npos;
	}
	at = s.find(':', at + quoted.size());
	if (at == std::string_view::npos || at >= to) {
		return std::string_view::npos;
	}
	++at;
	while (at < s.size() && (s[at] == ' ' || s[at] == '\n' || s[at] == '\r' || s[at] == '\t')) {
		++at;
	}
	return at;
}

// The end of the bracketed / braced value starting at `at` (the index after its closing bracket).
inline auto Close(std::string_view s, size_t at) -> size_t {
	int depth = 0;
	for (size_t i = at; i < s.size(); ++i) {
		if (s[i] == '[' || s[i] == '{') {
			++depth;
		} else if (s[i] == ']' || s[i] == '}') {
			if (--depth == 0) {
				return i + 1;
			}
		}
	}
	return std::string_view::npos;
}

// Every integer in [from, to), in order.
inline auto Ints(std::string_view s, size_t from, size_t to) -> std::vector<int> {
	std::vector<int> v;
	for (size_t i = from; i < to && i < s.size();) {
		if (s[i] == '-' || (s[i] >= '0' && s[i] <= '9')) {
			const bool neg = s[i] == '-';
			size_t j = neg ? i + 1 : i;
			int n = 0;
			bool any = false;
			for (; j < to && s[j] >= '0' && s[j] <= '9'; ++j) {
				n = n * 10 + (s[j] - '0');
				any = true;
			}
			if (any) {
				v.push_back(neg ? -n : n);
			}
			i = j > i ? j : i + 1;
		} else {
			++i;
		}
	}
	return v;
}

inline auto Rects(std::string_view s, std::string_view key, size_t from, size_t to) -> std::vector<Rect> {
	std::vector<Rect> out;
	const size_t at = ValueAt(s, key, from, to);
	if (at == std::string_view::npos || s[at] != '[') {
		return out;
	}
	const size_t end = Close(s, at);
	const std::vector<int> v = Ints(s, at, end);
	for (size_t i = 0; i + 3 < v.size(); i += 4) {
		out.push_back(Rect{v[i], v[i + 1], v[i + 2], v[i + 3]});
	}
	return out;
}

inline auto Int(std::string_view s, std::string_view key, size_t from, size_t to) -> int {
	const size_t at = ValueAt(s, key, from, to);
	if (at == std::string_view::npos) {
		return 0;
	}
	const std::vector<int> v = Ints(s, at, at + 12 < to ? at + 12 : to);
	return v.empty() ? 0 : v[0];
}

}  // namespace detail

// The rectangles of one layout ("pc" or "pad") of statbook-layout.json.
inline auto ParseGeometry(std::string_view json, std::string_view layout) -> Geometry {
	Geometry g;
	const size_t at = detail::ValueAt(json, layout, 0, json.size());
	if (at == std::string_view::npos || json[at] != '{') {
		return g;
	}
	const size_t end = detail::Close(json, at);
	if (end == std::string_view::npos) {
		return g;
	}
	g.tabs = detail::Rects(json, "tabs", at, end);
	g.lineRects = detail::Rects(json, "lineRects", at, end);
	g.allRowRects = detail::Rects(json, "allRowRects", at, end);
	const size_t s = detail::ValueAt(json, "search", at, end);
	if (s != std::string_view::npos && json[s] == '[') {
		const std::vector<int> v = detail::Ints(json, s, detail::Close(json, s));
		if (v.size() >= 3) {
			g.search = Rect{v[0], v[1], v[2], v.size() >= 4 ? v[3] : 44};
		}
	}
	const size_t tg = detail::ValueAt(json, "toggle", at, end);
	if (tg != std::string_view::npos && json[tg] == '[') {
		const std::vector<int> v = detail::Ints(json, tg, detail::Close(json, tg));
		if (v.size() >= 4) {
			g.toggle = Rect{v[0], v[1], v[2], v[3]};
		}
	}
	g.lines = detail::Int(json, "lines", at, end);
	g.allRows = detail::Int(json, "allRows", at, end);
	g.allColumns = detail::Int(json, "allColumns", at, end);
	g.ok = !g.tabs.empty() && g.lines > 0 && g.allRows > 0;
	return g;
}

// The rectangle holding (x, y), or -1.
inline auto HitRect(const std::vector<Rect>& rects, double x, double y) -> int {
	for (size_t i = 0; i < rects.size(); ++i) {
		const Rect& r = rects[i];
		if (x >= r.x && x < r.x + r.w && y >= r.y && y < r.y + r.h) {
			return static_cast<int>(i);
		}
	}
	return -1;
}

// What a click at (x, y) (the layout's units) hits: the toggle, a tab, an All Stats row (on All Stats), or nothing. The
// toggle comes first (on the sheet it sits over the end of the first heading's rule); a tab of zero size (the side panel's
// Character tab) is never hit.
struct ClickHit {
	enum class Kind : uint8_t { None, Toggle, Tab, Row } kind = Kind::None;
	int index = -1;
};

inline auto ClickOn(const Geometry& g, const statbook::Tabs& t, double x, double y) -> ClickHit {
	if (g.toggle.w > 0 && HitRect({g.toggle}, x, y) == 0) {
		return {ClickHit::Kind::Toggle, 0};
	}
	const int tab = HitRect(g.tabs, x, y);
	if (tab >= 0 && tab < t.Count()) {
		return {ClickHit::Kind::Tab, tab};
	}
	if (t.current == t.AllStats()) {
		const int row = HitRect(g.allRowRects, x, y);
		if (row >= 0) {
			return {ClickHit::Kind::Row, row};
		}
	}
	return {};
}

// The side panel has no Character tab (the sheet is beside it): its tab is never 0, and a step goes round the others.
inline auto SideTab(int tab) -> int {
	return tab < 1 ? 1 : tab;
}

inline void SideStep(statbook::Tabs& t, int by) {
	const int n = t.Count() - 1;  // tabs 1 .. Count() - 1
	if (n <= 0) {
		return;
	}
	const int i = SideTab(t.current) - 1;
	t.current = ((i + by) % n + n) % n + 1;
}

// The tab of the themed page that has a row of `stat` (an All Stats row's Go arrow), or -1.
inline auto TabOfStat(const statbook::Book& book, uint16_t stat) -> int {
	for (size_t p = 0; p < book.pages.size(); ++p) {
		for (const auto& sec : book.pages[p].sections) {
			for (const auto& r : sec.rows) {
				for (uint8_t k = 0; k < r.stats; ++k) {
					if (r.stat[k].id == stat) {
						return static_cast<int>(p) + 1;
					}
				}
			}
		}
	}
	return -1;
}

// ---- the All Stats lines from the book's groups ------------------------------------------------------------------------

// One All Stats row as text: `statText(stat)` gives the game's own item line for a plain stat row (empty: not known), `value`
// a stat's value, `text(key, english)` a string. A row with every value 0 gives "" (left out of the list).
template <class Value, class StatText, class Strings>
auto AllRowText(const statbook::AllRow& r, Value&& value, StatText&& statText, Strings&& text) -> std::string {
	int32_t v[3] = {0, 0, 0};
	bool any = false;
	for (uint8_t k = 0; k < r.stats && k < 3; ++k) {
		v[k] = value(r.stat[k]);
		any = any || v[k] != 0;
	}
	if (!any) {
		return {};
	}
	if (r.kind == statbook::AllKind::Stat) {
		std::string s = Plain(statText(r.stat[0], v[0]));
		if (s.empty()) {
			char b[64];
			std::snprintf(b, sizeof(b), "stat %u: %d", static_cast<unsigned>(r.stat[0]), v[0]);
			s = b;
		}
		return s;
	}
	const std::string pattern = text(r.key, r.english);
	return Plain(statbook::Fill(pattern, v, r.stats));
}

template <class Value, class StatText, class Strings>
auto AllLines(const statbook::Book& book, Value&& value, StatText&& statText, Strings&& text, std::vector<statbook::ListLine>* out,
              std::vector<uint16_t>* stats) -> void {
	out->clear();
	stats->clear();
	for (const auto& g : book.all) {
		const size_t head = out->size();
		out->push_back(statbook::ListLine{true, text(g.key, g.heading)});
		stats->push_back(0);
		for (const auto& r : g.rows) {
			std::string s = AllRowText(r, value, statText, text);
			if (!s.empty()) {
				out->push_back(statbook::ListLine{false, std::move(s)});
				stats->push_back(r.stat[0]);
			}
		}
		if (out->size() == head + 1) {  // nothing in the group
			out->pop_back();
			stats->pop_back();
		}
	}
}

}  // namespace sheet_host

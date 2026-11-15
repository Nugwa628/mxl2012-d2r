// The Stat Book's pure part (docs/statbook.md): the book file (tools/statbook.py) parsed into pages and the All Stats
// list, a page filled into lines of text and tone, the All Stats search, and the tab state. Nothing here knows widgets or
// the game: a host (the character sheet's folder tabs, statbook.cpp) asks for a PageView of N lines and puts each line
// into its own widgets, so another frame (a side panel with its tabs down the side) is another host over the same views.
// No Windows headers: the tests build it anywhere.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string>
#include <string_view>
#include <vector>

namespace statbook {

enum class Tone : uint8_t { White, Grey, Red, Blue, Yellow, Purple, Magic, Gold, ItemBlue, Green };

struct StatRef {
	uint16_t id = 0;
	bool classParam = false;  // the player's class id as the stat's param (item_addclassskills)
};

struct Row {
	std::string label;
	StatRef stat[2];
	uint8_t stats = 1;
	std::string format;  // %d %+d %% only, or "yesno" / "block"
	Tone colour = Tone::White;
	int32_t capBase = -1;   // -1: no cap
	uint16_t capStat = 0;   // 0: the cap is capBase alone
	int32_t capMax = 0;
	int32_t base[2] = {0, 0};
	bool half = false;
};

struct Section {
	std::string heading;
	std::vector<Row> rows;
};

struct Page {
	std::string id, title;
	std::vector<Section> sections;
};

enum class AllKind : uint8_t { Stat, Range, Value, Avoid };

struct AllRow {
	AllKind kind = AllKind::Stat;
	uint16_t stat[3] = {0, 0, 0};
	uint8_t stats = 1;
	std::string key, english;  // the own text of a range / value row ("-" none)
};

struct AllGroup {
	std::string key, heading;
	std::vector<AllRow> rows;
};

struct Book {
	std::vector<Page> pages;
	std::vector<AllGroup> all;
	std::string error;  // empty when the whole file parsed
};

namespace detail {

inline auto Split(std::string_view line, std::vector<std::string_view>& out) -> size_t {
	out.clear();
	size_t start = 0;
	for (size_t i = 0; i <= line.size(); ++i) {
		if (i == line.size() || line[i] == '\t') {
			out.push_back(line.substr(start, i - start));
			start = i + 1;
		}
	}
	return out.size();
}

inline auto Int(std::string_view s, int32_t& v) -> bool {
	if (s.empty()) {
		return false;
	}
	bool neg = s[0] == '-';
	size_t i = neg ? 1 : 0;
	if (i == s.size()) {
		return false;
	}
	int64_t n = 0;
	for (; i < s.size(); ++i) {
		if (s[i] < '0' || s[i] > '9' || n > 100000000) {
			return false;
		}
		n = n * 10 + (s[i] - '0');
	}
	v = static_cast<int32_t>(neg ? -n : n);
	return true;
}

inline auto Stat(std::string_view s, StatRef& r) -> bool {
	r.classParam = s.size() > 2 && s.substr(s.size() - 2) == ":c";
	int32_t v = 0;
	if (!Int(r.classParam ? s.substr(0, s.size() - 2) : s, v) || v < 0 || v > 0xffff) {
		return false;
	}
	r.id = static_cast<uint16_t>(v);
	return true;
}

inline auto Colour(std::string_view s, Tone& t) -> bool {
	struct Name {
		const char* name;
		Tone tone;
	};
	static constexpr Name names[] = {{"w", Tone::White}, {"r", Tone::Red}, {"b", Tone::Blue}, {"y", Tone::Yellow}, {"p", Tone::Purple},
	                                 {"m", Tone::Magic}, {"gold", Tone::Gold}, {"blue", Tone::ItemBlue}, {"green", Tone::Green}};
	for (const Name& n : names) {
		if (s == n.name) {
			t = n.tone;
			return true;
		}
	}
	return false;
}

// "-" | "<n>" | "<n>+<id><=<max>"
inline auto Cap(std::string_view s, Row& r) -> bool {
	if (s == "-") {
		return true;
	}
	const size_t plus = s.find('+');
	if (plus == std::string_view::npos) {
		return Int(s, r.capBase);
	}
	const size_t le = s.find("<=", plus);
	int32_t stat = 0;
	return le != std::string_view::npos && Int(s.substr(0, plus), r.capBase) && Int(s.substr(plus + 1, le - plus - 1), stat) && stat > 0 &&
	       stat <= 0xffff && Int(s.substr(le + 2), r.capMax) && (r.capStat = static_cast<uint16_t>(stat), true);
}

}  // namespace detail

// The book file (tools/statbook.py's format). A bad record stops the parse with `error` set and what came before kept.
inline auto ParseBook(std::string_view text) -> Book {
	Book b;
	std::vector<std::string_view> f;
	size_t lineNo = 0;
	auto fail = [&](const char* what) {
		b.error = "line " + std::to_string(lineNo) + ": " + what;
		return b;
	};
	size_t pos = 0;
	while (pos < text.size()) {
		size_t end = text.find('\n', pos);
		if (end == std::string_view::npos) {
			end = text.size();
		}
		std::string_view line = text.substr(pos, end - pos);
		pos = end + 1;
		++lineNo;
		if (!line.empty() && line.back() == '\r') {
			line.remove_suffix(1);
		}
		if (line.empty()) {
			continue;
		}
		const size_t n = detail::Split(line, f);
		if (lineNo == 1) {
			if (n < 2 || f[0] != "statbook" || f[1] != "1") {
				return fail("not a statbook 1 file");
			}
			continue;
		}
		if (f[0] == "page" && n == 3) {
			b.pages.push_back(Page{std::string(f[1]), std::string(f[2]), {}});
		} else if (f[0] == "section" && n == 2) {
			if (b.pages.empty()) {
				return fail("section before a page");
			}
			b.pages.back().sections.push_back(Section{std::string(f[1]), {}});
		} else if (f[0] == "row" && n == 8) {
			if (b.pages.empty() || b.pages.back().sections.empty()) {
				return fail("row before a section");
			}
			Row r;
			r.label = std::string(f[1]);
			std::vector<std::string_view> stats;
			for (size_t s = 0, k = 0; k <= f[2].size(); ++k) {
				if (k == f[2].size() || f[2][k] == ',') {
					stats.push_back(f[2].substr(s, k - s));
					s = k + 1;
				}
			}
			if (stats.empty() || stats.size() > 2) {
				return fail("one or two stats");
			}
			r.stats = static_cast<uint8_t>(stats.size());
			for (size_t k = 0; k < stats.size(); ++k) {
				if (!detail::Stat(stats[k], r.stat[k])) {
					return fail("bad stat");
				}
			}
			r.format = std::string(f[3]);
			if (!detail::Colour(f[4], r.colour) || !detail::Cap(f[5], r)) {
				return fail("bad colour or cap");
			}
			if (f[6] != "-") {
				const size_t comma = f[6].find(',');
				if (!detail::Int(f[6].substr(0, comma), r.base[0]) ||
				    (comma != std::string_view::npos && !detail::Int(f[6].substr(comma + 1), r.base[1]))) {
					return fail("bad base");
				}
			}
			r.half = f[7] == "h";
			b.pages.back().sections.back().rows.push_back(std::move(r));
		} else if (f[0] == "group" && n == 3) {
			b.all.push_back(AllGroup{std::string(f[1]), std::string(f[2]), {}});
		} else if (f[0] == "all" && n == 5) {
			if (b.all.empty()) {
				return fail("all row before a group");
			}
			AllRow a;
			a.kind = f[1] == "range" ? AllKind::Range : f[1] == "value" ? AllKind::Value : f[1] == "avoid" ? AllKind::Avoid : AllKind::Stat;
			a.stats = 0;
			for (size_t s = 0, k = 0; k <= f[2].size() && a.stats < 3; ++k) {
				if (k == f[2].size() || f[2][k] == ',') {
					int32_t v = 0;
					if (!detail::Int(f[2].substr(s, k - s), v) || v < 0 || v > 0xffff) {
						return fail("bad all stat");
					}
					a.stat[a.stats++] = static_cast<uint16_t>(v);
					s = k + 1;
				}
			}
			a.key = std::string(f[3]);
			a.english = std::string(f[4]);
			b.all.back().rows.push_back(std::move(a));
		} else {
			return fail("unknown record");
		}
	}
	return b;
}

// printf-like fill of `pattern` with `count` ints: %d, %+d and %% only (the pattern comes from a data file, so it is never
// handed to printf). A %d past the values prints 0.
inline auto Fill(std::string_view pattern, const int32_t* values, size_t count) -> std::string {
	std::string out;
	size_t next = 0;
	for (size_t i = 0; i < pattern.size(); ++i) {
		const char c = pattern[i];
		if (c == '%' && i + 1 < pattern.size() && pattern[i + 1] == '%') {
			out += '%';
			++i;
			continue;
		}
		const bool plus = c == '%' && i + 2 < pattern.size() && pattern[i + 1] == '+' && pattern[i + 2] == 'd';
		if (plus || (c == '%' && i + 1 < pattern.size() && pattern[i + 1] == 'd')) {
			const int32_t v = next < count ? values[next] : 0;
			++next;
			if (plus && v >= 0) {
				out += '+';
			}
			out += std::to_string(v);
			i += plus ? 2 : 1;
			continue;
		}
		out += c;
	}
	return out;
}

// Chance to Block (format "block"): not a stat. FillRow asks the host for it as this pseudo stat id; the plugin answers with
// D2R's own GetBlockRate for the client's player (block_rate_logic.h), the value the server rolls against.
inline constexpr uint16_t BlockRateStat = 0xffff;

struct Cell {
	std::string label, value;
	Tone tone = Tone::White;
};

// One row's value and tone. `values(id, classParam)` gives the stat as the sheet reads it (>> ValShift).
template <class Values>
auto FillRow(const Row& r, Values&& values) -> Cell {
	Cell c;
	c.label = r.label;
	int32_t raw[2] = {0, 0}, v[2] = {0, 0};
	for (uint8_t k = 0; k < r.stats; ++k) {
		raw[k] = values(r.stat[k].id, r.stat[k].classParam);
		v[k] = raw[k] + r.base[k];
	}
	if (r.format == "yesno") {
		c.value = raw[0] != 0 ? "yes" : "no";
	} else if (r.format == "block") {
		c.value = std::to_string(values(BlockRateStat, false)) + "%";
	} else {
		c.value = Fill(r.format, v, r.stats);
	}
	const bool zero = raw[0] == 0 && (r.stats < 2 || raw[1] == 0);
	if (r.capBase >= 0) {
		int32_t cap = r.capBase + (r.capStat != 0 ? values(r.capStat, false) : 0);
		if (r.capStat != 0 && cap > r.capMax) {
			cap = r.capMax;
		}
		c.tone = v[0] < 0 ? Tone::Red : v[0] >= cap ? Tone::Gold : zero ? Tone::Grey : r.colour;
		return c;
	}
	c.tone = zero ? Tone::Grey : v[0] < 0 ? Tone::Red : r.colour;
	return c;
}

// A page laid out in lines: a heading line, a full line of one row, or a line of two half rows (left, right).
struct Line {
	enum class Kind : uint8_t { Empty, Heading, Full, Pair } kind = Kind::Empty;
	std::string heading;
	Cell cell[2];
	bool right = false;  // a Pair line with its right half filled
};

// The page's lines from `first` on, at most `count`; returns the page's whole line count (for "more below").
template <class Values>
auto PageLines(const Page& p, Values&& values, size_t first, Line* out, size_t count) -> size_t {
	size_t n = 0;
	auto put = [&](Line&& l) {
		if (n >= first && n - first < count) {
			out[n - first] = std::move(l);
		}
		++n;
	};
	for (size_t i = 0; i < count; ++i) {
		out[i] = Line{};
	}
	for (const Section& s : p.sections) {
		Line h;
		h.kind = Line::Kind::Heading;
		h.heading = s.heading;
		put(std::move(h));
		Line pending;
		bool open = false;
		for (const Row& r : s.rows) {
			if (r.half) {
				if (open) {
					pending.cell[1] = FillRow(r, values);
					pending.right = true;
					put(std::move(pending));
					open = false;
				} else {
					pending = Line{};
					pending.kind = Line::Kind::Pair;
					pending.cell[0] = FillRow(r, values);
					open = true;
				}
				continue;
			}
			if (open) {
				put(std::move(pending));
				open = false;
			}
			Line l;
			l.kind = Line::Kind::Full;
			l.cell[0] = FillRow(r, values);
			put(std::move(l));
		}
		if (open) {
			put(std::move(pending));
		}
	}
	return n;
}

// ---- All Stats search -------------------------------------------------------------------------------------------------

inline auto Lower(char c) -> char {
	return c >= 'A' && c <= 'Z' ? static_cast<char>(c - 'A' + 'a') : c;
}

// Where `query` is in `text`, ignoring ASCII case; npos when not (an empty query is at 0).
inline auto Find(std::string_view text, std::string_view query) -> size_t {
	if (query.empty()) {
		return 0;
	}
	for (size_t i = 0; i + query.size() <= text.size(); ++i) {
		size_t k = 0;
		while (k < query.size() && Lower(text[i + k]) == Lower(query[k])) {
			++k;
		}
		if (k == query.size()) {
			return i;
		}
	}
	return std::string_view::npos;
}

// The All Stats texts as the host has them: a heading or a row. `match` / `length`: the highlighted part of a shown row.
struct ListLine {
	bool heading = false;
	std::string text;
};

struct Shown {
	size_t index = 0;   // into the ListLine list
	size_t match = std::string::npos;
	size_t length = 0;
};

// The lines the search keeps: every row whose text holds the query, under its group's heading (a heading whose own text
// holds it keeps its whole group); a group with nothing kept goes. Returns the count written (at most `cap`).
inline auto Search(const std::vector<ListLine>& lines, std::string_view query, Shown* out, size_t cap) -> size_t {
	size_t n = 0;
	for (size_t i = 0; i < lines.size();) {
		if (!lines[i].heading) {  // rows before any heading: their own group
			const size_t at = Find(lines[i].text, query);
			if (at != std::string_view::npos && n < cap) {
				out[n++] = Shown{i, query.empty() ? std::string::npos : at, query.size()};
			}
			++i;
			continue;
		}
		const size_t head = i++;
		const bool whole = !query.empty() && Find(lines[head].text, query) != std::string_view::npos;
		const size_t headAt = n;
		if (n < cap) {
			out[n++] = Shown{head, std::string::npos, 0};
		}
		size_t kept = 0;
		for (; i < lines.size() && !lines[i].heading; ++i) {
			const size_t at = Find(lines[i].text, query);
			if ((whole || at != std::string_view::npos) && n < cap) {
				out[n++] = Shown{i, query.empty() || at == std::string_view::npos ? std::string::npos : at, query.size()};
				++kept;
			}
		}
		if (kept == 0) {
			n = headAt;
		}
	}
	return n;
}

// ---- tabs --------------------------------------------------------------------------------------------------------------

// Tab 0 is the game's own sheet, 1..pages the themed pages, pages + 1 All Stats.
struct Tabs {
	int current = 0;
	int pages = 0;

	auto Count() const -> int {
		return pages + 2;
	}
	auto AllStats() const -> int {
		return pages + 1;
	}
	void Select(int tab) {
		if (tab >= 0 && tab < Count()) {
			current = tab;
		}
	}
	void Step(int by) {
		const int n = Count();
		current = ((current + by) % n + n) % n;
	}
	auto IsSheet() const -> bool {
		return current == 0;
	}
	auto Page() const -> int {  // index into Book::pages, -1 on the sheet and All Stats
		return current >= 1 && current <= pages ? current - 1 : -1;
	}
};

}  // namespace statbook

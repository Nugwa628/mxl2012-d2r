// The charm-tab summary's pure part: no game, no Windows headers (tests: invtabs/tests/summary_test.cpp).
//
// The summary adds up the stats of the charms that count and hands the totals to the game's own tooltip formatter
// (summary.cpp). This header does the arithmetic and the list handling around it:
//   Sum            raw values per (stat, param) over the items that count; inactive items are left out
//   OrderForDisplay the fallback order when only the one-stat formatter is there (descpriority, as the tooltip)
//   SplitLines     the formatter's text block into lines
//   Scroll / RowText which lines a fixed number of rows shows (the classic layout, which has no scroll view)
//   LayoutFragment the summary's widgets for the charm tab's layout (HD scroll view, classic fixed rows)
//   pattern scan   ParsePattern / FindUnique / RipTarget, for summary_natives.h
#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace invtabs::summary {

// One stat entry of an item's stat list. `param` is the entry's layer: the skill of +skill stats, the class of
// +class-skills, the tab of +skill-tab, 0 for most stats. `value` is raw (before itemstatcost valshift / op scaling),
// exactly as the list stores it.
struct StatValue {
	std::uint16_t stat  = 0;
	std::uint16_t param = 0;
	std::int32_t  value = 0;
	friend bool operator==(const StatValue&, const StatValue&) = default;
};

// One item: its stat entries and whether it counts. An item counts when the game has merged its stats into the
// player: a charm in the tab whose requirements are met and that is the active copy of a carry1 unique
// (docs/d2r-addresses.md 22c). The caller decides; Sum only honours the flag.
struct ItemStats {
	bool                   counts = true;
	std::vector<StatValue> stats;
};

// Raw totals per (stat, param) over the items that count, ordered by (stat, param). A total of 0 is dropped (the
// tooltip does not show a 0 either: +5 and -5 cancel). Totals are clamped to int32: the game's stat value is 32-bit.
inline std::vector<StatValue> Sum(const std::vector<ItemStats>& items) {
	std::map<std::pair<std::uint16_t, std::uint16_t>, std::int64_t> totals;
	for (const ItemStats& item : items) {
		if (!item.counts) continue;
		for (const StatValue& s : item.stats) totals[{ s.stat, s.param }] += s.value;
	}
	std::vector<StatValue> out;
	out.reserve(totals.size());
	constexpr std::int64_t lo = std::numeric_limits<std::int32_t>::min(), hi = std::numeric_limits<std::int32_t>::max();
	for (const auto& [key, total] : totals) {
		if (total == 0) continue;
		out.push_back({ key.first, key.second, static_cast<std::int32_t>(std::clamp(total, lo, hi)) });
	}
	return out;
}

// What itemstatcost says about a stat, for the fallback order. shown = the stat has a tooltip description (descfunc
// not 0); stats without one (hidden) never become a line.
struct StatInfo {
	int  descpriority = 0;
	bool shown        = false;
};

// The tooltip order: higher descpriority first; equal priorities by stat id, then param (the game's priority table is
// built in stat order). Hidden stats are dropped. `info(stat)` returns std::optional<StatInfo>; nullopt = unknown stat,
// dropped as well.
template <class InfoFn>
std::vector<StatValue> OrderForDisplay(std::vector<StatValue> totals, InfoFn&& info) {
	std::vector<std::pair<int, StatValue>> keyed;
	keyed.reserve(totals.size());
	for (const StatValue& s : totals) {
		const std::optional<StatInfo> i = info(s.stat);
		if (i && i->shown) keyed.push_back({ i->descpriority, s });
	}
	std::stable_sort(keyed.begin(), keyed.end(), [](const auto& a, const auto& b) {
		if (a.first != b.first) return a.first > b.first;
		if (a.second.stat != b.second.stat) return a.second.stat < b.second.stat;
		return a.second.param < b.second.param;
	});
	std::vector<StatValue> out;
	out.reserve(keyed.size());
	for (const auto& k : keyed) out.push_back(k.second);
	return out;
}

// The formatter's block into lines: split at '\n', drop '\r', drop empty lines. D2R's colour codes stay in.
inline std::vector<std::string> SplitLines(std::string_view text) {
	std::vector<std::string> out;
	std::string              line;
	const auto               flush = [&] {
		if (!line.empty()) out.push_back(line);
		line.clear();
	};
	for (const char c : text) {
		if (c == '\n') flush();
		else if (c != '\r') line.push_back(c);
	}
	flush();
	return out;
}

// The stat block writer (0x2da760) emits the lowest descpriority first; the item tooltip shows the highest on top (checked in
// the game: Azmodan's Heart test charm, "+1 to Sorceress Skill Levels" (150) above "+3 to Strength" (67)). One stat's line
// is one line, so reversing the lines gives the tooltip's order.
inline std::vector<std::string> TooltipOrder(std::vector<std::string> lines) {
	std::reverse(lines.begin(), lines.end());
	return lines;
}

// D2R's colour code is U+00FF 'c' plus one character ("\xC3\xBF" "c" "3" in UTF-8; the single byte 0xFF in the
// classic code page). StripColour removes them, for logs and for comparing with tooltip text.
inline std::string StripColour(std::string_view text) {
	std::string out;
	out.reserve(text.size());
	for (std::size_t i = 0; i < text.size();) {
		if (i + 3 < text.size() && static_cast<unsigned char>(text[i]) == 0xC3 && static_cast<unsigned char>(text[i + 1]) == 0xBF && text[i + 2] == 'c') {
			i += 4;
			continue;
		}
		if (i + 2 < text.size() && static_cast<unsigned char>(text[i]) == 0xFF && text[i + 1] == 'c') {
			i += 3;
			continue;
		}
		out.push_back(text[i]);
		++i;
	}
	return out;
}

// The most lines the summary keeps. A full tab of charms with every stat distinct stays far below it; past it the
// last kept line says how many were left out (MoreLine), so a runaway list cannot grow the layout without bound.
inline constexpr std::size_t MaxLines = 160;

inline std::string MoreLine(std::size_t hidden) { return "... +" + std::to_string(hidden); }

inline std::vector<std::string> CapLines(std::vector<std::string> lines, std::size_t max = MaxLines) {
	if (max == 0) return {};
	if (lines.size() <= max) return lines;
	const std::size_t hidden = lines.size() - (max - 1);
	lines.resize(max - 1);
	lines.push_back(MoreLine(hidden));
	return lines;
}

// The classic layout shows `rows` lines at a time, starting at `first`. ClampFirst keeps the window inside the list;
// Scroll moves it by `delta` lines (a wheel notch is one line, negative = up).
inline std::size_t ClampFirst(long long first, std::size_t total, std::size_t rows) {
	if (first < 0 || total <= rows) return 0;
	const std::size_t last = total - rows;
	return static_cast<std::size_t>(first) > last ? last : static_cast<std::size_t>(first);
}

inline std::size_t Scroll(std::size_t first, long long delta, std::size_t total, std::size_t rows) {
	return ClampFirst(static_cast<long long>(first) + delta, total, rows);
}

// Row i of a window showing `rows` lines from `first`: the line's text, or "" past the end.
inline std::string RowText(const std::vector<std::string>& lines, std::size_t first, std::size_t row) {
	const std::size_t i = first + row;
	return i < lines.size() ? lines[i] : std::string();
}

// --- layout fragment --------------------------------------------------------------------------------------------------
// The summary's widgets, for the core to put into the charm tab's layout above the grid (docs/invtabs-summary.md "UI").
//
// HD: a ScrollViewWidget (clipChildrenDraw) holding one TextBoxWidget per line, and a ScrollControllerWidget with the
// arrows and bar of D2R's own scroll lists (EULA, Chronicle). The view scrolls with the wheel over it and with the bar;
// the row count is fixed when the layout is registered, so the core registers it with LayoutRows() rows (the core
// re-registers the tab layout before it opens the tab).
// Classic: D2R's classic UI has no scroll view (its Advanced Stats panel is HD only), so the classic fragment is a fixed
// window of VisibleRows() lines; Scroll() moves the window and the texts are set again (the core forwards the wheel).

enum class LayoutMode { Hd, Classic };

struct Rect {
	int x = 0, y = 0, width = 0, height = 0;
};

inline constexpr int HdRowPitch = 32, HdRowHeight = 30, HdBarWidth = 26, HdBarGap = 10;
inline constexpr int ClassicRowPitch = 13, ClassicRowHeight = 12;

inline constexpr char ScrollViewName[] = "SummaryView";
inline constexpr char ScrollBarName[]  = "SummaryScroll";

inline std::string RowName(std::size_t i) { return "SummaryLine" + std::to_string(i); }

inline std::size_t VisibleRows(LayoutMode mode, int height) {
	const int pitch = mode == LayoutMode::Hd ? HdRowPitch : ClassicRowPitch;
	return height <= 0 ? 0 : static_cast<std::size_t>(height / pitch);
}

// Rows to register: HD one per line (at least a screenful, at most MaxLines); classic the window.
inline std::size_t LayoutRows(LayoutMode mode, int height, std::size_t lineCount) {
	const std::size_t visible = VisibleRows(mode, height);
	if (mode == LayoutMode::Classic) return visible;
	return std::min(std::max(lineCount, visible), MaxLines);
}

// A layout registered with `rows` rows shows `lineCount` lines without being registered again.
inline bool Fits(LayoutMode mode, std::size_t rows, std::size_t lineCount) {
	return mode == LayoutMode::Classic || lineCount <= rows || rows >= MaxLines;
}

inline std::string JsonRect(int x, int y, int w, int h) {
	return "{ \"x\": " + std::to_string(x) + ", \"y\": " + std::to_string(y) + ", \"width\": " + std::to_string(w) + ", \"height\": " + std::to_string(h) + " }";
}

inline std::string RowWidget(LayoutMode mode, std::size_t i, int x, int y, int width) {
	const bool hd = mode == LayoutMode::Hd;
	std::string style = hd ? "{ \"fontColor\": \"$FontColorBlue\", \"pointSize\": \"$SmallFontSize\", \"alignment\": { \"h\": \"center\", \"v\": \"center\" } }"
	                       : "{ \"fontColor\": { \"r\": 110, \"g\": 110, \"b\": 255, \"a\": 255 }, \"alignment\": { \"h\": \"center\", \"v\": \"center\" } }";
	return "{ \"type\": \"TextBoxWidget\", \"name\": \"" + RowName(i) + "\", \"fields\": { \"rect\": " +
	       JsonRect(x, y, width, hd ? HdRowHeight : ClassicRowHeight) + ", \"text\": \"\", \"style\": " + style + (hd ? "" : ", \"fontType\": \"8pt\"") + " } }";
}

// The widgets as a comma-separated list of JSON objects, to splice into the panel's "children" array. `area` is in the
// panel's coordinates (the band the core reserves above the charm grid).
inline std::string LayoutFragment(LayoutMode mode, Rect area, std::size_t rows) {
	std::string out;
	if (mode == LayoutMode::Classic) {
		for (std::size_t i = 0; i < rows; ++i) {
			if (i) out += ",\n";
			out += RowWidget(mode, i, area.x, area.y + static_cast<int>(i) * ClassicRowPitch, area.width);
		}
		return out;
	}
	const int viewWidth = area.width - HdBarWidth - HdBarGap;
	out += "{ \"type\": \"ScrollViewWidget\", \"name\": \"" + std::string(ScrollViewName) + "\", \"fields\": { \"rect\": " +
	       JsonRect(area.x, area.y, viewWidth, area.height) + ", \"scrollControllerName\": \"" + ScrollBarName +
	       "\", \"clipChildrenDraw\": true }, \"children\": [\n";
	for (std::size_t i = 0; i < rows; ++i) {
		if (i) out += ",\n";
		out += RowWidget(mode, i, 0, static_cast<int>(i) * HdRowPitch, viewWidth);
	}
	out += "\n] },\n";
	out += "{ \"type\": \"ScrollControllerWidget\", \"name\": \"" + std::string(ScrollBarName) + "\", \"fields\": { \"rect\": " +
	       JsonRect(area.x + area.width - HdBarWidth, area.y, HdBarWidth, area.height) +
	       ", \"upArrowFilepath\": \"FrontEnd/HD/Final/FrontEnd_ScrollUpBtn\", \"downArrowFilepath\": \"FrontEnd/HD/Final/FrontEnd_ScrollDownBtn\""
	       ", \"barFilepath\": \"PauseMenu/VerticalIndicator\", \"viewName\": \"" + ScrollViewName +
	       "\", \"wheelScrollSound\": \"cursor_scroll_hd\", \"buttonScrollSound\": \"cursor_scroll_hd\" } }";
	return out;
}

// --- pattern scan (the same format as invtabs_logic.h, kept here so the module stands alone) ---------------------------

// "48 8B ?? 05" -> {0x48, 0x8B, -1, 0x05}; empty on a malformed pattern or one that starts with a wildcard.
inline std::vector<int> ParsePattern(std::string_view text) {
	std::vector<int> out;
	const auto       hex = [](char c) -> int {
		if (c >= '0' && c <= '9') return c - '0';
		if (c >= 'a' && c <= 'f') return c - 'a' + 10;
		if (c >= 'A' && c <= 'F') return c - 'A' + 10;
		return -1;
	};
	std::size_t i = 0;
	while (i < text.size()) {
		if (text[i] == ' ') {
			++i;
			continue;
		}
		if (i + 1 >= text.size() || (i + 2 < text.size() && text[i + 2] != ' ')) return {};
		if (text[i] == '?' && text[i + 1] == '?') out.push_back(-1);
		else {
			const int hi = hex(text[i]), lo = hex(text[i + 1]);
			if (hi < 0 || lo < 0) return {};
			out.push_back(hi << 4 | lo);
		}
		i += 2;
	}
	if (!out.empty() && out.front() < 0) return {};
	return out;
}

// Offsets where the pattern matches, at most `limit`.
inline std::vector<std::size_t> FindPattern(const std::uint8_t* data, std::size_t size, const std::vector<int>& pattern, std::size_t limit = 2) {
	std::vector<std::size_t> hits;
	if (pattern.empty() || size < pattern.size()) return hits;
	const auto first = static_cast<std::uint8_t>(pattern.front());
	for (std::size_t at = 0; at + pattern.size() <= size && hits.size() < limit; ++at) {
		if (data[at] != first) continue;
		std::size_t k = 1;
		while (k < pattern.size() && (pattern[k] < 0 || data[at + k] == static_cast<std::uint8_t>(pattern[k]))) ++k;
		if (k == pattern.size()) hits.push_back(at);
	}
	return hits;
}

// The one match, or nullopt when the pattern is malformed, missing or ambiguous.
inline std::optional<std::size_t> FindUnique(const std::uint8_t* data, std::size_t size, std::string_view text) {
	const auto hits = FindPattern(data, size, ParsePattern(text), 2);
	if (hits.size() != 1) return std::nullopt;
	return hits.front();
}

// The address a rel32 / RIP disp32 at `dispAt` points to (both are relative to the end of the 4 bytes).
inline std::int64_t RipTarget(const std::uint8_t* image, std::size_t dispAt) {
	std::uint32_t raw = 0;
	for (int k = 3; k >= 0; --k) raw = raw << 8 | image[dispAt + static_cast<std::size_t>(k)];
	return static_cast<std::int64_t>(dispAt) + 4 + static_cast<std::int32_t>(raw);
}

} // namespace invtabs::summary

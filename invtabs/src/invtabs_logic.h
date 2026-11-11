// invtabs: the pure part (no Windows headers, no game): signature patterns, tab areas on the 16 x 16 page, the grid
// marker, the tab type rule and the config reader. Tested by tests/invtabs_test.cpp.
//
// Area geometry, packing and the grid marker follow wild-healer's aaa-player-page-host (D2R-Tools, no licence file,
// github.com/wild-healer/D2R-Tools, commit 6722cc5); the pinned charm tab and the config reader are ours.
#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <optional>
#include <string>
#include <string_view>
#include <set>
#include <vector>

#include "tab_config.h"

namespace invtabs {

// ---- signature patterns ----

// "48 8B ?? 05": each byte, -1 for a wildcard. Empty on a malformed pattern.
inline std::vector<int> ParsePattern(std::string_view text) {
	std::vector<int> out;
	std::size_t      i = 0;
	const auto       hex = [](char c) -> int {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        return -1;
	};
	while (i < text.size()) {
		if (text[i] == ' ') {
			++i;
			continue;
		}
		if (i + 1 >= text.size()) return {};
		if (text[i] == '?' && text[i + 1] == '?') out.push_back(-1);
		else {
			const int hi = hex(text[i]), lo = hex(text[i + 1]);
			if (hi < 0 || lo < 0) return {};
			out.push_back(hi * 16 + lo);
		}
		i += 2;
		if (i < text.size() && text[i] != ' ') return {};
	}
	if (!out.empty() && (out.front() < 0)) return {}; // the scan anchors on the first byte
	return out;
}

// Offsets of up to `limit` matches of `pattern` in data[0..size).
inline std::vector<std::size_t> FindPattern(const std::uint8_t* data, std::size_t size, const std::vector<int>& pattern, std::size_t limit = 2) {
	std::vector<std::size_t> hits;
	if (pattern.empty() || size < pattern.size()) return hits;
	const auto first = static_cast<std::uint8_t>(pattern.front());
	for (std::size_t at = 0; at + pattern.size() <= size && hits.size() < limit; ++at) {
		if (data[at] != first) continue;
		bool same = true;
		for (std::size_t k = 1; k < pattern.size() && same; ++k) same = pattern[k] < 0 || data[at + k] == pattern[k];
		if (same) hits.push_back(at);
	}
	return hits;
}

// The one match, else nothing (none or several).
inline std::optional<std::size_t> FindUnique(const std::uint8_t* data, std::size_t size, std::string_view text) {
	const auto hits = FindPattern(data, size, ParsePattern(text), 2);
	if (hits.size() != 1) return std::nullopt;
	return hits.front();
}

// A RIP-relative target: the disp32 at `dispAt` (offset in the image), relative to the end of the disp32.
inline std::int64_t RipTarget(const std::uint8_t* image, std::size_t dispAt) {
	std::int32_t disp = 0;
	for (int k = 3; k >= 0; --k) disp = static_cast<std::int32_t>(static_cast<std::uint32_t>(disp) << 8 | image[dispAt + k]);
	return static_cast<std::int64_t>(dispAt) + 4 + disp;
}

// Where a signature points in the image (an RVA), or -1 when it does not match exactly once in the .text section
// (`textRva`, `textSize`). `P` has pattern, rip (>= 0: disp32 offset in the match) and adjust (target = match + adjust).
template <typename P>
inline std::int64_t ResolveNative(const std::uint8_t* image, std::size_t textRva, std::size_t textSize, const P& native) {
	const auto hits = FindPattern(image + textRva, textSize, ParsePattern(native.pattern), 2);
	if (hits.size() != 1) return -1;
	const std::size_t at = textRva + hits.front();
	return native.rip >= 0 ? RipTarget(image, at + static_cast<std::size_t>(native.rip)) : static_cast<std::int64_t>(at) + native.adjust;
}

// ---- the page and its areas ----

inline constexpr int PageSize = 16;
inline constexpr int MaxTabs  = 12;

struct Area {
	int x = -1, y = -1, w = 0, h = 0;
	bool placed() const { return x >= 0 && y >= 0 && w > 0 && h > 0; }
};

inline bool Inside(const Area& a, int x, int y, int w = 1, int h = 1) {
	return a.placed() && x >= a.x && y >= a.y && x + w <= a.x + a.w && y + h <= a.y + a.h;
}

inline bool Overlap(const Area& a, const Area& b) {
	return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

// Grid cells are packed as (y << 32) | x, as the game's grid passes them.
inline constexpr std::uint64_t NoCell = ~std::uint64_t { 0 };
constexpr std::uint64_t PackCell(int x, int y) { return static_cast<std::uint64_t>(static_cast<std::uint32_t>(y)) << 32 | static_cast<std::uint32_t>(x); }
constexpr int           CellX(std::uint64_t cell) { return static_cast<std::int32_t>(cell & 0xFFFFFFFF); }
constexpr int           CellY(std::uint64_t cell) { return static_cast<std::int32_t>(cell >> 32); }

// A page cell inside the area -> the widget's own cell (the area shows at the grid's corner); else unchanged.
inline std::uint64_t PageToWidget(const Area& a, std::uint64_t cell) {
	if (cell == NoCell || !Inside(a, CellX(cell), CellY(cell))) return cell;
	return PackCell(CellX(cell) - a.x, CellY(cell) - a.y);
}

// The widget cell under the mouse -> the page cell an item of w x h would take, or NoCell when it would leave the area.
inline std::uint64_t WidgetToPage(const Area& a, std::uint64_t widgetCell, int w, int h) {
	if (widgetCell == NoCell || !a.placed()) return NoCell;
	const int x = CellX(widgetCell) + a.x, y = CellY(widgetCell) + a.y;
	return Inside(a, x, y, w, h) ? PackCell(x, y) : NoCell;
}

// Places every tab that has no place yet. Tabs with a preset place (x, y >= 0) stay where they are; the others go
// largest area first, then taller first (stable), at the first free row then column, no rotation. False when one does
// not fit or two preset places overlap.
inline bool PackAreas(std::vector<Area>& areas) {
	std::vector<std::size_t> order;
	for (std::size_t i = 0; i < areas.size(); ++i) {
		const auto& a = areas[i];
		if (a.w < 1 || a.h < 1 || a.w > PageSize || a.h > PageSize) return false;
		if (a.x >= 0 || a.y >= 0) {
			if (a.x < 0 || a.y < 0 || a.x + a.w > PageSize || a.y + a.h > PageSize) return false;
			for (std::size_t j = 0; j < i; ++j)
				if ((areas[j].x >= 0) && Overlap(a, areas[j])) return false;
		} else order.push_back(i);
	}
	std::stable_sort(order.begin(), order.end(), [&](std::size_t l, std::size_t r) {
		const int al = areas[l].w * areas[l].h, ar = areas[r].w * areas[r].h;
		return al != ar ? al > ar : areas[l].h > areas[r].h;
	});
	for (const std::size_t i : order) {
		Area& a     = areas[i];
		bool  found = false;
		for (int y = 0; y + a.h <= PageSize && !found; ++y)
			for (int x = 0; x + a.w <= PageSize && !found; ++x) {
				const Area spot { x, y, a.w, a.h };
				bool       free = true;
				for (const auto& other : areas)
					if (&other != &a && other.placed() && Overlap(spot, other)) free = false;
				if (free) a.x = x, a.y = y, found = true;
			}
		if (!found) return false;
	}
	return true;
}

// The area holding a page cell (an item's top-left), or -1.
inline int AreaAt(const std::vector<Area>& areas, int x, int y) {
	for (std::size_t i = 0; i < areas.size(); ++i)
		if (Inside(areas[i], x, y)) return static_cast<int>(i);
	return -1;
}

// ---- grid marker ----
// Our grid widgets carry chronicleFlourishOffset {MarkerBase + slot, MarkerBase} in HD layouts and
// {MarkerBase + slot, MarkerBase + 1} in classic ones; slot MaxTabs is the whole-page view.

inline constexpr float MarkerBase = 7400.0f;
inline constexpr int   AllSlot    = MaxTabs;

inline bool ClassicMarker(float second) { return second == MarkerBase + 1.0f; }

inline int SlotOfMarker(float first, float second) {
	if (second != MarkerBase && !ClassicMarker(second)) return -1;
	const float slot = first - MarkerBase;
	if (slot < 0.0f || slot > static_cast<float>(AllSlot)) return -1;
	const int whole = static_cast<int>(slot);
	return static_cast<float>(whole) == slot ? whole : -1;
}

// ---- the type rule ----

using TypeCode = std::string; // an itemtypes code, 1..4 characters

// The four-byte code as D2RLoader's ItemTypeFourCC holds it (space or NUL padded) -> trimmed text.
inline TypeCode TrimCode(const char (&value)[4]) {
	std::string out(value, 4);
	while (!out.empty() && (out.back() == ' ' || out.back() == '\0')) out.pop_back();
	return out;
}

// True when one of the item's types (its own type and its Equiv parents, as D2RLoader gives them) is accepted.
inline bool Accepts(const std::vector<TypeCode>& accepted, const std::vector<TypeCode>& itemTypes) {
	for (const auto& type : itemTypes)
		if (std::find(accepted.begin(), accepted.end(), type) != accepted.end()) return true;
	return false;
}

inline std::vector<TypeCode> CharmFallbackTypes() { return { "char" }; }

// ---- config ----
// Reads invtabs.toml: a tiny TOML subset (sections, `key = value`, "strings", ["arrays"], # comments). The tab list is
// the `[tabs.<name>]` sections in file order (the data lane's schema, docs/invtabs-data.md); every tab is checked with
// tab_config.h's rules and placed by PlanTabs below.

// CharmInv 1.0.1 saved 10 x 4: a smaller charm tab would leave its charms outside.
inline constexpr int         MinCharmColumns = 10, MinCharmRows = 4;
inline constexpr const char* CharmTabName    = "charms";

struct Config {
	bool                     enabled         = true;
	bool                     inventoryCharms = true;
	bool                     openButton      = true;
	int                      openKey         = 73; // Windows virtual key of the Controls action (0: none)
	std::vector<Tab>         tabs;     // toml order; Tab is tab_config.h's (x, y -1 unless the toml sets them)
	std::vector<std::string> problems; // one log line each
};

inline std::string_view Trim(std::string_view s) {
	while (!s.empty() && (s.front() == ' ' || s.front() == '\t' || s.front() == '\r')) s.remove_prefix(1);
	while (!s.empty() && (s.back() == ' ' || s.back() == '\t' || s.back() == '\r')) s.remove_suffix(1);
	return s;
}

// "text" -> text; anything else -> nullopt.
inline std::optional<std::string> Quoted(std::string_view v) {
	v = Trim(v);
	if (v.size() < 2 || v.front() != '"' || v.back() != '"') return std::nullopt;
	v = v.substr(1, v.size() - 2);
	if (v.find('"') != std::string_view::npos || v.find('\\') != std::string_view::npos) return std::nullopt;
	return std::string(v);
}

// ["a", "b"] -> {a, b}; anything else -> nullopt.
inline std::optional<std::vector<std::string>> QuotedList(std::string_view v) {
	v = Trim(v);
	if (v.size() < 2 || v.front() != '[' || v.back() != ']') return std::nullopt;
	v = Trim(v.substr(1, v.size() - 2));
	std::vector<std::string> out;
	while (!v.empty()) {
		const auto comma = v.find(',');
		const auto one   = Quoted(v.substr(0, comma));
		if (!one) return std::nullopt;
		out.push_back(*one);
		v = comma == std::string_view::npos ? std::string_view {} : Trim(v.substr(comma + 1));
	}
	return out;
}

// '#' starts a comment outside a string.
inline std::string_view StripComment(std::string_view line) {
	bool quoted = false;
	for (std::size_t i = 0; i < line.size(); ++i) {
		if (line[i] == '"') quoted = !quoted;
		else if (line[i] == '#' && !quoted) return line.substr(0, i);
	}
	return line;
}

inline Config ParseConfig(std::string_view text) {
	Config      c;
	std::string section;
	std::size_t tab = 0; // index + 1 into c.tabs, 0: not a tab section
	while (!text.empty()) {
		const auto       end  = text.find('\n');
		std::string_view line = text.substr(0, end);
		text                  = end == std::string_view::npos ? std::string_view {} : text.substr(end + 1);
		line                  = Trim(StripComment(line));
		if (line.empty()) continue;
		if (line.front() == '[') {
			const auto close = line.find(']');
			section          = std::string(Trim(line.substr(1, close == std::string_view::npos ? std::string_view::npos : close - 1)));
			tab              = 0;
			if (section.rfind("tabs.", 0) == 0) {
				const std::string name = section.substr(5);
				for (std::size_t i = 0; i < c.tabs.size(); ++i)
					if (c.tabs[i].name == name) tab = i + 1;
				if (!tab) {
					Tab t;
					t.name = name;
					if (name == CharmTabName) t.columns = 10, t.rows = 6;
					c.tabs.push_back(t);
					tab = c.tabs.size();
				}
			}
			continue;
		}
		const auto eq = line.find('=');
		if (eq == std::string_view::npos) continue;
		const std::string      key(Trim(line.substr(0, eq)));
		const std::string_view value = Trim(line.substr(eq + 1));
		const auto             bad   = [&] { c.problems.push_back("[" + section + "] " + key + ": unreadable value, ignored"); };
		const auto             flag  = [&](bool& out) {
            if (value == "true") out = true;
            else if (value == "false") out = false;
            else bad();
		};
		const auto number = [&](int& out) {
			const std::string digits(value);
			char*             stop = nullptr;
			const long        v    = std::strtol(digits.c_str(), &stop, 10);
			if (digits.empty() || !stop || *stop != '\0' || v < 0 || v > 255) return bad();
			out = static_cast<int>(v);
		};
		if (section == "invtabs") {
			if (key == "enabled") flag(c.enabled);
			else if (key == "inventory_charms") flag(c.inventoryCharms);
			else if (key == "open_button") flag(c.openButton);
			else if (key == "open_key") number(c.openKey);
		} else if (tab) {
			Tab& t = c.tabs[tab - 1];
			if (key == "columns") number(t.columns);
			else if (key == "rows") number(t.rows);
			else if (key == "x") number(t.x);
			else if (key == "y") number(t.y);
			else if (key == "label") {
				if (const auto s = Quoted(value)) t.label = *s;
				else bad();
			} else if (key == "types") {
				if (const auto s = Quoted(value)) t.typesFile = *s;
				else bad();
			} else if (key == "item_types") {
				if (const auto l = QuotedList(value)) t.types = *l;
				else bad();
			}
		}
	}
	for (auto& t : c.tabs) {
		if (t.label.empty()) t.label = t.name;
		if (t.typesFile.empty() && t.types.empty()) t.typesFile = "types_" + t.name + ".txt";
	}
	return c;
}

// tab_config.h's table rules for one tab given in the toml. Empty when fine.
inline std::string CheckTab(const Tab& t) {
	if (!Token(t.name)) return "tab name '" + t.name + "': letters, digits, _ and - only";
	if (t.columns < 1 || t.columns > PageSize || t.rows < 1 || t.rows > PageSize) return "tab " + t.name + ": columns and rows must be 1..16";
	if (t.label.empty()) return "tab " + t.name + ": empty label";
	for (const unsigned char ch : t.label)
		if (ch < 32 || ch >= 127) return "tab " + t.name + ": the label must be printable ASCII";
	if (!t.typesFile.empty()) {
		const auto& f = t.typesFile;
		if (f.size() <= 10 || f.substr(0, 6) != "types_" || f.substr(f.size() - 4) != ".txt" || !Token(f.substr(6, f.size() - 10)))
			return "tab " + t.name + ": types must be a file name types_<name>.txt";
	}
	for (const auto& code : t.types)
		if (!Code(code)) return "tab " + t.name + ": item type '" + code + "' is not an itemtypes code";
	if ((t.x >= 0) != (t.y >= 0)) return "tab " + t.name + ": give both x and y, or neither";
	return {};
}

// ---- the tab plan: where each tab goes, and the refusals that keep items reachable ----
// The plugin remembers the layout it last used (name, rectangle, and the box of cells items were seen in, per tab) in a
// small text file beside its config. A new config is refused as a whole, and the remembered layout used again, when it
// would leave a remembered item box outside its tab (a tab shrunk, moved or removed under items), when two rectangles
// overlap, or when the tabs do not fit the page. Remembered tabs keep their place; new tabs are packed around them.

struct Remembered {
	std::string name;
	Area        area;
	Area        used; // placed() false: no item seen in it
};

inline bool Contains(const Area& outer, const Area& inner) { return Inside(outer, inner.x, inner.y, inner.w, inner.h); }

// Grows `used` to cover the w x h item at x, y.
inline void AddUsed(Area& used, int x, int y, int w, int h) {
	if (!used.placed()) {
		used = { x, y, w, h };
		return;
	}
	const int x1 = std::max(used.x + used.w, x + w), y1 = std::max(used.y + used.h, y + h);
	used.x = std::min(used.x, x), used.y = std::min(used.y, y);
	used.w = x1 - used.x, used.h = y1 - used.y;
}

// One line per tab: name x y w h ux uy uw uh (ux -1: nothing seen).
inline std::string FormatMemory(const std::vector<Remembered>& tabs) {
	std::string out = "# invtabs: where each tab sits on the page (name x y w h) and the box its items reach (-1 -1 0 0: none seen).\n"
	                  "# A config that would leave an item outside its tab is refused. Delete this file to forget it.\n";
	for (const auto& r : tabs) {
		const Area u = r.used.placed() ? r.used : Area { -1, -1, 0, 0 };
		out += r.name + ' ' + std::to_string(r.area.x) + ' ' + std::to_string(r.area.y) + ' ' + std::to_string(r.area.w) + ' ' + std::to_string(r.area.h) + ' ' + std::to_string(u.x) + ' '
		     + std::to_string(u.y) + ' ' + std::to_string(u.w) + ' ' + std::to_string(u.h) + '\n';
	}
	return out;
}

// Unreadable lines are skipped.
inline std::vector<Remembered> ParseMemory(std::string_view text) {
	std::vector<Remembered> out;
	while (!text.empty()) {
		const auto       end  = text.find('\n');
		std::string_view line = Trim(text.substr(0, end));
		text                  = end == std::string_view::npos ? std::string_view {} : text.substr(end + 1);
		if (line.empty() || line.front() == '#') continue;
		std::vector<std::string> f;
		while (!line.empty()) {
			const auto sp = line.find(' ');
			f.emplace_back(line.substr(0, sp));
			line = sp == std::string_view::npos ? std::string_view {} : Trim(line.substr(sp + 1));
		}
		if (f.size() != 9 || !Token(f[0])) continue;
		int  v[8] {};
		bool ok = true;
		for (std::size_t i = 0; i < 8 && ok; ++i) {
			char*      stop = nullptr;
			const long n    = std::strtol(f[i + 1].c_str(), &stop, 10);
			ok              = stop && *stop == '\0' && !f[i + 1].empty() && n >= -1 && n <= PageSize;
			v[i]            = static_cast<int>(n);
		}
		Remembered r { f[0], { v[0], v[1], v[2], v[3] }, { v[4], v[5], v[6], v[7] } };
		if (!ok || !r.area.placed() || r.area.x + r.area.w > PageSize || r.area.y + r.area.h > PageSize) continue;
		if (!r.used.placed() || !Contains({ 0, 0, PageSize, PageSize }, r.used)) r.used = {};
		out.push_back(r);
	}
	return out;
}

struct Plan {
	std::vector<Tab>         tabs;  // tab 0 is the charm tab
	std::vector<Area>        areas; // same order
	bool                     refused = false;
	std::vector<std::string> notes; // log lines (a refusal first)
};

inline Plan PlanTabs(std::vector<Tab> wanted, const std::vector<Remembered>& memory) {
	Plan        plan;
	std::string refusal;
	// the charm tab: always there, first, at 0,0, at least CharmInv's 10 x 4
	const auto charm = std::find_if(wanted.begin(), wanted.end(), [](const Tab& t) { return t.name == CharmTabName; });
	if (charm == wanted.end()) {
		plan.notes.push_back("no [tabs.charms] in the config: the charm tab is added (10 x 6)");
		wanted.insert(wanted.begin(), CharmFallback());
	} else std::rotate(wanted.begin(), charm, charm + 1);
	Tab& c = wanted.front();
	if (c.columns < MinCharmColumns || c.rows < MinCharmRows) {
		plan.notes.push_back("the charm tab is at least 10 x 4 (CharmInv's charms must fit): " + std::to_string(c.columns) + " x " + std::to_string(c.rows) + " raised");
		c.columns = std::max(c.columns, MinCharmColumns), c.rows = std::max(c.rows, MinCharmRows);
	}
	if (c.x >= 0 && (c.x != 0 || c.y != 0)) plan.notes.push_back("the charm tab stays at 0,0 (its x, y are ignored)");
	c.x = 0, c.y = 0;
	if (wanted.size() > static_cast<std::size_t>(MaxTabs)) refusal = "more than 12 tabs";
	std::set<std::string> names;
	for (const auto& t : wanted) {
		if (!refusal.empty()) break;
		if (!names.insert(t.name).second) refusal = "tab " + t.name + " is given twice";
		else refusal = CheckTab(t);
	}
	// places: remembered tabs keep theirs, else the toml's x, y, else packing
	std::vector<Area> areas;
	for (std::size_t i = 0; i < wanted.size(); ++i) {
		const Tab& t = wanted[i];
		Area       a { t.x, t.y, t.columns, t.rows };
		if (i > 0)
			for (const auto& r : memory)
				if (r.name == t.name) a.x = r.area.x, a.y = r.area.y;
		areas.push_back(a);
	}
	if (refusal.empty() && !PackAreas(areas)) refusal = "the tabs overlap or do not fit the 16 x 16 page";
	for (const auto& r : memory) {
		if (!refusal.empty()) break;
		if (!r.used.placed()) continue;
		const auto at = std::find_if(wanted.begin(), wanted.end(), [&](const Tab& t) { return t.name == r.name; });
		if (at == wanted.end()) {
			refusal = "tab " + r.name + " is gone from the config but held items";
			break;
		}
		const Area& n = areas[static_cast<std::size_t>(at - wanted.begin())];
		if (!Contains(n, r.used))
			refusal = "tab " + r.name + " " + std::to_string(n.w) + "x" + std::to_string(n.h) + " at " + std::to_string(n.x) + "," + std::to_string(n.y) + " would leave items seen in cells "
			        + std::to_string(r.used.x) + "," + std::to_string(r.used.y) + " to " + std::to_string(r.used.x + r.used.w - 1) + "," + std::to_string(r.used.y + r.used.h - 1) + " outside it";
	}
	if (refusal.empty()) {
		for (std::size_t i = 0; i < wanted.size(); ++i) wanted[i].x = areas[i].x, wanted[i].y = areas[i].y;
		plan.tabs = wanted, plan.areas = areas;
		return plan;
	}
	// refused: the remembered layout (charm tab first), labels and types from the config where the name is still there
	plan.refused = true;
	plan.notes.insert(plan.notes.begin(), "config refused (" + refusal + "): the previous tab layout stays");
	std::vector<Tab>  tabs;
	std::vector<Area> kept;
	for (const auto& r : memory) {
		Tab        t;
		const auto at = std::find_if(wanted.begin(), wanted.end(), [&](const Tab& w) { return w.name == r.name; });
		if (at != wanted.end() && CheckTab(*at).empty()) t = *at;
		else {
			t.name = r.name, t.label = r.name;
			t.typesFile = "types_" + r.name + ".txt";
		}
		t.columns = r.area.w, t.rows = r.area.h, t.x = r.area.x, t.y = r.area.y;
		if (r.name == CharmTabName) tabs.insert(tabs.begin(), t), kept.insert(kept.begin(), r.area);
		else tabs.push_back(t), kept.push_back(r.area);
	}
	const bool usable = !tabs.empty() && tabs.front().name == CharmTabName && kept.front().x == 0 && kept.front().y == 0 && tabs.size() <= static_cast<std::size_t>(MaxTabs) && PackAreas(kept);
	if (!usable) {
		plan.notes.push_back("no usable previous layout: the charm tab alone, 10 x 6");
		Tab t = CharmFallback();
		t.x = t.y = 0;
		tabs = { t }, kept = { { 0, 0, t.columns, t.rows } };
	}
	plan.tabs = tabs, plan.areas = kept;
	return plan;
}

// The memory after a plan: every tab's place; item boxes carried over by name.
inline std::vector<Remembered> MemoryOf(const Plan& plan, const std::vector<Remembered>& old) {
	std::vector<Remembered> out;
	for (std::size_t i = 0; i < plan.tabs.size(); ++i) {
		Remembered r { plan.tabs[i].name, plan.areas[i], {} };
		for (const auto& o : old)
			if (o.name == r.name) r.used = o.used;
		out.push_back(r);
	}
	return out;
}

} // namespace invtabs

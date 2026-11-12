// Pure rules shared by the plugin's native panels: the developer menu (devmenu_logic.h) and the wiki panel (wiki.cpp). No Windows headers, no
// game calls: tab-separated lines, the word search, result paging, cutting and wrapping a line to a character count, which keys type into a
// text box, and where a click or the pointer is in a panel's own units. Unit tests: plugin/tests/panel_logic_test.cpp and devmenu_test.cpp.
#pragma once

#include <algorithm>
#include <cctype>
#include <cstddef>
#include <cstdlib>
#include <cstring>
#include <string>
#include <string_view>
#include <vector>

namespace panel_logic {

inline auto SplitTabs(std::string_view line) -> std::vector<std::string_view> {
	std::vector<std::string_view> out;
	size_t from = 0;
	for (;;) {
		const size_t tab = line.find('\t', from);
		out.push_back(line.substr(from, tab == std::string_view::npos ? std::string_view::npos : tab - from));
		if (tab == std::string_view::npos) {
			return out;
		}
		from = tab + 1;
	}
}

inline auto ToInt(std::string_view s, int fallback = -1) -> int {
	if (s.empty() || s.size() > 11) {
		return fallback;
	}
	char buf[12];
	std::memcpy(buf, s.data(), s.size());
	buf[s.size()] = 0;
	char* end = nullptr;
	const long v = std::strtol(buf, &end, 10);
	return end == buf + s.size() ? static_cast<int>(v) : fallback;
}

inline auto Fold(std::string_view s) -> std::string {
	std::string out(s);
	std::transform(out.begin(), out.end(), out.begin(), [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
	return out;
}

// All the words of the query appear in the name (ASCII case folded; UTF-8 sequences compare as bytes).
inline auto Matches(std::string_view name, std::string_view query) -> bool {
	const std::string hay = Fold(name), q = Fold(query);
	size_t from = 0;
	for (;;) {
		while (from < q.size() && q[from] == ' ') {
			++from;
		}
		if (from >= q.size()) {
			return true;
		}
		size_t end = q.find(' ', from);
		if (end == std::string::npos) {
			end = q.size();
		}
		if (hay.find(q.substr(from, end - from)) == std::string::npos) {
			return false;
		}
		from = end;
	}
}

// Keys of a panel's text box while it has the keyboard (panel_shared.cpp "typing"), by Windows virtual key. A typed key makes a character
// (letters, digits, space, punctuation, numpad digits and operators): D2R gets its character and not its key press, so no binding runs. An
// editing key moves or deletes in the box and keeps going to D2R, with its binding blocked. Everything else (Esc, F-keys, Tab, modifiers) stays
// the game's.
inline auto TypedKey(unsigned vk) -> bool {
	return vk == 0x20 || (vk >= 0x30 && vk <= 0x39) || (vk >= 0x41 && vk <= 0x5A) || (vk >= 0x60 && vk <= 0x6F && vk != 0x6C) || (vk >= 0xBA && vk <= 0xC0) ||
	       (vk >= 0xDB && vk <= 0xDF) || vk == 0xE2;
}

inline auto EditingKey(unsigned vk) -> bool {
	return vk == 0x08 || vk == 0x0D || vk == 0x2E || (vk >= 0x23 && vk <= 0x28);  // Backspace, Enter, Delete, End, Home, arrows
}

// The key D2R is given instead of a typed key while the box has the keyboard: a key with no binding by default (F24), so D2R treats the key
// press like any unbound key and turns its character into typing.
inline constexpr unsigned StandInKey = 0x87;

// Layout units per client pixel, inverted: a panel is centred in the window (anchor 0.5, 0.5); HD layouts are in units of a 2160-pixel-high
// screen, classic ones in an 800 x 600 screen scaled to fit (the same mapping the in-game checks click with).
inline auto UnitScale(bool hd, int clientW, int clientH) -> double {
	return hd ? clientH / 2160.0 : (clientH / 600.0 < clientW / 800.0 ? clientH / 600.0 : clientW / 800.0);
}

// Whether client pixel (x, y) is on the rectangle (boxX, boxY, boxW, boxH) of a panel at (panelX, panelY) from the screen centre, all in layout
// units. `margin` widens the rectangle by that many layout units on each side.
inline auto OnBox(bool hd, int clientW, int clientH, int panelX, int panelY, int boxX, int boxY, int boxW, int boxH, int x, int y, int margin = 6) -> bool {
	if (clientW <= 0 || clientH <= 0) {
		return false;
	}
	const double scale = UnitScale(hd, clientW, clientH);
	const double left = clientW / 2.0 + (panelX + boxX - margin) * scale, top = clientH / 2.0 + (panelY + boxY - margin) * scale;
	const double right = left + (boxW + 2 * margin) * scale, bottom = top + (boxH + 2 * margin) * scale;
	return x >= left && x < right && y >= top && y < bottom;
}

// Client pixel (x, y) in a panel's own layout units (the panel at (panelX, panelY) from the screen centre). False for an empty client area.
inline auto ToPanelUnits(bool hd, int clientW, int clientH, int panelX, int panelY, int x, int y, double* unitsX, double* unitsY) -> bool {
	if (clientW <= 0 || clientH <= 0) {
		return false;
	}
	const double scale = UnitScale(hd, clientW, clientH);
	*unitsX = (x - clientW / 2.0) / scale - panelX;
	*unitsY = (y - clientH / 2.0) / scale - panelY;
	return true;
}

// The rectangle of `rects` (x, y, width, height each, layout units) that holds the point, or -1: which button of a panel a click was on,
// for panels whose buttons all send one message (wiki.cpp). The rectangles do not overlap; a point just outside one (by up to `margin`)
// still counts for it when it is inside no other.
struct UnitRect {
	int x, y, w, h;
};

inline auto RectAt(const UnitRect* rects, int count, double unitsX, double unitsY, int margin = 4) -> int {
	for (const int m : {0, margin}) {
		for (int i = 0; i < count; ++i) {
			const UnitRect& r = rects[i];
			if (unitsX >= r.x - m && unitsX < r.x + r.w + m && unitsY >= r.y - m && unitsY < r.y + r.h + m) {
				return i;
			}
		}
	}
	return -1;
}

// Pages over a result list. `page` is zero-based; a page past the end clamps.
struct Page {
	int first = 0, count = 0, page = 0, pages = 1;
};

inline auto PageOf(int total, int page, int perPage) noexcept -> Page {
	Page p;
	p.pages = total == 0 ? 1 : (total + perPage - 1) / perPage;
	p.page = std::clamp(page, 0, p.pages - 1);
	p.first = p.page * perPage;
	p.count = std::min(perPage, total - p.first);
	if (p.count < 0) {
		p.count = 0;
	}
	return p;
}

// A line cut to at most maxChars bytes, ending in "..." when cut, and never inside a UTF-8 sequence.
inline auto Ellipsize(const std::string& text, size_t maxChars) -> std::string {
	if (text.size() <= maxChars) {
		return text;
	}
	size_t keep = maxChars > 3 ? maxChars - 3 : 0;
	while (keep > 0 && (static_cast<unsigned char>(text[keep]) & 0xC0) == 0x80) {
		--keep;
	}
	return text.substr(0, keep) + "...";
}

// Word wrap: at most maxLines lines no wider than maxWidth by `width(string)`. A single word wider than the line keeps its own line. What no
// longer fits is cut, and the last line ends in "...".
template <class Width>
auto WrapText(const std::string& text, float maxWidth, size_t maxLines, Width&& width) -> std::vector<std::string> {
	std::vector<std::string> lines;
	std::string current;
	size_t pos = 0;
	while (pos < text.size()) {
		size_t end = text.find(' ', pos);
		end = end == std::string::npos ? text.size() : end;
		const std::string word = text.substr(pos, end - pos);
		pos = end + 1;
		if (word.empty()) {
			continue;
		}
		std::string joined = current.empty() ? word : current + " " + word;
		if (current.empty() || width(joined) <= maxWidth) {
			current = std::move(joined);
			continue;
		}
		if (lines.size() + 1 == maxLines) {
			lines.push_back(current + "...");
			return lines;
		}
		lines.push_back(current);
		current = word;
	}
	if (!current.empty()) {
		lines.push_back(current);
	}
	return lines;
}

}  // namespace panel_logic

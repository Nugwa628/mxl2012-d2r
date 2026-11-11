#pragma once
// invtabs: the controller (gamepad) panel of a tab, the part without the SDK: geometry, layout JSON, background art.
// docs/invtabs-pad.md. tools/invtabs_pad.py is the reference: pad_tests.cpp compares LayoutJson with its golden strings
// (pad_golden.inc, `py -3 -I tools/invtabs_pad.py golden`). Change both together.

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

namespace invtabs::pad {

inline constexpr const char* Plugin = "invtabs";
// D2R's controller left panel ($ConsoleLeftPanelRect in layouts/controller/_profilehd.json): the Cube, stash and hireling panels.
inline constexpr int PanelW = 1305, PanelH = 1421;
inline constexpr int Cell        = 98;   // $ItemCellSize (HD)
inline constexpr int Margin      = 60;   // left, right and top inner margin of the art
inline constexpr int GridBottom  = 1371; // the grid's lower edge
inline constexpr int Gap         = 30;   // between the summary area and the grid
inline constexpr int SummaryMin  = 240;  // the summary area is never lower
inline constexpr int FieldW      = PanelW - 2 * Margin;
inline constexpr int MarkerBase  = 7400; // the core's grid marker: chronicleFlourishOffset {7400 + slot, 7400}
inline constexpr int MaxCells    = 16;   // the custom page is 16 x 16
inline constexpr int MaxSlot     = 63;

struct Rect {
	int x, y, w, h;
};

struct Geometry {
	int  scaleMilli; // grid scale in thousandths (1000 = full size)
	Rect grid;       // panel pixels, the scaled grid
	Rect summary;    // panel pixels, the summary area above it
};

constexpr bool ValidSpec(int cols, int rows, int slot) noexcept {
	return cols >= 1 && cols <= MaxCells && rows >= 1 && rows <= MaxCells && slot >= 0 && slot <= MaxSlot;
}

// The grid sits at the bottom, centred (an odd spare pixel goes left: 10 columns at x 163), scaled down when the tab is wider
// than 12 columns or the summary area would get lower than SummaryMin; the summary area takes the rest above it.
constexpr Geometry Layout(int cols, int rows) noexcept {
	const int availH = GridBottom - (Margin + SummaryMin + Gap);
	const int milli  = std::min({ 1000, FieldW * 1000 / (cols * Cell), availH * 1000 / (rows * Cell) });
	const int gw = cols * Cell * milli / 1000, gh = rows * Cell * milli / 1000;
	const int gx = (PanelW - gw + 1) / 2, gy = GridBottom - gh;
	return { milli, { gx, gy, gw, gh }, { Margin, Margin, FieldW, gy - Gap - Margin } };
}

// 0.663, 0.7, 0.05: the shortest decimal, as Python's json writes float(milli / 1000).
inline std::string ScaleText(int milli) {
	char text[16] {};
	std::snprintf(text, sizeof(text), "%d.%03d", milli / 1000, milli % 1000);
	std::string s = text;
	while (s.back() == '0') s.pop_back();
	if (s.back() == '.') s.pop_back();
	return s;
}

inline std::string LocalId(int slot) { return "Pad" + std::to_string(slot); }
inline std::string PanelName(int slot) { return std::string(Plugin) + "/" + LocalId(slot); }
inline std::string LayoutPath(int slot) { return std::string("data/global/ui/layouts/") + Plugin + "/" + LocalId(slot) + "hd.json"; }
// The art's sprite name below data/hd/global/ui/d2rloader/invtabs/ (the core registers it, see pad_route.h).
inline std::string BackgroundName(int cols, int rows) { return "pad_" + std::to_string(cols) + "x" + std::to_string(rows); }

// The panel layout, compact JSON byte for byte as tools/invtabs_pad.py writes it. `summary`: the core's summary widgets
// (summary.h Fragment: comma-separated children inside the summary area), spliced in after invtabs/Summary.
inline std::string LayoutJson(int cols, int rows, int slot, const std::string& summary = {}) {
	const Geometry g = Layout(cols, rows);
	const auto     n = [](int v) { return std::to_string(v); };
	std::string    rect = R"({"x":)" + n(g.grid.x) + R"(,"y":)" + n(g.grid.y);
	if (g.scaleMilli < 1000) rect += R"(,"scale":)" + ScaleText(g.scaleMilli);
	rect += "}";
	std::string j;
	j += R"({"type":"Panel","name":")" + PanelName(slot) + R"(","fields":{"priority":10,"rect":"$ConsoleLeftPanelRect","anchor":"$LeftPanelAnchor","defaultWidget":"invtabs/Grid"},"children":[)";
	j += R"({"type":"ClickCatcherWidget","name":"invtabs/PadClickCatcher","fields":{"rect":{"x":0,"y":0,"width":0,"height":0},"fitToParent":true}},)";
	j += R"({"type":"ImageWidget","name":"invtabs/PadBackground","fields":{"rect":{"x":0,"y":0},"filename":"d2rloader\\invtabs\\)" + BackgroundName(cols, rows) + R"("}},)";
	j += R"({"type":"Widget","name":"invtabs/Summary","fields":{"rect":{"x":)" + n(g.summary.x) + R"(,"y":)" + n(g.summary.y) + R"(,"width":)" + n(g.summary.w)
	   + R"(,"height":)" + n(g.summary.h) + "}}},";
	if (!summary.empty()) j += summary + ",";
	j += R"({"type":"InventoryGridWidget","name":"invtabs/Grid","fields":{"rect":)" + rect + R"(,"cellCount":{"x":)" + n(cols) + R"(,"y":)" + n(rows)
	   + R"(},"cellSize":"$ItemCellSize","gemSocketFilename":"PANEL\\gemsocket","chronicleFlourishOffset":{"x":)" + n(MarkerBase + slot) + R"(,"y":)" + n(MarkerBase)
	   + R"(},"navigation":{"right":{"panelBoundary":true}}}})";
	return j + "]}";
}

// The panel art, PanelW x PanelH RGBA: dark stone with a gold rim, a sunken summary well, the grid's cells.
inline std::vector<std::uint8_t> Background(int cols, int rows) {
	const Geometry            g = Layout(cols, rows);
	std::vector<std::uint8_t> rgba(static_cast<std::size_t>(PanelW) * PanelH * 4);
	const auto                inside = [](const Rect& r, int x, int y) { return x >= r.x && y >= r.y && x < r.x + r.w && y < r.y + r.h; };
	for (int y = 0; y < PanelH; ++y)
		for (int x = 0; x < PanelW; ++x) {
			std::uint32_t h = static_cast<std::uint32_t>(x) * 374761393u + static_cast<std::uint32_t>(y) * 668265263u;
			h               = (h ^ (h >> 13)) * 1274126177u;
			const int grain = static_cast<int>((h ^ (h >> 16)) & 0x0F);
			const int edge  = std::min({ x, y, PanelW - 1 - x, PanelH - 1 - y });
			int       r = 22 + grain, gr = 20 + grain, b = 18 + grain;
			if (edge < 5) r = 150, gr = 120, b = 70;
			else if (edge < 10) r = 40, gr = 34, b = 26;
			else if (inside(g.summary, x, y)) {
				const int e = std::min({ x - g.summary.x, y - g.summary.y, g.summary.x + g.summary.w - 1 - x, g.summary.y + g.summary.h - 1 - y });
				if (e < 2) r = 90, gr = 74, b = 48;
				else r = 12 + grain / 2, gr = 11 + grain / 2, b = 10 + grain / 2;
			} else if (inside(g.grid, x, y)) {
				const int  cx = (x - g.grid.x) * 1000 % (Cell * g.scaleMilli), cy = (y - g.grid.y) * 1000 % (Cell * g.scaleMilli);
				const int  line = 2 * 1000; // 2 px at full size
				const bool rim  = cx < line || cy < line || cx >= Cell * g.scaleMilli - line || cy >= Cell * g.scaleMilli - line;
				if (rim) r = 70, gr = 62, b = 50;
				else r = 8 + grain / 2, gr = 8 + grain / 2, b = 10 + grain / 2;
			}
			std::uint8_t* px = &rgba[(static_cast<std::size_t>(y) * PanelW + x) * 4];
			px[0] = static_cast<std::uint8_t>(r), px[1] = static_cast<std::uint8_t>(gr), px[2] = static_cast<std::uint8_t>(b), px[3] = 255;
		}
	return rgba;
}

} // namespace invtabs::pad

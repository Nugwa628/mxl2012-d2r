#pragma once
// invtabs: the tab panels' layouts and art, pure (no game, no Windows headers; tests/invtabs_test.cpp).
//
// HD: the panel is built like D2R's own left panels (Horadric Cube, stash): PANEL\panel_bg (D2R's empty framed panel
// with its title plate), the left hinge, the title in $StyleTitleBlock, D2R's close button, the stash's tab sprite
// (PANEL\stash\MKB_Tabs_195_TGA) for the tab row, and the stash's own grid cells under the grid. The cells come from the
// stash background cut at mod build time (tools/invtabs_hdart.py -> data/hd/global/ui/panel/invtabs/stockgrid.sprite,
// 10 x 10 cells of 98 px with the grid's frame) and are re-tiled here to the tab's size; without that file a plain
// drawn grid stands in. The summary band sits between the tab row and the grid.
//
// Classic: the panel of docs/invtabs-legacy.md (Median's stash pieces, built per tab at mod build time by
// tools/invtabs_art.py, PANEL\invtabs_<tab>) with the geometry of tools/invtabs_legacy.py.

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace invtabs::layout {

// ---- pictures and D2R's sprite file ----

struct Picture {
	int                        width {}, height {};
	std::vector<unsigned char> rgba;
	unsigned char*             at(int x, int y) { return rgba.data() + (static_cast<std::size_t>(y) * width + x) * 4; }
	const unsigned char*       at(int x, int y) const { return rgba.data() + (static_cast<std::size_t>(y) * width + x) * 4; }
};

inline Picture Blank(int w, int h) {
	Picture p { w, h, {} };
	p.rgba.assign(static_cast<std::size_t>(w) * h * 4, 0);
	return p;
}

// Box filter to w x h (any ratio; area-weighted on each axis).
inline Picture Resize(const Picture& in, int w, int h) {
	if (w == in.width && h == in.height) return in;
	Picture    out = Blank(std::max(1, w), std::max(1, h));
	const auto span = [](int i, int n, int m, double& a, double& b) { a = static_cast<double>(i) * m / n, b = static_cast<double>(i + 1) * m / n; };
	for (int y = 0; y < out.height; ++y) {
		double y0, y1;
		span(y, out.height, in.height, y0, y1);
		for (int x = 0; x < out.width; ++x) {
			double x0, x1;
			span(x, out.width, in.width, x0, x1);
			double sum[4] {}, weight = 0;
			for (int sy = static_cast<int>(y0); sy < std::min(in.height, static_cast<int>(y1 + 0.999999)); ++sy) {
				const double wy = std::min<double>(sy + 1, y1) - std::max<double>(sy, y0);
				if (wy <= 0) continue;
				for (int sx = static_cast<int>(x0); sx < std::min(in.width, static_cast<int>(x1 + 0.999999)); ++sx) {
					const double wx = std::min<double>(sx + 1, x1) - std::max<double>(sx, x0);
					if (wx <= 0) continue;
					const unsigned char* px = in.at(sx, sy);
					for (int k = 0; k < 4; ++k) sum[k] += px[k] * wx * wy;
					weight += wx * wy;
				}
			}
			for (int k = 0; k < 4; ++k) out.at(x, y)[k] = static_cast<unsigned char>(weight > 0 ? std::clamp(sum[k] / weight + 0.5, 0.0, 255.0) : 0);
		}
	}
	return out;
}

inline Picture Half(const Picture& in) { return Resize(in, std::max(1, in.width / 2), std::max(1, in.height / 2)); }

// SpA1 version 31 (uncompressed RGBA): frames side by side.
inline std::string SpriteFile(const std::vector<Picture>& frames) {
	const auto& first = frames.front();
	const auto  count = static_cast<std::uint32_t>(frames.size());
	std::string out(40, '\0');
	const auto  put = [&](std::size_t at, std::uint32_t value, int bytes) {
        for (int i = 0; i < bytes; ++i) out[at + static_cast<std::size_t>(i)] = static_cast<char>((value >> (8 * i)) & 0xFF);
	};
	std::memcpy(out.data(), "SpA1", 4);
	put(4, 31, 2);
	put(6, static_cast<std::uint32_t>(first.width), 2);
	put(8, static_cast<std::uint32_t>(first.width) * count, 4);
	put(12, static_cast<std::uint32_t>(first.height), 4);
	put(20, count, 4);
	const std::size_t row = static_cast<std::size_t>(first.width) * 4;
	for (int y = 0; y < first.height; ++y)
		for (const auto& frame : frames) out.append(reinterpret_cast<const char*>(frame.rgba.data()) + static_cast<std::size_t>(y) * row, row);
	return out;
}

// The first frame of an uncompressed SpA1 v31 sprite; nothing for anything else.
inline std::optional<Picture> ParseSprite(std::string_view bytes) {
	if (bytes.size() < 40 || bytes.substr(0, 4) != "SpA1") return std::nullopt;
	const auto get = [&](std::size_t at, int n) {
		std::uint32_t v = 0;
		for (int i = 0; i < n; ++i) v |= static_cast<std::uint32_t>(static_cast<unsigned char>(bytes[at + static_cast<std::size_t>(i)])) << (8 * i);
		return v;
	};
	const std::uint32_t version = get(4, 2), frameW = get(6, 2), totalW = get(8, 4), h = get(12, 4), frames = get(20, 4);
	if (version != 31 || !frameW || !h || !frames || totalW != frameW * frames || frameW > 4096 || h > 4096) return std::nullopt;
	if (bytes.size() < 40 + static_cast<std::size_t>(totalW) * h * 4) return std::nullopt;
	Picture p = Blank(static_cast<int>(frameW), static_cast<int>(h));
	for (std::uint32_t y = 0; y < h; ++y)
		std::memcpy(p.rgba.data() + static_cast<std::size_t>(y) * frameW * 4, bytes.data() + 40 + static_cast<std::size_t>(y) * totalW * 4, static_cast<std::size_t>(frameW) * 4);
	return p;
}

// ---- the grid's cells ----

inline constexpr int StockCell = 98, StockCells = 10, StockFrame = 8; // the stash grid as stockgrid.sprite holds it
inline constexpr int StockSize = StockCells * StockCell + 2 * StockFrame;

// The stock 10 x 10 grid re-tiled to cols x rows at 98 px: the frame from the stock edges, cells from the stock cells in
// the same position (first / last row and column from the stock's first / last, the inside from its inner cells).
inline Picture TileStockGrid(const Picture& stock, int cols, int rows) {
	Picture    out = Blank(cols * StockCell + 2 * StockFrame, rows * StockCell + 2 * StockFrame);
	const auto map = [](int v, int n) {
		if (v < StockFrame) return v;
		const int inner = v - StockFrame;
		if (inner >= n * StockCell) return inner - n * StockCell + StockCells * StockCell + StockFrame;
		const int c = inner / StockCell, o = inner % StockCell;
		const int s = c == 0 ? 0 : c == n - 1 ? StockCells - 1 : 1 + (c - 1) % (StockCells - 2);
		return StockFrame + s * StockCell + o;
	};
	for (int y = 0; y < out.height; ++y) {
		const int sy = map(y, rows);
		for (int x = 0; x < out.width; ++x) std::memcpy(out.at(x, y), stock.at(map(x, cols), sy), 4);
	}
	return out;
}

// A plain stand-in when the stock cut is missing: dark cells with a light rim, a gold frame.
inline Picture DrawnGrid(int cols, int rows) {
	Picture p = Blank(cols * StockCell + 2 * StockFrame, rows * StockCell + 2 * StockFrame);
	for (int y = 0; y < p.height; ++y)
		for (int x = 0; x < p.width; ++x) {
			unsigned char* px   = p.at(x, y);
			const int      edge = std::min({ x, y, p.width - 1 - x, p.height - 1 - y });
			px[3]               = 255;
			if (edge < StockFrame) {
				const bool gold = edge >= 2 && edge < 5;
				px[0] = gold ? 150 : 24, px[1] = gold ? 118 : 24, px[2] = gold ? 64 : 27;
				continue;
			}
			const int cx = (x - StockFrame) % StockCell, cy = (y - StockFrame) % StockCell;
			const int e  = std::min({ cx, cy, StockCell - 1 - cx, StockCell - 1 - cy });
			if (e == 1 || e == 2) px[0] = 95, px[1] = 80, px[2] = 74;
			else px[0] = 8, px[1] = 8, px[2] = 10;
		}
	return p;
}

// The cell picture for a grid of cell px: the 98 px picture scaled by cell / 98 (frame included).
inline Picture GridPicture(const Picture* stock, int cols, int rows, int cell) {
	Picture full = stock && stock->width == StockSize && stock->height == StockSize ? TileStockGrid(*stock, cols, rows) : DrawnGrid(cols, rows);
	if (cell == StockCell) return full;
	const int frame = std::max(1, StockFrame * cell / StockCell);
	return Resize(full, cols * cell + 2 * frame, rows * cell + 2 * frame);
}

inline int ScaledFrame(int cell) { return cell == StockCell ? StockFrame : std::max(1, StockFrame * cell / StockCell); }

// ---- JSON helpers ----

inline std::string Json(std::string_view text) {
	std::string out = "\"";
	for (const char c : text) {
		if (c == '"' || c == '\\') out += '\\';
		if (static_cast<unsigned char>(c) >= 0x20) out += c;
	}
	return out + '"';
}

inline std::string N(int v) { return std::to_string(v); }

inline std::string XY(int x, int y) { return R"({"x": )" + N(x) + R"(, "y": )" + N(y) + "}"; }

inline std::string XYWH(int x, int y, int w, int h) { return R"({"x": )" + N(x) + R"(, "y": )" + N(y) + R"(, "width": )" + N(w) + R"(, "height": )" + N(h) + "}"; }

// The grid bound to the page: 16 x 16 cells (the wrappers show the tab's area at its corner), our marker.
inline std::string GridWidget(int slot, int x, int y, const std::string& cellSize, bool classic, int pageSize = 16) {
	char marker[96];
	std::snprintf(marker, sizeof(marker), R"({"x": %d, "y": %d})", 7400 + slot, classic ? 7401 : 7400);
	return R"({"type": "InventoryGridWidget", "name": "invtabs/Grid", "fields": {"rect": )" + XY(x, y) + R"(, "cellCount": )" + XY(pageSize, pageSize)
	     + R"(, "cellSize": )" + cellSize + R"(, "gemSocketFilename": "PANEL\\gemsocket", "chronicleFlourishOffset": )" + marker + "}}";
}

// ---- HD ----

struct Box {
	int x {}, y {}, w {}, h {};
};

struct TabRef {
	std::string panel; // full panel name, invtabs/<Id>
	std::string label;
};

inline constexpr int HdPanelW = 1162, HdPanelH = 1507;
inline constexpr int HdInnerX = 89, HdInnerW = 980;          // the stash grid's columns
inline constexpr int HdTabY = 146, HdTabW = 195, HdTabH = 72; // the stash's tab row
inline constexpr int HdTabsPerRow = 5;
inline constexpr int HdContentTop = 160;    // under the title plate when there is no tab row
inline constexpr int HdGridBottom = 1418;   // the grid's last row ends here (its frame below, then the panel's rim)
inline constexpr int HdBandGap = 26;        // between the summary band and the grid's frame
inline constexpr int HdSummaryMin = 240;

struct HdGeometry {
	int cell {}, frame {};
	Box grid;     // the cells (frame outside)
	Box band;     // the summary band; h 0 when there is none
	int tabRows {};
};

inline HdGeometry HdLayoutOf(int cols, int rows, int tabCount, bool summary) {
	HdGeometry g;
	g.tabRows     = tabCount > 1 ? (tabCount + HdTabsPerRow - 1) / HdTabsPerRow : 0;
	const int top = g.tabRows ? HdTabY + g.tabRows * HdTabH + 14 : HdContentTop;
	const int maxH = HdGridBottom - top - (summary ? HdSummaryMin + HdBandGap : 0);
	g.cell        = std::max(20, std::min({ StockCell, HdInnerW / std::max(1, cols), maxH / std::max(1, rows) }));
	g.frame       = ScaledFrame(g.cell);
	g.grid        = { HdInnerX + (HdInnerW - cols * g.cell) / 2, HdGridBottom - rows * g.cell, cols * g.cell, rows * g.cell };
	if (summary) g.band = { HdInnerX, top, HdInnerW, g.grid.y - g.frame - HdBandGap - top };
	return g;
}

// The whole HD panel of one tab. `tabs` is every tab (the row), `self` its index; cellsSprite the registered cell
// picture (d2rloader\invtabs\...); summaryFragment the summary's widgets (empty: none).
inline std::string HdPanel(const std::vector<TabRef>& tabs, int self, int slot, int cols, int rows, const HdGeometry& g, const std::string& cellsSprite,
                           const std::string& summaryFragment, const std::string& title) {
	const std::string& name = tabs[static_cast<std::size_t>(self)].panel;
	std::string        j    = R"({"type": "Panel", "name": )" + Json(name) + R"(, "fields": {"priority": 10, "rect": "$LeftPanelRect", "anchor": "$LeftPanelAnchor"}, "children": [)";
	j += R"({"type": "ClickCatcherWidget", "name": "PanelClickCatcher", "fields": {"rect": "$PanelClickCatcherRect"}})";
	j += R"(, {"type": "ImageWidget", "name": "Background", "fields": {"filename": "PANEL\\panel_bg"}})";
	j += R"(, {"type": "ImageWidget", "name": "LeftHinge", "fields": {"rect": "$LeftHingeRect", "filename": "$LeftHingeSprite"}})";
	j += R"(, {"type": "TextBoxWidget", "name": "Title", "fields": {"rect": "$InGamePanelTitleRect", "style": "$StyleTitleBlock", "text": )" + Json(title) + "}}";
	if (g.tabRows)
		for (std::size_t i = 0; i < tabs.size(); ++i) {
			const int  x = HdInnerX - 7 + static_cast<int>(i % HdTabsPerRow) * HdTabW, y = HdTabY + static_cast<int>(i / HdTabsPerRow) * HdTabH;
			const bool on = static_cast<int>(i) == self;
			const auto f  = N(on ? 1 : 0);
			j += R"(, {"type": "ButtonWidget", "name": "TabButton)" + N(static_cast<int>(i)) + R"(", "fields": {"rect": )" + XY(x, y)
			   + R"(, "filename": "PANEL\\stash\\MKB_Tabs_195_TGA", "normalFrame": )" + f + R"(, "pressedFrame": )" + f + R"(, "hoveredFrame": )" + f
			   + R"(, "disabledFrame": )" + f + (on ? std::string() : R"(, "onClickMessage": )" + Json("PanelManager:OpenPanel:" + tabs[i].panel)) + "}}";
			j += R"(, {"type": "TextBoxWidget", "name": "TabLabel)" + N(static_cast<int>(i)) + R"(", "fields": {"rect": )" + XYWH(x, y, HdTabW, HdTabH)
			   + R"(, "text": )" + Json(tabs[i].label) + R"(, "style": {"pointSize": "$SmallPanelFontSize", "fontColor": )"
			   + (on ? R"("$TabsActiveTextColor")" : R"("$TabsInactiveTextColor")") + R"(, "alignment": {"h": "center", "v": "center"}}}})";
		}
	j += R"(, {"type": "ImageWidget", "name": "Cells", "fields": {"rect": )" + XY(g.grid.x - g.frame, g.grid.y - g.frame) + R"(, "filename": )" + Json(cellsSprite) + "}}";
	if (!summaryFragment.empty()) j += ", " + summaryFragment;
	// cellSize is a struct field: a bare number makes the game assert (TypeDesc.cpp:197) and the panel does not open
	j += ", " + GridWidget(slot, g.grid.x, g.grid.y, g.cell == StockCell ? "\"$ItemCellSize\"" : XY(g.cell, g.cell), false);
	j += R"(, {"type": "ButtonWidget", "name": "CloseButton", "fields": {"rect": {"x": 1075, "y": 9}, "filename": "PANEL\\closebtn_4x", "hoveredFrame": 3, )"
	     R"("tooltipString": "@d2r:strClose", "sound": "cursor_close_window_hd", "onClickMessage": )"
	   + Json("PanelManager:ClosePanel:" + name) + "}}";
	(void)cols, (void)rows;
	return j + "]}";
}

// ---- classic (tools/invtabs_legacy.py) ----

inline constexpr int ClassicW = 320, ClassicH = 432, ClassicCell = 29, ClassicMaxCols = 10;
inline constexpr int ClassicInnerX0 = 16, ClassicInnerX1 = 306, ClassicBodyTop = 83, ClassicGridBottom = 372, ClassicLine = 3;
inline constexpr int ClassicTabW = 24, ClassicTabH = 24, ClassicTabGap = 4, ClassicSummaryMargin = 4, ClassicSummaryInset = 5;
inline constexpr int ClassicLineH = 12, ClassicMaxSummaryLines = 8, ClassicMinSummaryLines = 2;

inline Box ClassicGrid(int cols, int rows) {
	return { ClassicInnerX0 + (ClassicMaxCols - cols) * ClassicCell / 2, ClassicGridBottom - rows * ClassicCell, cols * ClassicCell, rows * ClassicCell };
}

inline int ClassicTabRowY(int rows) { return ClassicGrid(ClassicMaxCols, rows).y - ClassicLine + 1 - ClassicTabGap - ClassicTabH; }

// The summary box with its rim (x1 / y1 exclusive), as Box.
inline Box ClassicSummaryBox(int rows) {
	const int y0 = ClassicBodyTop + ClassicSummaryMargin - 1;
	const int y1 = std::min(ClassicTabRowY(rows) - ClassicSummaryMargin, y0 + 2 * ClassicSummaryInset + ClassicMaxSummaryLines * ClassicLineH);
	return { ClassicInnerX0 + ClassicSummaryMargin, y0, ClassicInnerX1 - ClassicSummaryMargin - (ClassicInnerX0 + ClassicSummaryMargin), y1 - y0 };
}

// The text area inside the summary box.
inline Box ClassicSummaryText(int rows) {
	const Box b     = ClassicSummaryBox(rows);
	const int lines = std::max(0, (b.h - 2 * ClassicSummaryInset) / ClassicLineH);
	return { b.x + ClassicSummaryInset, b.y + ClassicSummaryInset, b.w - 2 * ClassicSummaryInset, lines * ClassicLineH };
}

inline bool ClassicFits(int cols, int rows) {
	if (cols < 1 || rows < 1 || cols > ClassicMaxCols) return false;
	return rows == 1 || ClassicSummaryText(rows).h / ClassicLineH >= ClassicMinSummaryLines;
}

struct ClassicTab {
	std::string panel, label, name; // name: the tab's config name (art PANEL\invtabs_tab_<name>)
};

// The classic panel of tabs[self] (only tabs that fit classic are in `tabs`). summaryFragment replaces the empty rows.
inline std::string ClassicPanel(const std::vector<ClassicTab>& tabs, int self, int slot, int cols, int rows, const std::string& summaryFragment) {
	const auto&       me   = tabs[static_cast<std::size_t>(self)];
	const std::string name = me.panel;
	std::string       j    = R"({"type": "Panel", "name": )" + Json(name) + R"(, "fields": {"priority": 10, "rect": {"x": -320, "y": -240, "width": 320, "height": 432}, "anchor": "$LeftPanelAnchor"}, "children": [)";
	j += R"({"type": "ClickCatcherWidget", "name": "invtabs/PanelClickCatcher", "fields": {"rect": )" + XYWH(0, 0, ClassicW, ClassicH) + "}}";
	j += R"(, {"type": "GridImageWidget", "name": "invtabs/Background", "fields": {"rect": )" + XYWH(0, 0, ClassicW, ClassicH) + R"(, "filename": )"
	   + Json("PANEL\\invtabs_" + me.name) + R"(, "frames": 4, "rows": 2}})";
	if (!summaryFragment.empty()) j += ", " + summaryFragment;
	for (std::size_t i = 0; i < tabs.size(); ++i) {
		const bool mine = static_cast<int>(i) == self;
		j += R"(, {"type": "ButtonWidget", "name": "invtabs/Tab)" + N(static_cast<int>(i)) + R"(", "fields": {"rect": )"
		   + XYWH(ClassicInnerX0 + 1 + static_cast<int>(i) * ClassicTabW, ClassicTabRowY(rows), ClassicTabW, ClassicTabH) + R"(, "filename": )"
		   + Json("PANEL\\invtabs_tab_" + tabs[i].name) + R"(, "normalFrame": )" + N(mine ? 2 : 0) + R"(, "pressedFrame": )" + N(mine ? 2 : 1)
		   + R"(, "tooltipString": )" + Json(tabs[i].label) + R"(, "tooltipOffset": {"x": 0, "y": -3}, "onClickMessage": )"
		   + Json("PanelManager:OpenPanel:" + tabs[i].panel) + "}}";
	}
	const Box g = ClassicGrid(cols, rows);
	j += ", " + GridWidget(slot, g.x, g.y, "\"$ItemCellSize\"", true);
	j += R"(, {"type": "ButtonWidget", "name": "invtabs/Close", "fields": {"rect": {"x": 275, "y": 383, "width": 32, "height": 32}, "filename": "PANEL\\buysellbtn", )"
	     R"("normalFrame": 10, "pressedFrame": 11, "tooltipString": "Close", "tooltipOffset": {"x": 0, "y": -3}, "onClickMessage": )"
	   + Json("PanelManager:ClosePanel:" + name) + "}}";
	return j + "]}";
}

} // namespace invtabs::layout

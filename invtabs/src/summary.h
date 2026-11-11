// The charm-tab summary: the total bonuses of the charms in the tab that count, worded by the game's own item tooltip
// formatter, as a scrollable list at the top of the charm tab. docs/invtabs-summary.md has the design and the evidence.
//
// What the core calls, and when (all on the game's UI thread unless noted):
//   1. Init(module base, log) once at plugin load (any thread). Scans summary_natives.h. False = the summary stays off
//      (the reason is logged); every other call is then harmless and shows nothing.
//   2. Refresh(items, count) when the charm tab opens, before its layout is built, and again after an item of the charm
//      page was added, removed or moved (the page's item change event). `items` are the client's item units on the
//      charm page (the core enumerates them; any order). Refresh decides which count (merged into the player: met
//      requirements, active carry1 copy) and formats the totals. Cheap: no allocation in the game beyond one stat list.
//   3. Fragment(mode, area) when the core builds the charm tab's layout (after Refresh): the widgets to splice into the
//      panel's "children" (summary_logic.h LayoutFragment). The core reserves `area` (SummaryHeight) above the grid.
//      Rows() is the row count that fragment was built with; NeedsRelayout() says a later Refresh produced more lines
//      than it holds, so the core should register the layout again at the next open.
//   4. ApplyTexts(panelName) after the panel opened and after every Refresh while it is open: sets each row's text
//      with D2R's TextBoxWidget setter (found by the panel's name, e.g. "invtabs/Tab0").
//   5. Classic layout only: ScrollBy(delta lines) on the mouse wheel over the summary, then ApplyTexts.
#pragma once

#include "summary_logic.h"
#include "summary_natives.h"

#include <cstdint>
#include <string>
#include <vector>

namespace invtabs::summary {

using LogFn = void (*)(const char* line);

class Summary {
public:
	bool Init(const void* gameModule, LogFn log);
	bool Ready() const { return ready_; }

	void Refresh(void* const* items, std::size_t count);
	// Lines the core puts above the totals at the next Refresh (empty: none). Used for the notice of a read-only tab in a
	// joined TCP/IP game. Like the totals it needs the summary's natives: without them the notice is in the log only.
	void SetNotice(std::vector<std::string> lines) { notice_ = std::move(lines); }
	const std::vector<std::string>& Lines() const { return lines_; }
	// The raw totals behind Lines(), and how many items counted / were left out (logs, tests).
	const std::vector<StatValue>& Totals() const { return totals_; }
	std::size_t Counted() const { return counted_; }
	std::size_t Skipped() const { return skipped_; }
	bool UsedFallback() const { return fallback_; }

	std::string Fragment(LayoutMode mode, Rect area);
	std::size_t Rows() const { return rows_; }
	bool NeedsRelayout() const { return !Fits(mode_, rows_, lines_.size()); }

	void ApplyTexts(const char* panelName, bool force = false);
	void ScrollBy(long long delta);

	// The stat entries of one item unit, as its tooltip reads them (the item's own list, flags 0x40). Empty when the
	// summary is off or the item has none.
	std::vector<StatValue> ReadItem(void* item) const;
	// The item's stats are merged into its owner (they count for the player).
	bool ItemCounts(void* item) const;

private:
	std::vector<std::string> Format(const std::vector<StatValue>& totals, void* context);

	bool        ready_ = false;
	LogFn       log_   = nullptr;
	std::uintptr_t fn_[SummaryNativeCount] {};

	std::vector<StatValue>   totals_;
	std::vector<std::string> lines_;
	std::vector<std::string> notice_;
	std::vector<std::string> shown_;
	std::size_t              counted_ = 0, skipped_ = 0;
	bool                     fallback_ = false;
	LayoutMode               mode_     = LayoutMode::Hd;
	std::size_t              rows_     = 0;
	std::size_t              first_    = 0;
};

} // namespace invtabs::summary

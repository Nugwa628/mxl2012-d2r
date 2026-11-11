// Pure rule of the carry1 duplicate copies (charm_dup.cpp; unit test plugin/tests/charm_dup_test.cpp). No Windows headers, no
// game calls.
//
// Median XL 2012's 45 carry1 uniques (unique charms, relics, quest charms) give their bonus once per character. With the part on,
// a player may carry more copies of one of them (to trade), but only one copy, the active one, gives its stats; the others act
// like an item whose requirements are not met (D2R draws them red and leaves their stats out).
#pragma once

#include <cstddef>
#include <cstdint>

namespace charm_dup {

// D2R item pages: 0 is the backpack; D2RLoader gives the mod's one custom player page number 6 (CharmInv's grid, or invtabs'
// 16 x 16 page whose charm tab is one rectangle of it).
inline constexpr int32_t BackpackPage = 0;
inline constexpr int32_t CharmInvPage = 6;
inline constexpr int32_t PageCells = 16;  // the custom page's cells per side at most (x and y are four bits in the .d2s)

// The part of the custom page that is charm inventory: the whole page (CharmInv, or no invtabs charm tab), or invtabs' charm
// tab rectangle (its export InvTabsCharmTab, docs/invtabs.md). Items elsewhere on the page (other tabs) are not charms here.
struct CharmArea {
	bool wholePage = true;
	int32_t x = 0, y = 0, w = 0, h = 0;
};

// The area from InvTabsCharmTab's answer: `found` 0 (no tab) or a rectangle that is not on the page gives the whole page, the
// old CharmInv behaviour (a bad answer never takes a charm's bonus away).
constexpr auto TabArea(int found, int32_t x, int32_t y, int32_t w, int32_t h) noexcept -> CharmArea {
	if (found == 0 || x < 0 || y < 0 || w <= 0 || h <= 0 || x + w > PageCells || y + h > PageCells) {
		return {};
	}
	return {false, x, y, w, h};
}

// True when an item whose top-left cell is x,y on the custom page lies in the charm area (invtabs: an item belongs to the area
// holding its top-left cell).
constexpr auto InCharmArea(const CharmArea& area, int32_t x, int32_t y) noexcept -> bool {
	return area.wholePage || (x >= area.x && x < area.x + area.w && y >= area.y && y < area.y + area.h);
}

// One stored copy of a carry1 unique on a page whose charms count.
struct Copy {
	uint32_t unitId;       // the item's unit id (unique while the game runs)
	int32_t uniqueIndex;   // row of uniqueitems.txt
	int32_t page;          // 0 backpack, 6 CharmInv
	int32_t x, y;          // grid cell
};

// Ordering of the copies of one unique (each PlaceOf Charm): the custom page's charm area (CharmInv, invtabs' charm tab) first,
// then the backpack; on a page the top row first, then the left column;
// the unit id breaks ties (two copies never share a cell). The order depends only on where the copies lie, so a reload, which
// gives the items new unit ids, picks the same copy.
constexpr auto Before(const Copy& a, const Copy& b) noexcept -> bool {
	const int ta = a.page == CharmInvPage ? 0 : 1;
	const int tb = b.page == CharmInvPage ? 0 : 1;
	if (ta != tb) {
		return ta < tb;
	}
	if (a.page != b.page) {
		return a.page < b.page;
	}
	if (a.y != b.y) {
		return a.y < b.y;
	}
	if (a.x != b.x) {
		return a.x < b.x;
	}
	return a.unitId < b.unitId;
}

// The active copy among `copies` (all of one unique index): the first in Before order. The choice depends only on where the
// copies lie, so the client and the server, which both ask, agree without sharing state, and a reload keeps it. Returns the
// index into `copies`, or -1 when there is none.
constexpr auto PickActive(const Copy* copies, size_t count) noexcept -> int {
	if (count == 0) {
		return -1;
	}
	size_t best = 0;
	for (size_t i = 1; i < count; ++i) {
		if (Before(copies[i], copies[best])) {
			best = i;
		}
	}
	return static_cast<int>(best);
}

// True when an item of this unique index is a carry1 unique (its uniqueitems.txt carry1 cell is above 0).
constexpr auto IsCarry1(int32_t carry1Cell) noexcept -> bool {
	return carry1Cell > 0;
}

// True when a page's charms count (CharmInv's policy for the mod: the backpack and the custom player page).
constexpr auto CountingPage(int32_t page) noexcept -> bool {
	return page == BackpackPage || page == CharmInvPage;
}

// Where a stored carry1 copy lies, for the duplicate rule.
enum class Place {
	Other,       // not on a counting page (cube, stash, ...): not a copy of the rule
	Charm,       // the backpack or the charm area of the custom page: a copy that may be the active one
	OutsideTab,  // the custom page outside the charm area (another invtabs tab): never the active one, never gives its bonus
};

constexpr auto PlaceOf(int32_t page, int32_t x, int32_t y, const CharmArea& area) noexcept -> Place {
	if (page == BackpackPage) {
		return Place::Charm;
	}
	if (page != CharmInvPage) {
		return Place::Other;
	}
	return InCharmArea(area, x, y) ? Place::Charm : Place::OutsideTab;
}

}  // namespace charm_dup

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

// D2R item pages: 0 is the backpack; D2RLoader gives the mod's one custom player page number 6 (CharmInv's grid).
inline constexpr int32_t BackpackPage = 0;
inline constexpr int32_t CharmInvPage = 6;

// One stored copy of a carry1 unique on a page whose charms count.
struct Copy {
	uint32_t unitId;       // the item's unit id (unique while the game runs)
	int32_t uniqueIndex;   // row of uniqueitems.txt
	int32_t page;          // 0 backpack, 6 CharmInv
	int32_t x, y;          // grid cell
};

// Ordering of the copies of one unique: CharmInv first, then the backpack; on a page the top row first, then the left column;
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

}  // namespace charm_dup

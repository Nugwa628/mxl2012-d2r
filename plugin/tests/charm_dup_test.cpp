// Standalone test of the carry1 duplicate rule, pure part (charm_dup_logic.h; not part of the plugin DLL).
#include "../src/charm_dup_logic.h"

#include <cstdio>

namespace {
int failures = 0;
void Check(bool ok, const char* what) {
	if (!ok) {
		++failures;
		std::printf("FAIL: %s\n", what);
	}
}
}  // namespace

int main() {
	using namespace charm_dup;
	Check(PickActive(nullptr, 0) == -1, "no copy: none active");

	const Copy one[] = {{10, 7, BackpackPage, 3, 1}};
	Check(PickActive(one, 1) == 0, "a single copy is active");

	// one copy in CharmInv, a second picked up into the backpack (even at its top-left cell): the CharmInv copy stays active
	const Copy inv[] = {{20, 7, BackpackPage, 0, 0}, {21, 7, CharmInvPage, 5, 3}};
	Check(PickActive(inv, 2) == 1, "CharmInv copy preferred over the backpack");
	const Copy invRev[] = {{21, 7, CharmInvPage, 5, 3}, {20, 7, BackpackPage, 0, 0}};
	Check(PickActive(invRev, 2) == 0, "the walk order does not matter");

	// the CharmInv copy dropped: the backpack copy becomes active
	const Copy left[] = {{20, 7, BackpackPage, 0, 0}};
	Check(PickActive(left, 1) == 0, "the remaining copy takes over");

	// two copies in the backpack: top row first, then left column
	const Copy two[] = {{31, 7, BackpackPage, 4, 1}, {30, 7, BackpackPage, 6, 0}};
	Check(PickActive(two, 2) == 1, "backpack: top row first");
	const Copy row[] = {{41, 7, BackpackPage, 4, 2}, {40, 7, BackpackPage, 1, 2}};
	Check(PickActive(row, 2) == 1, "backpack: same row, left column first");
	const Copy two6[] = {{51, 7, CharmInvPage, 1, 0}, {50, 7, CharmInvPage, 0, 0}};
	Check(PickActive(two6, 2) == 1, "two in CharmInv: top-left first");
	const Copy three[] = {{60, 7, BackpackPage, 0, 0}, {61, 7, CharmInvPage, 9, 3}, {62, 7, CharmInvPage, 2, 3}};
	Check(PickActive(three, 3) == 2, "three copies: CharmInv, then its top-left");

	// a reload gives new unit ids: same cells, same choice
	const Copy reload[] = {{900, 7, BackpackPage, 4, 1}, {901, 7, BackpackPage, 6, 0}};
	Check(PickActive(reload, 2) == 1, "after a reload the same cell wins");

	// the order is strict: never both a < b and b < a
	Check(!(Before(two[0], two[1]) && Before(two[1], two[0])), "strict order");
	Check(!Before(one[0], one[0]), "irreflexive");
	const Copy same[] = {{71, 7, BackpackPage, 0, 0}, {70, 7, BackpackPage, 0, 0}};
	Check(PickActive(same, 2) == 1, "unit id breaks a tie");

	Check(IsCarry1(1) && IsCarry1(46) && !IsCarry1(0), "carry1 cell above 0");
	Check(CountingPage(0) && CountingPage(6) && !CountingPage(3) && !CountingPage(4), "backpack and CharmInv count, cube and stash do not");

	// CharmInv (no InvTabsCharmTab export): the whole custom page is charm inventory, as before
	const CharmArea whole{};
	Check(whole.wholePage && InCharmArea(whole, 0, 0) && InCharmArea(whole, 9, 3) && InCharmArea(whole, 15, 15), "no invtabs: whole page");
	Check(PlaceOf(CharmInvPage, 9, 3, whole) == Place::Charm && PlaceOf(BackpackPage, 0, 0, whole) == Place::Charm, "no invtabs: page 6 and backpack");
	Check(PlaceOf(3, 0, 0, whole) == Place::Other && PlaceOf(4, 0, 0, whole) == Place::Other, "cube and stash are no copies");

	// invtabs: the charm tab 10 x 6 at 0,0 of the 16 x 16 page; other tabs elsewhere on the page are not charm inventory
	const CharmArea tab = TabArea(1, 0, 0, 10, 6);
	Check(!tab.wholePage && tab.w == 10 && tab.h == 6, "invtabs tab taken");
	Check(InCharmArea(tab, 0, 0) && InCharmArea(tab, 9, 5) && !InCharmArea(tab, 10, 0) && !InCharmArea(tab, 0, 6) && !InCharmArea(tab, 15, 15),
	      "tab edges");
	Check(PlaceOf(CharmInvPage, 9, 2, tab) == Place::Charm, "CharmInv's 10 x 4 cells are inside the pinned tab");
	Check(PlaceOf(CharmInvPage, 12, 0, tab) == Place::OutsideTab && PlaceOf(CharmInvPage, 0, 10, tab) == Place::OutsideTab, "other tab");
	Check(PlaceOf(BackpackPage, 12, 3, tab) == Place::Charm, "the backpack still counts with invtabs");
	const CharmArea moved = TabArea(1, 6, 10, 10, 6);
	Check(PlaceOf(CharmInvPage, 0, 0, moved) == Place::OutsideTab && PlaceOf(CharmInvPage, 6, 10, moved) == Place::Charm &&
	          PlaceOf(CharmInvPage, 15, 15, moved) == Place::Charm,
	      "a tab not at 0,0");

	// a missing tab or a rectangle off the page: the old whole-page behaviour (never takes a bonus away)
	Check(TabArea(0, 0, 0, 10, 6).wholePage, "no tab: whole page");
	Check(TabArea(1, 0, 0, 0, 6).wholePage && TabArea(1, -1, 0, 10, 6).wholePage && TabArea(1, 7, 0, 10, 6).wholePage &&
	          TabArea(1, 0, 11, 10, 6).wholePage,
	      "bad rectangle: whole page");
	Check(!TabArea(1, 0, 0, 16, 16).wholePage && TabArea(1, 0, 0, 16, 16).w == 16, "a 16 x 16 tab is fine");

	// the rule with invtabs: only copies whose place is Charm take part; an active copy in the tab beats the backpack, a copy in
	// another tab is never chosen (charm_dup.cpp leaves it out of the walk and answers it "not met")
	const Copy withTab[] = {{80, 7, BackpackPage, 0, 0}, {81, 7, CharmInvPage, 3, 1}};
	Check(PickActive(withTab, 2) == 1, "invtabs: the tab copy is active");

	if (failures == 0) {
		std::printf("charm_dup: all checks passed\n");
	}
	return failures == 0 ? 0 : 1;
}

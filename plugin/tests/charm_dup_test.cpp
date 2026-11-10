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

	if (failures == 0) {
		std::printf("charm_dup: all checks passed\n");
	}
	return failures == 0 ? 0 : 1;
}

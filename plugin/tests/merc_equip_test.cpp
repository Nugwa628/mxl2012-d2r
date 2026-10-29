// Standalone test of the mercenary weapon / shield rule (merc_equip_logic.h; not part of the plugin DLL). Lane mercs2.
#include "../src/merc_equip_logic.h"

#include <cstdio>

namespace {
int failures = 0;
void Check(bool ok, const char* what) {
	if (!ok) {
		++failures;
		std::printf("FAIL: %s\n", what);
	}
}

// An item described by the item types it belongs to (its own type and its parents, as D2R's type test walks them).
struct Item {
	int types[3] = {-1, -1, -1};
	auto Is(int t) const -> bool { return t >= 0 && (types[0] == t || types[1] == t || types[2] == t); }
};
auto Wears(int cls, const Item& it) -> bool {
	const auto* c = merc_equip::ClassOf(cls);
	return c != nullptr && merc_equip::MayWear(*c, [&](int t) { return it.Is(t); });
}
}  // namespace

int main() {
	using namespace merc_equip;
	const Item bow{{TypeBow, TypeWeapon}}, sword{{TypeSword, TypeWeapon}}, spear{{TypeSpear, TypeWeapon}}, pole{{TypePolearm, TypeWeapon}};
	const Item axe{{24, TypeWeapon}}, crossbow{{35, TypeWeapon}}, shield{{TypeShield, TypeAnyShield}}, helm{{37, -1, -1}}, armour{{3, -1, -1}};
	Check(ClassOf(271) && ClassOf(338) && ClassOf(359) && ClassOf(561) && !ClassOf(560) && !ClassOf(150), "the four hire classes only");
	Check(Wears(271, bow) && !Wears(271, sword) && !Wears(271, crossbow) && !Wears(271, shield), "Rogue: bows only");
	Check(Wears(338, pole) && Wears(338, spear) && !Wears(338, bow) && !Wears(338, sword) && !Wears(338, shield), "Desert: polearm, spear");
	Check(Wears(359, sword) && Wears(359, shield) && !Wears(359, bow) && !Wears(359, spear) && !Wears(359, axe), "Iron Wolf: sword, shield");
	Check(Wears(561, sword) && !Wears(561, axe) && !Wears(561, shield) && !Wears(561, bow), "Barbarian: sword only");
	const int hires[] = {271, 338, 359, 561};
	for (int c : hires) {
		Check(Wears(c, helm) && Wears(c, armour), "helms and body armour are not limited");
	}
	std::printf(failures == 0 ? "merc equip tests: all passed\n" : "merc equip tests: %d failures\n", failures);
	return failures == 0 ? 0 : 1;
}

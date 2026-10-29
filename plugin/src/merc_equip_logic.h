// Mercenary weapon and shield types (merc_equip.cpp; pure part, unit-tested in plugin/tests/merc_equip_test.cpp). Lane mercs2.
//
// 1.13c lets a mercenary wield a weapon or a shield only when the item is of one of its hireling.txt row's WType1 / WType2
// item types; Median XL 2012 v005 keeps the vanilla values on all 120 rows: Rogue Scout bow, Desert Mercenary polearm / spear,
// Iron Wolf sword / shield, Barbarian sword. D2R 3.3 has no WType columns and its own equip test lets every mercenary wield
// any weapon and shield (checked by clicks in game, docs/testing.md `mercs`). Armour and helms are not limited (1.13c's
// head / torso slots take any helm and body armour); class items stay refused by D2R's own class test (equivalentcharclass
// is empty, tools/d2r_adds.py merc_classitems).
#pragma once

#include <cstdint>

namespace merc_equip {

// itemtypes.txt rows (0-based), the same in D2R and in v005 (tools/validate.py merc_rules checks the built table).
inline constexpr int32_t TypeShield = 2;     // shie
inline constexpr int32_t TypeBow = 27;       // bow
inline constexpr int32_t TypeSword = 30;     // swor
inline constexpr int32_t TypeSpear = 33;     // spea
inline constexpr int32_t TypePolearm = 34;   // pole
inline constexpr int32_t TypeWeapon = 45;    // weap: every weapon
inline constexpr int32_t TypeAnyShield = 51; // shld: every shield (shie, the paladin and necromancer ones)

struct HireClass {
	int32_t monsterClass;  // the hireling's monster class (hireling.txt Class)
	int32_t wtype[2];      // WType1 / WType2, -1 = none
	const char* name;
};

inline constexpr HireClass Classes[] = {
    {271, {TypeBow, -1}, "Rogue Scout"},
    {338, {TypePolearm, TypeSpear}, "Desert Mercenary"},
    {359, {TypeSword, TypeShield}, "Iron Wolf"},
    {561, {TypeSword, -1}, "Barbarian"},
};

constexpr auto ClassOf(int32_t monsterClass) noexcept -> const HireClass* {
	for (const HireClass& c : Classes) {
		if (c.monsterClass == monsterClass) {
			return &c;
		}
	}
	return nullptr;
}

// May a mercenary of this class wear the item? isType(type id) answers whether the item is of that item type (or a child of it).
template <typename IsType>
constexpr auto MayWear(const HireClass& c, IsType&& isType) -> bool {
	if (!isType(TypeWeapon) && !isType(TypeAnyShield)) {
		return true;  // helm, body armour, anything else: not limited by WType
	}
	for (const int32_t t : c.wtype) {
		if (t >= 0 && isType(t)) {
			return true;
		}
	}
	return false;
}

}  // namespace merc_equip

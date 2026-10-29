// Mercenary weapon and shield types as 1.13c / Median XL 2012 (merc_equip_logic.h has the rule and the table; off word mercequip).
//
// D2R's item requirement test 0x36bc50 (item, unit, flag, &str, &dex, &level, flag2) -> 1 usable answers for a mercenary with
// the strength / dexterity / level and class-item checks only (its mercenary branch tests the item's class byte against
// equivalentcharclass, nothing else): every mercenary could wield every weapon and shield. The equip packet handler 0x4c0e20
// (client packet 0x51, the hireling panel click) and the client's panel both ask it, so a refusal here gives the game's own
// "cannot use" reaction. The hook runs D2R's test first and only turns a 1 into 0. The rule is 1.13c's
// hireling WType lists.
#include "merc_equip.h"

#include "d2r.h"
#include "merc_equip_logic.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>

namespace {

constexpr uint64_t RvaRequirement = 0x36bc50;
// MOV [RSP+0x20],R9 / MOV [RSP+0x18],R8D / PUSH RBP / PUSH RSI / PUSH RDI / SUB RSP,0x60
constexpr uint8_t RequirementEntry[] = {0x4c, 0x89, 0x4c, 0x24, 0x20, 0x44, 0x89, 0x44, 0x24, 0x18, 0x55, 0x56, 0x57, 0x48, 0x83, 0xec, 0x60};
constexpr uint64_t RvaIsItemType = 0x373890;  // (item, item type) -> non-zero when the item is of that type
constexpr int32_t UnitTypeMonster = 1, UnitTypeItem = 4;

using RequirementFn = uint64_t (*)(void* item, void* unit, int32_t a3, uint32_t* str, uint32_t* dex, uint32_t* level, int32_t a7);
using IsItemTypeFn = int32_t (*)(void* item, int32_t type);
RequirementFn g_requirement = nullptr;
IsItemTypeFn g_isType = nullptr;
volatile LONG g_checked = 0;
volatile LONG g_refused = 0;

uint64_t RequirementHook(void* item, void* unit, int32_t a3, uint32_t* str, uint32_t* dex, uint32_t* level, int32_t a7) noexcept {
	const uint64_t result = g_requirement(item, unit, a3, str, dex, level, a7);
	if ((result & 0xff) == 0 || item == nullptr || unit == nullptr || d2r::At<int32_t>(item, d2r::UnitType) != UnitTypeItem ||
	    d2r::At<int32_t>(unit, d2r::UnitType) != UnitTypeMonster) {
		return result;
	}
	const merc_equip::HireClass* hire = merc_equip::ClassOf(d2r::At<int32_t>(unit, d2r::UnitClass));
	if (hire == nullptr) {
		return result;
	}
	InterlockedIncrement(&g_checked);
	if (merc_equip::MayWear(*hire, [item](int32_t type) { return g_isType(item, type) != 0; })) {
		return result;
	}
	InterlockedIncrement(&g_refused);
	return 0;
}

}  // namespace

auto InstallMercEquip(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int {
	g_isType = reinterpret_cast<IsItemTypeFn>(context->exeBase + RvaIsItemType);
	const bool ok = context->InstallInlineHook(RvaRequirement, RequirementEntry, sizeof(RequirementEntry), reinterpret_cast<void*>(&RequirementHook),
	                                           reinterpret_cast<void**>(&g_requirement));
	std::snprintf(report, reportSize, "mercenary weapons / shields of 1.13c's WType (Rogue bow, Desert polearm / spear, Iron Wolf sword / shield, "
	              "Barbarian sword; 0x36bc50 hooked)%s", ok ? "" : " FAILED");
	return ok ? 1 : 0;
}

void MercEquipStats(long* checked, long* refused) noexcept {
	*checked = g_checked;
	*refused = g_refused;
}

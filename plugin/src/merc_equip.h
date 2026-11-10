// Mercenary weapon and shield types as 1.13c / Median XL 2012 (merc_equip.cpp, merc_equip_logic.h). Off word: mercequip.
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>
#include <cstdint>

// Hooks D2R's item requirement test 0x36bc50 (the hireling panel's equip path asks it): a weapon or shield outside the
// mercenary's WType1 / WType2 is refused. Returns 1 when the hook is in.
auto InstallMercEquip(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int;

// Tests of a mercenary and refusals since start, for `mxl2012`.
void MercEquipStats(long* checked, long* refused) noexcept;
// Another part's veto on the same requirement test (one hook per entry: D2RLoader refuses a second one at 0x36bc50). `filter`
// is asked after D2R said "met" and answers true to make it "not met". Returns false when this part's hook is not in (the
// caller then hooks 0x36bc50 itself).
using RequirementFilter = bool (*)(void* item, void* unit, int32_t equipping) noexcept;
auto MercEquipAddRequirementFilter(RequirementFilter filter) noexcept -> bool;

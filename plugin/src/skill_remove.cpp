// Skill-remove guard for units that own no skill (docs/bugs.md #15, off word skillremove).
//
// Median XL 2012's summons whose pets own no skill (Batstrike's bats, Summon Rampagor, Summon Lamia) give the pets their
// `sumskill`s at level 0 when the caster lacks them; D2R's pet skill step sets that level, level 0 removes the skill, and the
// remove (0x3402d0) asserts `ptSkill` (Skills.cpp:904) on a skill list without a first skill, then removes nothing. 1.13c removed
// nothing without a word. The hook returns before the assert when the unit has no skill list or no skill (skill_remove_logic.h);
// every other call runs D2R's function unchanged. Call chain of the assert (lane skills, asserttrace): 340358 33efec 433ac3
// 55f4e4 575bb5 (summon do 119).
#include "skill_remove.h"

#include "d2r.h"
#include "skill_remove_logic.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>

namespace {

using d2r::At;

constexpr uint64_t RvaSkillRemove = 0x3402d0;
constexpr int UnitSkillList = 0x100;  // 0x34b6e0(unit) reads it; the list's first word is its first skill
// PUSH RBP / PUSH RSI / PUSH R14 / SUB RSP,0x20 / MOV R14D,R8D / MOV ESI,EDX / MOV RBP,RCX
constexpr uint8_t SkillRemoveEntry[] = {0x40, 0x55, 0x56, 0x41, 0x56, 0x48, 0x83, 0xec, 0x20,
                                        0x45, 0x8b, 0xf0, 0x8b, 0xf2, 0x48, 0x8b, 0xe9};

using SkillRemoveFn = void (*)(d2r::Unit* unit, int32_t skill, int32_t flag);
SkillRemoveFn g_skillRemove = nullptr;
volatile LONG g_skips = 0;
volatile LONG g_lastSkill = 0;

void SkillRemoveHook(d2r::Unit* unit, int32_t skill, int32_t flag) noexcept {
	const void* list = unit != nullptr ? At<const void*>(unit, UnitSkillList) : nullptr;
	const void* first = list != nullptr ? At<const void*>(list, 0) : nullptr;
	if (skill_remove::SkipsRemove(unit != nullptr, list != nullptr, first != nullptr)) {
		InterlockedIncrement(&g_skips);
		InterlockedExchange(&g_lastSkill, skill);
		return;
	}
	g_skillRemove(unit, skill, flag);
}

}  // namespace

auto InstallSkillRemoveGuard(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int {
	const bool ok = context->InstallInlineHook(RvaSkillRemove, SkillRemoveEntry, sizeof(SkillRemoveEntry),
	                                           reinterpret_cast<void*>(&SkillRemoveHook), reinterpret_cast<void**>(&g_skillRemove));
	std::snprintf(report, reportSize, "skill removes from units without skills return (0x3402d0 hooked)%s", ok ? "" : " FAILED");
	return ok ? 1 : 0;
}

auto SkillRemoveSkips() noexcept -> long {
	return g_skips;
}

auto SkillRemoveLastSkill() noexcept -> long {
	return g_lastSkill;
}

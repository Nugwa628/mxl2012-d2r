// Item-event skill guard (docs/bugs.md #40, off word itemeffect).
//
// Item properties that fire a skill on an event name their skill in skills.txt; D2R's resolver 0x589930 (called by the event
// dispatchers 0x5896e0 / 0x589820 / 0x56b020) asserts "ptSkill->nItemEffect != 0" for a skill without ItemEffect and returns
// 0. Median XL 2012's own data has such properties (item_effect_logic.h), and the tooltip lines are kept; so the call is
// answered with 0 before the assert, which is what 1.13c did (nothing).
#include "item_effect.h"

#include "d2r.h"
#include "item_effect_logic.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>

namespace {

using d2r::At;

constexpr uint64_t RvaItemEventSkill = 0x589930;
// MOV [RSP+0x20],R9D / PUSH RBX / PUSH RBP / PUSH RSI / PUSH RDI / PUSH R13 / PUSH R15 / SUB RSP,0x68 / MOV R15,RCX
constexpr uint8_t ItemEventSkillEntry[] = {0x44, 0x89, 0x4c, 0x24, 0x20, 0x53, 0x55, 0x56, 0x57, 0x41,
                                           0x55, 0x41, 0x57, 0x48, 0x83, 0xec, 0x68, 0x4c, 0x8b, 0xf9};

// (game, unit, skill, a4, then eight stack slots): the arguments the hook does not read are forwarded untouched, 8 bytes each.
using ItemEventSkillFn = int32_t (*)(void* game, void* unit, int32_t skill, uint32_t a4, uint64_t s5, uint64_t s6, uint64_t s7,
                                     uint64_t s8, uint64_t s9, uint64_t s10, uint64_t s11, uint64_t s12);
ItemEventSkillFn g_itemEventSkill = nullptr;
volatile LONG g_skips = 0;
volatile LONG g_lastSkill = 0;

int32_t ItemEventSkillHook(void* game, void* unit, int32_t skill, uint32_t a4, uint64_t s5, uint64_t s6, uint64_t s7, uint64_t s8,
                           uint64_t s9, uint64_t s10, uint64_t s11, uint64_t s12) noexcept {
	if (game != nullptr && skill > 0) {
		const uint8_t* record = d2r::api.getSkillRecord(d2r::DataFlag(static_cast<d2r::Game*>(game)), skill);
		if (item_effect::SkipsEventSkill(skill, record != nullptr, record != nullptr ? At<uint16_t>(record, d2r::SkItemEffect) : 1u)) {
			InterlockedIncrement(&g_skips);
			InterlockedExchange(&g_lastSkill, skill);
			return 0;
		}
	}
	return g_itemEventSkill(game, unit, skill, a4, s5, s6, s7, s8, s9, s10, s11, s12);
}

}  // namespace

auto InstallItemEffectGuard(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int {
	d2r::Bind(context->exeBase);
	const bool ok = context->InstallInlineHook(RvaItemEventSkill, ItemEventSkillEntry, sizeof(ItemEventSkillEntry),
	                                           reinterpret_cast<void*>(&ItemEventSkillHook), reinterpret_cast<void**>(&g_itemEventSkill));
	std::snprintf(report, reportSize, "item event skills without ItemEffect answered 0 (0x589930 hooked)%s", ok ? "" : " FAILED");
	return ok ? 1 : 0;
}

auto ItemEffectSkips() noexcept -> long {
	return g_skips;
}

auto ItemEffectLastSkill() noexcept -> long {
	return g_lastSkill;
}

// Leap Attack, Cherub Strike and Level 90 Cherub stun for Median's skill length (docs/bugs.md #580; off word stunlen).
//
// Their stun missiles (leapattack, deathrockbolt) have missiles.txt pSrvDmgFunc 7 and dParam1 0: the length comes from the
// skill. D2R's function 7 reads it from the skill's calc4, which their server functions (78, 11) read as "% Damage Dealt as
// Elemental", so tools/txt_migrate.py cannot put the length there (it does for Blink, Bear Claw, Stampede ...). This hook runs
// D2R's function, then writes 1.13c's Param1 + Param2 * (lvl - 1) of the missile's skill and level for those three skills
// only (stun_len_logic.h). Every other missile keeps D2R's result.
#include "stun_len.h"

#include "d2r.h"
#include "stun_len_logic.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>

namespace {

using d2r::Game;
using d2r::Unit;

using StunFn = uint64_t (*)(Game* game, Unit* missile, Unit* target, uint8_t* damage);
StunFn g_original = nullptr;
volatile LONG g_calls = 0;
volatile LONG g_written = 0;
volatile LONG g_logged = 0;
const D2RL::PluginContext* g_context = nullptr;

volatile LONG64 g_seenKeys[64] = {};

// True the first time this combination is seen (up to 64 combinations): each goes to the log once.
auto FirstTime(int32_t missile, int32_t skill, int32_t level, int32_t before, int32_t after) noexcept -> bool {
	const LONG64 key = static_cast<LONG64>(stun_len::NoteKey(missile, skill, level, before, after));
	for (auto& slot : g_seenKeys) {
		const LONG64 was = InterlockedCompareExchange64(&slot, key, 0);
		if (was == 0) {
			return true;
		}
		if (was == key) {
			return false;
		}
	}
	return false;
}

void Note(int32_t missile, int32_t skill, int32_t level, int32_t dParam1, int32_t before, int32_t after, bool written) noexcept {
	if (g_context == nullptr || !FirstTime(missile, skill, level, before, after)) {
		return;
	}
	InterlockedIncrement(&g_logged);
	char line[200];
	if (written) {
		std::snprintf(line, sizeof(line), "mxl2012-core: stunlen missile %d skill %d level %d dParam1 %d: stun %d -> %d frames", missile, skill, level,
		              dParam1, before, after);
	} else {
		std::snprintf(line, sizeof(line), "mxl2012-core: stunlen missile %d skill %d level %d dParam1 %d: stun %d frames (D2R's)", missile, skill,
		              level, dParam1, before);
	}
	g_context->LogInfo(line);
}

// Each new combination of missile, skill, level and length of a function-7 hit goes to the log once (up to 64), with D2R's
// length and the one written (if any).
auto Hook(Game* game, Unit* missile, Unit* target, uint8_t* damage) noexcept -> uint64_t {
	const uint64_t result = g_original(game, missile, target, damage);
	InterlockedIncrement(&g_calls);
	if (game == nullptr || missile == nullptr || damage == nullptr || d2r::At<int32_t>(missile, d2r::UnitType) != 3) {
		return result;
	}
	const uint8_t* data = d2r::At<const uint8_t*>(missile, stun_len::UnitData);
	const uint32_t flag = d2r::DataFlag(game);
	const int32_t missileId = d2r::At<int32_t>(missile, d2r::UnitClass);
	const uint8_t* mrec = d2r::api.missileRecord(flag, missileId);
	if (data == nullptr || mrec == nullptr) {
		return result;
	}
	const int32_t skill = d2r::At<int16_t>(data, stun_len::MisDataSkill);
	const int32_t level = d2r::At<int16_t>(data, stun_len::MisDataLevel);
	const int32_t dParam1 = d2r::At<int32_t>(mrec, stun_len::MisDParam1);
	int32_t* slot = reinterpret_cast<int32_t*>(damage + stun_len::DmgStunLength);
	const int32_t before = *slot;
	const uint8_t* srec = stun_len::IsParamStunSkill(skill) && stun_len::TakesSkillLength(dParam1) ? d2r::api.getSkillRecord(flag, skill) : nullptr;
	if (srec == nullptr) {
		Note(missileId, skill, level, dParam1, before, before, false);
		return result;
	}
	const int32_t length = stun_len::StunLength(d2r::At<int32_t>(srec, stun_len::SkParam1), d2r::At<int32_t>(srec, stun_len::SkParam2), level);
	Note(missileId, skill, level, dParam1, before, length, true);
	*slot = length;
	InterlockedIncrement(&g_written);
	return result;
}

}  // namespace

auto InstallStunLen(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int {
	d2r::Bind(context->exeBase);
	g_context = context;
	const bool ok = context->InstallInlineHook(stun_len::RvaSrvDmgStun, stun_len::Entry, sizeof(stun_len::Entry), reinterpret_cast<void*>(&Hook),
	                                           reinterpret_cast<void**>(&g_original));
	std::snprintf(report, reportSize, "skills 143 / 665 / 1001 (Leap Attack, Cherub Strike, Level 90 Cherub) stun Param1 + Param2 * (lvl - 1): 0x453e30%s",
	              ok ? "" : " FAILED (bytes differ, off)");
	return ok ? 1 : 0;
}

void StunLenCounts(long* calls, long* written) noexcept {
	*calls = g_calls;
	*written = g_written;
}

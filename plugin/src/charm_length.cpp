// The conversion length of skill server do 51 as in 1.13c: Param3 frames, not calc2 (charm_length_logic.h has the reading;
// bug #527). Batstrike's charm (its third charge, calc2 `ulvl` for the bats of the second) lasted 2.4 s at level 60 on D2R
// instead of 1.13c's 10 s (Param3 250). The charms with srvdofunc 51 carry calc2 `par3` from txt_migrate.py, so for them
// this part changes nothing; with the part off Batstrike falls back to D2R's ulvl frames.
#include "charm_length.h"

#include "charm_length_logic.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

using namespace charm_length;

using SkillRecordFn = const uint8_t* (*)(uint8_t game, int32_t skill) noexcept;

const D2RL::PluginContext* g_context = nullptr;
SkillRecordFn g_skillRecord = nullptr;
volatile long g_calls = 0;
volatile long g_lastSkill = -1;
volatile long g_lastLength = 0;

// Called in place of the calc evaluator 0x3b5160 with its arguments (rcx game byte, rdx unit, r8d calc2, r9d skill, level).
auto Length(uint8_t game, void* /*unit*/, int32_t /*calc*/, int32_t skill, int32_t level) noexcept -> int32_t {
	const uint8_t* record = g_skillRecord(game, skill);
	int32_t param3 = 0;
	if (record != nullptr) {
		std::memcpy(&param3, record + Param3Offset, sizeof(param3));
	}
	const int32_t length = ClassicLength(record != nullptr, param3);
	const long n = InterlockedIncrement(&g_calls);
	InterlockedExchange(&g_lastSkill, skill);
	InterlockedExchange(&g_lastLength, length);
	if (n <= 4 && g_context != nullptr) {  // the first casts: confirms the Param3 offset on real records
		char line[128];
		std::snprintf(line, sizeof(line), "mxl2012-core charmlen: skill %d level %d -> Param3 %d frames", skill, level, length);
		g_context->LogInfo(line);
	}
	return length;
}

}  // namespace

auto InstallCharmLength(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	g_context = context;
	const auto* image = reinterpret_cast<const uint8_t*>(context->exeBase);
	const bool same = std::memcmp(image + LengthCallRva, LengthCall, sizeof(LengthCall)) == 0 &&
	                  std::memcmp(image + LengthLoadRva, LengthLoad, sizeof(LengthLoad)) == 0 &&
	                  std::memcmp(image + PadRva, Pad, sizeof(Pad)) == 0;
	if (!same) {
		std::snprintf(report, reportSize, "off: bytes differ at 0x57090f / 0x57091b / 0x570772, left as D2R (calc2 frames)");
		return false;
	}
	g_skillRecord = reinterpret_cast<SkillRecordFn>(context->exeBase + SkillRecordRva);
	const AbsJump pad = AbsJumpBytes(reinterpret_cast<uint64_t>(&Length));
	const bool ok = context->PatchBytes(PadRva, Pad, sizeof(Pad), pad.bytes, sizeof(pad.bytes)) &&
	                context->PatchCallRel32(LengthCallRva, LengthCall, sizeof(LengthCall), PadRva);
	std::snprintf(report, reportSize, "%s: srvdofunc 51 converts for Param3 + rand(Param4) frames as 1.13c (0x57091b calc2 call)",
	              ok ? "on" : "FAILED");
	return ok;
}

void CharmLengthStats(long* calls, long* lastSkill, long* lastLength) noexcept {
	*calls = g_calls;
	*lastSkill = g_lastSkill;
	*lastLength = g_lastLength;
}

// Whirlwind's hit rate as in 1.13c (whirlwind_logic.h has the rule; bug #281). Without a `wwproc`
// half: chance to cast on striking during a spin was a Median 2.x fix, and 1.13c (so Median XL 2012) has
// the same refusal as D2R (the caster holds state 54 uninterruptable for the spin).
//
// Hook on 0x56ac00 (unit, weapon) -> frames until the next hit. Only Whirlwind's do function calls it (0x56916d, 0x569186,
// 0x5691e2), so nothing else changes; D2R's dual wield (both weapons, average of the two delays) stays. Entry bytes of build
// 93847, whole instructions, no rip-relative operand:
//   mov [rsp+0x18],rbx / push rbp / push rsi / push rdi / push r14 / push r15 / sub rsp,0x80   (19 bytes)
#include "whirlwind.h"

#include "whirlwind_logic.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>

namespace {

constexpr uint64_t HitDelayRva = 0x56ac00;
constexpr uint8_t HitDelayEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x18, 0x55, 0x56, 0x57, 0x41, 0x56,
                                     0x41, 0x57, 0x48, 0x81, 0xec, 0x80, 0x00, 0x00, 0x00};
constexpr uint64_t UnitStatRva = 0x2f5020;    // (unit, stat, param) -> value (what 0x56ac00 reads stat 68 with)
constexpr uint64_t UnitStatNpRva = 0x2f5c60;  // (unit, stat) -> value (what D2R's IAS term reads stat 93 with)
constexpr uint64_t SpeedMaxRva = 0x34a5c0;    // (unit) -> 175 (250 for a player in some states)
constexpr int32_t StatAttackRate = 68;
constexpr int32_t StatIas = 93;

using HitDelayFn = int32_t (*)(void* unit, void* weapon) noexcept;
using UnitStatFn = int32_t (*)(void* unit, int32_t stat, int32_t param) noexcept;
using UnitStatNpFn = int32_t (*)(void* unit, int32_t stat) noexcept;
using SpeedMaxFn = int32_t (*)(void* unit) noexcept;

const D2RL::PluginContext* g_context = nullptr;
HitDelayFn g_original = nullptr;
UnitStatFn g_unitStat = nullptr;
UnitStatNpFn g_unitStatNp = nullptr;
SpeedMaxFn g_speedMax = nullptr;
volatile long g_calls = 0;
volatile long g_lastD2R = 0;
volatile long g_lastDelay = 0;

auto HitDelay(void* unit, void* weapon) noexcept -> int32_t {
	const int32_t d2r = g_original(unit, weapon);
	if (unit == nullptr || weapon == nullptr) {
		return whirlwind::NoWeaponDelay;
	}
	const int32_t rate = g_unitStat(unit, StatAttackRate, 0);
	const int32_t ias = g_unitStatNp(unit, StatIas);
	const int32_t speedMax = g_speedMax(unit);
	const int32_t delay = whirlwind::HitDelay(d2r, rate, ias, speedMax, true);
	const long n = InterlockedIncrement(&g_calls);
	InterlockedExchange(&g_lastD2R, d2r);
	InterlockedExchange(&g_lastDelay, delay);
	if (n <= 6 && g_context != nullptr) {  // the first hits' values: confirms the stat 68 base on real units
		char line[192];
		std::snprintf(line, sizeof(line), "mxl2012-core whirlwind: stat68 %d, IAS %d, D2R speed %d -> %d frames; 1.13c speed %d -> hit every %d",
		              rate, ias, whirlwind::D2RSpeed(rate, ias, speedMax), d2r, whirlwind::ClassicSpeed(rate, ias), delay);
		g_context->LogInfo(line);
	}
	return delay;
}

}  // namespace

auto InstallWhirlwind(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	g_context = context;
	g_unitStat = reinterpret_cast<UnitStatFn>(context->exeBase + UnitStatRva);
	g_unitStatNp = reinterpret_cast<UnitStatNpFn>(context->exeBase + UnitStatNpRva);
	g_speedMax = reinterpret_cast<SpeedMaxFn>(context->exeBase + SpeedMaxRva);
	const bool ok = context->InstallInlineHook(HitDelayRva, HitDelayEntry, sizeof(HitDelayEntry), reinterpret_cast<void*>(&HitDelay),
	                                           reinterpret_cast<void**>(&g_original));
	std::snprintf(report, reportSize, "srvdofunc 76 hits as 1.13c (a hit every 4-16 frames by weapon speed; 0x56ac00 hooked)%s", ok ? "" : " FAILED");
	return ok;
}

void WhirlwindStats(long* calls, long* lastD2R, long* lastDelay) noexcept {
	*calls = g_calls;
	*lastD2R = g_lastD2R;
	*lastDelay = g_lastDelay;
}

// Ctrl stat range line for descfuncs D2R has no range case for (docs/bugs.md #617, off word rangedesc).
//
// With Ctrl stat ranges on (`item_stat_ranges = true`, bug #528) D2R builds every tooltip stat line with its ranged mod
// string (0x2d7850). That function has no case for descfuncs 5, 10, 11, 17, 18, 22 and 23: it logs "Tried to get a ranged mod
// string on an invalid DescFunc type" (mods.cpp:998) and the line comes out blank. Median's "Reanimate as:" (item_reanimate,
// descfunc 23) is on many uniques, runewords and set items. The hook takes only those descfuncs and builds the line with
// D2R's plain mod string (0x2d6520) at min and at max, merged into "(min-max)" (ranged_desc_logic.h); every other line runs
// D2R's function unchanged.
#include "ranged_desc.h"

#include "ranged_desc_logic.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

constexpr uint64_t RvaRangedModString = 0x2d7850;
constexpr uint64_t RvaPlainModString = 0x2d6520;
constexpr size_t LineSize = 0x100;  // the size D2R gives both functions' buffers (its strcat calls use 0x100)
constexpr int RecDescfunc = 0x32;    // ItemStatCost record: descfunc (byte)
constexpr int RecGroupDescfunc = 0x3c;  // dgrpfunc (byte)
// both functions start alike: PUSH RBP / PUSH RBX / PUSH RSI / PUSH RDI / PUSH R12-R15 / LEA RBP,[RSP-X]
constexpr uint8_t RangedEntry[] = {0x40, 0x55, 0x53, 0x56, 0x57, 0x41, 0x54, 0x41, 0x55, 0x41, 0x56,
                                   0x41, 0x57, 0x48, 0x8d, 0xac, 0x24, 0x48, 0xf5, 0xff, 0xff};
constexpr uint8_t PlainEntry[] = {0x40, 0x55, 0x53, 0x56, 0x57, 0x41, 0x54, 0x41, 0x55, 0x41, 0x56,
                                  0x41, 0x57, 0x48, 0x8d, 0xac, 0x24, 0x78, 0xf6, 0xff, 0xff};

// item, ItemStatCost record, min, max, param, group flag, out buffer, mode -> line written
using RangedFn = bool (*)(void* item, const uint8_t* rec, int32_t min, int32_t max, int32_t param, bool group, char* out, int32_t mode);
// item, ItemStatCost record, value, param, group flag, out buffer, mode -> line written
using PlainFn = bool (*)(void* item, const uint8_t* rec, int32_t value, int32_t param, bool group, char* out, int32_t mode);
RangedFn g_ranged = nullptr;
PlainFn g_plain = nullptr;
volatile LONG g_lines = 0;
volatile LONG g_lastDescfunc = 0;

bool RangedHook(void* item, const uint8_t* rec, int32_t min, int32_t max, int32_t param, bool group, char* out, int32_t mode) noexcept {
	const int descfunc = rec != nullptr ? ranged_desc::SwitchDescfunc(rec[RecDescfunc], rec[RecGroupDescfunc], group, mode) : 0;
	if (!ranged_desc::NoRangeCase(descfunc) || out == nullptr) {
		return g_ranged(item, rec, min, max, param, group, out, mode);
	}
	InterlockedIncrement(&g_lines);
	InterlockedExchange(&g_lastDescfunc, descfunc);
	if (min == max) {
		out[0] = '\0';
		return g_plain(item, rec, min, param, group, out, mode);
	}
	char lo[LineSize] = {};
	char hi[LineSize] = {};
	const bool haveLo = g_plain(item, rec, min, param, group, lo, mode);
	const bool haveHi = g_plain(item, rec, max, param, group, hi, mode);
	lo[LineSize - 1] = '\0';
	hi[LineSize - 1] = '\0';
	if (!haveHi) {
		out[0] = '\0';
		if (!haveLo) {
			return false;
		}
		std::memcpy(out, lo, LineSize);
		return true;
	}
	ranged_desc::MergeRange(haveLo ? lo : nullptr, hi, out, LineSize);
	return true;
}

}  // namespace

auto InstallRangedDesc(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int {
	// the plain builder is called, not hooked: its entry must be D2R's too
	const bool plainOk = std::memcmp(reinterpret_cast<const void*>(context->exeBase + RvaPlainModString), PlainEntry, sizeof(PlainEntry)) == 0;
	bool ok = false;
	if (plainOk) {
		g_plain = reinterpret_cast<PlainFn>(context->exeBase + RvaPlainModString);
		ok = context->InstallInlineHook(RvaRangedModString, RangedEntry, sizeof(RangedEntry), reinterpret_cast<void*>(&RangedHook),
		                                reinterpret_cast<void**>(&g_ranged));
	}
	std::snprintf(report, reportSize, "Ctrl stat range lines of descfuncs 5 10 11 17 18 22 23 (Reanimate as) from the plain line (0x2d7850 hooked)%s",
	              ok ? "" : (plainOk ? " FAILED" : " FAILED: plain mod string 0x2d6520 not as expected"));
	return ok ? 1 : 0;
}

auto RangedDescLines() noexcept -> long {
	return g_lines;
}

auto RangedDescLastDescfunc() noexcept -> long {
	return g_lastDescfunc;
}

// Move Only's start function (move_only_logic.h has the rule; docs/left-skills.md).
//
// D2R's server start table (RVA 0x238e710, 91 x 8-byte function pointers indexed by skills.txt srvstfunc) has functions in
// 0-70 and null in 71-90; the server runs the entry, when there is one, before the skill's do function and stops the cast
// when it returns 0. Slot 71 gets a function that always returns 0 and counts the refusal.
#include "move_only.h"

#include "d2r.h"
#include "move_only_logic.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>

namespace {

using d2r::Game;
using d2r::Unit;

volatile LONG g_refused = 0;
volatile LONG g_lastSkill = -1;

auto MoveOnlyStart(Game*, Unit*, int32_t skillId, int32_t) noexcept -> int64_t {
	InterlockedIncrement(&g_refused);
	InterlockedExchange(&g_lastSkill, skillId);
	return move_only::Start();
}

}  // namespace

auto InstallMoveOnly(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	static constexpr uint8_t Empty[8] = {};
	const uint64_t rva = d2r::SrvStTable + static_cast<uint64_t>(move_only::StartSlot) * 8;
	const uint64_t entry = *reinterpret_cast<const volatile uint64_t*>(context->exeBase + rva);
	const bool free = move_only::SlotFree(move_only::StartSlot, entry);
	// PatchWriteU64 checks the old value (0) itself as well: a slot D2R uses is never overwritten
	const bool ok = free && context->PatchWriteU64(rva, Empty, sizeof(Empty), reinterpret_cast<uint64_t>(&MoveOnlyStart));
	std::snprintf(report, reportSize, "srvstfunc %d Move Only start (refuses every cast)%s", move_only::StartSlot,
	              ok ? "" : (free ? " FAILED (write)" : " FAILED (slot not empty)"));
	return ok;
}

void MoveOnlyStats(long* refused, long* lastSkill) noexcept {
	*refused = g_refused;
	*lastSkill = g_lastSkill;
}

// Guard for the client's end of the game on server command 0x15 (unit reassign), bugs #511 / #292 (reassign_guard_logic.h has
// the addresses and the rule; off word `reassign`).
//
// The client's handler moves the unit to the command's x, y and, when the unit then has no client room, asserts "Could not get
// act!" (SCmd.cpp:1254) and ends the process: a player who walked into the Underground Passage with a mercenary lost the game
// that way (d2rloader.log: the assert, then the access violation of the fatal stub at image +0x1255802). The guard takes that
// very branch (it fires only where D2R would end the game): a unit other than the local player is left without a room and the
// handler returns (one log line each, the first 16); the client learns the unit again when the server sends it into a room the
// client has. The local player without a room still gets D2R's end (logged first). The command's fields come from a hook on
// the handler's entry; nothing else in the handler changes.
#include "reassign_guard.h"

#include "d2r.h"
#include "reassign_guard_logic.h"

#include <windows.h>

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

using namespace reassign_guard;

using HandlerFn = void (*)(uint8_t* packet);
using LocalIdFn = uint32_t (*)();
using PlayerByIdFn = void* (*)(uint32_t id);

HandlerFn g_original = nullptr;
LocalIdFn g_localId = nullptr;
PlayerByIdFn g_playerById = nullptr;
const D2RL::PluginContext* g_context = nullptr;
Reassign g_current{};  // the command being handled (the client's command loop runs on one thread)
std::atomic<unsigned> g_seen{0}, g_left{0}, g_ended{0}, g_logged{0};

void Log(const char* what, const void* unit) noexcept {
	if (g_context == nullptr || g_logged.fetch_add(1) >= 16) {
		return;
	}
	char line[240];
	std::snprintf(line, sizeof(line), "mxl2012-core: reassign (server command 0x15) of unit type %u class %d id %u to %u,%u (flags %u) left "
	              "it without a client room: %s", g_current.unitType, unit != nullptr ? d2r::At<int32_t>(unit, d2r::UnitClass) : -1,
	              g_current.id, g_current.x, g_current.y, g_current.flags, what);
	g_context->LogWarn(line);
}

// Called from the stub at D2R's no-room branch; true = leave the unit without a room and return.
bool OnNoRoom(void* unit) noexcept {
	const bool local = unit == g_playerById(g_localId());
	if (Decide(local) == Verdict::Leave) {
		g_left.fetch_add(1);
		Log("unit left without a room, the game goes on", unit);
		return true;
	}
	g_ended.fetch_add(1);
	Log("the local player: D2R ends the game (\"Could not get act!\")", unit);
	return false;
}

void ReassignHandler(uint8_t* packet) noexcept {
	g_seen.fetch_add(1);
	if (packet != nullptr) {
		g_current = Parse(packet);
	}
	g_original(packet);
}

}  // namespace

void ReassignGuardStats(unsigned* seen, unsigned* left, unsigned* ended) noexcept {
	*seen = g_seen.load();
	*left = g_left.load();
	*ended = g_ended.load();
}

auto InstallReassignGuard(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	g_context = context;
	g_localId = reinterpret_cast<LocalIdFn>(context->exeBase + RvaLocalPlayerId);
	g_playerById = reinterpret_cast<PlayerByIdFn>(context->exeBase + RvaPlayerById);
	const auto* image = reinterpret_cast<const uint8_t*>(context->exeBase);
	bool ok = std::memcmp(image + RvaNoRoomBranch, NoRoomBranch, sizeof(NoRoomBranch)) == 0 && std::memcmp(image + RvaPad, Pad, sizeof(Pad)) == 0;
	auto* stub = ok ? static_cast<uint8_t*>(VirtualAlloc(nullptr, StubSize, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)) : nullptr;
	ok = stub != nullptr;
	if (ok) {
		const Stub bytes = StubBytes(reinterpret_cast<uint64_t>(&OnNoRoom), context->exeBase + RvaLeave, context->exeBase + RvaFail);
		std::memcpy(stub, bytes.bytes, StubSize);
		DWORD old = 0;
		ok = VirtualProtect(stub, StubSize, PAGE_EXECUTE_READ, &old) != 0;
		FlushInstructionCache(GetCurrentProcess(), stub, StubSize);
	}
	// the entry hook first (the command's fields), then the pad, then the branch that makes the stub live
	ok = ok && context->InstallInlineHook(RvaHandler, HandlerEntry, sizeof(HandlerEntry), reinterpret_cast<void*>(&ReassignHandler),
	                                      reinterpret_cast<void**>(&g_original));
	if (ok) {
		const AbsJump pad = AbsJumpBytes(reinterpret_cast<uint64_t>(stub));
		const Branch branch = BranchBytes();
		ok = context->PatchBytes(RvaPad, Pad, sizeof(Pad), pad.bytes, sizeof(pad.bytes)) &&
		     context->PatchBytes(RvaNoRoomBranch, NoRoomBranch, sizeof(NoRoomBranch), branch.bytes, sizeof(branch.bytes));
	}
	std::snprintf(report, reportSize, "unit reassign 0x12ab40: a unit other than the player left without a client room is not the end of "
	              "the game (\"Could not get act!\", image +0x1255802; branch 0x12addb)%s", ok ? "" : " FAILED");
	return ok;
}

// The cube's second `useitem` output (docs/bugs.md #350, docs/plugin-plan.md section 17; off word cubedupe).
//
// Median XL 2012's dupe rows put `useitem` in output a and output b: 1.13c makes a copy of input 1 for each (1.14d 0x565ab0
// with its item duplicate 0x55a2a0), D2R keeps input 1 for output a and makes nothing for output b (cube_dupe_logic.h has
// the reading). The recipe executor 0x5269c0 is detoured: when the original returns its first output and the record asks for
// more `useitem` outputs, each gets a copy of that output made with D2R's own duplicate 0x43d660, placed in the cube (or the
// backpack when the cube is full) and sent to the client with the calls and values the executor uses for its outputs
// (0x527d40..0x527e93).
#include "cube_dupe.h"

#include "cube_dupe_logic.h"
#include "d2r.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>

namespace {

using d2r::Game;
using d2r::Unit;

constexpr uint64_t RvaExec = 0x5269c0;        // (game, player, record, ctx) -> first output item or null
constexpr uint64_t RvaDuplicate = 0x43d660;   // (game, item) -> new item (1.14d 0x55a2a0), socketed items copied with it
constexpr uint64_t RvaItemData = 0x34a500;    // (item) -> item data, +0x18 flags
constexpr uint64_t RvaItemFlag = 0x36d8f0;    // (item, mask, on)
constexpr uint64_t RvaInventory = 0x34a360;   // (unit, file, line) -> inventory
constexpr uint64_t RvaInvRecord = 0x34a410;   // (player, page kind, expansion)
constexpr uint64_t RvaFindSpot = 0x3865b0;    // (inventory, item, record, &x, &y, page) -> found
constexpr uint64_t RvaLocInit = 0x382e10;     // (loc*, page, packed xy)
constexpr uint64_t RvaPlace = 0x471500;       // (player, loc*, ids*, count, 0) -> placed
constexpr uint64_t RvaSendItem = 0x535f60;    // (game, player, item, 0, 2, loc[0], loc[1], loc[3], loc[2]) as 0x527e93
constexpr uint64_t RvaFreeItem = 0x43ec10;    // (game, item)
constexpr int ItemDataFlags = 0x18;
constexpr int UnitId = 0x08;
constexpr int GameExpansion = 0x106;          // the executor: 0x34a410(..., game[0x106] != 1)

// 0x5269c0: push rbp rbx rsi rdi r12 r13 r14 r15 / lea rbp,[rsp-0x15f8] (21 bytes, whole instructions; dump of build 93847)
constexpr uint8_t ExecEntry[] = {0x40, 0x55, 0x53, 0x56, 0x57, 0x41, 0x54, 0x41, 0x55, 0x41, 0x56,
                                 0x41, 0x57, 0x48, 0x8d, 0xac, 0x24, 0x08, 0xea, 0xff, 0xff};

using ExecFn = void* (*)(Game*, Unit*, const uint8_t*, void*);
ExecFn g_exec = nullptr;
uint64_t g_base = 0;
volatile LONG g_made = 0;
volatile LONG g_noRoom = 0;
volatile LONG g_failed = 0;

template <typename F>
auto Fn(uint64_t rva) noexcept -> F {
	return reinterpret_cast<F>(g_base + rva);
}

auto Flags(Unit* item) noexcept -> uint32_t {
	const uint8_t* data = Fn<uint8_t* (*)(Unit*)>(RvaItemData)(item);
	return data != nullptr ? d2r::At<uint32_t>(data, ItemDataFlags) : 0U;
}

// The executor's output placement for one item: a free spot on the page, the move, the identified flag and the item packet.
auto Place(Game* game, Unit* player, Unit* item) noexcept -> bool {
	void* inv = Fn<void* (*)(Unit*, const char*, int32_t)>(RvaInventory)(player, "cube_dupe", 0);
	if (inv == nullptr) {
		return false;
	}
	for (const cube_dupe::Page& p : cube_dupe::Pages) {
		const int32_t record = Fn<int32_t (*)(Unit*, int32_t, int32_t)>(RvaInvRecord)(player, p.kind, d2r::At<uint8_t>(game, GameExpansion) != 1);
		uint16_t x = 0, y = 0;
		if (Fn<int32_t (*)(void*, Unit*, int32_t, uint16_t*, uint16_t*, int64_t)>(RvaFindSpot)(inv, item, record, &x, &y, p.page) == 0) {
			continue;
		}
		int32_t loc[4] = {};
		Fn<int32_t* (*)(int32_t*, int32_t, int32_t)>(RvaLocInit)(loc, p.page, static_cast<int32_t>((static_cast<uint32_t>(y) << 16) | x));
		uint32_t id = d2r::At<uint32_t>(item, UnitId);
		if (Fn<uint8_t (*)(Unit*, int32_t*, uint32_t*, uint64_t, int64_t)>(RvaPlace)(player, loc, &id, 1, 0) == 0) {
			continue;
		}
		Fn<void (*)(Unit*, int32_t, int32_t)>(RvaItemFlag)(item, static_cast<int32_t>(cube_dupe::ItemFlagIdentified), 1);
		Fn<void (*)(Game*, Unit*, Unit*, int32_t, int32_t, int32_t, int32_t, int32_t, int32_t)>(RvaSendItem)(game, player, item, 0, 2, loc[0], loc[1],
		                                                                                                      loc[3], loc[2]);
		return true;
	}
	return false;
}

void* ExecHook(Game* game, Unit* player, const uint8_t* record, void* ctx) {
	void* out = g_exec(game, player, record, ctx);
	const int copies = out != nullptr && game != nullptr && player != nullptr ? cube_dupe::ExtraCopies(record) : 0;
	if (copies == 0) {
		return out;
	}
	Unit* source = static_cast<Unit*>(out);
	const bool sourceFlag = (Flags(source) & cube_dupe::ItemFlagDupeSource) != 0;
	for (int i = 0; i < copies; ++i) {
		Unit* copy = Fn<Unit* (*)(Game*, Unit*)>(RvaDuplicate)(game, source);
		if (copy == nullptr) {
			InterlockedIncrement(&g_failed);
			continue;
		}
		if (Place(game, player, copy)) {
			InterlockedIncrement(&g_made);
		} else {
			Fn<void (*)(Game*, Unit*)>(RvaFreeItem)(game, copy);
			InterlockedIncrement(&g_noRoom);
		}
	}
	// 0x43d660 marks its source; 1.13c's source (input 1) was used up, here it is output a, kept as it was.
	if (!sourceFlag) {
		Fn<void (*)(Unit*, int32_t, int32_t)>(RvaItemFlag)(source, static_cast<int32_t>(cube_dupe::ItemFlagDupeSource), 0);
	}
	return out;
}

}  // namespace

auto InstallCubeDupe(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	g_base = context->exeBase;
	const bool ok = context->InstallInlineHook(RvaExec, ExecEntry, sizeof(ExecEntry), reinterpret_cast<void*>(&ExecHook),
	                                           reinterpret_cast<void**>(&g_exec));
	std::snprintf(report, reportSize, ok ? "on: a second useitem output copies output a, as 1.13c (executor 0x5269c0)"
	                                     : "off: hook on 0x5269c0 FAILED");
	return ok;
}

void CubeDupeCounts(long* made, long* noRoom, long* failed) noexcept {
	*made = g_made;
	*noRoom = g_noRoom;
	*failed = g_failed;
}

// Pet-warp spread (docs/bugs.md #493, docs/plugin-plan.md section 26, off word petspread).
//
// Median XL 2012's totems (pettype `totemic`, `warp` 1) are brought to the Necromancer by D2R in two ways, and both put them on
// the owner's own sub-tile; being immobile they stay stacked there: drawn as one in legacy, three of four as bare orbs in HD, all
// aiming from one point.
//  - The owner's move (`0x491ca0`, every teleport: Bend the Shadows, Teleport, a waypoint) ends with `0x500a40(game, owner, x, y)`
//    (D2Game SUnitInactive area): for every pettype with the warp bit it sets each of the owner's pets of that type exactly on
//    (x, y) with `0x501df0(game, pet, node, room, x, y)` (no free-spot search). This is the Bend the Shadows path (seen in game).
//  - The pet warp to the owner (`0x596d40`, D2Game AiUtil.cpp: game, owner, pet; a pet left in an inactive room, AI warps): its
//    last two tries put the pet on the owner's sub-tile (the free-spot search's mask 0x1c09 has no unit bit).
// The part hooks both. During `0x500a40` a hook on `0x501df0` only records the pets placed (no move inside D2R's pet-list loop);
// when `0x500a40` returns, each recorded pet that is on its owner's spot is moved to the first free spot of a ring round the owner
// (pet_spread_logic.h; not within 2 sub-tiles of a pet the same gather already placed) with the unit move the warp itself uses (`0x491ca0`, free-spot search), then flagged teleported
// (`0x34f490(unit, 1)`) as D2R does after a pet move. `0x596d40`'s pet gets the same after it returns. The gather itself, its
// tries and its results are unchanged; a pet already off the owner's spot is left where it is.
#include "pet_spread.h"

#include "d2r.h"
#include "pet_spread_logic.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>

namespace {

constexpr uint64_t RvaGather = 0x500a40;       // (game, owner, x, y): the owner's warp pets set on (x, y); called by 0x491ca0
constexpr uint64_t RvaPlace = 0x501df0;        // (game, unit, pet-list node or 0, room, x, y): sets the unit on (x, y) as it is
constexpr uint64_t RvaPetWarp = 0x596d40;      // (game, owner, pet) -> 1 when the pet was moved next to its owner
constexpr uint64_t RvaMove = 0x491ca0;         // (game, unit, room or 0, x, y, exact, 0): the unit move every teleport uses
constexpr uint64_t RvaSpotBlocked = 0x350a20;  // (unit, x, y, mask) -> non-zero when the unit's footprint there is blocked
constexpr uint64_t RvaSetTeleported = 0x34f490;  // (unit, 1): unit flag 0x10000, set by D2R after a pet move
// MOV [RSP+0x20],RSI / MOV [RSP+0x10],RDX / PUSH RBP / PUSH RDI / PUSH R12 / PUSH R13
constexpr uint8_t GatherEntry[] = {0x48, 0x89, 0x74, 0x24, 0x20, 0x48, 0x89, 0x54, 0x24, 0x10, 0x55, 0x57, 0x41, 0x54, 0x41, 0x55};
// MOV [RSP+0x10],RBX / MOV [RSP+0x18],RBP / PUSH RSI / PUSH RDI / PUSH R14 / SUB RSP,0x40
constexpr uint8_t PlaceEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x10, 0x48, 0x89, 0x6c, 0x24, 0x18,
                                  0x56, 0x57, 0x41, 0x56, 0x48, 0x83, 0xec, 0x40};
// MOV [RSP+0x18],RBX / PUSH RBP / PUSH RSI / PUSH RDI / PUSH R12 / PUSH R13 / PUSH R14 / PUSH R15
constexpr uint8_t PetWarpEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x18, 0x55, 0x56, 0x57,
                                    0x41, 0x54, 0x41, 0x55, 0x41, 0x56, 0x41, 0x57};

using GatherFn = int64_t (*)(d2r::Game* game, d2r::Unit* owner, int32_t x, int32_t y);
using PlaceFn = int64_t (*)(d2r::Game* game, d2r::Unit* unit, void* node, void* room, int32_t x, int32_t y);
using PetWarpFn = int32_t (*)(d2r::Game* game, d2r::Unit* owner, d2r::Unit* pet);
using MoveFn = int64_t (*)(d2r::Game*, d2r::Unit*, void*, int32_t, int32_t, int32_t, int32_t);
using SpotBlockedFn = int32_t (*)(d2r::Unit*, int32_t, int32_t, int32_t);
using SetTeleportedFn = void (*)(d2r::Unit*, int32_t);

uint64_t g_base = 0;
GatherFn g_gather = nullptr;
PlaceFn g_place = nullptr;
PetWarpFn g_petWarp = nullptr;
volatile LONG g_gathers = 0;  // owner moves that set pets on the owner (0x500a40)
volatile LONG g_warps = 0;    // single pet warps that moved a pet (0x596d40)
volatile LONG g_stacked = 0;  // pets of either left on the owner's spot
volatile LONG g_spread = 0;   // ... moved to a ring spot
volatile LONG g_lastClass = -1;

// The pets 0x501df0 sets during one 0x500a40 call on this thread (the game's server thread); moved after it returns.
constexpr int MaxPets = 32;
thread_local int t_inGather = 0;
thread_local int t_petCount = 0;
thread_local d2r::Unit* t_pets[MaxPets] = {};

template <typename F>
auto Fn(uint64_t rva) noexcept -> F {
	return reinterpret_cast<F>(g_base + rva);
}

// `taken` / `count`: the spots earlier pets of the same gather got (nullptr for a single warp); the new spot is added.
void Spread(d2r::Game* game, d2r::Unit* owner, d2r::Unit* pet, pet_spread::Spot* taken, int* count) noexcept {
	int32_t ox = 0, oy = 0, px = 0, py = 0;
	if (!d2r::UnitXY(owner, &ox, &oy) || !d2r::UnitXY(pet, &px, &py) || !pet_spread::OnOwner(px, py, ox, oy)) {
		return;
	}
	InterlockedIncrement(&g_stacked);
	InterlockedExchange(&g_lastClass, d2r::At<int32_t>(pet, d2r::UnitClass));
	for (const auto& o : pet_spread::Ring) {
		const int32_t x = ox + o.dx, y = oy + o.dy;
		if (taken != nullptr && pet_spread::Taken(x, y, taken, *count)) {
			continue;
		}
		if (Fn<SpotBlockedFn>(RvaSpotBlocked)(pet, x, y, pet_spread::SpotMask) != 0) {
			continue;
		}
		Fn<MoveFn>(RvaMove)(game, pet, nullptr, x, y, 0, 0);
		int32_t nx = 0, ny = 0;
		if (d2r::UnitXY(pet, &nx, &ny) && pet_spread::Landed(nx, ny, x, y)) {
			Fn<SetTeleportedFn>(RvaSetTeleported)(pet, 1);
			InterlockedIncrement(&g_spread);
			if (taken != nullptr && *count < MaxPets) {
				taken[(*count)++] = {nx, ny};
			}
			return;
		}
	}
}

void SpreadGuarded(d2r::Game* game, d2r::Unit* owner, d2r::Unit* pet, pet_spread::Spot* taken, int* count) noexcept {
	__try {
		Spread(game, owner, pet, taken, count);
	} __except (EXCEPTION_EXECUTE_HANDLER) {
	}
}

auto PlaceHook(d2r::Game* game, d2r::Unit* unit, void* node, void* room, int32_t x, int32_t y) noexcept -> int64_t {
	const int64_t r = g_place(game, unit, node, room, x, y);
	if (t_inGather != 0 && unit != nullptr && t_petCount < MaxPets) {
		t_pets[t_petCount++] = unit;
	}
	return r;
}

auto GatherHook(d2r::Game* game, d2r::Unit* owner, int32_t x, int32_t y) noexcept -> int64_t {
	if (t_inGather != 0) {  // not expected (0x500a40 does not call itself); leave it to the outer call
		return g_gather(game, owner, x, y);
	}
	t_inGather = 1;
	t_petCount = 0;
	const int64_t r = g_gather(game, owner, x, y);
	t_inGather = 0;
	// copy first: a spread move runs 0x491ca0 on the pet, which calls 0x500a40 again for the pet's own pets
	d2r::Unit* pets[MaxPets];
	const int n = t_petCount;
	for (int i = 0; i < n; ++i) {
		pets[i] = t_pets[i];
	}
	t_petCount = 0;
	if (n > 0 && game != nullptr && owner != nullptr) {
		InterlockedIncrement(&g_gathers);
		pet_spread::Spot taken[MaxPets];
		int count = 0;
		for (int i = 0; i < n; ++i) {
			SpreadGuarded(game, owner, pets[i], taken, &count);
		}
	}
	return r;
}

auto PetWarpHook(d2r::Game* game, d2r::Unit* owner, d2r::Unit* pet) noexcept -> int32_t {
	const int32_t moved = g_petWarp(game, owner, pet);
	if (moved != 0 && game != nullptr && owner != nullptr && pet != nullptr) {
		InterlockedIncrement(&g_warps);
		SpreadGuarded(game, owner, pet, nullptr, nullptr);
	}
	return moved;
}

}  // namespace

auto InstallPetSpread(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int {
	g_base = context->exeBase;
	// the place hook first: the gather hook relies on it to see the pets
	const bool place = context->InstallInlineHook(RvaPlace, PlaceEntry, sizeof(PlaceEntry), reinterpret_cast<void*>(&PlaceHook),
	                                              reinterpret_cast<void**>(&g_place));
	const bool gather = place && context->InstallInlineHook(RvaGather, GatherEntry, sizeof(GatherEntry), reinterpret_cast<void*>(&GatherHook),
	                                                        reinterpret_cast<void**>(&g_gather));
	const bool warp = context->InstallInlineHook(RvaPetWarp, PetWarpEntry, sizeof(PetWarpEntry), reinterpret_cast<void*>(&PetWarpHook),
	                                             reinterpret_cast<void**>(&g_petWarp));
	std::snprintf(report, reportSize, "pets brought onto their owner's spot are spread round it (0x500a40 / 0x501df0%s, 0x596d40%s hooked)",
	              place && gather ? "" : " FAILED", warp ? "" : " FAILED");
	return (place && gather ? 1 : 0) + (warp ? 1 : 0);
}

void PetSpreadCounts(long* gathers, long* warps, long* stacked, long* spread, long* lastClass) noexcept {
	*gathers = g_gathers;
	*warps = g_warps;
	*stacked = g_stacked;
	*spread = g_spread;
	*lastClass = g_lastClass;
}

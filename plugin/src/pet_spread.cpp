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
// Only totems move (owner ruling 2026-10-29): a pet counts as one when its unit id is in its owner's list of pettype `totemic`
// (`0x5013f0` on the player data's pet root). Mercenaries, golems and the other warp pets keep D2R's placement and walk off.
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
constexpr uint64_t RvaPlayerData = 0x34b240;     // (player) -> player data; +0x98 = the root of its pet lists (0x500a40 reads it)
constexpr uint64_t RvaPetList = 0x5013f0;        // (dataFlag, root, pettype) -> that pettype's list (+0 first node), null outside the table
constexpr int PlayerDataPets = 0x98;
constexpr int UnitId = 0x08;
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
using PlayerDataFn = uint8_t* (*)(d2r::Unit*);
using PetListFn = uint8_t** (*)(uint32_t dataFlag, void* root, int32_t petType);

uint64_t g_base = 0;
GatherFn g_gather = nullptr;
PlaceFn g_place = nullptr;
PetWarpFn g_petWarp = nullptr;
volatile LONG g_gathers = 0;  // owner moves that set pets on the owner (0x500a40)
volatile LONG g_warps = 0;    // single pet warps that moved a pet (0x596d40)
volatile LONG g_stacked = 0;  // pets of either left on the owner's spot
volatile LONG g_spread = 0;   // ... moved to a ring spot
volatile LONG g_kept = 0;     // pets on the owner's spot that are no totem: left to D2R
volatile LONG g_lastClass = -1;
volatile LONG g_shifted = 0;       // spread totems the move landed more than one sub-tile from the asked spot (kept, bug #509)
volatile LONG g_secondPass = 0;    // totems spread by pass 2 (the move asked for spots the spot test refused, bug #509)
volatile LONG g_missed = 0;        // totems no ring spot took: left where the last try put them
volatile LONG g_triesTaken = 0;    // ring spots skipped: within 2 sub-tiles of a pet of the same gather
volatile LONG g_triesBlocked = 0;  // ... refused by the spot test
volatile LONG g_triesStill = 0;    // moves that left the pet where it was
volatile LONG g_triesOff = 0;      // moves that landed it on a spot it could not keep

// The pets 0x501df0 sets during one 0x500a40 call on this thread (the game's server thread); moved after it returns.
constexpr int MaxPets = 32;
thread_local int t_inGather = 0;
thread_local int t_petCount = 0;
thread_local d2r::Unit* t_pets[MaxPets] = {};

template <typename F>
auto Fn(uint64_t rva) noexcept -> F {
	return reinterpret_cast<F>(g_base + rva);
}

// True when the pet is in its owner's `totemic` list. Only a player owner has the pet root the gather reads.
auto IsTotem(d2r::Game* game, d2r::Unit* owner, d2r::Unit* pet) noexcept -> bool {
	if (d2r::At<int32_t>(owner, d2r::UnitType) != 0) {
		return false;
	}
	const uint8_t* data = Fn<PlayerDataFn>(RvaPlayerData)(owner);
	void* root = data != nullptr ? d2r::At<void*>(data, PlayerDataPets) : nullptr;
	uint8_t** list = root != nullptr ? Fn<PetListFn>(RvaPetList)(d2r::DataFlag(game), root, pet_spread::TotemicPetType) : nullptr;
	return list != nullptr && pet_spread::Listed(*list, d2r::At<uint32_t>(pet, UnitId));
}

// The tries of the first totems that needed pass 2 or that no spot took (bug #509), for the log: "dx,dy" asked, then B (blocked),
// T (taken by a pet of the same gather), = (the move left the pet where it was) or ">dx,dy" the spot it landed on, as offsets
// from the owner; "|" starts pass 2.
const D2RL::PluginContext* g_context = nullptr;
volatile LONG g_logged = 0;
constexpr LONG MaxLogs = 8;

void Trace(char* buf, size_t size, size_t* used, const char* fmt, int32_t a, int32_t b, int32_t c = 0, int32_t d = 0) noexcept {
	if (*used + 1 < size) {
		const int n = std::snprintf(buf + *used, size - *used, fmt, a, b, c, d);
		*used = n > 0 ? (*used + static_cast<size_t>(n) < size ? *used + static_cast<size_t>(n) : size - 1) : *used;
	}
}

void Log(d2r::Unit* pet, const char* what, int32_t x, int32_t y, int32_t ox, int32_t oy, int placed, const char* trace) noexcept {
	if (g_context != nullptr && InterlockedIncrement(&g_logged) <= MaxLogs) {
		char line[1024];
		std::snprintf(line, sizeof(line), "petspread: totem class %d %s at %d,%d (owner %d,%d, %d placed before); tries:%s",
		              d2r::At<int32_t>(pet, d2r::UnitClass), what, x, y, ox, oy, placed, trace);
		g_context->LogInfo(line);
	}
}

// `taken` / `count`: the spots earlier pets of the same gather got (nullptr for a single warp); the new spot is added.
void Spread(d2r::Game* game, d2r::Unit* owner, d2r::Unit* pet, pet_spread::Spot* taken, int* count) noexcept {
	int32_t ox = 0, oy = 0, px = 0, py = 0;
	if (!d2r::UnitXY(owner, &ox, &oy) || !d2r::UnitXY(pet, &px, &py) || !pet_spread::OnOwner(px, py, ox, oy)) {
		return;
	}
	InterlockedIncrement(&g_stacked);
	InterlockedExchange(&g_lastClass, d2r::At<int32_t>(pet, d2r::UnitClass));
	if (!IsTotem(game, owner, pet)) {
		InterlockedIncrement(&g_kept);
		return;
	}
	const int n = count != nullptr ? *count : 0;
	char trace[960];
	size_t used = 0;
	trace[0] = '\0';
	// Pass 1 moves only to spots `0x350a20` calls free. Next to rocks that test and the move's own free-spot search (`0x362f90`,
	// the unit's footprint) disagree (bug #509, seen in game): spots at 5 and 7 were refused as blocked on open ground, and the one
	// spot it let through put the totem 1 sub-tile from its owner. So pass 2 asks the move for every ring spot not taken and keeps
	// where D2R's own search landed the totem.
	for (int pass = 1; pass <= 2; ++pass) {
		if (pass == 2) {
			Trace(trace, sizeof(trace), &used, " |", 0, 0);
		}
		for (const auto& o : pet_spread::Ring) {
			const int32_t x = ox + o.dx, y = oy + o.dy;
			if (taken != nullptr && pet_spread::Taken(x, y, taken, n)) {
				if (pass == 1) {
					InterlockedIncrement(&g_triesTaken);
					Trace(trace, sizeof(trace), &used, " %d,%dT", o.dx, o.dy);
				}
				continue;
			}
			if (pass == 1 && Fn<SpotBlockedFn>(RvaSpotBlocked)(pet, x, y, pet_spread::SpotMask) != 0) {
				InterlockedIncrement(&g_triesBlocked);
				Trace(trace, sizeof(trace), &used, " %d,%dB", o.dx, o.dy);
				continue;
			}
			int32_t bx = 0, by = 0;
			d2r::UnitXY(pet, &bx, &by);
			Fn<MoveFn>(RvaMove)(game, pet, nullptr, x, y, 0, 0);
			int32_t nx = 0, ny = 0;
			if (!d2r::UnitXY(pet, &nx, &ny)) {
				return;
			}
			if (pet_spread::Keep(nx, ny, ox, oy, taken, n)) {
				Fn<SetTeleportedFn>(RvaSetTeleported)(pet, 1);
				InterlockedIncrement(&g_spread);
				if (!pet_spread::Landed(nx, ny, x, y)) {
					InterlockedIncrement(&g_shifted);
				}
				if (taken != nullptr && *count < MaxPets) {
					taken[(*count)++] = {nx, ny};
				}
				if (pass == 2) {
					InterlockedIncrement(&g_secondPass);
					Trace(trace, sizeof(trace), &used, " %d,%d>%d,%d kept", o.dx, o.dy, nx - ox, ny - oy);
					Log(pet, "spread by pass 2", nx, ny, ox, oy, n, trace);
				}
				return;
			}
			if (nx == bx && ny == by) {
				InterlockedIncrement(&g_triesStill);
				Trace(trace, sizeof(trace), &used, " %d,%d=", o.dx, o.dy);
			} else {
				InterlockedIncrement(&g_triesOff);
				Trace(trace, sizeof(trace), &used, " %d,%d>%d,%d", o.dx, o.dy, nx - ox, ny - oy);
			}
		}
	}
	InterlockedIncrement(&g_missed);
	int32_t ex = 0, ey = 0;
	d2r::UnitXY(pet, &ex, &ey);
	Log(pet, "left", ex, ey, ox, oy, n, trace);
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
	g_context = context;
	// the place hook first: the gather hook relies on it to see the pets
	const bool place = context->InstallInlineHook(RvaPlace, PlaceEntry, sizeof(PlaceEntry), reinterpret_cast<void*>(&PlaceHook),
	                                              reinterpret_cast<void**>(&g_place));
	const bool gather = place && context->InstallInlineHook(RvaGather, GatherEntry, sizeof(GatherEntry), reinterpret_cast<void*>(&GatherHook),
	                                                        reinterpret_cast<void**>(&g_gather));
	const bool warp = context->InstallInlineHook(RvaPetWarp, PetWarpEntry, sizeof(PetWarpEntry), reinterpret_cast<void*>(&PetWarpHook),
	                                             reinterpret_cast<void**>(&g_petWarp));
	std::snprintf(report, reportSize, "totems brought onto their owner's spot are spread round it (0x500a40 / 0x501df0%s, 0x596d40%s hooked)",
	              place && gather ? "" : " FAILED", warp ? "" : " FAILED");
	return (place && gather ? 1 : 0) + (warp ? 1 : 0);
}

void PetSpreadCounts(long* gathers, long* warps, long* stacked, long* spread, long* kept, long* lastClass) noexcept {
	*gathers = g_gathers;
	*warps = g_warps;
	*stacked = g_stacked;
	*spread = g_spread;
	*kept = g_kept;
	*lastClass = g_lastClass;
}

void PetSpreadTries(long* shifted, long* secondPass, long* missed, long* taken, long* blocked, long* still, long* off) noexcept {
	*shifted = g_shifted;
	*secondPass = g_secondPass;
	*missed = g_missed;
	*taken = g_triesTaken;
	*blocked = g_triesBlocked;
	*still = g_triesStill;
	*off = g_triesOff;
}

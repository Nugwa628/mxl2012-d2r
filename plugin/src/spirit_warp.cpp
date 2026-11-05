// The Barbarian spirits' owner warp (docs/bugs.md #534, docs/plugin-plan.md section 30, off word spiritwarp).
//
// Owner ruling (2026-11-04): Guardian, Defender and Protector Spirit teleport to their owner when they are more than about 20
// sub-tiles away. Median gives them hostile AIs, Vampire (28) and PinHead (39), which have no owner follow; D2R only warps a pet
// that is left in an inactive room, so after a fight they stood 32-91 sub-tiles off.
//
// Once a second (server frame 0x406550 through server_frame.cpp, game +0x170 % 25) the part walks each in-game player's
// guardianspet / defenderspet / protectorspet lists. A live spirit farther than 20 sub-tiles is warped with the game's own pet warp
// 0x596d40(game, owner, pet), unless it is within 40 and fighting, for at most 4 s. D2R does not run the think of an idle spirit, so fighting comes
// from the two AIs' think functions (AI table 0x2397210: entry 28 -> 0x5b7590, entry 39 -> 0x5b2b10; both (game, unit, tick)): a
// spirit's think notes whether it has a live target (tick +0x10) in reach (tick +0x24) and within 25 of the owner, and the frame
// check takes a note under 1.5 s old as fighting (spirit_warp_logic.h). Other Vampire / PinHead units (hostile ones, Daystar,
// Sinner) only pay the owner lookup in the think.
#include "spirit_warp.h"

#include "d2r.h"
#include "pet_spread_logic.h"
#include "server_frame.h"
#include "spirit_warp_logic.h"

#include <windows.h>

#include <cmath>
#include <cstdint>
#include <cstdio>

namespace {

constexpr uint64_t RvaVampireThink = 0x5b7590;  // AI 28 think (game, unit, tick)
constexpr uint64_t RvaPinHeadThink = 0x5b2b10;  // AI 39 think (game, unit, tick)
constexpr uint64_t RvaMinionOwner = 0x4a53c0;   // (monster) -> its owner unit or null (monster data +0x30 -> owner id +0x68, type +0x6c)
constexpr uint64_t RvaPetWarp = 0x596d40;       // (game, owner, pet) -> 1 when the pet was moved next to its owner
constexpr uint64_t RvaPlayerData = 0x34b240;    // (player) -> player data; +0x98 = the root of its pet lists
constexpr uint64_t RvaPetList = 0x5013f0;       // (dataFlag, root, pettype) -> that pettype's list (+0 first node)
constexpr uint64_t RvaClientUnit = 0x484c90;    // (client, 0) -> player unit
constexpr uint64_t RvaUnitById = 0x48fe80;      // (game, type, id) -> unit or null
constexpr int PlayerDataPets = 0x98;
constexpr int GameClients = 0x138, ClientNext = 0x628, ClientState = 0x04, GameFrame = 0x170;
constexpr int UnitId = 0x08;
constexpr int UnitMode = 0x0c;
constexpr int TickTarget = 0x10;   // the AI's target unit or null (both thinks read it)
constexpr int TickInReach = 0x24;  // int: the AI's target is in reach (both thinks branch on it first)
// MOV [RSP+8],RBX / PUSH RBP / PUSH RSI / PUSH RDI / PUSH R12 / PUSH R13 / PUSH R14 / PUSH R15
constexpr uint8_t VampireEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x08, 0x55, 0x56, 0x57, 0x41, 0x54, 0x41, 0x55, 0x41, 0x56, 0x41, 0x57};
// MOV [RSP+8],RBX / MOV [RSP+0x10],RBP / MOV [RSP+0x18],RSI / MOV [RSP+0x20],RDI
constexpr uint8_t PinHeadEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x08, 0x48, 0x89, 0x6c, 0x24, 0x10,
                                    0x48, 0x89, 0x74, 0x24, 0x18, 0x48, 0x89, 0x7c, 0x24, 0x20};

using ThinkFn = int64_t (*)(d2r::Game* game, d2r::Unit* unit, uint8_t* tick);
using MinionOwnerFn = d2r::Unit* (*)(d2r::Unit* monster);
using PetWarpFn = int32_t (*)(d2r::Game* game, d2r::Unit* owner, d2r::Unit* pet);
using PlayerDataFn = uint8_t* (*)(d2r::Unit*);
using PetListFn = uint8_t** (*)(uint32_t dataFlag, void* root, int32_t petType);
using ClientUnitFn = d2r::Unit* (*)(uint8_t* client, int32_t);
using UnitByIdFn = d2r::Unit* (*)(d2r::Game* game, int32_t type, uint32_t id);

uint64_t g_base = 0;
ThinkFn g_vampire = nullptr;
ThinkFn g_pinHead = nullptr;
volatile LONG g_checks = 0;     // spirit checks (once a second per spirit)
volatile LONG g_far = 0;        // ... farther than WarpBeyond
volatile LONG g_held = 0;       // ... of those left fighting (within HardBeyond)
volatile LONG g_warps = 0;      // warps that moved the spirit
volatile LONG g_failed = 0;     // warps that did not
volatile LONG g_lastFrom = -1;  // sub-tiles from the owner before / after the last warp
volatile LONG g_lastTo = -1;
volatile LONG g_lastClass = -1;
volatile LONG g_thinks = 0;        // think calls of a spirit
volatile LONG g_fightNotes = 0;    // ... that saw it fighting
volatile LONG g_checkDist = -1;    // the last check: sub-tiles from the owner, verdict (0 stay, 1 held, 2 warp)
volatile LONG g_checkVerdict = -1;
spirit_warp::Slot g_slots[spirit_warp::SlotCount] = {};  // touched on the game's server thread only
// What held a spirit: its last think's target, for the held counters below. Server thread only, as g_slots.
struct Seen {
	uint32_t unitId;
	int32_t targetClass;  // -1: no live target
	int32_t inReach;
	int32_t targetOwner;  // sub-tiles from the owner
};
Seen g_seen[spirit_warp::SlotCount] = {};
int g_seenNext = 0;
volatile LONG g_heldReach = 0;       // held checks whose target was in reach ...
volatile LONG g_heldZombie = 0;      // ... whose target was a zombie (class 5, the lab's)
volatile LONG g_heldTarget[3] = {};  // ... target within 20 / 21-25 / 26-40 of the owner
volatile LONG g_heldAt[3] = {};      // ... spirit 21-25 / 26-30 / 31-40 from the owner
volatile LONG g_heldLastClass = -1;
volatile LONG g_capped = 0;          // warps of a fighting spirit whose hold reached HoldMaxMs
volatile LONG g_holdLongest = 0;     // the longest hold of one spirit (ms)
spirit_warp::Slot g_holds[spirit_warp::SlotCount] = {};  // per spirit: the first check of its current hold (HoldFor)

template <typename F>
auto Fn(uint64_t rva) noexcept -> F {
	return reinterpret_cast<F>(g_base + rva);
}

auto PetsRoot(d2r::Unit* owner) noexcept -> void* {
	const uint8_t* data = Fn<PlayerDataFn>(RvaPlayerData)(owner);
	return data != nullptr ? d2r::At<void*>(data, PlayerDataPets) : nullptr;
}

auto IsSpirit(d2r::Game* game, d2r::Unit* owner, d2r::Unit* pet) noexcept -> bool {
	void* root = PetsRoot(owner);
	if (root == nullptr) {
		return false;
	}
	const uint32_t id = d2r::At<uint32_t>(pet, UnitId);
	for (const int32_t type : spirit_warp::SpiritPetTypes) {
		uint8_t** list = Fn<PetListFn>(RvaPetList)(d2r::DataFlag(game), root, type);
		if (list != nullptr && pet_spread::Listed(*list, id)) {
			return true;
		}
	}
	return false;
}

auto SubTiles(int64_t distanceSq) noexcept -> LONG {
	return static_cast<LONG>(std::lround(std::sqrt(static_cast<double>(distanceSq))));
}

// In a spirit's think: note whether it is fighting.
void Think(d2r::Game* game, d2r::Unit* pet, const uint8_t* tick) noexcept {
	if (game == nullptr || pet == nullptr || tick == nullptr || d2r::At<int32_t>(pet, d2r::UnitType) != 1) {
		return;
	}
	d2r::Unit* owner = Fn<MinionOwnerFn>(RvaMinionOwner)(pet);
	if (owner == nullptr || d2r::At<int32_t>(owner, d2r::UnitType) != 0 || !IsSpirit(game, owner, pet)) {
		return;
	}
	InterlockedIncrement(&g_thinks);
	d2r::Unit* target = d2r::At<d2r::Unit*>(tick, TickTarget);
	int32_t ox = 0, oy = 0, tx = 0, ty = 0;
	const bool live = target != nullptr && spirit_warp::Alive(d2r::At<int32_t>(target, UnitMode)) && d2r::UnitXY(target, &tx, &ty) &&
	                  d2r::UnitXY(owner, &ox, &oy);
	const bool fighting =
	    spirit_warp::Fighting(live, d2r::At<int32_t>(tick, TickInReach) != 0, live ? spirit_warp::DistanceSq(tx, ty, ox, oy) : 0);
	if (fighting) {
		InterlockedIncrement(&g_fightNotes);
	}
	const uint32_t id = d2r::At<uint32_t>(pet, UnitId);
	spirit_warp::Note(g_slots, id, fighting, GetTickCount64());
	Seen* seen = nullptr;
	for (Seen& s : g_seen) {
		if (s.unitId == id) {
			seen = &s;
		}
	}
	if (seen == nullptr) {
		seen = &g_seen[g_seenNext];
		g_seenNext = (g_seenNext + 1) % spirit_warp::SlotCount;
	}
	*seen = {id, live ? d2r::At<int32_t>(target, d2r::UnitClass) : -1, d2r::At<int32_t>(tick, TickInReach) != 0 ? 1 : 0,
	         live ? SubTiles(spirit_warp::DistanceSq(tx, ty, ox, oy)) : -1};
}

// A held check: count what held it (the spirit's last think).
void CountHeld(uint32_t unitId, LONG dist) noexcept {
	InterlockedIncrement(&g_heldAt[dist <= 25 ? 0 : dist <= 30 ? 1 : 2]);
	for (const Seen& s : g_seen) {
		if (s.unitId != unitId || s.targetClass < 0) {
			continue;
		}
		if (s.inReach != 0) {
			InterlockedIncrement(&g_heldReach);
		}
		if (s.targetClass == 5) {
			InterlockedIncrement(&g_heldZombie);
		}
		InterlockedIncrement(&g_heldTarget[s.targetOwner <= 20 ? 0 : s.targetOwner <= 25 ? 1 : 2]);
		InterlockedExchange(&g_heldLastClass, s.targetClass);
		return;
	}
}

void CheckPet(d2r::Game* game, d2r::Unit* owner, d2r::Unit* pet, uint64_t nowMs) noexcept {
	int32_t ox = 0, oy = 0, px = 0, py = 0;
	if (!spirit_warp::Alive(d2r::At<int32_t>(pet, UnitMode)) || !d2r::UnitXY(owner, &ox, &oy) || !d2r::UnitXY(pet, &px, &py)) {
		return;
	}
	InterlockedIncrement(&g_checks);
	const uint32_t id = d2r::At<uint32_t>(pet, UnitId);
	const int64_t d2 = spirit_warp::DistanceSq(px, py, ox, oy);
	const bool fighting = spirit_warp::FightingRecently(g_slots, id, nowMs);
	// the hold runs while the check would keep the spirit (with no cap); it ends when the spirit stays or is warped for any other reason
	const bool wouldHold = spirit_warp::Decide(d2, fighting, 0) == spirit_warp::Verdict::Held;
	const uint64_t heldMs = spirit_warp::HoldFor(g_holds, id, wouldHold, nowMs);
	const spirit_warp::Verdict v = spirit_warp::Decide(d2, fighting, heldMs);
	InterlockedExchange(&g_checkDist, SubTiles(d2));
	InterlockedExchange(&g_checkVerdict, static_cast<LONG>(v));
	if (static_cast<LONG>(heldMs) > g_holdLongest) {
		InterlockedExchange(&g_holdLongest, static_cast<LONG>(heldMs));
	}
	if (v == spirit_warp::Verdict::Stay) {
		return;
	}
	InterlockedIncrement(&g_far);
	if (v == spirit_warp::Verdict::Held) {
		InterlockedIncrement(&g_held);
		CountHeld(id, SubTiles(d2));
		return;
	}
	if (wouldHold) {
		InterlockedIncrement(&g_capped);
		spirit_warp::HoldFor(g_holds, id, false, nowMs);
	}
	InterlockedExchange(&g_lastClass, d2r::At<int32_t>(pet, d2r::UnitClass));
	InterlockedExchange(&g_lastFrom, SubTiles(d2));
	if (Fn<PetWarpFn>(RvaPetWarp)(game, owner, pet) == 0) {  // through petspread's hook when that part is on: it leaves spirits alone
		InterlockedIncrement(&g_failed);
		return;
	}
	InterlockedIncrement(&g_warps);
	if (d2r::UnitXY(owner, &ox, &oy) && d2r::UnitXY(pet, &px, &py)) {
		InterlockedExchange(&g_lastTo, SubTiles(spirit_warp::DistanceSq(px, py, ox, oy)));
	}
}

void CheckOwner(d2r::Game* game, d2r::Unit* owner, uint64_t nowMs) noexcept {
	void* root = PetsRoot(owner);
	if (root == nullptr) {
		return;
	}
	for (const int32_t type : spirit_warp::SpiritPetTypes) {
		uint8_t** list = Fn<PetListFn>(RvaPetList)(d2r::DataFlag(game), root, type);
		int guard = 0;
		// the warp does not change the pet lists, so the walk stays valid
		for (const uint8_t* node = list != nullptr ? *list : nullptr; node != nullptr && guard < 64;
		     node = d2r::At<const uint8_t*>(node, pet_spread::PetNodeNext), ++guard) {
			d2r::Unit* pet = Fn<UnitByIdFn>(RvaUnitById)(game, 1, d2r::At<uint32_t>(node, pet_spread::PetNodeUnitId));
			if (pet != nullptr) {
				CheckPet(game, owner, pet, nowMs);
			}
		}
	}
}

void Frame(d2r::Game* game) noexcept {
	if (!spirit_warp::FrameDue(d2r::At<uint32_t>(game, GameFrame))) {
		return;
	}
	const uint64_t nowMs = GetTickCount64();
	int guard = 0;
	for (auto* client = d2r::At<uint8_t*>(game, GameClients); client != nullptr && guard < 64;
	     client = d2r::At<uint8_t*>(client, ClientNext), ++guard) {
		if (d2r::At<int32_t>(client, ClientState) != 4) {
			continue;
		}
		d2r::Unit* owner = Fn<ClientUnitFn>(RvaClientUnit)(client, 0);
		if (owner != nullptr && d2r::At<int32_t>(owner, d2r::UnitType) == 0) {
			CheckOwner(game, owner, nowMs);
		}
	}
}

void FrameGuarded(d2r::Game* game) noexcept {
	__try {
		Frame(game);
	} __except (EXCEPTION_EXECUTE_HANDLER) {
	}
}

void ThinkGuarded(d2r::Game* game, d2r::Unit* pet, const uint8_t* tick) noexcept {
	__try {
		Think(game, pet, tick);
	} __except (EXCEPTION_EXECUTE_HANDLER) {
	}
}

auto VampireHook(d2r::Game* game, d2r::Unit* unit, uint8_t* tick) noexcept -> int64_t {
	ThinkGuarded(game, unit, tick);
	return g_vampire(game, unit, tick);
}

auto PinHeadHook(d2r::Game* game, d2r::Unit* unit, uint8_t* tick) noexcept -> int64_t {
	ThinkGuarded(game, unit, tick);
	return g_pinHead(game, unit, tick);
}

}  // namespace

auto InstallSpiritWarp(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int {
	g_base = context->exeBase;
	const bool frame = InstallServerFrame(context) && AddServerFrameCallback(&FrameGuarded);
	const bool vampire = context->InstallInlineHook(RvaVampireThink, VampireEntry, sizeof(VampireEntry), reinterpret_cast<void*>(&VampireHook),
	                                                reinterpret_cast<void**>(&g_vampire));
	const bool pinHead = context->InstallInlineHook(RvaPinHeadThink, PinHeadEntry, sizeof(PinHeadEntry), reinterpret_cast<void*>(&PinHeadHook),
	                                                reinterpret_cast<void**>(&g_pinHead));
	std::snprintf(report, reportSize,
	              "Barbarian spirits farther than %d sub-tiles warp to their owner (0x406550%s, 0x5b7590%s, 0x5b2b10%s hooked)",
	              spirit_warp::WarpBeyond, frame ? "" : " FAILED", vampire ? "" : " FAILED", pinHead ? "" : " FAILED");
	return (frame ? 1 : 0) + (vampire ? 1 : 0) + (pinHead ? 1 : 0);
}

void SpiritWarpCounts(long* checks, long* beyond, long* held, long* warps, long* failed, long* lastFrom, long* lastTo, long* lastClass) noexcept {
	*checks = g_checks;
	*beyond = g_far;
	*held = g_held;
	*warps = g_warps;
	*failed = g_failed;
	*lastFrom = g_lastFrom;
	*lastTo = g_lastTo;
	*lastClass = g_lastClass;
}

void SpiritWarpLast(long* thinks, long* fightNotes, long* checkDist, long* checkVerdict) noexcept {
	*thinks = g_thinks;
	*fightNotes = g_fightNotes;
	*checkDist = g_checkDist;
	*checkVerdict = g_checkVerdict;
}

void SpiritWarpHeld(long* inReach, long* zombie, long* targetOwner, long* spiritOwner, long* lastClass, long* capped, long* longestMs) noexcept {
	*inReach = g_heldReach;
	*zombie = g_heldZombie;
	for (int i = 0; i < 3; ++i) {
		targetOwner[i] = g_heldTarget[i];
		spiritOwner[i] = g_heldAt[i];
	}
	*lastClass = g_heldLastClass;
	*capped = g_capped;
	*longestMs = g_holdLongest;
}

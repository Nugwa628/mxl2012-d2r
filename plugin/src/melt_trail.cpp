// State-22 melt trail (docs/bugs.md #52, docs/unported.md; off word melttrail).
//
// Median XL 2012 keeps `raptured` (Rapture, NTRAP) on vanilla state id 22. 1.13c's / 1.14d's state-22 code (Game.exe client
// 0x4e2d40, server 0x5ce4f0) makes missile 143 one step (step table) off every unit in that state at each walk step, so raptured
// units left Median's `spidergoolay` (IceBreakSmallMelt) behind. D2R's functions for the id (client 0x221650, server 0x578680)
// read the skill from the state's list instead, which names none for Median, and make nothing. Both are hooked at their entry:
// with a skill in the list D2R's function runs unchanged; without one the hook makes 1.14d's missile with D2R's own helpers,
// the same ones D2R's functions call (melt_trail_logic.h has the values and where they come from).
#include "melt_trail.h"

#include "d2r.h"
#include "melt_trail_logic.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

using d2r::Game;
using d2r::Unit;

// D2R helpers, as 0x221650 / 0x578680 call them.
constexpr uint64_t RvaUnitPath = 0x34ae80;     // (unit) -> path
constexpr uint64_t RvaPathActive = 0x381810;   // (path) -> 0 when the path is not in use (both functions leave)
constexpr uint64_t RvaStateList = 0x2f5940;    // (unit, state) -> the state's stat list
constexpr uint64_t RvaListStat = 0x2f5df0;     // (dataFlag, list, stat, layer) -> value
constexpr uint64_t RvaListSetStat = 0x2f7c00;  // (dataFlag, list, stat, value, layer)
constexpr uint64_t RvaSkillCount = 0x21ed80;   // (dataFlag) -> rows in skills.txt
constexpr uint64_t RvaNewSeed = 0x8d5d0;       // () -> seed (client, for a list without stat 202)
constexpr uint64_t RvaPathDir = 0x341930;      // (path) -> direction
constexpr uint64_t RvaDirIndex = 0x3aeb30;     // (direction) -> index 0-7 of the step table
constexpr uint64_t RvaDirStep = 0x3aeb40;      // (direction, &dx, &dy)
constexpr uint64_t RvaUnitRoom = 0x34b440;     // (unit) -> room
constexpr uint64_t RvaRoomAt = 0x38dfb0;       // (room, x, y) -> room of the spot
constexpr uint64_t RvaRoomNoTrail = 0x2f0750;  // (room) -> non-zero: the client makes nothing there (1.14d 0x61ab00)
constexpr uint64_t RvaPlaySound = 0x1a0780;    // (sound, unit, 0, 0, 0): client
// The skill level as 1.14d reads it (0x6439f0 -> 0x643810, then 0x6442a0(unit, skill, 1)): the unit's skill of that id (its own
// first, else the highest), then its level with bonuses; 0 without the skill. D2R's 0x33dd40 is 1.14d's 0x643810 (same
// loop: owner -1 first, then the higher base level; flag 0 = only entries with +0x54 0, as 1.14d's +0x3c test).
constexpr uint64_t RvaSkillById = 0x33dd40;  // (unit, id, includeAll) -> Skill*
constexpr uint64_t RvaSkillLevel = 0x33d1e0; // (unit, Skill*, bonus, 0) -> level; 0 for no skill

using ClientFn = Unit* (*)(Unit* unit);
using ServerFn = Unit* (*)(Game* game, Unit* unit);
ClientFn g_client = nullptr;
ServerFn g_server = nullptr;
uint64_t g_base = 0;
volatile LONG g_clientTrails = 0;
volatile LONG g_serverTrails = 0;

template <typename F>
auto Fn(uint64_t rva) noexcept -> F {
	return reinterpret_cast<F>(g_base + rva);
}

auto ListStat(uint32_t dataFlag, void* list, int32_t stat) noexcept -> int32_t {
	return Fn<int32_t (*)(uint32_t, void*, int32_t, int32_t)>(RvaListStat)(dataFlag, list, stat, 0);
}

// What both sides share: the path and list checks D2R makes first, the decision, the level and the spot.
struct Trail {
	void* list;
	int32_t level;
	melt_trail::Spot spot;
};
enum class Kind { D2R, Fixed, None };

auto Prepare(Unit* unit, uint32_t dataFlag, Trail* t) noexcept -> Kind {
	void* path = unit != nullptr ? Fn<void* (*)(Unit*)>(RvaUnitPath)(unit) : nullptr;
	if (path == nullptr || Fn<int32_t (*)(void*)>(RvaPathActive)(path) == 0) {
		return Kind::D2R;  // D2R's function leaves here too, without a word
	}
	t->list = Fn<void* (*)(Unit*, int32_t)>(RvaStateList)(unit, melt_trail::State);
	if (t->list == nullptr) {
		return Kind::D2R;
	}
	const int32_t skill = ListStat(dataFlag, t->list, melt_trail::StatSkill);
	if (!melt_trail::FixedTrail(skill, Fn<int32_t (*)(uint32_t)>(RvaSkillCount)(dataFlag))) {
		return Kind::D2R;
	}
	void* own = Fn<void* (*)(Unit*, int32_t, uint32_t)>(RvaSkillById)(unit, melt_trail::Skill, 0);
	t->level = Fn<int32_t (*)(Unit*, void*, int32_t, int32_t)>(RvaSkillLevel)(unit, own, 1, 0);
	uint8_t direction = 0;
	if (!melt_trail::StepDirection(Fn<uint8_t (*)(uint8_t)>(RvaDirIndex)(Fn<uint8_t (*)(void*)>(RvaPathDir)(path)), &direction)) {
		return Kind::None;
	}
	int32_t dx = 0, dy = 0, ux = 0, uy = 0;
	Fn<void (*)(uint8_t, int32_t*, int32_t*)>(RvaDirStep)(direction, &dx, &dy);
	if (!d2r::UnitXY(unit, &ux, &uy)) {
		return Kind::None;
	}
	t->spot = melt_trail::SpotFrom(ux, uy, dx, dy);
	return Kind::Fixed;
}

void FillParams(d2r::MissileParams* p, Unit* unit, const Trail& t, uint32_t flags, int32_t skill, int32_t seed) noexcept {
	std::memset(p, 0, sizeof(*p));
	p->flags = flags;
	p->owner = unit;
	p->missile = melt_trail::Missile;
	p->x = t.spot.x;
	p->y = t.spot.y;
	p->targetX = t.spot.targetX;
	p->targetY = t.spot.targetY;
	p->velocity = melt_trail::Velocity;
	p->skill = skill;
	p->skillLevel = t.level;
	p->seed = seed;
}

auto ClientHook(Unit* unit) noexcept -> Unit* {
	const uint32_t dataFlag = unit != nullptr ? d2r::api.unitDataFlag(unit) : 0;
	Trail t{};
	const Kind kind = Prepare(unit, dataFlag, &t);
	if (kind == Kind::D2R) {
		return g_client(unit);
	}
	if (kind == Kind::None) {
		return nullptr;
	}
	// 1.14d's client and D2R's both skip a spot whose room says so (0x61ab00 / 0x2f0750).
	void* room = Fn<void* (*)(void*, int32_t, int32_t)>(RvaRoomAt)(Fn<void* (*)(Unit*)>(RvaUnitRoom)(unit), t.spot.x, t.spot.y);
	if (Fn<int32_t (*)(void*)>(RvaRoomNoTrail)(room) != 0) {
		return nullptr;
	}
	// The seed as D2R's client takes it: stat 202 of the list, a new one stored there when it is 0.
	int32_t seed = ListStat(dataFlag, t.list, melt_trail::StatSeed);
	if (seed == 0) {
		seed = Fn<int32_t (*)()>(RvaNewSeed)();
		Fn<void (*)(uint32_t, void*, int32_t, int32_t, int32_t)>(RvaListSetStat)(dataFlag, t.list, melt_trail::StatSeed, seed, 0);
	}
	d2r::MissileParams params;
	FillParams(&params, unit, t, melt_trail::ClientFlags, melt_trail::ClientSkill, seed);
	Unit* missile = d2r::api.clientMissile(&params, 0);
	Fn<void (*)(int32_t, Unit*, int32_t, int32_t, uint8_t)>(RvaPlaySound)(melt_trail::Sound, unit, 0, 0, 0);
	InterlockedIncrement(&g_clientTrails);
	return missile;
}

auto ServerHook(Game* game, Unit* unit) noexcept -> Unit* {
	if (game == nullptr) {
		return g_server(game, unit);
	}
	const uint32_t dataFlag = d2r::DataFlag(game);
	Trail t{};
	const Kind kind = Prepare(unit, dataFlag, &t);
	if (kind == Kind::D2R) {
		return g_server(game, unit);
	}
	if (kind == Kind::None) {
		return nullptr;
	}
	d2r::MissileParams params;
	FillParams(&params, unit, t, melt_trail::ServerFlags, melt_trail::ServerSkill, ListStat(dataFlag, t.list, melt_trail::StatSeed));
	Unit* missile = d2r::api.createMissile(game, &params);
	InterlockedIncrement(&g_serverTrails);
	return missile;
}

}  // namespace

auto InstallMeltTrail(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int {
	d2r::Bind(context->exeBase);
	g_base = context->exeBase;
	const bool client = context->InstallInlineHook(melt_trail::RvaClient, melt_trail::ClientEntry, sizeof(melt_trail::ClientEntry),
	                                               reinterpret_cast<void*>(&ClientHook), reinterpret_cast<void**>(&g_client));
	const bool server = context->InstallInlineHook(melt_trail::RvaServer, melt_trail::ServerEntry, sizeof(melt_trail::ServerEntry),
	                                               reinterpret_cast<void*>(&ServerHook), reinterpret_cast<void**>(&g_server));
	std::snprintf(report, reportSize, "state 22 without a list skill makes 1.14d's trail (missile %d, skill %d): client 0x221650%s, server 0x578680%s",
	              melt_trail::Missile, melt_trail::Skill, client ? "" : " FAILED", server ? "" : " FAILED");
	return (client ? 1 : 0) + (server ? 1 : 0);
}

void MeltTrailCounts(long* client, long* server) noexcept {
	*client = g_clientTrails;
	*server = g_serverTrails;
}

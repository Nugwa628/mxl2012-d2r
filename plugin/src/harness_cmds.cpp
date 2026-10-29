// Gameplay commands of the test harness: "h <verb> ..." (testharness.cpp routes a console line that starts with "h" here).
//
// Dev builds only (MXL_RELEASE leaves this file out, testharness_release.cpp), and only active while mxl2012-testharness.txt
// sits next to the DLL. The verbs call the game's own functions directly, no simulated mouse or keyboard, so an unattended
// background run can do what the game checks of docs/plugin-plan.md section 10 need (rockshock, srvhit6spawn, srvhit23,
// cltdo83, skillprog, cltdostub, pandewp, terrorzones).
//
// Cut down from a larger harness (5,583 lines): the framework (verb
// table, SEH wrapper, one-slot mailbox run on the game thread) and the verbs below. Of its ~150 other
// verbs only `item` (MakeItem, with its generator hook for set / unique rows) came over, plus `identify` / `items` of our own
// (lane monitems); cube, quests, NPCs, ... did not. Server-side verbs run on the game thread after the server frame
// 0x406550, which this file hooks while the harness is on (elsewhere a goblins part owns that hook). Parsing lives in
// harness_cmds_logic.h (unit-tested).
//
// A verb ends with a line "h: <verb> OK" or "h: <verb> FAIL <reason>" in the harness console file.
#include "harness_cmds_logic.h"

#include "client_skills.h"
#include "d2r.h"
#include "item_effect.h"
#include "skill_remove.h"
#include "missile_stubs.h"
#include "testharness.h"

#include <D2RLPlugin/api.h>

#define NOMINMAX
#include <windows.h>

#include <intrin.h>

#include <cmath>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

using d2r::Game;
using d2r::Unit;

uint64_t g_base = 0;
volatile LONG g_ready = 0;
volatile LONG g_frames = 0;
volatile LONG g_lastGame = 0;
volatile LONG g_playerId = 0;  // unit id of the player the last server frame saw (client verbs look up their client copy)
const D2RL::PluginContext* g_context = nullptr;

template <typename F>
auto Fn(uint64_t rva) noexcept -> F {
	return reinterpret_cast<F>(g_base + rva);
}

// --- addresses (image 0x6ab3782c) ------------------------------------------------------------------------------------
constexpr uint64_t RvaFrame = 0x406550;         // (Game*) the per-game server frame
// 0x406550: mov [rsp+0x20],rsi / push rbp / push rdi / push r15 / lea rbp,[rsp-0x47]   (14 bytes)
constexpr uint8_t FrameEntry[] = {0x48, 0x89, 0x74, 0x24, 0x20, 0x55, 0x57, 0x41, 0x57, 0x48, 0x8d, 0x6c, 0x24, 0xb9};
constexpr uint64_t RvaGetStat = 0x2f5020;       // (unit, stat, layer)
constexpr uint64_t RvaSetStat = 0x2f7d10;       // (unit, stat, value, layer)
constexpr uint64_t RvaPlayerData = 0x34b240;    // (player) -> player data; +0x58 + difficulty * 8 = waypoint record
constexpr uint64_t RvaWaypointSet = 0x3d6890;   // (record, number)
constexpr uint64_t RvaWaypointTest = 0x3d6930;  // (record, number) -> bit
constexpr uint64_t RvaWaypointSend = 0x4812c0;  // (client, record): packet 0x63, the client opens its waypoint panel
constexpr uint64_t RvaWaypointBits = 0x2389010; // 112 x {u16 word, u16 mask}
constexpr int WaypointNumbers = 112;
constexpr uint64_t RvaUnitRoom = 0x34b440;      // (unit) -> room
constexpr uint64_t RvaRoomLevel = 0x2efc10;     // (room) -> level id
constexpr uint64_t RvaClientUnit = 0x484c90;    // (client, 0) -> player unit
constexpr uint64_t RvaKill = 0x44db20;          // (game, victim, killer unit, 1): the unit death function
constexpr uint64_t RvaSpawn = 0x4929e0;         // (game, room, x, y, class, 1, radius, 0, 0)
constexpr uint64_t RvaInRoom = 0x38dfb0;        // (room, x, y) -> the room (or a neighbour) holding the point
constexpr uint64_t RvaTravel = 0x4f2e40;        // (game, player, level, 0): the NPC travel; inside one act it only opens a portal
constexpr uint64_t RvaLevelWarp = 0x488180;     // (game, player, level, 0): the waypoint warp's move inside an act (bug #5)
constexpr uint64_t RvaLevelAct = 0x3e2b5c8;     // (dataFlag, level id) -> act (`levelact`)
constexpr uint64_t RvaPacketTable = 0x1d2a790;  // server packet handlers: (game, player, packet, size)
constexpr uint64_t RvaSkillById = 0x33dcd0;     // (unit, skill id, owner item id or -1) -> Skill* or null
constexpr uint64_t RvaLeftSkill = 0x34a540;     // (unit) -> Skill* on the left button
constexpr uint64_t RvaRightSkill = 0x34b400;    // (unit) -> Skill* on the right button
constexpr uint64_t RvaAddSkillLevel = 0x438670; // (version byte, unit, skill id): one skill point (cost from stat 5) -> 1 / 0
constexpr uint64_t RvaCastAtPoint = 0x4fdb40;   // (game, unit, x, y, 1, Skill*)
constexpr uint64_t RvaCastAtUnit = 0x4f8de0;    // (game, unit, target type, target id, Skill*, 1, shift)
constexpr uint64_t RvaSkillUsable = 0x33f360;   // (unit, Skill*) -> 0 usable; 1 mana / cooldown, 2 requirements, ...
constexpr uint64_t RvaUnitClientOf = 0x48fde0;  // (unit) -> client
constexpr uint64_t RvaMonsterUseSkill = 0x4a7bc0;  // (game, monster, mode < 0x10, skill id, target unit, x, y, 0) -> 1 started
constexpr uint64_t RvaUnitHasState = 0x3351b0;  // (unit, state) -> non-zero when set
constexpr uint64_t RvaClientFind = 0x9a5d0;     // (id, type) -> client unit
constexpr uint64_t RvaPortalUse = 0x58f680;     // (int64 ctx[8] = {game, portal, player, 0, class}) -> moved
constexpr uint64_t RvaPortalLevel = 0x34ad40;   // (portal object) -> destination level (word)
constexpr uint64_t RvaCreateUnit = 0x490410;    // (type, class, x, y, game, room, 1, 1, 0, 0) -> unit
constexpr uint64_t RvaOperateTable = 0x23a51c0; // object operate functions (objects.txt OperateFn)
constexpr uint64_t RvaSetMode = 0x34e5f0;       // (unit, mode)
constexpr uint64_t RvaMonStats = 0x976e0;       // (dataFlag, class) -> monstats record or null

constexpr int GameClients = 0x138, ClientNext = 0x628, ClientState = 0x04, GameFrame = 0x170, GameDifficulty = 0x104;
constexpr int HashPlayers = 0x446, HashMonsters = 0x4c6, HashObjects = 0x546, HashMissiles = 0x646;  // game + (base + (id & 0x7f)) * 8
constexpr int UnitNextInHash = 0x158, UnitId = 0x08, UnitMode = 0x0c;
constexpr int StatLife = 6, StatMana = 8, StatLevel = 12, StatExperience = 13, StatGold = 14, StatGoldBank = 15;

using GetStatFn = int32_t (*)(Unit*, int32_t, int32_t);
using SetStatFn = void (*)(Unit*, int32_t, int32_t, int32_t);
using PlayerDataFn = uint8_t* (*)(Unit*);
using WaypointFn = int32_t (*)(void* record, int32_t number);
using WaypointSendFn = void (*)(void* client, void* record);
using UnitRoomFn = void* (*)(Unit*);
using RoomLevelFn = int32_t (*)(void*);
using ClientUnitFn = Unit* (*)(void*, int32_t);
using KillFn = void (*)(Game*, Unit*, Unit*, int32_t);
using SpawnFn = Unit* (*)(Game*, void*, int32_t, int32_t, int32_t, int32_t, int32_t, int32_t, uint16_t);
using InRoomFn = void* (*)(void*, int32_t, int32_t);
using TravelFn = void (*)(Game*, Unit*, int32_t, int32_t);
using PacketFn = void (*)(Game*, Unit*, const uint8_t*, int32_t);
using SkillByIdFn = uint8_t* (*)(Unit*, int32_t, int32_t);
using ActiveSkillFn = uint8_t* (*)(Unit*);
using AddSkillFn = int32_t (*)(uint32_t, Unit*, uint32_t);
using CastPointFn = int32_t (*)(Game*, Unit*, uint32_t, uint32_t, uint32_t, void*);
using CastUnitFn = void (*)(Game*, Unit*, uint32_t, uint32_t, void*, uint32_t, uint32_t);
using SkillUsableFn = int32_t (*)(Unit*, void*);
using UnitClientFn = void* (*)(Unit*);
using MonsterUseSkillFn = int64_t (*)(Game*, Unit*, uint32_t, int32_t, Unit*, int32_t, int32_t, uint8_t);
using UnitHasStateFn = uint64_t (*)(Unit*, int32_t);
using ClientFindFn = Unit* (*)(uint32_t, int32_t);
using FrameFn = void (*)(Game*);

FrameFn g_frameOriginal = nullptr;
bool g_frameHooked = false;

// --- output -----------------------------------------------------------------------------------------------------
void Out(const char* fmt, ...) noexcept {
	char body[400];
	va_list ap;
	va_start(ap, fmt);
	std::vsnprintf(body, sizeof(body), fmt, ap);
	va_end(ap);
	char line[420];
	std::snprintf(line, sizeof(line), "h: %s", body);
	HarnessEcho(line);
}

struct Ctx {
	Game* game = nullptr;
	Unit* player = nullptr;
	uint32_t dataFlag = 2;
	char verb[24] = "";
	char why[160] = "";
};

auto Fail(Ctx* c, const char* fmt, ...) noexcept -> bool {
	va_list ap;
	va_start(ap, fmt);
	std::vsnprintf(c->why, sizeof(c->why), fmt, ap);
	va_end(ap);
	return false;
}

auto TypeOf(const Unit* u) noexcept -> int32_t { return d2r::At<int32_t>(u, d2r::UnitType); }
auto IdOf(Unit* u) noexcept -> uint32_t { return d2r::At<uint32_t>(u, UnitId); }
auto ClassOf(Unit* u) noexcept -> int32_t { return d2r::At<int32_t>(u, d2r::UnitClass); }
auto ModeOf(Unit* u) noexcept -> int32_t { return d2r::At<int32_t>(u, UnitMode); }
auto IsAlive(Unit* u) noexcept -> bool {
	const int32_t m = ModeOf(u);
	return m != 0 && m != 12;
}
auto Stat(Unit* u, int stat, int layer = 0) noexcept -> int32_t { return Fn<GetStatFn>(RvaGetStat)(u, stat, layer); }
auto LevelOf(Unit* u) noexcept -> int32_t {
	void* room = Fn<UnitRoomFn>(RvaUnitRoom)(u);
	return room != nullptr ? Fn<RoomLevelFn>(RvaRoomLevel)(room) : -1;
}

auto DistTo(Unit* a, Unit* b) noexcept -> double {
	int32_t ax = 0, ay = 0, bx = 0, by = 0;
	if (!d2r::UnitXY(a, &ax, &ay) || !d2r::UnitXY(b, &bx, &by)) {
		return 1e9;
	}
	return std::sqrt(static_cast<double>(ax - bx) * (ax - bx) + static_cast<double>(ay - by) * (ay - by));
}

auto FindPlayer(Game* game) noexcept -> Unit* {
	int guard = 0;
	for (auto* client = d2r::At<uint8_t*>(game, GameClients); client != nullptr && guard < 64;
	     client = d2r::At<uint8_t*>(client, ClientNext), ++guard) {
		if (d2r::At<int32_t>(client, ClientState) != 4) {
			continue;
		}
		Unit* unit = Fn<ClientUnitFn>(RvaClientUnit)(client, 0);
		if (unit != nullptr && TypeOf(unit) == 0) {
			return unit;
		}
	}
	return nullptr;
}

// Calls f(unit) for every unit in one of the game's hash tables.
template <typename F>
void EachUnit(Game* game, int hashBase, F f) noexcept {
	int guard = 0;
	for (int b = 0; b < 128; ++b) {
		for (auto* u = d2r::At<Unit*>(game, (hashBase + b) * 8); u != nullptr && guard < 20000;
		     u = d2r::At<Unit*>(u, UnitNextInHash), ++guard) {
			f(u);
		}
	}
}

auto NearestMonster(Ctx* c, long long cls) noexcept -> Unit* {
	Unit* best = nullptr;
	double bestD = 1e18;
	EachUnit(c->game, HashMonsters, [&](Unit* u) {
		if (TypeOf(u) != 1 || !IsAlive(u) || (cls >= 0 && ClassOf(u) != cls)) {
			return;
		}
		const double d = DistTo(c->player, u);
		if (d < bestD) {
			bestD = d;
			best = u;
		}
	});
	return best;
}

auto FindMonsterById(Ctx* c, uint32_t id) noexcept -> Unit* {
	Unit* found = nullptr;
	EachUnit(c->game, HashMonsters, [&](Unit* u) {
		if (found == nullptr && TypeOf(u) == 1 && IdOf(u) == id) {
			found = u;
		}
	});
	return found;
}

auto FindObjectById(Ctx* c, uint32_t id) noexcept -> Unit* {
	Unit* found = nullptr;
	EachUnit(c->game, HashObjects, [&](Unit* u) {
		if (found == nullptr && TypeOf(u) == 2 && IdOf(u) == id) {
			found = u;
		}
	});
	return found;
}

auto SkillIdOf(const uint8_t* skill) noexcept -> int {
	const uint8_t* row = skill != nullptr ? d2r::At<const uint8_t*>(skill, 0) : nullptr;
	return row != nullptr ? static_cast<int>(*reinterpret_cast<const int16_t*>(row)) : -1;
}
auto SkillBaseLevel(const uint8_t* skill) noexcept -> int { return skill != nullptr ? d2r::At<int32_t>(skill, 0x40) : -1; }

// --- missiles seen since `missiles reset` (short lived: a poll of the live list misses most of them) --------------------
hcmd::SeenUnits g_missileSeen;
volatile LONG g_trackMissiles = 0;

void TrackMissiles(Game* game) noexcept {
	EachUnit(game, HashMissiles, [&](Unit* u) {
		if (TypeOf(u) == 3) {
			g_missileSeen.Add(IdOf(u), ClassOf(u));
		}
	});
}

void PrintMissiles(Ctx* c) noexcept {
	int live = 0;
	EachUnit(c->game, HashMissiles, [&](Unit* u) {
		if (TypeOf(u) != 3) {
			return;
		}
		if (live++ < 10) {
			int32_t x = 0, y = 0;
			d2r::UnitXY(u, &x, &y);
			Out("mis id=%u class=%d mode=%d at %d,%d dist=%.0f", IdOf(u), ClassOf(u), ModeOf(u), x, y, DistTo(c->player, u));
		}
	});
	char sum[200];
	g_missileSeen.Summary(sum, sizeof(sum));
	Out("missiles live=%d seen=%d%s tracking=%s [%s]", live, g_missileSeen.n, g_missileSeen.overflow > 0 ? "+" : "",
	    g_trackMissiles != 0 ? "on" : "off (missiles reset starts it)", sum);
}

// --- unit hash tables (bug #4 diagnosis) -------------------------------------------------------------------------
// One 128-bucket table per unit type at game + base * 8, chained through +0x158. Walks table `k` (base 0x446 + k * 0x80) with
// its own SEH frame, so a base that holds no unit table cannot take the verb down: counts per unit type (0-5, 6 = other),
// and whether `want` is in it (bucket returned, else -1). -2 when the walk faulted.
auto WalkHashBase(Game* game, int base, int counts[7], const Unit* want, int* chains) noexcept -> int {
	int found = -1;
	__try {
		int guard = 0;
		for (int b = 0; b < 128; ++b) {
			auto* u = d2r::At<Unit*>(game, (base + b) * 8);
			if (u != nullptr) {
				++*chains;
			}
			for (; u != nullptr && guard < 20000; u = d2r::At<Unit*>(u, UnitNextInHash), ++guard) {
				const int32_t type = TypeOf(u);
				++counts[type >= 0 && type <= 5 ? type : 6];
				if (u == want && found < 0) {
					found = b;
				}
			}
		}
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		return -2;
	}
	return found;
}

// Prints one line per hash base 0x346..0x846 (players 0x446, monsters 0x4c6, objects 0x546, items 0x5c6, missiles 0x646 as
// the harness reads them) with the unit types found; with `want` also where that unit is.
void PrintHashBases(Game* game, const Unit* want) noexcept {
	for (int k = -2; k <= 8; ++k) {
		const int base = 0x446 + k * 0x80;
		int counts[7] = {};
		int chains = 0;
		const int r = WalkHashBase(game, base, counts, want, &chains);
		Out("hash 0x%x: %s chains=%d types p%d m%d o%d mis%d it%d tile%d other%d%s", base, r == -2 ? "FAULT" : "ok", chains, counts[0], counts[1],
		    counts[2], counts[3], counts[4], counts[5], counts[6], want != nullptr && r >= 0 ? " <- the unit is here" : "");
	}
}

// --- verbs ------------------------------------------------------------------------------------------------------

auto CmdHelp(Ctx*, const hcmd::Tokens&) noexcept -> bool {
	Out("harness frames seen %ld last game %ld, frame hook %s", static_cast<long>(g_frames), static_cast<long>(g_lastGame),
	    g_frameHooked ? "on" : "OFF (server verbs cannot run)");
	Out("verbs: help | echo <text> | frames | state | units | stat player|merc|mon:<id> <stat> [layer] [set <v>] | level <id> [warp [kind]|npc] | spawn <class> [count [x y]] | kill <id>|nearest [class]");
	Out("verbs: setskill <id> <level> | skill [left|right <id>] | cast <id> [x y|unit <id>|nearest [class]|self] | mcast <id> <mode> unit <id>|nearest [class] [at <id>]");
	Out("verbs: missile <row> [dx dy [skill level [where]]] | missiles [reset] | missilescan | cltdo <skill> [level] [orig] | cltst <skill> [orig] (client) | slot <table> [index] (client)");
	Out("verbs: waypoint n <number> [get|set|clear] | waypoint open | objects [class] | object <class> [dx dy] | operate <id> <fn> | objmode <id> <mode> | enter nearest|<id> | dump mon <class> [offset]");
	Out("verbs: item <code> [normal|magic|rare|set|unique [row]] [q=n] [uniq=row] [set=row] [ilvl=n] [inv|cube|ground] [unid] [stat=value ..] | equip <code> ... <head|rhand|lhand|body|...> | unequip <bodyloc> | identify [all|<item id>] | items");
	Out("verbs: pkt <hex bytes> | pickup <item id> [inv] | cursor | ground [code] | move <x> <y> [walk] [packet] | packclear | remove <code> [n]|id <item id> | istat <item id> <stat> [layer|scan] | interact nearest|<npc class> | menu list|<line>|cancel (client) | msg nearest|<npc class> <message> | quest <id> dump|<bit> [get|set|clear] | xp <amount> | moveto <id>|nearest [class] | presets [type|rooms] | place <x> <y>");
	Out("verbs (lane act1start, read only): walkmap <x> <y> <half> <step> [mask] | find <class>");
	Out("verbs (lane realpath): gold get|set <carried> <bank> | shop [npc class] | gamble | usecheck <item id> | tiles");
	Out("verbs: states player|mon:<id> [state] | cstates player|mon:<id> [state] (client) | asserttrace on|count|show [n]|clear (client) | watch cltdo|srvhit <index> | watch [off] (client)");
	Out("verbs: merc [dead] | mercprice [level] | interact <npc class>|nearest | menu list|<line>|cancel (client) | hire [npc class] [n] [reopen] | cursor | shop [npc class] | gamble | pkt <hex bytes> | quest <id> <bit>|dump [set|clear|get]");
	return true;
}

auto CmdEcho(Ctx*, const hcmd::Tokens& t) noexcept -> bool {
	for (int i = 1; i < t.n; ++i) {
		Out("echo %s", t.tok[i]);
	}
	return true;
}

auto CmdFrames(Ctx*, const hcmd::Tokens&) noexcept -> bool {
	Out("frames %ld last game %ld frame hook %s", static_cast<long>(g_frames), static_cast<long>(g_lastGame), g_frameHooked ? "on" : "off");
	return true;
}

// `state`: the player (area, position, life, mana, skills), the plugin's counters, monsters and objects nearby, missiles.
auto CmdState(Ctx* c, const hcmd::Tokens&) noexcept -> bool {
	Unit* p = c->player;
	int32_t x = 0, y = 0;
	d2r::UnitXY(p, &x, &y);
	Out("player id=%u class=%d level=%d life=%d/%d mana=%d area=%d x=%d y=%d mode=%d difficulty=%d frame=%u gold=%d bank=%d", IdOf(p), ClassOf(p),
	    Stat(p, StatLevel), Stat(p, StatLife) >> 8, Stat(p, 7) >> 8, Stat(p, StatMana) >> 8, LevelOf(p), x, y, ModeOf(p),
	    static_cast<int>(d2r::At<uint8_t>(c->game, GameDifficulty)), d2r::At<uint32_t>(c->game, GameFrame), Stat(p, StatGold),
	    Stat(p, StatGoldBank));
	Out("skills left=%d right=%d", SkillIdOf(Fn<ActiveSkillFn>(RvaLeftSkill)(p)), SkillIdOf(Fn<ActiveSkillFn>(RvaRightSkill)(p)));
	long cltDo = 0, srvHit = 0;
	MissileStubHits(&cltDo, &srvHit);
	Out("plugin client wall calls=%ld | missile rows into a stub: client do %ld, server hit %ld | area aura radius skips %ld | item event skills answered 0 %ld (last %ld) | skill removes without skills %ld (last %ld)", ClientWallCalls(), cltDo, srvHit, AreaAuraSkips(), ItemEffectSkips(), ItemEffectLastSkill(), SkillRemoveSkips(), SkillRemoveLastSkill());
	PrintMissiles(c);
	int mons = 0;
	EachUnit(c->game, HashMonsters, [&](Unit* u) {
		if (TypeOf(u) == 1 && IsAlive(u) && DistTo(p, u) < 40 && mons < 60) {
			++mons;
			int32_t mx = 0, my = 0;
			d2r::UnitXY(u, &mx, &my);
			Out("mon id=%u class=%d mode=%d dist=%.0f life=%d/%d mx=%d my=%d area=%d", IdOf(u), ClassOf(u), ModeOf(u), DistTo(p, u),
			    Stat(u, StatLife) >> 8, Stat(u, 7) >> 8, mx, my, LevelOf(u));
		}
	});
	int dead = 0;  // corpses (mode 0 death / 12 dead): a hit-6 row with sHitPar2 0 spawns its monster in mode 0 (bug #11)
	EachUnit(c->game, HashMonsters, [&](Unit* u) {
		if (TypeOf(u) == 1 && !IsAlive(u) && DistTo(p, u) < 40 && dead < 30) {
			++dead;
			Out("corpse id=%u class=%d mode=%d dist=%.0f area=%d", IdOf(u), ClassOf(u), ModeOf(u), DistTo(p, u), LevelOf(u));
		}
	});
	int objs = 0;
	EachUnit(c->game, HashObjects, [&](Unit* u) {
		const int32_t ocls = TypeOf(u) == 2 ? ClassOf(u) : -1;
		const bool portal = ocls == 59 || ocls == 60 || ocls == 600;
		if (TypeOf(u) == 2 && DistTo(p, u) < 30 && (objs < 40 || portal)) {
			++objs;
			int32_t ox = 0, oy = 0;
			d2r::UnitXY(u, &ox, &oy);
			if (portal) {
				Out("obj id=%u class=%d mode=%d dist=%.0f at %d,%d dest=%d", IdOf(u), ocls, ModeOf(u), DistTo(p, u), ox, oy,
				    static_cast<int>(Fn<uint16_t (*)(Unit*)>(RvaPortalLevel)(u)));
			} else {
				Out("obj id=%u class=%d mode=%d dist=%.0f at %d,%d", IdOf(u), ocls, ModeOf(u), DistTo(p, u), ox, oy);
			}
		}
	});
	return true;
}

constexpr uint64_t RvaFindMerc = 0x4ff1a0;  // (game, player, 7, alive flag) -> the player's mercenary unit or null
using FindMercFn = Unit* (*)(Game*, Unit*, int32_t, int32_t);

auto MercOf(Ctx* c, int32_t flag = 0) noexcept -> Unit* { return Fn<FindMercFn>(RvaFindMerc)(c->game, c->player, 7, flag); }

// `stat player|merc|mon:<id> <stat> [layer] [set <value>]`: a stat of the player, its mercenary or a monster, read (and written) through the
// game's own stat calls. Life / mana are in 1/256 (stat 6 / 8; maximum 7 / 9). Output "stat <ref> <stat>:<layer> = <value>"
// (tools/game_checks.py rd / setstat). The checks fill the mana before a cast with it.
auto CmdStat(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long stat = 0, layer = 0, value = 0;
	hcmd::UnitRef ref;
	int next = 3;
	if (t.n < 3 || !hcmd::ParseUnitRef(t.tok[1], &ref) || !hcmd::ParseInt(t.tok[2], &stat) || stat < 0 || stat > 0xffff) {
		return Fail(c, "usage: stat player|merc|mon:<id> <stat> [layer] [set <value>]");
	}
	if (t.n > next && !hcmd::LowerEq(t.tok[next], "set")) {
		if (!hcmd::ParseInt(t.tok[next], &layer)) {
			return Fail(c, "stat: layer must be a number");
		}
		++next;
	}
	const bool set = t.n > next && hcmd::LowerEq(t.tok[next], "set");
	if (set && (t.n <= next + 1 || !hcmd::ParseInt(t.tok[next + 1], &value))) {
		return Fail(c, "stat: set needs a number");
	}
	Unit* unit = ref.kind == hcmd::UnitRef::Player ? c->player
	             : ref.kind == hcmd::UnitRef::Merc ? MercOf(c)
	                                               : FindMonsterById(c, static_cast<uint32_t>(ref.id));
	if (unit == nullptr) {
		return Fail(c, "stat: unit not found");
	}
	if (set) {
		Fn<SetStatFn>(RvaSetStat)(unit, static_cast<int>(stat), static_cast<int32_t>(value), static_cast<int>(layer));
	}
	Out("stat %s %lld:%lld = %d", t.tok[1], stat, layer, Stat(unit, static_cast<int>(stat), static_cast<int>(layer)));
	return true;
}

// `units`: the unit hash tables of the game (bug #4: which base holds the missiles on this image).
auto CmdUnits(Ctx* c, const hcmd::Tokens&) noexcept -> bool {
	PrintHashBases(c->game, nullptr);
	return true;
}

// `level <id> [warp|npc]`: moves the player to a level (D2R level id after tools/idmap.py). Inside the player's act the waypoint
// warp's move 0x488180 (Worldstone and item teleports use it); into another act the NPC travel 0x4f2e40, which inside
// one act only opens a portal (bug #5: `level 2` from area 1 answered OK and the player stayed). `warp` / `npc` force one;
// `warp <kind>` passes the warp's entry kind (0 default; 13 = at the level's waypoint object, as D2R's waypoint travel 0x5933f0
// picks for towns, 46 / 74 and 133-137; 11 the Worldstone's). Takes a few frames: `state` shows the new area. Do not send
// another `level` while one loads.
auto CmdLevel(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long level = 0, kind = 0;
	const bool forceWarp = t.n > 2 && hcmd::LowerEq(t.tok[2], "warp"), forceNpc = t.n > 2 && hcmd::LowerEq(t.tok[2], "npc");
	if (t.n < 2 || !hcmd::ParseInt(t.tok[1], &level) || level < 1 || level > 0xffff || (t.n > 2 && !forceWarp && !forceNpc) ||
	    (t.n > 3 && (!forceWarp || !hcmd::ParseInt(t.tok[3], &kind) || kind < 0 || kind > 0xff))) {
		return Fail(c, "usage: level <level id> [warp [entry kind]|npc]");
	}
	const int from = LevelOf(c->player);
	const auto act = Fn<uint8_t (*)(uint32_t, int32_t)>(RvaLevelAct);
	const int actFrom = from > 0 ? act(c->dataFlag, from) : -1, actTo = act(c->dataFlag, static_cast<int32_t>(level));
	const bool npc = hcmd::UseNpcTravel(actFrom, actTo, forceWarp, forceNpc);
	Fn<TravelFn>(npc ? RvaTravel : RvaLevelWarp)(c->game, c->player, static_cast<int>(level), npc ? 0 : static_cast<int>(kind));
	Out("level %lld (act %d) from area %d (act %d) by %s kind %lld", level, actTo, from, actFrom, npc ? "NPC travel 0x4f2e40" : "warp 0x488180",
	    npc ? 0LL : kind);
	return true;
}

auto CmdSpawn(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long cls = 0, count = 1, sx = 0, sy = 0;
	if (t.n < 2 || !hcmd::ParseInt(t.tok[1], &cls) || (t.n > 2 && !hcmd::ParseInt(t.tok[2], &count)) ||
	    (t.n > 3 && (t.n != 5 || !hcmd::ParseInt(t.tok[3], &sx) || !hcmd::ParseInt(t.tok[4], &sy)))) {
		return Fail(c, "usage: spawn <monster class> [count [x y]]");
	}
	void* room = Fn<UnitRoomFn>(RvaUnitRoom)(c->player);
	int32_t px = 0, py = 0;
	if (room == nullptr || !d2r::UnitXY(c->player, &px, &py)) {
		return Fail(c, "spawn: player has no room");
	}
	int made = 0;
	for (long long i = 0; i < count && i < 20; ++i) {
		const int32_t x = (t.n == 5 ? static_cast<int32_t>(sx) : px + 6) + static_cast<int32_t>(i % 5) * 2;
		const int32_t y = (t.n == 5 ? static_cast<int32_t>(sy) : py + 6) + static_cast<int32_t>(i / 5) * 2;
		void* spawnRoom = Fn<InRoomFn>(RvaInRoom)(room, x, y);
		if (spawnRoom == nullptr) {
			continue;
		}
		if (Unit* m = Fn<SpawnFn>(RvaSpawn)(c->game, spawnRoom, x, y, static_cast<int32_t>(cls), 1, 2, 0, 0)) {
			Out("spawned class %lld id=%u at %d,%d", cls, IdOf(m), x, y);
			++made;
		}
	}
	return made > 0 ? true : Fail(c, "spawn: nothing spawned");
}

auto CmdKill(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	Unit* victim = nullptr;
	long long v = 0, cls = -1;
	if (t.n >= 2 && hcmd::LowerEq(t.tok[1], "nearest") && (t.n < 3 || hcmd::ParseInt(t.tok[2], &cls))) {
		victim = NearestMonster(c, cls);
	} else if (t.n >= 2 && hcmd::ParseInt(t.tok[1], &v)) {
		victim = FindMonsterById(c, static_cast<uint32_t>(v));
	} else {
		return Fail(c, "usage: kill <unit id> | kill nearest [class]");
	}
	if (victim == nullptr) {
		return Fail(c, "kill: no such live monster");
	}
	const uint32_t id = IdOf(victim);
	const int32_t vcls = ClassOf(victim);
	Fn<KillFn>(RvaKill)(c->game, victim, c->player, 1);
	Out("kill id=%u class=%d: mode now %d (0 or 12 = dead)", id, vcls, ModeOf(victim));
	// D2R's death function leaves a monster whose monstats `killable` is off alive (Median 2012's dark_kid, bug #11)
	return !IsAlive(victim) ? true : Fail(c, "kill: the game left class %d alive (monstats killable off?)", vcls);
}

// --- acts verbs (lane acts, same D2R build): talk to an NPC through the server's own talk
// packet, read / click the client's NPC menu, quest bits, experience, walk to a unit. ---------------------------------------
constexpr uint64_t RvaNpcRecord = 0x3971a0;      // (dataFlag, class) -> NPC table row or null (the unit is an NPC)
constexpr uint64_t RvaMove = 0x491ca0;           // (game, unit, 0, x, y, 0, 0): places the unit
constexpr uint64_t RvaMoveBlocked = 0x350a20;    // (unit, x, y, mask) -> non-zero when the spot is blocked
constexpr uint64_t RvaPlayerAction = 0x42d2c0;   // (game, unit, Skill* or null, mode, x, y, 0, 0): what the walk packet ends in
constexpr uint64_t RvaQuestTest = 0x325c50;      // (record, quest, bit)
constexpr uint64_t RvaQuestSet = 0x325c00;
constexpr uint64_t RvaQuestClear = 0x325990;
constexpr uint64_t RvaAddExperience = 0x44f2e0;  // (game, unit, old level, amount): stat 13 and the level-ups
constexpr uint64_t RvaMenuRecord = 0x113990;     // (client npc unit) -> row of the client's NPC menu table
constexpr uint64_t RvaMenuOpenFlag = 0x2a486a4, RvaMenuNpcValid = 0x2a48760, RvaMenuNpcId = 0x2a4875c, RvaMenuNpcClass = 0x2a48764;
constexpr uint64_t RvaMenuTable = 0x2a48830, RvaMenuCount = 0x2a48838;  // 0x48-byte rows: +4 lines (with Cancel), +8 u16 strings, +0x18 handlers
constexpr uint64_t RvaMenuCancel = 0x112c30;     // the Cancel line's handler
using NpcRecordFn = void* (*)(uint32_t, int32_t);
using MoveFn = int64_t (*)(Game*, Unit*, int32_t, int32_t, int32_t, int32_t, int32_t);
using BlockedFn = int32_t (*)(Unit*, int32_t, int32_t, int32_t);
using PlayerActionFn = int64_t (*)(Game*, Unit*, void*, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t);
using QuestFn = int32_t (*)(void*, int32_t, int32_t);
using AddExperienceFn = void (*)(Game*, Unit*, int32_t, int32_t);
using MenuRecordFn = int32_t (*)(Unit*);
using MenuHandlerFn = uint8_t (*)(uint8_t);

auto NearestNpc(Ctx* c, long long cls) noexcept -> Unit* {
	Unit* best = nullptr;
	double bestD = 1e18;
	EachUnit(c->game, HashMonsters, [&](Unit* u) {
		if (TypeOf(u) != 1 || !IsAlive(u) || (cls >= 0 && ClassOf(u) != cls) || Fn<NpcRecordFn>(RvaNpcRecord)(c->dataFlag, ClassOf(u)) == nullptr) {
			return;
		}
		const double d = DistTo(c->player, u);
		if (d < bestD) {
			bestD = d;
			best = u;
		}
	});
	return best;
}

void SendPacket(Ctx* c, const uint8_t* pkt, int32_t size) noexcept {
	const auto handler = reinterpret_cast<PacketFn>(*reinterpret_cast<const uint64_t*>(g_base + RvaPacketTable + pkt[0] * 8));
	handler(c->game, c->player, pkt, size);
}

// `interact nearest|<npc class>`: stands the player next to the NPC (as the walk of a click ends) and sends packet 0x2f (start
// talking: u8 0x2f, u32 unit id, as the verb sends it). The server plays the NPC's speech, runs quest
// event 0 (the quest scripts' NPC activate) and answers 0x27; the client opens the NPC menu through its own builder when the
// speech is over (up to ~30 s on a first talk). `menu list` shows it.
auto CmdInteract(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long cls = -1;
	if (t.n < 2 || !hcmd::ParseNpcTarget(t.tok[1], &cls)) {
		return Fail(c, "usage: interact nearest | interact <npc class>");
	}
	Unit* npc = NearestNpc(c, cls);
	if (npc == nullptr) {
		return Fail(c, "interact: no such NPC alive in this area");
	}
	if (DistTo(c->player, npc) > hcmd::InteractReach) {
		int32_t nx = 0, ny = 0;
		d2r::UnitXY(npc, &nx, &ny);
		for (const auto& o : hcmd::InteractOffsets) {
			if (Fn<BlockedFn>(RvaMoveBlocked)(c->player, nx + o[0], ny + o[1], 0x804) != 0) {
				continue;
			}
			Fn<MoveFn>(RvaMove)(c->game, c->player, 0, nx + o[0], ny + o[1], 0, 0);
			if (DistTo(c->player, npc) <= hcmd::InteractReach) {
				break;
			}
		}
	}
	uint8_t pkt[5] = {0x2f};
	const uint32_t id = IdOf(npc);
	std::memcpy(pkt + 1, &id, 4);
	SendPacket(c, pkt, 5);
	Out("interact npc id=%u class=%d distance %.1f", id, ClassOf(npc), DistTo(c->player, npc));
	return true;
}

// `msg nearest|<npc class> <message id>`: packet 0x31 (a dialog line of the NPC was played to its end): quest event 11.
auto CmdMsg(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long cls = -1, msg = 0;
	if (t.n < 3 || !hcmd::ParseNpcTarget(t.tok[1], &cls) || !hcmd::ParseInt(t.tok[2], &msg) || msg < 0 || msg > 0xffff) {
		return Fail(c, "usage: msg nearest|<npc class> <message id>");
	}
	Unit* npc = NearestNpc(c, cls);
	if (npc == nullptr) {
		return Fail(c, "msg: no such NPC alive in this area");
	}
	uint8_t pkt[8] = {0x31, 1};
	const uint16_t m = static_cast<uint16_t>(msg);
	const uint32_t id = IdOf(npc);
	std::memcpy(pkt + 2, &m, 2);
	std::memcpy(pkt + 4, &id, 4);
	SendPacket(c, pkt, 8);
	Out("msg npc id=%u class=%d message 0x%x sent", id, ClassOf(npc), static_cast<unsigned>(m));
	return true;
}

// The player's quest record of the game's difficulty (player data + 0x40 + difficulty * 8).
auto QuestRecord(Ctx* c) noexcept -> void* {
	uint8_t* data = Fn<PlayerDataFn>(RvaPlayerData)(c->player);
	return data != nullptr ? d2r::At<void*>(data, 0x40 + static_cast<int>(d2r::At<uint8_t>(c->game, GameDifficulty)) * 8) : nullptr;
}

// `quest <id> dump` | `quest <id> <bit> [get|set|clear]`: the quest bits of the game's difficulty. The acts checks read them;
// a `set` is a shortcut a verdict must name.
auto CmdQuest(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	hcmd::QuestArgs a;
	if (!hcmd::ParseQuestArgs(t, &a)) {
		return Fail(c, "usage: quest <id> dump | quest <id> <bit 0-15> [get|set|clear]");
	}
	void* rec = QuestRecord(c);
	if (rec == nullptr) {
		return Fail(c, "no quest record");
	}
	const int q = static_cast<int>(a.quest), bit = static_cast<int>(a.bit);
	if (a.op == hcmd::QuestArgs::Dump) {
		char bits[17] = {};
		for (int i = 0; i < 16; ++i) {
			bits[i] = Fn<QuestFn>(RvaQuestTest)(rec, q, i) != 0 ? '1' : '0';
		}
		Out("quest %d bits0-15 %s", q, bits);
		return true;
	}
	if (a.op == hcmd::QuestArgs::Set) {
		Fn<QuestFn>(RvaQuestSet)(rec, q, bit);
	} else if (a.op == hcmd::QuestArgs::Clear) {
		Fn<QuestFn>(RvaQuestClear)(rec, q, bit);
	}
	Out("quest %d bit %d = %d", q, bit, Fn<QuestFn>(RvaQuestTest)(rec, q, bit) != 0 ? 1 : 0);
	return true;
}

// `xp <amount>`: D2R's experience award (level-ups, stat / skill points and the level cap are the engine's).
auto CmdXp(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long amount = 0;
	if (!hcmd::ParseXp(t, &amount)) {
		return Fail(c, "usage: xp <amount 1..2147483647>");
	}
	Fn<AddExperienceFn>(RvaAddExperience)(c->game, c->player, Stat(c->player, StatLevel), static_cast<int32_t>(amount));
	Out("xp level=%d experience=%u statpoints=%d skillpoints=%d", Stat(c->player, StatLevel), static_cast<uint32_t>(Stat(c->player, 13)),
	    Stat(c->player, 4), Stat(c->player, 5));
	return true;
}

// `moveto <unit id>|nearest [class]`: the player runs to a monster / NPC (0x42d2c0 mode 3, the server finds the path).
auto CmdMoveTo(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long id = 0, cls = -1;
	Unit* u = nullptr;
	if (t.n >= 2 && hcmd::LowerEq(t.tok[1], "nearest") && (t.n < 3 || hcmd::ParseNpcTarget(t.tok[2], &cls))) {
		u = NearestMonster(c, cls);
	} else if (t.n == 2 && hcmd::ParseInt(t.tok[1], &id)) {
		u = FindMonsterById(c, static_cast<uint32_t>(id));
	} else {
		return Fail(c, "usage: moveto <unit id> | moveto nearest [class]");
	}
	int32_t ux = 0, uy = 0;
	if (u == nullptr || !d2r::UnitXY(u, &ux, &uy)) {
		return Fail(c, "moveto: no such live monster");
	}
	const int64_t rc =
	    Fn<PlayerActionFn>(RvaPlayerAction)(c->game, c->player, nullptr, 3, static_cast<uint32_t>(ux), static_cast<uint32_t>(uy), 0, 0) & 0xffffffffLL;
	Out("moveto unit id=%u class=%d at %d,%d: code %lld, mode now %d", IdOf(u), ClassOf(u), ux, uy, static_cast<long long>(rc), ModeOf(c->player));
	return rc == 0 ? true : Fail(c, "moveto: the server refused the path (code %lld)", static_cast<long long>(rc));
}

// `presets [type]`: the preset units of the player's level (the map's own monsters, NPCs, objects, warps), also of rooms
// not loaded yet: what the level will place where. D2R's DRLG walk (waypoint arrival 0x3dad90): unit room +0x18 -> DRLG room,
// room +0x90 -> level (+0x1f8 id, +0x10 first room), room +0x48 next room, room +0x98 preset list (+4 class / row, +8 x,
// +0x10 next, +0x20 unit type, +0x24 y; x / y are sub-tiles inside the room), room +0x60 / +0x64 the room's tile origin.
// Prints the position in `state` units (origin * 5 + x).
auto CmdPresets(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long want = -1;
	const bool roomsOnly = t.n > 1 && std::strcmp(t.tok[1], "rooms") == 0;
	if (t.n > 1 && !roomsOnly && (!hcmd::ParseInt(t.tok[1], &want) || want < 0 || want > 5)) {
		return Fail(c, "usage: presets [unit type 0-5|rooms]");
	}
	void* room = Fn<UnitRoomFn>(RvaUnitRoom)(c->player);
	const uint8_t* drlg = room != nullptr ? d2r::At<const uint8_t*>(room, hcmd::Room1Drlg) : nullptr;
	const uint8_t* level = drlg != nullptr ? d2r::At<const uint8_t*>(drlg, hcmd::DrlgRoomLevel) : nullptr;
	if (level == nullptr) {
		return Fail(c, "presets: no level for the player's room");
	}
	int rooms = 0, shown = 0;
	for (const uint8_t* r = d2r::At<const uint8_t*>(level, hcmd::LevelFirstRoom); r != nullptr && rooms < 4000;
	     r = d2r::At<const uint8_t*>(r, hcmd::DrlgRoomNext), ++rooms) {
		if (roomsOnly) {  // `presets rooms`: each room's origin in `state` units (where a level spreads, rooms not loaded too)
			if (rooms < 400) {
				Out("room x=%d y=%d", hcmd::PresetToState(d2r::At<int32_t>(r, hcmd::DrlgRoomTileX), 0),
				    hcmd::PresetToState(d2r::At<int32_t>(r, hcmd::DrlgRoomTileY), 0));
			}
			continue;
		}
		int guard = 0;
		for (const uint8_t* p = d2r::At<const uint8_t*>(r, hcmd::DrlgRoomPresets); p != nullptr && guard < 400;
		     p = d2r::At<const uint8_t*>(p, hcmd::PresetNext), ++guard) {
			const int32_t type = d2r::At<int32_t>(p, hcmd::PresetType);
			if ((want >= 0 && type != want) || shown >= 200) {
				continue;
			}
			++shown;
			Out("preset type=%d class=%d x=%d y=%d", type, d2r::At<int32_t>(p, hcmd::PresetClass),
			    hcmd::PresetToState(d2r::At<int32_t>(r, hcmd::DrlgRoomTileX), d2r::At<int32_t>(p, hcmd::PresetX)),
			    hcmd::PresetToState(d2r::At<int32_t>(r, hcmd::DrlgRoomTileY), d2r::At<int32_t>(p, hcmd::PresetY)));
		}
	}
	Out("presets level %d rooms %d units %d", d2r::At<int32_t>(level, hcmd::LevelId), rooms, shown);
	return true;
}

// `place <x> <y>`: puts the player on the first free spot near (x, y) (`state` units) with the unit move 0x491ca0, the call
// `interact` stands the player next to an NPC with. A travel shortcut (the checks name it): the walk is skipped, nothing else.
auto CmdPlace(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long x = 0, y = 0;
	if (t.n != 3 || !hcmd::ParseInt(t.tok[1], &x) || !hcmd::ParseInt(t.tok[2], &y) || x < 0 || y < 0 || x > 0xfffff || y > 0xfffff) {
		return Fail(c, "usage: place <x> <y>   (positions as in `state`)");
	}
	for (const auto& o : hcmd::PlaceOffsets) {
		const int32_t px = static_cast<int32_t>(x) + o[0], py = static_cast<int32_t>(y) + o[1];
		if (Fn<BlockedFn>(RvaMoveBlocked)(c->player, px, py, 0x804) != 0) {
			continue;
		}
		Fn<MoveFn>(RvaMove)(c->game, c->player, 0, px, py, 0, 0);
		int32_t nx = 0, ny = 0;
		d2r::UnitXY(c->player, &nx, &ny);
		if (std::abs(nx - px) > 5 || std::abs(ny - py) > 5) {  // bug #438: the move call left the player where it was (the
			Out("place at %d,%d: the move did not take, player still %d,%d", px, py, nx, ny);  // spot's room not active)
			continue;
		}
		Out("place at %d,%d: player now %d,%d area %d", px, py, nx, ny, LevelOf(c->player));
		return true;
	}
	return Fail(c, "place: no free spot near %lld,%lld (or the room is not loaded, or the move did not take)", x, y);
}

// `walkmap <x> <y> <half> <step> [mask]` (lane act1start, read only): the walk collision of the loaded rooms in the square
// round (x, y) (`state` units), one `wm y=<row>` line per map row, a character per cell: `.` free in the player's level, `A`..`H`
// free in another level (the `walkmap` line names them), `#` blocked, `?` unknown: no loaded room, or a room that is not the
// player's or a neighbour of it (0x350a20 answers "blocked" for every spot there, lane act1start run checks-20261029-081648-s3),
// so a map reaches about one room round the player's. The cells are filled outward from the middle one. Mask default 0x1c09
// (the free-spot search's player mask). The player path checks plan their clicks on it and plan again from each stop.
constexpr int WalkMapSide = 241;
char g_wmCell[WalkMapSide * WalkMapSide];
void* g_wmRoom[WalkMapSide * WalkMapSide];
int g_wmQueue[WalkMapSide * WalkMapSide];

auto CmdWalkMap(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long x = 0, y = 0, half = 0, step = 0, mask = 0x1c09;
	if (t.n < 5 || !hcmd::ParseInt(t.tok[1], &x) || !hcmd::ParseInt(t.tok[2], &y) || !hcmd::ParseInt(t.tok[3], &half) ||
	    !hcmd::ParseInt(t.tok[4], &step) || (t.n > 5 && !hcmd::ParseInt(t.tok[5], &mask)) || half < 4 || half > 400 || step < 1 ||
	    step > 20 || half / step > 120 || x < half || y < half) {
		return Fail(c, "usage: walkmap <x> <y> <half 4-400> <step 1-20> [mask]   (half / step at most 120)");
	}
	void* home = Fn<UnitRoomFn>(RvaUnitRoom)(c->player);
	if (home == nullptr) {
		return Fail(c, "walkmap: the player has no room");
	}
	const int side = static_cast<int>(half / step) * 2 + 1;
	const long long x0 = x - (side / 2) * step, y0 = y - (side / 2) * step;
	const int32_t own = LevelOf(c->player);
	int32_t others[8] = {};
	int nOthers = 0, nFree = 0, blocked = 0;
	std::memset(g_wmCell, '?', sizeof(g_wmCell));
	std::memset(g_wmRoom, 0, sizeof(g_wmRoom));
	auto fill = [&](int i, void* hint) -> bool {
		const int32_t px = static_cast<int32_t>(x0 + (i % side) * step), py = static_cast<int32_t>(y0 + (i / side) * step);
		(void)hint;
		void* r = Fn<InRoomFn>(RvaInRoom)(home, px, py);  // the player's room or a neighbour: where 0x350a20 answers
		if (r == nullptr) {
			return false;
		}
		g_wmRoom[i] = r;
		if (Fn<BlockedFn>(RvaMoveBlocked)(c->player, px, py, static_cast<int32_t>(mask)) != 0) {
			g_wmCell[i] = '#';
			++blocked;
			return true;
		}
		const int32_t lv = Fn<RoomLevelFn>(RvaRoomLevel)(r);
		char ch = '.';
		if (lv != own) {
			int k = 0;
			while (k < nOthers && others[k] != lv) {
				++k;
			}
			if (k == nOthers && nOthers < 8) {
				others[nOthers++] = lv;
			}
			ch = k < 8 ? static_cast<char>('A' + k) : '+';
		}
		g_wmCell[i] = ch;
		++nFree;
		return true;
	};
	static bool seen[WalkMapSide * WalkMapSide];
	std::memset(seen, 0, sizeof(seen));
	int head = 0, tail = 0;
	const int mid = (side / 2) * side + side / 2;
	seen[mid] = true;
	if (fill(mid, home)) {
		g_wmQueue[tail++] = mid;
	}
	while (head < tail) {
		const int i = g_wmQueue[head++];
		const int row = i / side, col = i % side;
		const int nb[4][2] = {{row, col + 1}, {row + 1, col}, {row, col - 1}, {row - 1, col}};
		for (const auto& n : nb) {
			if (n[0] < 0 || n[0] >= side || n[1] < 0 || n[1] >= side) {
				continue;
			}
			const int j = n[0] * side + n[1];
			if (seen[j]) {
				continue;
			}
			seen[j] = true;
			if (fill(j, g_wmRoom[i])) {
				g_wmQueue[tail++] = j;
			}
		}
	}
	for (int row = 0; row < side; ++row) {
		char line[WalkMapSide + 1];
		std::memcpy(line, g_wmCell + row * side, static_cast<size_t>(side));
		line[side] = '\0';
		Out("wm y=%lld %s", y0 + row * step, line);
	}
	char names[96] = "";
	for (int k = 0, o = 0; k < nOthers; ++k) {
		o += std::snprintf(names + o, sizeof(names) - o, "%s%c=%d", k ? "," : "", 'A' + k, others[k]);
	}
	Out("walkmap x0=%lld y0=%lld step=%lld level=%d free=%d blocked=%d others=%s", x0, y0, step, own, nFree, blocked,
	    nOthers ? names : "none");
	return true;
}

// `find <class>` (lane act1start, read only): every live monster / NPC of the class in the game, wherever it stands (`state`
// lists only the units within 40), nearest first is not promised.
auto CmdFind(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long cls = -1;
	if (t.n != 2 || !hcmd::ParseInt(t.tok[1], &cls)) {
		return Fail(c, "usage: find <monstats class>");
	}
	int found = 0;
	EachUnit(c->game, HashMonsters, [&](Unit* u) {
		if (TypeOf(u) == 1 && IsAlive(u) && ClassOf(u) == cls && found < 20) {
			++found;
			int32_t mx = 0, my = 0;
			d2r::UnitXY(u, &mx, &my);
			Out("found id=%u class=%d mode=%d dist=%.0f mx=%d my=%d area=%d", IdOf(u), ClassOf(u), ModeOf(u), DistTo(c->player, u), mx, my,
			    LevelOf(u));
		}
	});
	return found > 0 ? true : Fail(c, "find: no live unit of class %lld", cls);
}

// Client side (UI thread): `menu list` | `menu <line>` | `menu cancel`: the NPC menu the 0x27 packet opened. `<line>` calls that
// line's own click handler (Trade, Talk, the travel line, Gamble...), as the click on it does.
auto CmdMenu(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	const auto* b = reinterpret_cast<const uint8_t*>(g_base);
	if (*reinterpret_cast<const uint32_t*>(b + RvaMenuNpcValid) == 0 || *reinterpret_cast<const uint32_t*>(b + RvaMenuOpenFlag) == 0) {
		return Fail(c, "menu: no NPC menu is open (interact first, then wait for the speech)");
	}
	Unit* npc = Fn<ClientFindFn>(RvaClientFind)(*reinterpret_cast<const uint32_t*>(b + RvaMenuNpcId), 1);
	const int32_t row = npc != nullptr ? Fn<MenuRecordFn>(RvaMenuRecord)(npc) : -1;
	const uint32_t count = *reinterpret_cast<const uint32_t*>(b + RvaMenuCount);
	const auto* table = *reinterpret_cast<const uint8_t* const*>(b + RvaMenuTable);
	if (row < 0 || static_cast<uint32_t>(row) >= count || table == nullptr) {
		return Fail(c, "menu: NPC row not found");
	}
	const uint8_t* r = table + static_cast<size_t>(row) * 0x48;
	const int32_t lines = d2r::At<int32_t>(r, 4);  // includes the final Cancel
	const int line = t.n >= 2 ? hcmd::ParseMenuLine(t.tok[1], lines) : -3;
	if (line == -1) {
		Out("menu npc id=%u class=%u row=%d lines=%d (+ Cancel)", *reinterpret_cast<const uint32_t*>(b + RvaMenuNpcId),
		    static_cast<unsigned>(*reinterpret_cast<const uint16_t*>(b + RvaMenuNpcClass)), row, lines - 1);
		for (int i = 0; i < lines - 1 && i < hcmd::MenuMaxLines; ++i) {
			const uint64_t handler = d2r::At<uint64_t>(r, 0x18 + 8 * i);
			const bool inImage = handler >= g_base && handler < g_base + 0x4000000;
			Out("  line %d string=0x%x handler=%s0x%llx", i, static_cast<unsigned>(d2r::At<uint16_t>(r, 8 + 2 * i)), inImage ? "image+" : "plugin@",
			    static_cast<unsigned long long>(inImage ? handler - g_base : handler));
		}
		return true;
	}
	if (line == -3) {
		return Fail(c, "usage: menu list | menu cancel | menu <line 0..%d>", lines - 2);
	}
	const uint64_t handler = line == -2 ? g_base + RvaMenuCancel : d2r::At<uint64_t>(r, 0x18 + 8 * line);
	if (handler == 0) {
		return Fail(c, "menu: that line has no handler");
	}
	const uint8_t res = reinterpret_cast<MenuHandlerFn>(handler)(static_cast<uint8_t>(c->dataFlag));
	Out("menu line %s handler 0x%llx returned %u", t.tok[1], static_cast<unsigned long long>(handler - g_base), static_cast<unsigned>(res));
	return true;
}

// Client side (UI thread), bug #488: `lvlbtn` prints the HUD panel's two level-up buttons (StatUp / SkillUp, class
// LevelUpButtonWidget, vtable 0x1fd9ee0): visible +0x51, disabled +0x67a, lit mask +0xd5c, and how often the class's
// Update (slot 2, 0x14d1090) and Draw (slot 3, 0x14d01a0) ran since `lvlbtn count` put counters into those slots;
// `lvlbtn update` runs Update on both once; `lvlbtn count off` puts the slots back.
using WidgetFn = void (*)(void*) noexcept;
using PanelByNameFn = void* (*)(const char*) noexcept;
using ChildByNameFn = void* (*)(void*, const char*) noexcept;
using TypeFn = void* (*)() noexcept;
constexpr uint64_t RvaPanelByName = 0x846170;     // (name) -> panel widget of the panel manager, null without one
constexpr uint64_t RvaChildByName = 0x856220;     // (widget, name) -> child widget
constexpr uint64_t RvaLevelUpType = 0x14d06d0;    // LevelUpButtonWidget's type descriptor
constexpr uint64_t RvaPanelMgrHd = 0x846210;      // bool: the panel manager's +0xb9 byte
constexpr uint64_t RvaLvlVtUpdate = 0x1fd9ef0;    // vtable slot 2
constexpr uint64_t RvaLvlVtDraw = 0x1fd9ef8;      // vtable slot 3
WidgetFn g_lvlUpdate = nullptr;
WidgetFn g_lvlDraw = nullptr;
volatile LONG g_lvlUpdates = 0;
volatile LONG g_lvlDraws = 0;
void LvlUpdateCount(void* w) noexcept {
	InterlockedIncrement(&g_lvlUpdates);
	g_lvlUpdate(w);
}
void LvlDrawCount(void* w) noexcept {
	InterlockedIncrement(&g_lvlDraws);
	g_lvlDraw(w);
}

auto LevelUpButton(void* panel, const char* name) noexcept -> uint8_t* {
	auto* w = static_cast<uint8_t*>(Fn<ChildByNameFn>(RvaChildByName)(panel, name));
	if (w == nullptr) {
		return nullptr;
	}
	void* want = Fn<TypeFn>(RvaLevelUpType)();
	using TypeOfFn = uint8_t* (*)(void*) noexcept;
	for (uint8_t* ty = (*reinterpret_cast<TypeOfFn* const*>(w))[0x58 / 8](w); ty != nullptr; ty = d2r::At<uint8_t*>(ty, 0x10)) {
		if (ty == want) {
			return w;
		}
	}
	return nullptr;
}

auto CmdLvlBtn(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	if (t.n >= 2 && hcmd::LowerEq(t.tok[1], "count")) {
		const bool off = t.n >= 3 && hcmd::LowerEq(t.tok[2], "off");
		if (g_context == nullptr) {
			return Fail(c, "lvlbtn: no plugin context");
		}
		if (off) {
			if (g_lvlUpdate != nullptr) {
				const uint64_t mine = reinterpret_cast<uint64_t>(&LvlUpdateCount), mine2 = reinterpret_cast<uint64_t>(&LvlDrawCount);
				const bool a = g_context->PatchWriteU64(RvaLvlVtUpdate, &mine, sizeof(mine), reinterpret_cast<uint64_t>(g_lvlUpdate));
				const bool b = g_context->PatchWriteU64(RvaLvlVtDraw, &mine2, sizeof(mine2), reinterpret_cast<uint64_t>(g_lvlDraw));
				if (!a || !b) {
					return Fail(c, "lvlbtn count off: a slot is no longer ours");
				}
				g_lvlUpdate = nullptr;
			}
			Out("lvlbtn count off");
			return true;
		}
		if (g_lvlUpdate == nullptr) {
			const uint64_t up = *reinterpret_cast<const volatile uint64_t*>(g_base + RvaLvlVtUpdate);
			const uint64_t dr = *reinterpret_cast<const volatile uint64_t*>(g_base + RvaLvlVtDraw);
			g_lvlUpdate = reinterpret_cast<WidgetFn>(up);
			g_lvlDraw = reinterpret_cast<WidgetFn>(dr);
			if (!g_context->PatchWriteU64(RvaLvlVtUpdate, &up, sizeof(up), reinterpret_cast<uint64_t>(&LvlUpdateCount)) ||
			    !g_context->PatchWriteU64(RvaLvlVtDraw, &dr, sizeof(dr), reinterpret_cast<uint64_t>(&LvlDrawCount))) {
				return Fail(c, "lvlbtn: vtable write failed");
			}
		}
		InterlockedExchange(&g_lvlUpdates, 0);
		InterlockedExchange(&g_lvlDraws, 0);
		Out("lvlbtn count on");
		return true;
	}
	const bool update = t.n >= 2 && hcmd::LowerEq(t.tok[1], "update");
	void* panel = Fn<PanelByNameFn>(RvaPanelByName)("HUDPanel");
	const bool hd = Fn<bool (*)() noexcept>(RvaPanelMgrHd)();
	Out("lvlbtn panelmgr+0xb9=%d HUDPanel=%p visible=%d updates=%ld draws=%ld", hd ? 1 : 0, panel,
	    panel != nullptr ? d2r::At<uint8_t>(panel, 0x51) : -1, static_cast<long>(g_lvlUpdates), static_cast<long>(g_lvlDraws));
	if (panel == nullptr) {
		return Fail(c, "lvlbtn: no HUDPanel");
	}
	for (const char* name : {"StatUp", "SkillUp", "LevelUpButton"}) {
		uint8_t* w = LevelUpButton(panel, name);
		if (w == nullptr) {
			Out("  %s: none", name);
			continue;
		}
		if (update) {
			(*reinterpret_cast<WidgetFn* const*>(w))[2](w);
		}
		Out("  %s %p: visible=%u disabled=%u mask=%d types=%d type0=%d floating=%u", name, w, d2r::At<uint8_t>(w, 0x51),
		    d2r::At<uint8_t>(w, 0x67a), d2r::At<int32_t>(w, 0xd5c), d2r::At<int32_t>(w, 0xb94), d2r::At<int32_t>(w, 0xb88),
		    d2r::At<uint8_t>(w, 0xb98));
	}
	return true;
}

// Selects an active skill through packet 0x3c's handler; returns the skill id that is active afterwards.
auto SelectSkill(Ctx* c, long long id, bool left, uint32_t owner = 0xffffffffU) noexcept -> int {
	uint8_t pkt[9];
	const size_t n = hcmd::BuildSelectSkillPacket(pkt, static_cast<int>(id), left, owner);
	const auto handler = reinterpret_cast<PacketFn>(*reinterpret_cast<const uint64_t*>(g_base + RvaPacketTable + 0x3c * 8));
	handler(c->game, c->player, pkt, static_cast<int32_t>(n));
	return SkillIdOf(left ? Fn<ActiveSkillFn>(RvaLeftSkill)(c->player) : Fn<ActiveSkillFn>(RvaRightSkill)(c->player));
}

// `skill` prints the active skills; `skill left|right <id>` selects one.
auto CmdSkill(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	if (t.n >= 3) {
		long long id = 0;
		const bool left = hcmd::LowerEq(t.tok[1], "left");
		if ((!left && !hcmd::LowerEq(t.tok[1], "right")) || !hcmd::ParseInt(t.tok[2], &id) || id < 0 || id > 0xffff) {
			return Fail(c, "usage: skill [left|right <skill id>]");
		}
		const int now = SelectSkill(c, id, left);
		Out("skill %s %lld: active now %d", left ? "left" : "right", id, now);
		return now == id ? true : Fail(c, "skill: the game did not select %lld (no level in it? try setskill)", id);
	}
	Out("skill left=%d right=%d", SkillIdOf(Fn<ActiveSkillFn>(RvaLeftSkill)(c->player)), SkillIdOf(Fn<ActiveSkillFn>(RvaRightSkill)(c->player)));
	return true;
}

// `setskill <id> <level>`: raises the skill with the game's own skill-point function (0x438670) with a refilled stat 5
// pool each step, then restores stat 5. Lowering writes the base level. Any skill (Rock Shock 28 is a monster skill row).
auto CmdSetSkill(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long id = 0, level = 0;
	if (t.n < 3 || !hcmd::ParseInt(t.tok[1], &id) || !hcmd::ParseInt(t.tok[2], &level) || id < 0 || id > 0xffff || level < 0 || level > 200) {
		return Fail(c, "usage: setskill <skill id> <level 0-200>");
	}
	const int pool = Stat(c->player, 5);
	const uint32_t version = d2r::At<uint8_t>(c->game, d2r::GameDataFlag);
	uint8_t* sk = Fn<SkillByIdFn>(RvaSkillById)(c->player, static_cast<int32_t>(id), -1);
	int guard = 0;
	while (SkillBaseLevel(sk) < level && guard++ < 220) {
		Fn<SetStatFn>(RvaSetStat)(c->player, 5, 255, 0);
		if (Fn<AddSkillFn>(RvaAddSkillLevel)(version, c->player, static_cast<uint32_t>(id)) == 0) {
			break;
		}
		sk = Fn<SkillByIdFn>(RvaSkillById)(c->player, static_cast<int32_t>(id), -1);
	}
	Fn<SetStatFn>(RvaSetStat)(c->player, 5, pool, 0);
	if (sk != nullptr && SkillBaseLevel(sk) > level) {
		*reinterpret_cast<int32_t*>(sk + 0x40) = static_cast<int32_t>(level);
	}
	const int now = sk != nullptr ? SkillBaseLevel(sk) : 0;
	Out("setskill %lld: base level %d (wanted %lld), skill points restored to %d", id, now, level, pool);
	return now == level ? true : Fail(c, "setskill: stopped at level %d (the game refused the next point)", now);
}

// `cast <skill id> [x y | unit <id> | nearest [class] | self] [item <id>]`: the skill used the way the cast packets do
// (location 0x4fdb40, unit 0x4f8de0). Poll `state` / `missiles` for the result. With `item <id>` the skill is the worn item's
// charged skill (owner = the item's id, selected as the skill menu does; lane bugsweep, bug #484: a charge used this way).
auto CmdCast(Ctx* c, const hcmd::Tokens& in) noexcept -> bool {
	long long id = 0, item = -1;
	hcmd::Tokens t = in;
	if (t.n >= 4 && hcmd::LowerEq(t.tok[t.n - 2], "item")) {
		if (!hcmd::ParseInt(t.tok[t.n - 1], &item) || item < 0 || item > 0xffffffffLL) {
			return Fail(c, "usage: cast ... item <item id>");
		}
		t.n -= 2;
	}
	hcmd::CastTarget tg;
	if (t.n < 2 || !hcmd::ParseInt(t.tok[1], &id) || id < 0 || id > 0xffff || !hcmd::ParseCastTarget(t, 2, &tg)) {
		return Fail(c, "usage: cast <skill id> [x y | unit <id> | nearest [class] | self] [item <id>]");
	}
	const uint32_t owner = item < 0 ? 0xffffffffU : static_cast<uint32_t>(item);
	uint8_t* sk = Fn<SkillByIdFn>(RvaSkillById)(c->player, static_cast<int32_t>(id), static_cast<int32_t>(owner));
	if (sk == nullptr) {
		return item < 0 ? Fail(c, "cast: the player has no skill %lld (setskill %lld 1 first)", id, id)
		                : Fail(c, "cast: the player has no skill %lld owned by item %lld (worn?)", id, item);
	}
	if (SkillIdOf(Fn<ActiveSkillFn>(RvaLeftSkill)(c->player)) != id && SelectSkill(c, id, true, owner) != id &&
	    SelectSkill(c, id, false, owner) != id && (tg.kind == hcmd::CastTarget::Unit || tg.kind == hcmd::CastTarget::Nearest)) {
		return Fail(c, "cast: the game would not select skill %lld (a passive, or not usable as an active skill)", id);
	}
	const int manaBefore = Stat(c->player, StatMana) >> 8;
	int32_t px = 0, py = 0;
	d2r::UnitXY(c->player, &px, &py);
	Out("cast checks: usable=%d (0 ok) skill mode=%d unit mode=%d", Fn<SkillUsableFn>(RvaSkillUsable)(c->player, sk), d2r::At<int32_t>(sk, 0x10),
	    ModeOf(c->player));
	if (tg.kind == hcmd::CastTarget::Unit || tg.kind == hcmd::CastTarget::Nearest) {
		Unit* target = tg.kind == hcmd::CastTarget::Unit ? FindMonsterById(c, static_cast<uint32_t>(tg.id)) : NearestMonster(c, tg.cls);
		if (target == nullptr) {
			return Fail(c, "cast: no such live monster");
		}
		Fn<CastUnitFn>(RvaCastAtUnit)(c->game, c->player, 1, IdOf(target), sk, 1, 0);
		Out("cast skill %lld (level %d) at monster id=%u class=%d dist %.0f: mode now %d, mana %d -> %d", id, SkillBaseLevel(sk), IdOf(target),
		    ClassOf(target), DistTo(c->player, target), ModeOf(c->player), manaBefore, Stat(c->player, StatMana) >> 8);
		return true;
	}
	const uint32_t x = tg.kind == hcmd::CastTarget::Point ? static_cast<uint32_t>(tg.x) : static_cast<uint32_t>(px);
	const uint32_t y = tg.kind == hcmd::CastTarget::Point ? static_cast<uint32_t>(tg.y) : static_cast<uint32_t>(py);
	const int32_t rc = Fn<CastPointFn>(RvaCastAtPoint)(c->game, c->player, x, y, 1, sk);
	Out("cast skill %lld (level %d) at %u,%u: code %d, mode now %d, mana %d -> %d", id, SkillBaseLevel(sk), x, y, rc, ModeOf(c->player),
	    manaBefore, Stat(c->player, StatMana) >> 8);
	return rc == 0 ? true : Fail(c, "cast: the game refused the skill use (code %d; town, no mana, cooldown or busy?)", rc);
}

// `mcast <skill id> <mode> unit <id> | nearest [class] [at <monster id>]`: the monster uses the skill on the player (or, with
// `at`, on another monster: Imp Teleport onto a Siege Beast, lane statefaith) through the AI's skill use (0x4a7bc0, mode as
// monstats Sk<n>mode: 6 = A1, 7 = A2, 9 = SC, 10 = S1). The monster must own the skill (monstats row).
// Lane fixes3: for Median's Zakarum cleric's Rapture (Sk3mode S1) mode 8, the S1 row of monmode.txt, made the cast and
// state 22; mode 10 left the unit in mode 10 (S3) without the state.
auto CmdMonsterCast(Ctx* c, const hcmd::Tokens& t0) noexcept -> bool {
	long long skill = 0, mode = 0, at = -1;
	hcmd::Tokens t = t0;
	if (t.n >= 6 && std::strcmp(t.tok[t.n - 2], "at") == 0) {
		if (!hcmd::ParseInt(t.tok[t.n - 1], &at) || at < 0) {
			return Fail(c, "usage: mcast ... at <monster id>");
		}
		t.n -= 2;
	}
	hcmd::CastTarget tg;
	if (t.n < 4 || !hcmd::ParseInt(t.tok[1], &skill) || !hcmd::ParseInt(t.tok[2], &mode) || skill < 0 || skill > 0xffff || mode < 0 || mode > 15 ||
	    !hcmd::ParseCastTarget(t, 3, &tg) || (tg.kind != hcmd::CastTarget::Unit && tg.kind != hcmd::CastTarget::Nearest)) {
		return Fail(c, "usage: mcast <skill id> <mode 0-15> unit <id> | nearest [class] [at <monster id>]");
	}
	Unit* mon = tg.kind == hcmd::CastTarget::Unit ? FindMonsterById(c, static_cast<uint32_t>(tg.id)) : NearestMonster(c, tg.cls);
	if (mon == nullptr) {
		return Fail(c, "mcast: no such live monster");
	}
	Unit* target = at >= 0 ? FindMonsterById(c, static_cast<uint32_t>(at)) : c->player;
	if (target == nullptr) {
		return Fail(c, "mcast: no such live target monster");
	}
	const int modeBefore = ModeOf(mon);
	const int64_t rc = Fn<MonsterUseSkillFn>(RvaMonsterUseSkill)(c->game, mon, static_cast<uint32_t>(mode), static_cast<int32_t>(skill), target, 0, 0, 0);
	Out("mcast monster id=%u class=%d skill %lld mode %lld at %s %u: returned %lld, unit mode %d -> %d", IdOf(mon), ClassOf(mon), skill, mode,
	    at >= 0 ? "monster" : "player", IdOf(target), static_cast<long long>(rc), modeBefore, ModeOf(mon));
	return rc != 0 ? true : Fail(c, "mcast: the monster did not start the skill (not its skill, or the mode is not allowed)");
}

// `missile <row> [dx dy [skill level]]`: a missile of missiles.txt row <row> from the player towards (player + dx, dy)
// (default 12, 0), made by skill <skill> at level <level> (default 0 / 0), the same call the skills use (0x5371a0).
// srvhit6spawn / srvhit23 fire their rows with it; cltdostub fires the rows with an empty pCltDoFunc.
auto CmdMissile(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long row = 0, dx = 12, dy = 0, skill = 0, level = 0;
	if (t.n < 2 || !hcmd::ParseInt(t.tok[1], &row) || row < 0 || row > 0x7fff || (t.n >= 3 && !hcmd::ParseInt(t.tok[2], &dx)) ||
	    (t.n >= 4 && !hcmd::ParseInt(t.tok[3], &dy)) || (t.n >= 5 && (!hcmd::ParseInt(t.tok[4], &skill) || skill < 0 || skill > 0x7fff)) ||
	    (t.n >= 6 && (!hcmd::ParseInt(t.tok[5], &level) || level < 0 || level > 0xff))) {
		return Fail(c, "usage: missile <missiles.txt row> [dx dy [skill level]]");
	}
	if (row >= d2r::api.missileCount(c->dataFlag)) {
		return Fail(c, "missile: row %lld is beyond missiles.txt (%d rows)", row, d2r::api.missileCount(c->dataFlag));
	}
	int32_t px = 0, py = 0;
	if (t.n >= 7 && !hcmd::LowerEq(t.tok[6], "where")) {
		return Fail(c, "usage: missile <missiles.txt row> [dx dy [skill level [where]]]");
	}
	if (!d2r::UnitXY(c->player, &px, &py)) {
		return Fail(c, "missile: player has no position");
	}
	const uint8_t* rec = d2r::api.missileRecord(c->dataFlag, static_cast<int32_t>(row));
	d2r::MissileParams params;
	std::memset(&params, 0, sizeof(params));
	params.flags = 0x820;
	params.owner = c->player;
	params.origin = c->player;
	params.missile = static_cast<int32_t>(row);
	params.targetX = px + static_cast<int32_t>(dx);
	params.targetY = py + static_cast<int32_t>(dy);
	params.skill = static_cast<int32_t>(skill);
	params.skillLevel = static_cast<int32_t>(level);
	Unit* m = d2r::api.createMissile(c->game, &params);
	if (m != nullptr) {
		if (g_trackMissiles != 0) {
			g_missileSeen.Add(IdOf(m), ClassOf(m));
		}
		Out("missile unit %p type=%d id=%u class=%d mode=%d bucket=%u", static_cast<void*>(m), TypeOf(m), IdOf(m), ClassOf(m), ModeOf(m), IdOf(m) & 0x7f);
		if (t.n >= 7 && hcmd::LowerEq(t.tok[6], "where")) {
			PrintHashBases(c->game, m);
		}
	}
	Out("missile row %lld (pCltDoFunc %d pCltHitFunc %d pSrvHitFunc %d) in area %d: %s", row,
	    rec != nullptr ? d2r::At<int16_t>(rec, d2r::MisCltDoFunc) : -1, rec != nullptr ? d2r::At<int16_t>(rec, d2r::MisCltHitFunc) : -1,
	    rec != nullptr ? d2r::At<int16_t>(rec, d2r::MisSrvHitFunc) : -1, LevelOf(c->player), m != nullptr ? "created" : "refused");
	return m != nullptr ? true : Fail(c, "missile: createMissile returned no unit");
}

// `missiles [reset]`: live missiles and the distinct ones seen since `missiles reset` (sampled every server frame).
auto CmdMissiles(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	if (t.n >= 2) {
		if (!hcmd::LowerEq(t.tok[1], "reset")) {
			return Fail(c, "usage: missiles [reset]");
		}
		g_missileSeen.Reset();
		InterlockedExchange(&g_trackMissiles, 1);
	}
	PrintMissiles(c);
	return true;
}

// `missilescan`: every missiles.txt row whose client do / client hit / server hit index lands on an empty slot of D2R's
// tables (bug #24b: called through a null pointer). With the stubs in, every count is 0.
auto CmdMissileScan(Ctx* c, const hcmd::Tokens&) noexcept -> bool {
	const uint32_t flag = c->dataFlag;
	const int32_t rows = d2r::api.missileCount(flag);
	const int32_t doBound = *reinterpret_cast<const int32_t*>(g_base + d2r::MissileCltDoBound);
	const int32_t hitBound = *reinterpret_cast<const int32_t*>(g_base + d2r::MissileCltHitBound);
	const int32_t srvBound = *reinterpret_cast<const int32_t*>(g_base + d2r::SrvHitBound);
	const auto* doTable = reinterpret_cast<const uint64_t*>(g_base + d2r::MissileCltDoTable);
	const auto* hitTable = reinterpret_cast<const uint64_t*>(g_base + d2r::MissileCltHitTable);
	const auto* srvTable = reinterpret_cast<const uint64_t*>(g_base + d2r::SrvHitTable);
	int badDo = 0, badHit = 0, badSrv = 0;
	char listDo[300] = "", listHit[200] = "", listSrv[200] = "";
	const auto note = [](char* list, size_t size, int count, int row, const char* kind, int slot) {
		if (count <= 12) {
			const size_t len = std::strlen(list);
			std::snprintf(list + len, size - len, " %d(%s %d)", row, kind, slot);
		}
	};
	for (int32_t row = 0; row < rows; ++row) {
		const uint8_t* r = d2r::api.missileRecord(flag, row);
		if (r == nullptr) {
			continue;
		}
		const int16_t d = d2r::At<int16_t>(r, d2r::MisCltDoFunc), h = d2r::At<int16_t>(r, d2r::MisCltHitFunc), s = d2r::At<int16_t>(r, d2r::MisSrvHitFunc);
		using hcmd::CallsEmptySlot;
		using hcmd::MissileTable;
		if (CallsEmptySlot(MissileTable::CltDo, d, doBound, d >= 0 && d < doBound && doTable[d] == 0)) {
			note(listDo, sizeof(listDo), ++badDo, row, "do", d);
		}
		if (CallsEmptySlot(MissileTable::CltHit, h, hitBound, h >= 0 && h < hitBound && hitTable[h] == 0)) {
			note(listHit, sizeof(listHit), ++badHit, row, "hit", h);
		}
		if (CallsEmptySlot(MissileTable::SrvHit, s, srvBound, s >= 0 && s < srvBound && srvTable[s] == 0)) {
			note(listSrv, sizeof(listSrv), ++badSrv, row, "srvhit", s);
		}
	}
	Out("missilescan: %d rows, client do bound %d, client hit bound %d, server hit bound %d", rows, doBound, hitBound, srvBound);
	Out("missilescan: %d rows call an empty client do slot:%s", badDo, listDo);
	Out("missilescan: %d rows call an empty client hit slot:%s", badHit, listHit);
	Out("missilescan: %d rows call an empty server hit slot:%s", badSrv, listSrv);
	return true;
}

// `cltdo <skill id> [level]` (client side): the skill's client do function (record +0x14a = cltdofunc, table 0x235f7d0) called
// the way the client dispatcher 0x216d20 calls it, for the client copy of the player. rockshock: Rock Shock (28) / ParasiteSkill
// (408) land on CltDoWall (slot 113, `client wall calls` in `state`); cltdo83: the four rows on slot 83.
auto CmdCltDo(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long skill = 0, level = 1;
	const bool orig = t.n > 2 && hcmd::LowerEq(t.tok[t.n - 1], "orig");
	const int args = orig ? t.n - 1 : t.n;
	if (t.n < 2 || !hcmd::ParseInt(t.tok[1], &skill) || skill < 0 || skill > 0xffff || (args > 2 && !hcmd::ParseInt(t.tok[2], &level))) {
		return Fail(c, "usage: cltdo <skill id> [level] [orig]");
	}
	if (g_playerId == 0) {
		return Fail(c, "cltdo: no player seen yet (run a server verb such as state first)");
	}
	Unit* unit = Fn<ClientFindFn>(RvaClientFind)(static_cast<uint32_t>(g_playerId), 0);
	if (unit == nullptr) {
		return Fail(c, "cltdo: no client player unit");
	}
	const uint32_t dataFlag = d2r::api.unitDataFlag(unit);
	const uint8_t* record = d2r::api.getSkillRecord(dataFlag, static_cast<int32_t>(skill));
	if (record == nullptr) {
		return Fail(c, "cltdo: no skills.txt row %lld", skill);
	}
	const int slot = d2r::At<int16_t>(record, d2r::SkCltDoFunc);
	const int missile = d2r::At<int16_t>(record, d2r::SkCltMissileA);
	const int bound = *reinterpret_cast<const volatile int32_t*>(g_base + d2r::CltDoBound);
	if (slot <= 0 || slot >= bound) {
		return Fail(c, "cltdo: skill %lld has no client function (cltdofunc %d, bound %d)", skill, slot, bound);
	}
	// `orig` on slot 30: D2R's own curse function past the cltnomis wrapper (the control of bug #6: it asserts without cltmissilea)
	const uint64_t entry = orig && slot == d2r::CltDoCurseSlot
	                           ? g_base + d2r::RvaCltDoCurse
	                           : *reinterpret_cast<const volatile uint64_t*>(g_base + d2r::CltDoTable + static_cast<uint64_t>(slot) * 8);
	if (entry == 0) {
		return Fail(c, "cltdo: slot %d is empty", slot);
	}
	const long before = ClientWallCalls();
	const int64_t r = reinterpret_cast<int64_t (*)(Unit*, int32_t, int32_t)>(entry)(unit, static_cast<int32_t>(skill), static_cast<int32_t>(level));
	const bool inExe = entry >= g_base && entry - g_base < 0x4000000;
	Out("cltdo skill=%lld cltdofunc=%d cltmissilea=%d entry=%s+0x%llx returned=%lld wall calls +%ld", skill, slot, missile, inExe ? "exe" : "plugin",
	    static_cast<unsigned long long>(inExe ? entry - g_base : 0), static_cast<long long>(r), ClientWallCalls() - before);
	return true;
}

// `cltst <skill id> [orig]` (client side): the skill's client start function (record +0x148 = cltstfunc, table 0x235f590)
// called for the client copy of the player. `orig` on slot 18 calls D2R's own 0x2b0df0 past the cltnomis wrapper: without a
// cltmissilec it asserts (bug #6 control); the table entry returns 1 without an assert.
auto CmdCltSt(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long skill = 0;
	if (t.n < 2 || !hcmd::ParseInt(t.tok[1], &skill) || skill < 0 || skill > 0xffff) {
		return Fail(c, "usage: cltst <skill id> [orig]");
	}
	if (g_playerId == 0) {
		return Fail(c, "cltst: no player seen yet (run a server verb such as state first)");
	}
	Unit* unit = Fn<ClientFindFn>(RvaClientFind)(static_cast<uint32_t>(g_playerId), 0);
	if (unit == nullptr) {
		return Fail(c, "cltst: no client player unit");
	}
	const uint8_t* record = d2r::api.getSkillRecord(d2r::api.unitDataFlag(unit), static_cast<int32_t>(skill));
	if (record == nullptr) {
		return Fail(c, "cltst: no skills.txt row %lld", skill);
	}
	const int slot = d2r::At<int16_t>(record, d2r::SkCltStFunc);
	const int missile = d2r::At<int16_t>(record, d2r::SkCltMissileC);
	const int bound = *reinterpret_cast<const volatile int32_t*>(g_base + d2r::CltStBound);
	if (slot <= 0 || slot >= bound) {
		return Fail(c, "cltst: skill %lld has no client start function (cltstfunc %d, bound %d)", skill, slot, bound);
	}
	const bool wantOrig = t.n > 2 && hcmd::LowerEq(t.tok[2], "orig");
	const bool orig = wantOrig && (slot == d2r::CltStMissileCSlot || slot == d2r::CltStMissileC19Slot);  // 18, 19 (bug #60)
	const uint64_t entry = orig ? g_base + (slot == d2r::CltStMissileC19Slot ? d2r::RvaCltStMissileC19 : d2r::RvaCltStMissileC)
	                            : *reinterpret_cast<const volatile uint64_t*>(g_base + d2r::CltStTable + static_cast<uint64_t>(slot) * 8);
	if (entry == 0) {
		return Fail(c, "cltst: slot %d is empty", slot);
	}
	const int64_t r = reinterpret_cast<int64_t (*)(Unit*, int32_t, int32_t)>(entry)(unit, static_cast<int32_t>(skill), 1);
	const bool inExe = entry >= g_base && entry - g_base < 0x4000000;
	Out("cltst skill=%lld cltstfunc=%d cltmissilec=%d %s entry=%s+0x%llx returned=%lld", skill, slot, missile, orig ? "orig" : "table",
	    inExe ? "exe" : "plugin", static_cast<unsigned long long>(inExe ? entry - g_base : 0), static_cast<long long>(r));
	return true;
}

// `slot <table> [index]` (client side): what a function table holds (the static step of docs/plugin-plan.md section 4 names
// the D2R function at each slot by its RVA). Tables: cltdo (skill client do), srvdo (skill server do), mcltdo (missile client
// do), mclthit (missile client hit), srvhit (missile server hit). Without an index: the bound and the empty slots.
auto CmdSlot(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	hcmd::SlotTable table;
	long long index = -1;
	if (t.n < 2 || !hcmd::ParseSlotTable(t.tok[1], &table) || (t.n > 2 && (!hcmd::ParseInt(t.tok[2], &index) || index < 0))) {
		return Fail(c, "usage: slot cltdo|srvdo|mcltdo|mclthit|srvhit [index]");
	}
	const int32_t bound = table.boundRva != 0 ? *reinterpret_cast<const volatile int32_t*>(g_base + table.boundRva) : table.fixedBound;
	const auto* entries = reinterpret_cast<const volatile uint64_t*>(g_base + table.tableRva);
	if (index >= 0) {
		if (index >= bound) {
			return Fail(c, "slot: %lld is not below the bound %d", index, bound);
		}
		const uint64_t e = entries[index];
		const bool inExe = e >= g_base && e - g_base < 0x4000000;
		Out("slot %s %lld: %s+0x%llx (bound %d)", table.name, index, e == 0 ? "empty" : (inExe ? "exe" : "plugin"),
		    static_cast<unsigned long long>(inExe ? e - g_base : 0), bound);
		return true;
	}
	char empty[300] = "";
	int n = 0;
	for (int32_t i = 0; i < bound; ++i) {
		if (entries[i] == 0) {
			++n;
			const size_t len = std::strlen(empty);
			std::snprintf(empty + len, sizeof(empty) - len, " %d", i);
		}
	}
	Out("slot %s: bound %d, %d empty:%s", table.name, bound, n, empty);
	return true;
}

// `watch cltdo|srvhit <index>` | `watch` | `watch off`: counts the calls of one function-table slot while the game runs it the
// normal way (a real cast, a real hit), e.g. cltdo 83 and srvhit 23 (lane triage): the slot's entry becomes a thunk that
// counts, keeps the last second argument (cltdo: the skill id; srvhit: the missile's class) and calls the entry it replaced.
// One slot at a time; `watch off` puts the old entry back. Both writes go through PatchWriteU64 with the expected old value.
using WatchFn = uint64_t (*)(uint64_t, uint64_t, uint64_t);
WatchFn g_watchOriginal = nullptr;
uint64_t g_watchAt = 0;  // RVA of the wrapped table entry, 0 = none
bool g_watchSrvHit = false;
char g_watchName[24] = "";
volatile LONG g_watchCalls = 0;
volatile LONG g_watchNonZero = 0;
volatile LONG g_watchLast = -1;

auto WatchThunk(uint64_t a, uint64_t b, uint64_t c) noexcept -> uint64_t {
	InterlockedIncrement(&g_watchCalls);
	LONG last = static_cast<LONG>(b);
	if (g_watchSrvHit) {
		last = -1;
		__try {
			last = b != 0 ? d2r::At<int32_t>(reinterpret_cast<const void*>(b), d2r::UnitClass) : -1;
		} __except (EXCEPTION_EXECUTE_HANDLER) {
		}
	}
	InterlockedExchange(&g_watchLast, last);
	const uint64_t r = g_watchOriginal(a, b, c);
	if (r != 0) {
		InterlockedIncrement(&g_watchNonZero);
	}
	return r;
}

auto WatchRelease() noexcept -> bool {
	if (g_watchAt == 0) {
		return true;
	}
	const uint64_t mine = reinterpret_cast<uint64_t>(&WatchThunk);
	if (g_context == nullptr || !g_context->PatchWriteU64(g_watchAt, &mine, sizeof(mine), reinterpret_cast<uint64_t>(g_watchOriginal))) {
		return false;
	}
	g_watchAt = 0;
	return true;
}

auto CmdWatch(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	if (t.n == 1 || (t.n == 2 && hcmd::LowerEq(t.tok[1], "off"))) {
		Out("watch %s: calls=%ld nonzero=%ld last=%ld", g_watchAt != 0 ? g_watchName : "(none)", static_cast<long>(g_watchCalls),
		    static_cast<long>(g_watchNonZero), static_cast<long>(g_watchLast));
		if (t.n == 2 && !WatchRelease()) {
			return Fail(c, "watch off: the entry is no longer ours, left as it is");
		}
		return true;
	}
	hcmd::SlotTable table;
	long long index = -1;
	if (t.n != 3 || !hcmd::ParseSlotTable(t.tok[1], &table) || !hcmd::WatchableTable(table) || !hcmd::ParseInt(t.tok[2], &index) || index < 0) {
		return Fail(c, "usage: watch cltdo|srvhit <index> | watch | watch off");
	}
	const int32_t bound = *reinterpret_cast<const volatile int32_t*>(g_base + table.boundRva);
	if (index >= bound) {
		return Fail(c, "watch: %lld is not below the bound %d", index, bound);
	}
	if (!WatchRelease()) {
		return Fail(c, "watch: the previous slot could not be put back");
	}
	const uint64_t at = table.tableRva + static_cast<uint64_t>(index) * 8;
	const uint64_t have = *reinterpret_cast<const volatile uint64_t*>(g_base + at);
	if (have == 0) {
		return Fail(c, "watch: slot %s %lld is empty", table.name, index);
	}
	g_watchOriginal = reinterpret_cast<WatchFn>(have);
	g_watchSrvHit = hcmd::LowerEq(table.name, "srvhit");
	InterlockedExchange(&g_watchCalls, 0);
	InterlockedExchange(&g_watchNonZero, 0);
	InterlockedExchange(&g_watchLast, -1);
	if (g_context == nullptr || !g_context->PatchWriteU64(at, &have, sizeof(have), reinterpret_cast<uint64_t>(&WatchThunk))) {
		return Fail(c, "watch: the table write failed");
	}
	g_watchAt = at;
	std::snprintf(g_watchName, sizeof(g_watchName), "%s %lld", table.name, index);
	const bool inExe = have >= g_base && have - g_base < 0x4000000;
	Out("watch %s on (entry %s+0x%llx)", g_watchName, inExe ? "exe" : "plugin", static_cast<unsigned long long>(inExe ? have - g_base : 0));
	return true;
}

// The player's waypoint record of the game's difficulty (playerData + 0x58 + difficulty * 8).
auto WaypointRecord(Ctx* c) noexcept -> uint8_t* {
	uint8_t* data = Fn<PlayerDataFn>(RvaPlayerData)(c->player);
	return data != nullptr ? d2r::At<uint8_t*>(data, 0x58 + static_cast<int>(d2r::At<uint8_t>(c->game, GameDifficulty)) * 8) : nullptr;
}

// `waypoint n <number> [get|set|clear]` | `waypoint open`: a waypoint bit by its levels.txt number (pandewp: number 17 is shared
// by Valley of the Kings and Pandemonium 2), and the panel (packet 0x63, as when a waypoint is clicked).
auto CmdWaypoint(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	const char* usage = "usage: waypoint n <number> [get|set|clear] | waypoint open";
	uint8_t* rec = WaypointRecord(c);
	if (rec == nullptr) {
		return Fail(c, "no waypoint record");
	}
	if (t.n >= 2 && hcmd::LowerEq(t.tok[1], "open")) {
		void* client = Fn<UnitClientFn>(RvaUnitClientOf)(c->player);
		if (client == nullptr) {
			return Fail(c, "waypoint: no client for the player");
		}
		Fn<WaypointSendFn>(RvaWaypointSend)(client, rec);
		Out("waypoint record sent to the client (the panel opens) in area %d", LevelOf(c->player));
		return true;
	}
	long long n = 0;
	if (t.n < 3 || !hcmd::LowerEq(t.tok[1], "n") || !hcmd::ParseInt(t.tok[2], &n) || n < 0 || n >= WaypointNumbers) {
		return Fail(c, usage);
	}
	const int number = static_cast<int>(n);
	if (t.n > 3) {
		if (hcmd::LowerEq(t.tok[3], "set")) {
			Fn<WaypointFn>(RvaWaypointSet)(rec, number);
		} else if (hcmd::LowerEq(t.tok[3], "clear")) {
			const auto* bits = reinterpret_cast<const uint16_t*>(g_base + RvaWaypointBits);
			*reinterpret_cast<uint16_t*>(rec + 2 * bits[2 * number]) &= static_cast<uint16_t>(~bits[2 * number + 1]);
		} else if (!hcmd::LowerEq(t.tok[3], "get")) {
			return Fail(c, usage);
		}
	}
	Out("waypoint number %d = %d (area %d)", number, Fn<WaypointFn>(RvaWaypointTest)(rec, number) != 0 ? 1 : 0, LevelOf(c->player));
	return true;
}

auto CmdObjects(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long cls = -1;
	if (t.n > 1 && !hcmd::ParseInt(t.tok[1], &cls)) {
		return Fail(c, "usage: objects [class]");
	}
	int n = 0;
	EachUnit(c->game, HashObjects, [&](Unit* u) {
		if (TypeOf(u) != 2 || (cls >= 0 && ClassOf(u) != cls) || n >= 150) {
			return;
		}
		++n;
		int32_t ox = 0, oy = 0;
		d2r::UnitXY(u, &ox, &oy);
		Out("object id=%u class=%d mode=%d dist=%.0f at %d,%d", IdOf(u), ClassOf(u), ModeOf(u), DistTo(c->player, u), ox, oy);
	});
	Out("objects %d", n);
	return true;
}

// `object <class> [dx dy]`: an object unit of the class next to the player (default 3 tiles east), made by D2R's unit creator.
auto CmdObject(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long cls = 0, dx = 3, dy = 0;
	if (t.n < 2 || !hcmd::ParseInt(t.tok[1], &cls) || cls < 0 || cls > 0xffff || (t.n > 2 && !hcmd::ParseInt(t.tok[2], &dx)) ||
	    (t.n > 3 && !hcmd::ParseInt(t.tok[3], &dy))) {
		return Fail(c, "usage: object <objects.txt class> [dx dy]");
	}
	int32_t px = 0, py = 0;
	if (!d2r::UnitXY(c->player, &px, &py)) {
		return Fail(c, "object: player has no position");
	}
	void* room = Fn<UnitRoomFn>(RvaUnitRoom)(c->player);
	const int32_t x = px + static_cast<int32_t>(dx), y = py + static_cast<int32_t>(dy);
	void* at = room != nullptr ? Fn<InRoomFn>(RvaInRoom)(room, x, y) : nullptr;
	if (at == nullptr) {
		return Fail(c, "object: no room at %d,%d", x, y);
	}
	Unit* u = Fn<Unit* (*)(int32_t, int32_t, int32_t, int32_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t)>(RvaCreateUnit)(
		2, static_cast<int32_t>(cls), x, y, reinterpret_cast<uint64_t>(c->game), reinterpret_cast<uint64_t>(at), 1, 1, 0, 0);
	if (u == nullptr) {
		return Fail(c, "object: the creator returned no unit");
	}
	Out("object created: id=%u class=%d mode=%d at %d,%d", IdOf(u), ClassOf(u), ModeOf(u), x, y);
	return true;
}

// `operate <object id> <function>`: the object operate function (objects.txt OperateFn) with the click context
// {game, object, player, 0, class}. pandewp operates the Pandemonium 2 waypoint with it.
auto CmdOperate(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long id = 0, fn = 0;
	if (t.n < 3 || !hcmd::ParseInt(t.tok[1], &id) || !hcmd::ParseInt(t.tok[2], &fn) || fn < 0 || fn > 120) {
		return Fail(c, "usage: operate <object id> <operate function>");
	}
	Unit* obj = FindObjectById(c, static_cast<uint32_t>(id));
	if (obj == nullptr) {
		return Fail(c, "operate: no such object");
	}
	const uint64_t entry = *reinterpret_cast<const uint64_t*>(g_base + RvaOperateTable + 8 * static_cast<uint64_t>(fn));
	if (entry == 0) {
		return Fail(c, "operate: function %lld has no entry", fn);
	}
	int64_t ctx[8] = {reinterpret_cast<int64_t>(c->game), reinterpret_cast<int64_t>(obj), reinterpret_cast<int64_t>(c->player), 0, ClassOf(obj), 0, 0, 0};
	const int64_t rc = reinterpret_cast<int64_t (*)(int64_t*)>(entry)(ctx);
	Out("operate object id=%u class=%d with function %lld (exe+%llx): result %lld, object mode now %d", IdOf(obj), ClassOf(obj), fn,
	    static_cast<unsigned long long>(entry - g_base), static_cast<long long>(rc), ModeOf(obj));
	return true;
}

// `objmode <object id> <mode>`: the game's set-mode call on an object.
auto CmdObjMode(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long id = 0, mode = 0;
	if (t.n < 3 || !hcmd::ParseInt(t.tok[1], &id) || !hcmd::ParseInt(t.tok[2], &mode) || mode < 0 || mode > 20) {
		return Fail(c, "usage: objmode <object id> <mode>");
	}
	Unit* obj = FindObjectById(c, static_cast<uint32_t>(id));
	if (obj == nullptr) {
		return Fail(c, "objmode: no such object");
	}
	const int64_t rc = Fn<int64_t (*)(Unit*, int32_t)>(RvaSetMode)(obj, static_cast<int32_t>(mode));
	Out("objmode object id=%u class=%d: set-mode returned %lld, mode now %d", IdOf(obj), ClassOf(obj), static_cast<long long>(rc), ModeOf(obj));
	return true;
}

// `enter nearest | <portal object id>`: the portal object's use handler (town portal, red portals: pandewp reaches
// Pandemonium through them when `level` cannot).
auto CmdEnter(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long id = -1;
	if (t.n < 2 || (!hcmd::LowerEq(t.tok[1], "nearest") && !hcmd::ParseInt(t.tok[1], &id))) {
		return Fail(c, "usage: enter nearest | enter <portal object id>");
	}
	Unit* portal = nullptr;
	double best = 1e18;
	EachUnit(c->game, HashObjects, [&](Unit* u) {
		const int32_t cls = ClassOf(u);
		const bool match = id >= 0 ? IdOf(u) == static_cast<uint32_t>(id) : (cls == 59 || cls == 60 || cls == 600);
		if (TypeOf(u) == 2 && match && DistTo(c->player, u) < best) {
			best = DistTo(c->player, u);
			portal = u;
		}
	});
	if (portal == nullptr) {
		return Fail(c, "enter: no such portal object");
	}
	// id, class and destination are read before the use: after the move the portal's room can be freed with the level the
	// player left (reading it then printed id=4294967295 class=1, raised `ptUnit->eType == UNIT_OBJECT` and could end the game)
	const uint32_t pid = IdOf(portal);
	const int32_t pcls = ClassOf(portal);
	const int pdest = static_cast<int>(Fn<uint16_t (*)(Unit*)>(RvaPortalLevel)(portal));
	int64_t ctx[8] = {reinterpret_cast<int64_t>(c->game), reinterpret_cast<int64_t>(portal), reinterpret_cast<int64_t>(c->player), 0, pcls, 0, 0, 0};
	const int64_t moved = Fn<int64_t (*)(int64_t*)>(RvaPortalUse)(ctx);
	Out("enter portal id=%u class=%d dest=%d: %s", pid, pcls, pdest, moved != 0 ? "moved" : "refused / failed");
	return moved != 0 ? true : Fail(c, "enter: the portal handler refused");
}

// `dump mon <class> [offset]`: 0x40 bytes of the monstats record from the offset (default 0; srvhit6spawn: is the spawned class
// the remapped row? lane integ: the compiled skill modes at +0x1d4).
auto CmdDump(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long cls = 0;
	long long from = 0;
	if (t.n < 3 || !hcmd::LowerEq(t.tok[1], "mon") || !hcmd::ParseInt(t.tok[2], &cls) ||
	    (t.n > 3 && (!hcmd::ParseInt(t.tok[3], &from) || from < 0 || from > 0x400))) {
		return Fail(c, "usage: dump mon <class> [offset 0-0x400]");
	}
	const auto* rec = Fn<const uint8_t* (*)(uint32_t, int32_t)>(RvaMonStats)(c->dataFlag, static_cast<int32_t>(cls));
	if (rec == nullptr) {
		return Fail(c, "dump mon: no monstats row %lld", cls);
	}
	for (int off = static_cast<int>(from); off < from + 0x40; off += 32) {
		char hex[32 * 3 + 1] = "";
		for (int i = 0; i < 32; ++i) {
			std::snprintf(hex + i * 3, 4, "%02x ", rec[off + i]);
		}
		Out("monstats %lld +%02x: %s", cls, off, hex);
	}
	return true;
}

// --- items (lane monitems): `item`, `identify`, `items` -------------------------------------------------------------------
// MakeItem (a port of 0x517530 with the page chosen) and its generator hook
// (quests_act1.cpp ItemGenHook: the block's "index asked for" picks a set / unique row). Same image.
constexpr uint64_t RvaInventory = 0x34a360;     // (unit, file, line) -> inventory
constexpr uint64_t RvaInvFirst = 0x388c10;      // (inventory) -> first item
constexpr uint64_t RvaInvNext = 0x38aba0;       // (item) -> next item
constexpr uint64_t RvaItemByCode = 0x314070;    // (dataFlag, code, &class id) -> items record
constexpr uint64_t RvaItemRecord = 0x314110;    // (dataFlag, class id) -> items record (+0x80 code)
constexpr uint64_t RvaDefaultIlvl = 0x43e8a0;   // (player, 0)
constexpr uint64_t RvaMakeItem = 0x43d530;      // (player, class, game, 4, quality, 0, 1, ilvl, 0, 0, 0) -> item
constexpr uint64_t RvaMaxDurability = 0x2f4b60; // (item) -> maximum durability
constexpr uint64_t RvaSetStatItem = 0x2f7940;   // (item, stat, value, layer)
constexpr uint64_t RvaItemStatList = 0x3d5230;  // (owner, item, state, flags) -> the item's stat list of those flags, made if missing
constexpr uint64_t RvaStatListAdd = 0x2f3330;   // (dataFlag, list, stat, value, layer)
constexpr uint64_t RvaLocInit = 0x382e10;       // (loc*, page, packed xy)
constexpr uint64_t RvaInvRecord = 0x34a410;     // (player, page kind, expansion)
constexpr uint64_t RvaFindSpot = 0x3865b0;      // (inventory, item, record, &x, &y, page) -> found
constexpr uint64_t RvaPlace = 0x471500;         // (player, loc*, ids*, count, 0)
constexpr uint64_t RvaSendItem = 0x535f60;      // (game, player, item, 1, kind, mode/page, ...): the item update packet (kind: hcmd::PlaceCmdKind)
constexpr uint64_t RvaAfterCreate = 0x46e8c0;   // (game, player, item, 0): MakeItem's step after the send
constexpr uint64_t RvaAfterPlace = 0x3e2b61c;   // (item, player) -> non-zero: re-check equipment
constexpr uint64_t RvaRecheck = 0x470c90;       // (game, player, 0, 0)
constexpr uint64_t RvaBodyLoc = 0x382df0;       // (int32 loc[4], body location 1-12): `equip`
constexpr uint64_t RvaInvChange = 0x472590;     // (player, adds, removes, addIds, removeIds, nAdds, nRemoves, 0): RemoveItem
constexpr uint64_t RvaSetByte5c = 0x36dea0;
constexpr uint64_t RvaItemFlag = 0x36d8f0;      // (item, mask, on): SetItemFlag
constexpr uint64_t RvaGround1 = 0x36de20, RvaGround2 = 0x36d730, RvaGround3 = 0x34e5f0, RvaGround4 = 0x34e210, RvaGround5 = 0x34e280;
constexpr uint64_t RvaUnitXYPair = 0x34a040;    // (unit, int32 xy[2])
constexpr uint64_t RvaGroundSpot = 0x43de10;    // (game, room, xy, &out, 1)
constexpr uint64_t RvaGroundDrop = 0x43dd00;    // (game, player, item, room, x, y)
constexpr uint64_t RvaFreeItem = 0x43ec10;      // (game, item)
constexpr uint64_t RvaItemData = 0x34a500;      // (item) -> item data: +0 quality, +0x18 flags, +0x34 set / unique index
constexpr uint64_t RvaItemLevel = 0x36ccf0;     // (item) -> item level
constexpr uint64_t RvaItemLocation = 0x382d20;  // (int32 location[4], item): unit id, page, packed x / y
constexpr uint64_t RvaItemPage = 0x36cfe0;      // (item) -> page byte (item data +0x55: 0 backpack, 3 cube, 4 stash)
constexpr uint64_t RvaItemByte54 = 0x36ca10;    // (item) -> item data +0x54
constexpr uint64_t RvaUnitPosition = 0x34a110;  // (unit) -> packed position
constexpr uint64_t RvaStatsChanged = 0x34dbe0;  // (unit, 1)
constexpr uint64_t RvaItemGen = 0x43cd50;       // (game, block*, int): item generator core
// 0x43cd50: push rbp / push rbx / push rsi / push r12 / push r15 / lea rbp,[rsp-0x37] / sub rsp,0x90
constexpr uint8_t ItemGenEntry[] = {0x40, 0x55, 0x53, 0x56, 0x41, 0x54, 0x41, 0x57, 0x48, 0x8d, 0x6c, 0x24, 0xc9,
                                    0x48, 0x81, 0xec, 0x90, 0x00, 0x00, 0x00};
constexpr int GenQuality = 0x40, GenFixed = 0x3c, GenIndex = 0x50;  // generator block: quality, "fixed" path, index asked for + 1
constexpr int32_t MagicStatListFlag = 0x40;    // the item's magic property list (the one the save writes)
constexpr int ItemDataFlags = 0x18, ItemDataIndex = 0x34;
constexpr int StatDurability = 0x48;

using InventoryFn = void* (*)(Unit*, const char*, int32_t);
using InvFirstFn = Unit* (*)(void*);
using InvNextFn = Unit* (*)(Unit*);
using ItemByCodeFn = const uint8_t* (*)(uint32_t, uint32_t, int32_t*);
using ItemRecordFn = const uint8_t* (*)(uint32_t, int32_t);
using DefaultIlvlFn = int32_t (*)(Unit*, int32_t);
using MakeItemFn = Unit* (*)(Unit*, int32_t, Game*, int32_t, int64_t, int32_t, int32_t, int32_t, int32_t, int32_t, int32_t);
using ItemStatFn = int32_t (*)(Unit*);
using SetItemStatFn = void (*)(Unit*, int32_t, int32_t, int32_t);
using ItemStatListFn = void* (*)(Unit*, Unit*, int32_t, int32_t);
using StatListAddFn = void (*)(uint32_t, void*, int32_t, int32_t, int32_t);
using LocInitFn = int32_t* (*)(int32_t*, int32_t, int32_t);
using InvRecordFn = int32_t (*)(Unit*, int32_t, int32_t);
using FindSpotFn = int32_t (*)(void*, Unit*, int32_t, uint16_t*, uint16_t*, int64_t);
using PlaceFn = uint8_t (*)(Unit*, int32_t*, uint32_t*, uint64_t, int64_t);
using SendItemFn = void (*)(Game*, Unit*, Unit*, int32_t, int32_t, int32_t, int32_t, int32_t, int32_t);
using AfterCreateFn = void (*)(Game*, Unit*, Unit*, int32_t);
using AfterPlaceFn = int32_t (*)(Unit*, Unit*);
using RecheckFn = void (*)(Game*, Unit*, int32_t, int32_t);
using BodyLocFn = int32_t* (*)(int32_t*, int32_t);
using InvChangeFn = uint8_t (*)(Unit*, int32_t*, int32_t*, uint32_t*, uint32_t*, uint64_t, uint64_t, uint8_t);
using ItemFlagFn = void (*)(Unit*, int32_t, int32_t);
using ByteSetFn = void (*)(Unit*, int32_t);
using UnitXYPairFn = void (*)(Unit*, int32_t*);
using GroundSpotFn = void* (*)(Game*, void*, int32_t*, int32_t*, int32_t);
using GroundDropFn = void (*)(Game*, Unit*, Unit*, void*, int32_t, int32_t);
using FreeItemFn = void (*)(Game*, Unit*);
using ItemDataFn = uint8_t* (*)(Unit*);
using ItemLevelFn = uint32_t (*)(Unit*);
using ItemLocationFn = int32_t* (*)(int32_t*, Unit*);
using ItemByteFn = uint8_t (*)(Unit*);
using UnitPositionFn = int32_t (*)(Unit*);
using StatsChangedFn = void (*)(Unit*, int32_t);
using ItemGenFn = uint64_t (*)(Game*, uint8_t*, int32_t);

ItemGenFn g_itemGenOriginal = nullptr;
bool g_itemGenHooked = false;
thread_local int32_t g_wantIndex = 0;    // row + 1 for the next generator call on this thread (the game thread)
thread_local int32_t g_wantQuality = 0;  // the quality that row belongs to (5 set, 7 unique)

uint64_t ItemGenHook(Game* game, uint8_t* block, int32_t flag) {
	if (g_wantIndex != 0 && block != nullptr) {
		if (d2r::At<int32_t>(block, GenQuality) == g_wantQuality && d2r::At<int32_t>(block, GenFixed) == 0) {
			*reinterpret_cast<int32_t*>(block + GenIndex) = g_wantIndex;
		}
		g_wantIndex = 0;
	}
	return g_itemGenOriginal(game, block, flag);
}

template <typename F>
void EachItemOf(Unit* owner, F f) noexcept {
	void* inv = Fn<InventoryFn>(RvaInventory)(owner, "harness", 0);
	int guard = 0;
	for (Unit* item = inv != nullptr ? Fn<InvFirstFn>(RvaInvFirst)(inv) : nullptr; item != nullptr && guard++ < 2000;) {
		Unit* next = Fn<InvNextFn>(RvaInvNext)(item);
		if (TypeOf(item) == 4) {
			f(item);
		}
		item = next;
	}
}

auto ItemFlags(Unit* item) noexcept -> uint32_t {
	const uint8_t* data = Fn<ItemDataFn>(RvaItemData)(item);
	return data != nullptr ? d2r::At<uint32_t>(data, ItemDataFlags) : 0U;
}

void DescribeItem(Ctx* c, Unit* item) noexcept {
	const uint8_t* rec = Fn<ItemRecordFn>(RvaItemRecord)(c->dataFlag, ClassOf(item));
	char code[5];
	hcmd::DwordToCode(rec != nullptr ? d2r::At<uint32_t>(rec, 0x80) : 0x3f3f3f3fU, code);
	const uint8_t* data = Fn<ItemDataFn>(RvaItemData)(item);
	const uint32_t flags = ItemFlags(item);
	int32_t loc[8] = {};
	Fn<ItemLocationFn>(RvaItemLocation)(loc, item);
	Out("item id=%u code=%s class=%d page=%d x=%d y=%d quality=%d index=%d identified=%d ilvl=%d sockets=%d flags=0x%x body=%d", IdOf(item), code,
	    ClassOf(item), static_cast<int>(Fn<ItemByteFn>(RvaItemPage)(item)), loc[2] & 0xffff, (loc[2] >> 16) & 0xffff,
	    data != nullptr ? d2r::At<int32_t>(data, 0) : -1,
	    data != nullptr ? d2r::At<int32_t>(data, ItemDataIndex) : -1, (flags & hcmd::ItemFlagIdentified) != 0 ? 1 : 0,
	    static_cast<int>(Fn<ItemLevelFn>(RvaItemLevel)(item)), Stat(item, 194), flags, loc[0] == 1 ? loc[3] : 0);
}

// MakeItem: the generator (with the set / unique row asked for), the stats on the item's magic list, then the backpack
// / cube (find a spot, place, send), the ground next to the player or, with a body location (`equip`), that body location.
auto MakeItem(Ctx* c, uint32_t code, const hcmd::ItemSpec& s) noexcept -> Unit* {
	int32_t classId = 0;
	if (Fn<ItemByCodeFn>(RvaItemByCode)(c->dataFlag, code, &classId) == nullptr) {
		Fail(c, "item: unknown code");
		return nullptr;
	}
	const int ilvl = s.ilvl != 0 ? s.ilvl : Fn<DefaultIlvlFn>(RvaDefaultIlvl)(c->player, 0);
	if (s.row >= 0 && s.quality == 7 && s.row < hcmd::UniqueSpawnedLimit) {  // "already dropped in this game" would refuse it
		*reinterpret_cast<uint32_t*>(reinterpret_cast<uint8_t*>(c->game) + hcmd::UniqueSpawnedOffset(s.row)) &= ~hcmd::UniqueSpawnedMask(s.row);
	}
	g_wantIndex = hcmd::GenIndexFor(s.quality, s.row);
	g_wantQuality = s.quality;
	Unit* item = Fn<MakeItemFn>(RvaMakeItem)(c->player, classId, c->game, 4, s.quality, 0, 1, ilvl, 0, 0, 0);
	g_wantIndex = 0;
	if (item == nullptr) {
		Fail(c, "item: creation failed");
		return nullptr;
	}
	if (const int32_t dur = Fn<ItemStatFn>(RvaMaxDurability)(item); dur != 0) {
		Fn<SetItemStatFn>(RvaSetStatItem)(item, StatDurability, dur, 0);
	}
	void* magic = s.nstats > 0 ? Fn<ItemStatListFn>(RvaItemStatList)(nullptr, item, 0, MagicStatListFlag) : nullptr;
	for (int i = 0; i < s.nstats; ++i) {
		if (magic != nullptr) {  // as a difference, so that the value is the item's total
			const int32_t delta = static_cast<int32_t>(s.values[i]) - Stat(item, s.stats[i][0], s.stats[i][1]);
			Fn<StatListAddFn>(RvaStatListAdd)(c->dataFlag, magic, s.stats[i][0], delta, s.stats[i][1]);
		} else {
			Fn<SetItemStatFn>(RvaSetStatItem)(item, s.stats[i][0], static_cast<int32_t>(s.values[i]), s.stats[i][1]);
		}
		if (s.stats[i][0] == hcmd::StatSockets && s.values[i] > 0) {  // sockets need the socketed flag as well
			Fn<ItemFlagFn>(RvaItemFlag)(item, static_cast<int32_t>(hcmd::ItemFlagSocketed), 1);
		}
	}
	if (s.unid) {
		Fn<ItemFlagFn>(RvaItemFlag)(item, static_cast<int32_t>(hcmd::ItemFlagIdentified), 0);
	}
	if (s.page < 0) {  // on the ground next to the player
		Fn<ItemFlagFn>(RvaItemFlag)(item, 0x4000, 0);
		Fn<ByteSetFn>(RvaGround1)(item, 0xff);
		Fn<ByteSetFn>(RvaGround2)(item, 0);
		Fn<ByteSetFn>(RvaGround3)(item, 3);
		Fn<ByteSetFn>(RvaGround4)(item, 0);
		Fn<ByteSetFn>(RvaGround5)(item, 0);
		int32_t xy[2] = {};
		Fn<UnitXYPairFn>(RvaUnitXYPair)(c->player, xy);
		int32_t out[2] = {};
		void* spot = Fn<GroundSpotFn>(RvaGroundSpot)(c->game, Fn<UnitRoomFn>(RvaUnitRoom)(c->player), xy, out, 1);
		if (spot == nullptr) {
			Fn<FreeItemFn>(RvaFreeItem)(c->game, item);
			Fail(c, "item: no free ground spot");
			return nullptr;
		}
		Fn<GroundDropFn>(RvaGroundDrop)(c->game, c->player, item, spot, out[0], out[1]);
		return item;
	}
	int32_t loc[4] = {};
	if (s.bodyLoc > 0) {  // Place with a body location, as the equip packet 0x1a's move does
		Fn<BodyLocFn>(RvaBodyLoc)(loc, s.bodyLoc);
	} else {
		void* inv = Fn<InventoryFn>(RvaInventory)(c->player, "harness", 0);
		const int32_t record = Fn<InvRecordFn>(RvaInvRecord)(c->player, s.page == 3 ? 3 : 0, d2r::At<uint8_t>(c->game, 0x106) != 1);
		uint16_t x = 0, y = 0;
		if (inv == nullptr || Fn<FindSpotFn>(RvaFindSpot)(inv, item, record, &x, &y, s.page) == 0) {
			Fn<FreeItemFn>(RvaFreeItem)(c->game, item);
			Fail(c, "item: no room in %s", s.page == 3 ? "the cube" : "the inventory");
			return nullptr;
		}
		Fn<LocInitFn>(RvaLocInit)(loc, s.page, static_cast<int32_t>((static_cast<uint32_t>(y) << 16) | x));
	}
	uint32_t itemId = IdOf(item);
	if ((s.bodyLoc <= 0 && loc[0] != 0) || Fn<PlaceFn>(RvaPlace)(c->player, loc, &itemId, 1, 0) == 0) {
		Fn<FreeItemFn>(RvaFreeItem)(c->game, item);
		if (s.bodyLoc > 0) {
			Fail(c, "equip: the item does not fit body location %d or it is occupied (unequip first)", s.bodyLoc);
		} else {
			Fail(c, "item: placing failed");
		}
		return nullptr;
	}
	if (s.bodyLoc > 0) {  // as D2R's own equip (packet 0x1a, 0x4aa682) does before its send
		Fn<ItemFlagFn>(RvaItemFlag)(item, static_cast<int32_t>(hcmd::ItemFlagEquipClear), 0);
	}
	Fn<SendItemFn>(RvaSendItem)(c->game, c->player, item, 1, hcmd::PlaceCmdKind(s.bodyLoc), loc[0], loc[1], loc[3], loc[2]);
	if (!s.unid) {
		Fn<AfterCreateFn>(RvaAfterCreate)(c->game, c->player, item, 0);
	}
	if (Fn<AfterPlaceFn>(RvaAfterPlace)(item, c->player) != 0) {
		Fn<RecheckFn>(RvaRecheck)(c->game, c->player, 0, 0);
	}
	if (s.bodyLoc > 0) {
		Fn<StatsChangedFn>(RvaStatsChanged)(c->player, 1);
	}
	return item;
}

// `item <code> [normal|magic|rare|set|unique|... [row]] [q=n] [uniq=row] [set=row] [ilvl=n] [inv|cube|ground] [stat=value ...]`
auto CmdItem(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	hcmd::ItemSpec s;
	if (t.n < 2) {
		return Fail(c, "usage: item <code> [low|normal|superior|magic|set|rare|unique|crafted [row]] [q=n] [uniq=row] [set=row] [ilvl=n] "
		               "[inv|cube|ground] [unid] [stat=value ...]");
	}
	if (!hcmd::ParseItemSpec(t, 2, &s)) {
		return Fail(c, "%s: cannot read '%.40s'", c->verb, s.bad >= 0 && s.bad < t.n ? t.tok[s.bad] : "?");
	}
	const bool equip = std::strcmp(c->verb, "equip") == 0;
	if (equip != (s.bodyLoc != 0)) {
		return Fail(c, equip ? "equip: name the body location (rhand, lhand, body, head, amulet, rring, lring, belt, boots, gloves)"
		                     : "item: a body location needs the equip verb");
	}
	if (s.row >= 0 && !g_itemGenHooked) {
		return Fail(c, "item: a set / unique row needs the generator hook 0x43cd50 (off, see the log)");
	}
	Unit* item = MakeItem(c, hcmd::CodeToDword(t.tok[1]), s);
	if (item == nullptr) {
		return false;
	}
	DescribeItem(c, item);
	for (int i = 0; i < s.nstats; ++i) {
		Out("  stat %d:%d = %d", s.stats[i][0], s.stats[i][1], Stat(item, s.stats[i][0], s.stats[i][1]));
	}
	const uint8_t* data = Fn<ItemDataFn>(RvaItemData)(item);
	const int32_t gotQuality = data != nullptr ? d2r::At<int32_t>(data, 0) : -1, gotIndex = data != nullptr ? d2r::At<int32_t>(data, ItemDataIndex) : -1;
	if (s.row >= 0 && (gotQuality != s.quality || gotIndex != s.row)) {
		return Fail(c, "item: asked for quality %d row %d, the generator made quality %d index %d (base code of the row? its lvl?)", s.quality,
		            s.row, gotQuality, gotIndex);
	}
	if (s.row < 0 && gotQuality != s.quality) {
		Out("item: note: asked for quality %d, the generator made %d", s.quality, gotQuality);
	}
	return true;
}

// Sets the identified flag and resends the item, as D2R does after identifying one (SendItem).
void IdentifyItem(Ctx* c, Unit* item) noexcept {
	Fn<ItemFlagFn>(RvaItemFlag)(item, static_cast<int32_t>(hcmd::ItemFlagIdentified), 1);
	Fn<SendItemFn>(RvaSendItem)(c->game, c->player, item, 1, 0, ModeOf(item), Fn<ItemByteFn>(RvaItemPage)(item),
	                            Fn<ItemByteFn>(RvaItemByte54)(item), Fn<UnitPositionFn>(RvaUnitPosition)(item));
}

// `identify [all|<item unit id>]`: identifies the player's items (all of them, or one by id).
auto CmdIdentify(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	hcmd::IdentifyTarget target;
	if (!hcmd::ParseIdentify(t, &target)) {
		return Fail(c, "usage: identify [all|<item unit id>]");
	}
	int done = 0, already = 0;
	EachItemOf(c->player, [&](Unit* item) {
		if (!target.all && IdOf(item) != static_cast<uint32_t>(target.id)) {
			return;
		}
		if ((ItemFlags(item) & hcmd::ItemFlagIdentified) != 0) {
			++already;
			return;
		}
		IdentifyItem(c, item);
		++done;
		DescribeItem(c, item);
	});
	if (done > 0) {
		Fn<StatsChangedFn>(RvaStatsChanged)(c->player, 1);
	}
	Out("identify: %d identified, %d were already", done, already);
	return target.all || done + already > 0 ? true : Fail(c, "identify: the player has no item %lld", target.id);
}

// `unequip <body location>`: takes the worn item off that slot and frees it (RemoveItem: the inventory change the game
// uses for a used-up tome, 0x472590, then the remove packet).
auto CmdUnequip(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	const int loc = t.n >= 2 ? hcmd::ParseBodyLoc(t.tok[1]) : 0;
	if (loc == 0) {
		return Fail(c, "usage: unequip <head|amulet|body|rhand|lhand|rring|lring|belt|boots|gloves|1-12>");
	}
	Unit* found = nullptr;
	EachItemOf(c->player, [&](Unit* it) {
		int32_t where[8] = {};
		Fn<ItemLocationFn>(RvaItemLocation)(where, it);
		if (found == nullptr && where[0] == 1 && where[3] == loc) {
			found = it;
		}
	});
	if (found == nullptr) {
		return Fail(c, "unequip: nothing on body location %d", loc);
	}
	DescribeItem(c, found);
	int32_t location[8] = {};
	Fn<ItemLocationFn>(RvaItemLocation)(location, found);
	uint32_t unitId = IdOf(found);
	if (Fn<InvChangeFn>(RvaInvChange)(c->player, nullptr, location, nullptr, &unitId, 0, 1, 0) == 0) {
		return Fail(c, "unequip: the game refused to take the item off");
	}
	Fn<ByteSetFn>(RvaSetByte5c)(found, 0);
	Fn<SendItemFn>(RvaSendItem)(c->game, c->player, found, 0x20, 4, 0, 0, 0, location[2]);
	Fn<ByteSetFn>(RvaSetByte5c)(found, 0);
	Fn<FreeItemFn>(RvaFreeItem)(c->game, found);
	Out("unequip %d: removed", loc);
	return true;
}

// `items`: every item of the player (backpack, cube, stash, worn).
auto CmdItems(Ctx* c, const hcmd::Tokens&) noexcept -> bool {
	int n = 0;
	EachItemOf(c->player, [&](Unit* item) {
		if (n++ < 120) {
			DescribeItem(c, item);
		}
	});
	Out("items: %d", n);
	return true;
}

// --- player-path verbs (lane cube; copied unchanged from lane realpath's) -----------------------------------------------
// The cube checks of tools/game_checks.py drive the game the way a player's client does: the client's packets go to the
// server's own handlers (`pkt` / `pickup`: pick-up 0x16, cursor to container 0x18 (page 3 = the cube), container to cursor
// 0x19, use 0x20 ...), so every check, hook and plugin part on that path runs. `move` ends in the same server function as a
// walk packet (0x42d2c0) without its 15-sub-tile limit. Nothing here sets a stat or places an item; `packclear` / `remove`
// take items away (clean-up only, the checks say when they use them).
constexpr uint64_t RvaUnitClass = 0x349860;     // (unit, file, line) -> class id
constexpr int HashItems = 0x5c6;
constexpr int InventoryCursor = 0x40;           // inventory (+0 magic 0x1020304) +0x40: the item on the cursor

using UnitClassFn = int32_t (*)(Unit*, const char*, int32_t);

auto PacketHandler(uint8_t id) noexcept -> PacketFn {
	const uint64_t h = id < 0x66 ? *reinterpret_cast<const uint64_t*>(g_base + RvaPacketTable + id * 8ULL) : 0;
	return reinterpret_cast<PacketFn>(h);
}

auto ItemCodeOf(Ctx* c, Unit* item) noexcept -> uint32_t {
	const uint8_t* rec = Fn<ItemRecordFn>(RvaItemRecord)(c->dataFlag, Fn<UnitClassFn>(RvaUnitClass)(item, "harness", 0));
	return rec != nullptr ? d2r::At<uint32_t>(rec, 0x80) : 0U;
}

auto FindItemUnit(Ctx* c, uint32_t id) noexcept -> Unit* {
	Unit* found = nullptr;
	EachUnit(c->game, HashItems, [&](Unit* it) {
		if (found == nullptr && TypeOf(it) == 4 && IdOf(it) == id) {
			found = it;
		}
	});
	return found;
}

// RemoveItem: the inventory change the game makes when an item leaves (the same path as `unequip`).
auto RemoveItem(Ctx* c, Unit* item) noexcept -> bool {
	int32_t location[8] = {};
	Fn<ItemLocationFn>(RvaItemLocation)(location, item);
	uint32_t unitId = IdOf(item);
	if (Fn<InvChangeFn>(RvaInvChange)(c->player, nullptr, location, nullptr, &unitId, 0, 1, 0) == 0) {
		return false;
	}
	Fn<ByteSetFn>(RvaSetByte5c)(item, 0);
	Fn<SendItemFn>(RvaSendItem)(c->game, c->player, item, 0x20, 4, 0, 0, 0, location[2]);
	Fn<ByteSetFn>(RvaSetByte5c)(item, 0);
	Fn<FreeItemFn>(RvaFreeItem)(c->game, item);
	return true;
}

auto CmdPkt(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	uint8_t pkt[64] = {};
	const size_t n = hcmd::ParseHexBytes(t, 1, pkt, sizeof(pkt));
	if (n == 0) {
		return Fail(c, "usage: pkt <hex byte> ...   (two hex digits each, the packet as the client sends it)");
	}
	const PacketFn handler = PacketHandler(pkt[0]);
	if (handler == nullptr) {
		return Fail(c, "pkt: no server handler for 0x%02x", pkt[0]);
	}
	handler(c->game, c->player, pkt, static_cast<int32_t>(n));
	Out("pkt 0x%02x (%d bytes) handled", pkt[0], static_cast<int>(n));
	return true;
}

// `pickup <item id> [inv]`: packet 0x16 for an item on the ground, the client's packet of a click on it (`inv` = a plain click:
// to the backpack or an empty body location; without it to the cursor, as a click with the inventory panel open).
auto CmdPickup(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long id = 0;
	if (t.n < 2 || !hcmd::ParseInt(t.tok[1], &id)) {
		return Fail(c, "usage: pickup <item unit id> [inv]");
	}
	Unit* found = FindItemUnit(c, static_cast<uint32_t>(id));
	if (found == nullptr) {
		return Fail(c, "pickup: no such item unit");
	}
	int32_t x = 0, y = 0;
	d2r::UnitXY(found, &x, &y);
	const int mode = ModeOf(found);
	const double dist = DistTo(c->player, found);
	uint8_t pkt[hcmd::PickupPacketSize];
	hcmd::BuildPickupPacket(pkt, static_cast<uint32_t>(id), static_cast<uint32_t>(x), static_cast<uint32_t>(y), t.n > 2 && hcmd::LowerEq(t.tok[2], "inv"));
	PacketHandler(0x16)(c->game, c->player, pkt, static_cast<int32_t>(sizeof(pkt)));
	Out("pickup id=%u at %d,%d mode before %d, player distance %.1f", static_cast<uint32_t>(id), x, y, mode, dist);
	return true;
}

auto CmdCursor(Ctx* c, const hcmd::Tokens&) noexcept -> bool {
	auto* inv = static_cast<uint8_t*>(Fn<InventoryFn>(RvaInventory)(c->player, "harness", 0));
	Unit* item = inv != nullptr && d2r::At<uint32_t>(inv, 0) == 0x1020304 ? d2r::At<Unit*>(inv, InventoryCursor) : nullptr;
	if (item == nullptr) {
		Out("cursor empty");
		return true;
	}
	char code[5];
	hcmd::DwordToCode(ItemCodeOf(c, item), code);
	Out("cursor id=%u code=%s", IdOf(item), code);
	return true;
}

// `ground [code]`: the items lying on the ground of the game (mode 3 / 5), their positions and distance to the player.
auto CmdGround(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	const uint32_t want = t.n > 1 ? hcmd::CodeToDword(t.tok[1]) : 0U;
	int n = 0;
	EachUnit(c->game, HashItems, [&](Unit* it) {
		if (TypeOf(it) != 4 || (ModeOf(it) != 3 && ModeOf(it) != 5)) {
			return;
		}
		const uint32_t code = ItemCodeOf(c, it);
		if (want != 0 && code != want) {
			return;
		}
		char text[5];
		hcmd::DwordToCode(code, text);
		int32_t x = 0, y = 0;
		d2r::UnitXY(it, &x, &y);
		if (n++ < 60) {
			Out("ground id=%u code=%s mode=%d x=%d y=%d dist=%.1f flags=0x%x", IdOf(it), text, ModeOf(it), x, y, DistTo(c->player, it), ItemFlags(it));
		}
	});
	Out("ground items %d", n);
	return true;
}

auto CmdMove(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long x = 0, y = 0;
	if (t.n < 3 || !hcmd::ParseInt(t.tok[1], &x) || !hcmd::ParseInt(t.tok[2], &y) || x < 0 || y < 0 || x > 0xffff || y > 0xffff) {
		return Fail(c, "usage: move <x> <y> [walk] [packet]   (positions as in `state`; packet: 0x01 / 0x03, at most 15 sub-tiles)");
	}
	bool walk = false, packet = false;
	for (int i = 3; i < t.n; ++i) {
		walk = walk || hcmd::LowerEq(t.tok[i], "walk");
		packet = packet || hcmd::LowerEq(t.tok[i], "packet");
	}
	int32_t px = 0, py = 0;
	d2r::UnitXY(c->player, &px, &py);
	int64_t rc = 0;
	if (packet) {
		uint8_t pkt[hcmd::WalkPacketSize];
		const uint8_t id = walk ? 1 : 3;
		hcmd::BuildWalkPacket(pkt, id, px, py, static_cast<int>(x), static_cast<int>(y));
		using WalkPacketFn = uint64_t (*)(Game*, Unit*, const uint8_t*, int32_t);
		const auto h = reinterpret_cast<WalkPacketFn>(PacketHandler(id));
		rc = static_cast<int64_t>(h(c->game, c->player, pkt, static_cast<int32_t>(sizeof(pkt))) & 0xffffffffU);
	} else {
		rc = Fn<PlayerActionFn>(RvaPlayerAction)(c->game, c->player, nullptr, walk ? 2 : 3, static_cast<uint32_t>(x), static_cast<uint32_t>(y), 0, 0) & 0xffffffffLL;
	}
	Out("move from %d,%d to %lld,%lld (%s%s): code %lld, mode now %d (0 = accepted; poll `state` for the arrival)", px, py, x, y, walk ? "walk" : "run",
	    packet ? ", packet" : "", static_cast<long long>(rc), ModeOf(c->player));
	return rc == 0 ? true : Fail(c, "move: the server refused (code %lld)", static_cast<long long>(rc));
}

// `packclear`: removes every backpack item but the cube (set-up only: room for a pickup or a purchase).
auto CmdPackclear(Ctx* c, const hcmd::Tokens&) noexcept -> bool {
	Unit* batch[200];
	int n = 0;
	EachItemOf(c->player, [&](Unit* it) {
		if (n < 200 && Fn<ItemByteFn>(RvaItemPage)(it) == 0 && ItemCodeOf(c, it) != hcmd::CodeToDword("box")) {
			batch[n++] = it;
		}
	});
	int removed = 0;
	for (int i = 0; i < n; ++i) {
		removed += RemoveItem(c, batch[i]) ? 1 : 0;
	}
	Out("packclear: %d items removed", removed);
	return true;
}

// `remove <code> [count]` / `remove id <item id>`: takes items of the player away (clean-up after a check).
auto CmdRemove(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long count = 1, id = -1;
	const bool byId = t.n >= 3 && hcmd::LowerEq(t.tok[1], "id");
	if (t.n < 2 || (byId && !hcmd::ParseInt(t.tok[2], &id)) || (!byId && t.n > 2 && !hcmd::ParseInt(t.tok[2], &count))) {
		return Fail(c, "usage: remove <item code> [count] | remove id <item id>");
	}
	const uint32_t code = byId ? 0U : hcmd::CodeToDword(t.tok[1]);
	int removed = 0;
	while (removed < count) {
		Unit* item = nullptr;
		EachItemOf(c->player, [&](Unit* it) {
			if (item == nullptr && (byId ? IdOf(it) == static_cast<uint32_t>(id) : ItemCodeOf(c, it) == code)) {
				item = it;
			}
		});
		if (item == nullptr || !RemoveItem(c, item)) {
			break;
		}
		++removed;
		if (byId) {
			break;
		}
	}
	Out("remove %s: %d removed", t.tok[t.n - 1], removed);
	return removed > 0 ? true : Fail(c, "remove: no such item");
}

// `istat <item unit id> <stat> [layer | scan]` (lane cube): one stat of an item of the game, read only (cube output mods).
auto CmdIstat(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	hcmd::IstatSpec s;
	if (!hcmd::ParseIstat(t, &s)) {
		return Fail(c, "usage: istat <item unit id> <stat> [layer | scan]");
	}
	Unit* item = FindItemUnit(c, static_cast<uint32_t>(s.id));
	if (item == nullptr) {
		return Fail(c, "istat: no such item unit");
	}
	if (!s.scan) {
		Out("istat %lld %lld:%lld = %d", s.id, s.stat, s.layer, Stat(item, static_cast<int>(s.stat), static_cast<int>(s.layer)));
		return true;
	}
	int found = 0;
	for (int layer = 0; layer <= 0xffff && found < 20; ++layer) {
		const int32_t v = Stat(item, static_cast<int>(s.stat), layer);
		if (v != 0) {
			Out("istat %lld %lld:%d = %d", s.id, s.stat, layer, v);
			++found;
		}
	}
	Out("istat %lld %lld scan: %d layers with a value", s.id, s.stat, found);
	return true;
}

// --- lane realpath: vendor / gamble / use verbs and warp tiles (the rest of its player-path verbs are above) --------
constexpr uint64_t RvaUseCheck = 0x5817f0;      // (game, player, item, target)
using UseFn = uint64_t (*)(Game*, Unit*, Unit*, Unit*);
constexpr int TileList = 0x3630;  // unit type 5 (warp tiles): ONE chain, not a 128-bucket hash like types 0-4

// `gold get | gold set <carried> <bank>` (set-up only: the money a purchase or a gamble needs).
auto CmdGold(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	if (t.n >= 4 && hcmd::LowerEq(t.tok[1], "set")) {
		long long carried = 0, bank = 0;
		if (!hcmd::ParseInt(t.tok[2], &carried) || !hcmd::ParseInt(t.tok[3], &bank)) {
			return Fail(c, "usage: gold get | gold set <carried> <bank>");
		}
		Fn<SetStatFn>(RvaSetStat)(c->player, hcmd::StatGold, static_cast<int32_t>(carried), 0);
		Fn<SetStatFn>(RvaSetStat)(c->player, hcmd::StatGoldBank, static_cast<int32_t>(bank), 0);
	} else if (!(t.n >= 2 && hcmd::LowerEq(t.tok[1], "get"))) {
		return Fail(c, "usage: gold get | gold set <carried> <bank>");
	}
	Out("gold carried=%d bank=%d", Stat(c->player, hcmd::StatGold), Stat(c->player, hcmd::StatGoldBank));
	return true;
}

// `shop [npc class]`: the stock of the nearest (vendor) NPC, as `item` lines (page 0-3 = the trade panel's tabs).
auto CmdShop(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long cls = -1;
	if (t.n > 1 && !hcmd::ParseInt(t.tok[1], &cls)) {
		return Fail(c, "usage: shop [npc class]");
	}
	Unit* npc = NearestNpc(c, cls);
	if (npc == nullptr) {
		return Fail(c, "shop: no such NPC alive in this area");
	}
	Out("shop npc id=%u class=%d", IdOf(npc), ClassOf(npc));
	int items = 0;
	EachItemOf(npc, [&](Unit* it) {
		if (++items <= 80) {
			DescribeItem(c, it);
		}
	});
	Out("shop items %d", items);
	return true;
}

// `gamble`: the player's gamble offers (built by the server on the Gamble menu line), read from the player data (+0x108).
auto CmdGamble(Ctx* c, const hcmd::Tokens&) noexcept -> bool {
	const uint8_t* data = Fn<PlayerDataFn>(RvaPlayerData)(c->player);
	void* list = data != nullptr ? d2r::At<void*>(data, 0x108) : nullptr;
	int offers = 0, guard = 0;
	for (Unit* item = list != nullptr ? Fn<InvFirstFn>(RvaInvFirst)(list) : nullptr; item != nullptr && guard++ < 200;) {
		Unit* next = Fn<InvNextFn>(RvaInvNext)(item);
		if (TypeOf(item) == 4 && ++offers <= 80) {
			DescribeItem(c, item);
		}
		item = next;
	}
	Out("gamble offers %d (list %s)", offers, list != nullptr ? "present" : "none");
	return list != nullptr;
}

// `usecheck <item id>`: would the server let the player use this item (potion, scroll, tome, elixir) now. The use itself goes
// through the client's packet with `pkt` (0x20 from the backpack, 0x26 from the belt).
auto CmdUseCheck(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long id = 0;
	if (t.n < 2 || !hcmd::ParseInt(t.tok[1], &id)) {
		return Fail(c, "usage: usecheck <item id>");
	}
	Unit* item = nullptr;
	EachItemOf(c->player, [&](Unit* it) {
		if (item == nullptr && IdOf(it) == static_cast<uint32_t>(id)) {
			item = it;
		}
	});
	if (item == nullptr) {
		return Fail(c, "usecheck: no such item of the player");
	}
	const uint64_t ok = Fn<UseFn>(RvaUseCheck)(c->game, c->player, item, nullptr) & 0xff;
	Out("usecheck id=%u usable=%d", static_cast<uint32_t>(id), static_cast<int>(ok));
	return true;
}

// `tiles`: the warp tiles (unit type 5) of the game, in list order; a player takes one with the interact packet 0x13
// (`pkt 13 05 00 00 00 <id>`), the client's packet of a click on the entrance.
// Bug #399: the verb answered `FAIL crashed` after the first tile or two, in every level (Catacombs 2 and 3, lane bugsweep run
// checks-20261029-185149-s1). It walked 128 "buckets" from game + 0x3630 as for types 0-4, but D2R keeps the tiles in a single
// chain there: the unit lookups 0x48fd54 / 0x48fe80 take `lea rax,[game+0x3630]` for type 5 (no id hash) and the tile walker
// 0x4922b0 follows `[game+0x3630]` through +0x158. The words after it are other fields of the game (0x50, 0x2f, ASCII text from
// "bucket" 65 on), and the first of them read as a unit threw. Now only that chain is walked, under its own SEH frame, and
// each tile's line is read in its own frame too (`stage`: 1 position, 2 distance, 3 room).
struct TileLine {
	uint32_t id = 0;
	int32_t cls = -1, mode = -1, x = 0, y = 0, area = -1;
	double dist = 1e9;
	int stage = 0;
};

auto ReadTile(Unit* player, Unit* u, TileLine* t) noexcept -> bool {
	__try {
		t->id = IdOf(u);
		t->cls = ClassOf(u);
		t->mode = ModeOf(u);
		t->stage = 1;
		d2r::UnitXY(u, &t->x, &t->y);
		t->stage = 2;
		t->dist = DistTo(player, u);
		t->stage = 3;
		t->area = LevelOf(u);
		t->stage = 4;
		return true;
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		return false;
	}
}

// The tile units of the game's tile chain into `out` (up to `cap`); false when a link faulted (`*bad` = that link).
auto TileChain(Game* game, Unit** out, int* n, int cap, Unit** bad) noexcept -> bool {
	Unit* u = d2r::At<Unit*>(game, TileList);
	__try {
		for (int guard = 0; u != nullptr && guard < 4000; ++guard) {
			if (TypeOf(u) == 5 && *n < cap) {
				out[(*n)++] = u;
			}
			u = d2r::At<Unit*>(u, UnitNextInHash);
		}
		return true;
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		*bad = u;
		return false;
	}
}

// Readable memory of at least n bytes at p (VirtualQuery, no exception: a caught one still writes D2R's last-resort report).
auto Readable(const void* p, size_t n) noexcept -> bool {
	const auto a = reinterpret_cast<uintptr_t>(p);
	if (a < 0x10000 || a > 0x7ffffffeffffULL || (a & 7) != 0) {
		return false;
	}
	MEMORY_BASIC_INFORMATION mbi{};
	if (VirtualQuery(p, &mbi, sizeof(mbi)) == 0 || mbi.State != MEM_COMMIT || (mbi.Protect & (PAGE_GUARD | PAGE_NOACCESS)) != 0) {
		return false;
	}
	return a + n <= reinterpret_cast<uintptr_t>(mbi.BaseAddress) + mbi.RegionSize;
}

// `hashscan [from] [to]`: bug #399. For each qword index i of the game struct in [from, to) (default 0x400 .. 0x900) whose value
// points at a unit (readable, type 0..5), the index, the unit's type, id and (id & 0x7f): a hash table of type t starts where
// i - (id & 0x7f) is the same for its units.
auto CmdHashScan(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long from = 0x400, to = 0x900;
	if (t.n > 1) {
		hcmd::ParseInt(t.tok[1], &from);
	}
	if (t.n > 2) {
		hcmd::ParseInt(t.tok[2], &to);
	}
	int shown = 0;
	for (long long i = from; i < to && shown < 120; ++i) {
		const auto* slot = reinterpret_cast<const uint8_t*>(c->game) + i * 8;
		if (!Readable(slot, 8)) {
			break;
		}
		Unit* u = *reinterpret_cast<Unit* const*>(slot);
		if (u == nullptr || !Readable(u, 0x160)) {
			continue;
		}
		const int32_t type = TypeOf(u);
		if (type < 0 || type > 5) {
			continue;
		}
		const uint32_t id = IdOf(u);
		++shown;
		Out("hash 0x%llx: type %d id %u class %d base 0x%llx", i, type, id, ClassOf(u), i - static_cast<long long>(id & 0x7f));
	}
	Out("hashscan 0x%llx..0x%llx: %d unit pointers", from, to, shown);
	return true;
}

auto CmdTiles(Ctx* c, const hcmd::Tokens&) noexcept -> bool {
	constexpr int Cap = 256;
	Unit* tiles[Cap];
	int n = 0, skipped = 0;
	Unit* bad = nullptr;
	if (!TileChain(c->game, tiles, &n, Cap, &bad)) {
		Out("tiles chain broken at %p (not a readable unit), the rest skipped", static_cast<void*>(bad));
	}
	int listed = 0;
	for (int i = 0; i < n; ++i) {
		TileLine t;
		if (!ReadTile(c->player, tiles[i], &t)) {
			++skipped;
			Out("tile id=%u class=%d skipped (exception at stage %d)", t.id, t.cls, t.stage);
			continue;
		}
		if (listed++ < 40) {
			Out("tile id=%u class=%d mode=%d at %d,%d dist=%.0f area=%d", t.id, t.cls, t.mode, t.x, t.y, t.dist, t.area);
		}
	}
	Out("tiles %d", listed);
	if (bad != nullptr || skipped > 0) {
		Out("tiles chain broken %d, skipped tiles %d", bad != nullptr ? 1 : 0, skipped);
	}
	return true;
}

// --- `states` / `cstates`: a unit's states and their stat lists (bug #20) --------------------------------------------------
// For every state id below the bound with the unit's state bit set (0x3351b0), the state's stat list (0x2f5940, list +0x1c flags,
// +0x20 state, +0x24 end frame as a float; stat array at +0x30, count at +0x38, 16-byte entries {u16 layer, u16, u32 stat}
// {i32 value, i32}: as a passivestate verb reads it). `states` reads the server's unit (game thread), `cstates` the client's copy
// (UI thread): the client skill do dispatcher 0x216920 reads stats 350 / 351 / 202 (modifierlist_skill / _level / _castid) of
// the caster's aurastate list there.
constexpr uint64_t RvaStateList = 0x2f5940;  // (unit, state) -> the unit's stat list for that state or null
constexpr uint64_t RvaDataTables = 0x300a90; // (dataFlag) -> the data tables; +0x298 = the number of states.txt rows
constexpr int StatListArray = 0x30, StatListCount = 0x38, StatEntrySize = 16;

void PrintStates(const char* side, Unit* unit, long long bound, long long only) noexcept {
	const auto hasState = Fn<UnitHasStateFn>(RvaUnitHasState);
	const auto listOf = Fn<uint8_t* (*)(Unit*, int32_t)>(RvaStateList);
	// a state id at or past the row count asserts `nShift < DataTablesGetNumStates` in 0x3351b0 (once per call), state 0 `dwState`
	const auto* tables = Fn<const uint8_t* (*)(uint32_t)>(RvaDataTables)(d2r::api.unitDataFlag(unit));
	const long long states = tables != nullptr ? static_cast<long long>(d2r::At<int64_t>(tables, 0x298)) : 0;
	bound = bound < states ? bound : states;
	if (only >= bound) {
		Out("%s states: state %lld is not below the %lld states.txt rows", side, only, states);
		return;
	}
	int on = 0;
	for (long long s = only >= 1 ? only : 1; s < (only >= 1 ? only + 1 : bound); ++s) {  // state 0 asserts `dwState` in 0x2f5940
		const bool bit = hasState(unit, static_cast<int32_t>(s)) != 0;
		uint8_t* list = listOf(unit, static_cast<int32_t>(s));
		if (!bit && list == nullptr) {
			continue;
		}
		++on;
		if (list == nullptr) {
			Out("%s state %lld: bit=1 list=none", side, s);
			continue;
		}
		const uint8_t* arr = d2r::At<const uint8_t*>(list, StatListArray);
		const uint64_t count = d2r::At<uint64_t>(list, StatListCount) & 0xffff;
		char stats[300] = "";
		size_t used = 0;
		for (uint64_t k = 0; arr != nullptr && k < count && k < 24 && used + 24 < sizeof(stats); ++k) {
			const uint8_t* e = arr + k * StatEntrySize;
			used += static_cast<size_t>(std::snprintf(stats + used, sizeof(stats) - used, " %u:%u=%d", d2r::At<uint32_t>(e, 4), d2r::At<uint16_t>(e, 0),
			                                          d2r::At<int32_t>(e, 8)));
		}
		Out("%s state %lld: bit=%d list flags=%08x state=%u end=%.0f stats(%llu) stat:layer=value%s", side, s, bit ? 1 : 0, d2r::At<uint32_t>(list, 0x1c),
		    d2r::At<uint32_t>(list, 0x20), static_cast<double>(d2r::At<float>(list, 0x24)), static_cast<unsigned long long>(count), stats);
	}
	Out("%s states: %d set (ids below %lld)", side, on, bound);
}

auto ParseStatesArgs(Ctx* c, const hcmd::Tokens& t, hcmd::UnitRef* ref, long long* bound, long long* only) noexcept -> bool {
	*bound = 1200;
	*only = -1;
	if (t.n < 2 || !hcmd::ParseUnitRef(t.tok[1], ref) || ref->kind == hcmd::UnitRef::Merc || (t.n > 2 && !hcmd::ParseInt(t.tok[2], only)) ||
	    *only >= 4096) {
		return Fail(c, "usage: %s player|mon:<id> [state id]", t.tok[0]);
	}
	return true;
}

auto CmdStates(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	hcmd::UnitRef ref;
	long long bound = 0, only = -1;
	if (!ParseStatesArgs(c, t, &ref, &bound, &only)) {
		return false;
	}
	Unit* unit = ref.kind == hcmd::UnitRef::Player ? c->player : FindMonsterById(c, static_cast<uint32_t>(ref.id));
	if (unit == nullptr) {
		return Fail(c, "states: unit not found");
	}
	PrintStates("server", unit, bound, only);
	return true;
}

auto CmdClientStates(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	hcmd::UnitRef ref;
	long long bound = 0, only = -1;
	if (!ParseStatesArgs(c, t, &ref, &bound, &only)) {
		return false;
	}
	if (ref.kind == hcmd::UnitRef::Player && g_playerId == 0) {
		return Fail(c, "cstates: no player seen yet (run a server verb such as state first)");
	}
	Unit* unit = ref.kind == hcmd::UnitRef::Player ? Fn<ClientFindFn>(RvaClientFind)(static_cast<uint32_t>(g_playerId), 0)
	                                               : Fn<ClientFindFn>(RvaClientFind)(static_cast<uint32_t>(ref.id), 1);
	if (unit == nullptr) {
		return Fail(c, "cstates: no client unit");
	}
	PrintStates("client", unit, bound, only);
	return true;
}

// --- `cistat`, `durwatch`: what the client gets of a worn item's durability (lane dursync, bug #433) ----------------------------
// `cistat <item unit id> <stat> [layer | scan]`: the stat of the CLIENT's copy of the item (istat reads the server's).
auto CmdClientIstat(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	hcmd::IstatSpec s;
	if (!hcmd::ParseIstat(t, &s)) {
		return Fail(c, "usage: cistat <item unit id> <stat> [layer | scan]");
	}
	Unit* item = Fn<ClientFindFn>(RvaClientFind)(static_cast<uint32_t>(s.id), 4);
	if (item == nullptr) {
		return Fail(c, "cistat: the client has no item unit %lld", s.id);
	}
	if (!s.scan) {
		Out("cistat %lld %lld:%lld = %d", s.id, s.stat, s.layer, Stat(item, static_cast<int>(s.stat), static_cast<int>(s.layer)));
		return true;
	}
	int found = 0;
	for (int layer = 0; layer <= 0xffff && found < 20; ++layer) {
		const int32_t v = Stat(item, static_cast<int>(s.stat), layer);
		if (v != 0) {
			Out("cistat %lld %lld:%d = %d", s.id, s.stat, layer, v);
			++found;
		}
	}
	Out("cistat %lld %lld scan: %d layers with a value", s.id, s.stat, found);
	return true;
}

// `durwatch on|show|off`: counts packet 0x3e for stat 0x48 (durability) on its way: the server sender 0x47a190 (D2RLoader's slot
// 0x3e2a1b8 behind its `jmp [rip]` thunk, wrapped), the client packet table's 0x3e handler (entry 0x22bc210, wrapped) and the
// client's stat apply 0x1c7710 (id, set flag, stat, value, param; inline hook), with the client item's stat 0x48 after the apply.
constexpr uint64_t RvaSrvStatSlot = 0x3e2a1b8;    // jmp target slot of 0x47a190 (client, item, set, stat, value, param)
constexpr uint64_t RvaCltHandler3e = 0x22bc210;   // client packet table 0x22bbc40, 24-byte rows: handler of 0x3e
constexpr uint64_t RvaCltStatApply = 0x1c7710;
// MOV [RSP+0x10],RBX / MOV [RSP+0x18],RBP / MOV [RSP+0x20],RSI / PUSH RDI / SUB RSP,0x20
constexpr uint8_t CltStatApplyEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x10, 0x48, 0x89, 0x6c, 0x24, 0x18, 0x48, 0x89,
                                         0x74, 0x24, 0x20, 0x57, 0x48, 0x83, 0xec, 0x20};
// The two stack arguments are taken and passed on as whole 8-byte slots: the watch must not change what the callee reads.
using SrvStatFn = void (*)(void*, Unit*, uint64_t, uint64_t, uint64_t, uint64_t);
using CltHandlerFn = uint64_t (*)(uint64_t, uint64_t, uint64_t, uint64_t);
using CltStatApplyFn = void (*)(uint32_t, uint8_t, int32_t, int32_t, uint16_t);
SrvStatFn g_dwSrvOriginal = nullptr;
CltHandlerFn g_dwCltOriginal = nullptr;
CltStatApplyFn g_dwApplyOriginal = nullptr;
bool g_dwApplyHooked = false;
volatile LONG g_dwSrv = 0, g_dwSrvDur = 0, g_dwSrvLastId = -1, g_dwSrvLastValue = -1;
volatile LONG64 g_dwSrvLastParam = -1;  // the raw 8-byte slot of the parameter (layer) argument
volatile LONG g_dwClt = 0, g_dwApply = 0, g_dwApplyDur = 0, g_dwApplyLastId = -1, g_dwApplyLastValue = -1, g_dwApplyAfter = -1;
volatile LONG g_dwOn = 0;

void DwSrvStat(void* client, Unit* item, uint64_t set, uint64_t stat, uint64_t value, uint64_t param) noexcept {
	InterlockedIncrement(&g_dwSrv);
	if (static_cast<uint32_t>(stat) == StatDurability) {
		InterlockedIncrement(&g_dwSrvDur);
		InterlockedExchange(&g_dwSrvLastId, item != nullptr ? static_cast<LONG>(IdOf(item)) : -1);
		InterlockedExchange(&g_dwSrvLastValue, static_cast<LONG>(value));
		InterlockedExchange64(&g_dwSrvLastParam, static_cast<LONG64>(param));
	}
	g_dwSrvOriginal(client, item, set, stat, value, param);
}

auto DwCltHandler(uint64_t a, uint64_t b, uint64_t c, uint64_t d) noexcept -> uint64_t {
	InterlockedIncrement(&g_dwClt);
	return g_dwCltOriginal(a, b, c, d);
}

void DwStatApply(uint32_t id, uint8_t set, int32_t stat, int32_t value, uint16_t param) noexcept {
	g_dwApplyOriginal(id, set, stat, value, param);
	if (g_dwOn == 0) {
		return;
	}
	InterlockedIncrement(&g_dwApply);
	if (stat == StatDurability) {
		InterlockedIncrement(&g_dwApplyDur);
		InterlockedExchange(&g_dwApplyLastId, static_cast<LONG>(id));
		InterlockedExchange(&g_dwApplyLastValue, value);
		Unit* item = Fn<ClientFindFn>(RvaClientFind)(id, 4);
		InterlockedExchange(&g_dwApplyAfter, item != nullptr ? Stat(item, StatDurability) : -2);
	}
}

auto DwSwap(uint64_t at, uint64_t have, uint64_t want) noexcept -> bool {
	return g_context != nullptr && g_context->PatchWriteU64(at, &have, sizeof(have), want);
}

auto CmdDurWatch(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	if (t.n != 2) {
		return Fail(c, "usage: durwatch on|show|off");
	}
	if (hcmd::LowerEq(t.tok[1], "on")) {
		if (g_dwOn != 0) {
			return Fail(c, "durwatch: already on");
		}
		const uint64_t srv = *reinterpret_cast<const volatile uint64_t*>(g_base + RvaSrvStatSlot);
		const uint64_t clt = *reinterpret_cast<const volatile uint64_t*>(g_base + RvaCltHandler3e);
		if (srv == 0 || clt == 0) {
			return Fail(c, "durwatch: an entry is empty (server slot %llx, client handler %llx)", static_cast<unsigned long long>(srv),
			            static_cast<unsigned long long>(clt));
		}
		g_dwSrvOriginal = reinterpret_cast<SrvStatFn>(srv);
		g_dwCltOriginal = reinterpret_cast<CltHandlerFn>(clt);
		if (!g_dwApplyHooked) {
			if (g_context == nullptr ||
			    !g_context->InstallInlineHook(RvaCltStatApply, CltStatApplyEntry, sizeof(CltStatApplyEntry), reinterpret_cast<void*>(&DwStatApply),
			                                  reinterpret_cast<void**>(&g_dwApplyOriginal))) {
				return Fail(c, "durwatch: hook of 0x1c7710 failed (entry bytes differ?)");
			}
			g_dwApplyHooked = true;
		}
		if (!DwSwap(RvaSrvStatSlot, srv, reinterpret_cast<uint64_t>(&DwSrvStat))) {
			return Fail(c, "durwatch: the server slot write failed");
		}
		if (!DwSwap(RvaCltHandler3e, clt, reinterpret_cast<uint64_t>(&DwCltHandler))) {
			DwSwap(RvaSrvStatSlot, reinterpret_cast<uint64_t>(&DwSrvStat), srv);
			return Fail(c, "durwatch: the client table write failed");
		}
		for (volatile LONG* v : {&g_dwSrv, &g_dwSrvDur, &g_dwClt, &g_dwApply, &g_dwApplyDur}) {
			InterlockedExchange(v, 0);
		}
		InterlockedExchange(&g_dwOn, 1);
		Out("durwatch on");
		return true;
	}
	Out("durwatch: server 0x3e %ld (durability %ld, last item %ld = %ld, parameter slot 0x%llx); client handler %ld; client apply %ld "
	    "(durability %ld, last item %ld = %ld, client stat after %ld)",
	    static_cast<long>(g_dwSrv), static_cast<long>(g_dwSrvDur), static_cast<long>(g_dwSrvLastId), static_cast<long>(g_dwSrvLastValue),
	    static_cast<unsigned long long>(g_dwSrvLastParam),
	    static_cast<long>(g_dwClt), static_cast<long>(g_dwApply), static_cast<long>(g_dwApplyDur), static_cast<long>(g_dwApplyLastId),
	    static_cast<long>(g_dwApplyLastValue), static_cast<long>(g_dwApplyAfter));
	if (hcmd::LowerEq(t.tok[1], "off") && g_dwOn != 0) {
		const bool a = DwSwap(RvaSrvStatSlot, reinterpret_cast<uint64_t>(&DwSrvStat), reinterpret_cast<uint64_t>(g_dwSrvOriginal));
		const bool b = DwSwap(RvaCltHandler3e, reinterpret_cast<uint64_t>(&DwCltHandler), reinterpret_cast<uint64_t>(g_dwCltOriginal));
		InterlockedExchange(&g_dwOn, 0);
		if (!a || !b) {
			return Fail(c, "durwatch off: an entry is no longer ours, left as it is");
		}
	}
	return true;
}

// --- `asserttrace`: who raises D2R's engine asserts (lane p4-engine-b) ---------------------------------------------------------
// Every BC_ASSERT of the engine ends in the report function 0x75ff0 (descriptor in rcx: file name at +0, message at +0x20), on the
// server and on the client side. D2RLoader's log names only the first assert of a kind per launch; `asserttrace on` hooks the
// report function and keeps every call (message, file, 12 return addresses found by scanning the stack) in a ring of 32 and a
// running count, and writes a line per call to the plugin log. `asserttrace show [n]` prints the ring, `asserttrace count` the
// count only (the skill sweep reads it before and after each cast), `asserttrace clear` empties both.
constexpr uint64_t RvaAssertReport = 0x75ff0;
constexpr uint8_t AssertReportEntry[] = {0x48, 0x83, 0xec, 0x28, 0x48, 0x8d, 0x05, 0x05, 0x1f, 0xc4, 0x01};
constexpr int AssertFrames = 12;
constexpr int AssertRing = 32;
struct AssertEvent {
	char message[96];
	char file[80];
	uint32_t frames[AssertFrames];
	int count;
};
AssertEvent g_asserts[AssertRing];
volatile LONG g_assertCount = 0;
void (*g_assertOriginal)(void*) = nullptr;
bool g_assertHooked = false;

void ReadGuarded(const void* at, char* out, size_t cap) noexcept {
	out[0] = '\0';
	__try {
		const char* p = static_cast<const char*>(at);
		size_t i = 0;
		for (; i + 1 < cap && p[i] != '\0' && static_cast<unsigned char>(p[i]) >= 0x20; ++i) {
			out[i] = p[i];
		}
		out[i] = '\0';
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		out[0] = '\0';
	}
}

void AssertReportHook(void* descriptor) noexcept {
	const LONG n = InterlockedIncrement(&g_assertCount);
	AssertEvent& e = g_asserts[(n - 1) % AssertRing];
	e.message[0] = e.file[0] = '\0';
	e.count = 0;
	if (descriptor != nullptr) {
		const char* const* d = static_cast<const char* const*>(descriptor);
		__try {
			ReadGuarded(d[0], e.file, sizeof(e.file));
			ReadGuarded(d[4], e.message, sizeof(e.message));
		} __except (EXCEPTION_EXECUTE_HANDLER) {
		}
	}
	// the unwinder stops after one frame in the engine's code, so the stack is scanned: a value inside the image with a call
	// instruction before it is a return address of the chain, innermost first
	char line[480];
	size_t used = static_cast<size_t>(std::snprintf(line, sizeof(line), "mxl2012-core: assert trace #%ld: %s | %s |", static_cast<long>(n), e.message, e.file));
	const uint64_t* sp = static_cast<const uint64_t*>(_AddressOfReturnAddress());
	__try {
		for (int i = 0; i < 400 && e.count < AssertFrames; ++i) {
			const uint64_t v = sp[i];
			if (v < g_base + 0x1000 || v >= g_base + 0x4000000) {
				continue;
			}
			const uint8_t* at = reinterpret_cast<const uint8_t*>(v);
			if (at[-5] != 0xe8 && !(at[-6] == 0xff && (at[-5] & 0x38) == 0x10) && !(at[-2] == 0xff && (at[-1] & 0x38) == 0x10)) {
				continue;
			}
			e.frames[e.count++] = static_cast<uint32_t>(v - g_base);
			if (used + 12 < sizeof(line)) {
				used += static_cast<size_t>(std::snprintf(line + used, sizeof(line) - used, " %x", e.frames[e.count - 1]));
			}
		}
	} __except (EXCEPTION_EXECUTE_HANDLER) {
	}
	if (g_context != nullptr) {
		g_context->LogInfo(line);
	}
	if (g_assertOriginal != nullptr) {
		g_assertOriginal(descriptor);
	}
}

auto CmdAssertTrace(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	if (t.n < 2) {
		return Fail(c, "usage: asserttrace on|count|show [n]|clear");
	}
	if (hcmd::LowerEq(t.tok[1], "on")) {
		if (!g_assertHooked) {
			if (g_context == nullptr ||
			    !g_context->InstallInlineHook(RvaAssertReport, AssertReportEntry, sizeof(AssertReportEntry), reinterpret_cast<void*>(&AssertReportHook),
			                                  reinterpret_cast<void**>(&g_assertOriginal))) {
				return Fail(c, "asserttrace: hook of 0x75ff0 failed (entry bytes differ?)");
			}
			g_assertHooked = true;
		}
		Out("asserttrace on (%ld asserts so far)", static_cast<long>(g_assertCount));
		return true;
	}
	if (hcmd::LowerEq(t.tok[1], "clear")) {
		InterlockedExchange(&g_assertCount, 0);
		Out("asserttrace cleared");
		return true;
	}
	const LONG total = g_assertCount;
	if (hcmd::LowerEq(t.tok[1], "count")) {
		Out("asserttrace count %ld hooked %d", static_cast<long>(total), g_assertHooked ? 1 : 0);
		return true;
	}
	long long last = AssertRing;
	if (t.n > 2 && (!hcmd::ParseInt(t.tok[2], &last) || last < 1)) {
		return Fail(c, "usage: asserttrace show [n]");
	}
	LONG first = total > AssertRing ? total - AssertRing : 0;
	if (total - first > last) {
		first = total - static_cast<LONG>(last);
	}
	for (LONG i = first; i < total; ++i) {
		const AssertEvent& e = g_asserts[i % AssertRing];
		char frames[160] = "";
		size_t used = 0;
		for (int k = 0; k < e.count && used + 12 < sizeof(frames); ++k) {
			used += static_cast<size_t>(std::snprintf(frames + used, sizeof(frames) - used, "%s%x", k > 0 ? " " : "", e.frames[k]));
		}
		Out("assert #%ld: %s | %s | %s", static_cast<long>(i + 1), e.message, e.file, frames);
	}
	Out("asserttrace show: %ld asserts", static_cast<long>(total));
	return true;
}

// --- mercenaries, NPC talk and trade (lane mercs2) ---------------------------------------------------------------------------------------------
// The checks drive what a player does: `interact` is the NPC click (packet 0x2f), `menu <line>` runs the client's own handler of
// that menu line (the click on it: Trade, Gamble, Hire, Resurrect), `hire` is the hire list's button (packet 0x36). Equipping the
// mercenary, buying and selling are real clicks of game_checks.py on the panels; these verbs only read the result.
constexpr uint64_t RvaNpcMercList = 0x502b70;   // (game, npc, &scratch) -> NPC state: hire list entries at +0x18, count at +0x20
constexpr uint64_t RvaOpenHireList = 0x540640;  // (game, client, npc): makes the NPC's hire list and tells the client
constexpr uint64_t RvaHireCost = 0x3c17b0;      // (expansion, player, hireling id, npc row byte +10, difficulty, &out): out[5] = price
constexpr uint64_t RvaRevivePrice = 0x3c1ad0;   // (merc, not classic, hireling id) -> gold (hireling.txt resurrectcost* columns)
using MercListFn = uint8_t* (*)(Game*, Unit*, void*);
using HireCostFn = int32_t (*)(int32_t, Unit*, uint32_t, uint8_t, uint32_t, uint32_t*);
using RevivePriceFn = int32_t (*)(Unit*, int32_t, int32_t);

// `merc [dead]`: the player's mercenary (alive, or with `dead` a dead one too) and every item it carries (worn: page 255, body=).
auto CmdMerc(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	Unit* merc = MercOf(c, t.n > 1 && hcmd::LowerEq(t.tok[1], "dead") ? 1 : 0);
	if (merc == nullptr) {
		return Fail(c, "merc: the player has no mercenary");
	}
	Out("merc id=%u class=%d level=%d mode=%d life=%d/%d exp=%u str=%d dex=%d", IdOf(merc), ClassOf(merc), Stat(merc, StatLevel), ModeOf(merc),
	    Stat(merc, StatLife) >> 8, Stat(merc, 7) >> 8, static_cast<uint32_t>(Stat(merc, StatExperience)), Stat(merc, 0), Stat(merc, 2));
	int items = 0;
	EachItemOf(merc, [&](Unit* it) {
		++items;
		DescribeItem(c, it);
	});
	Out("merc items %d", items);
	return true;
}

// `mercprice [level]`: D2R's revive price function (the one the hirer's dialog shows and charges) for the mercenary, at its
// level or at the one given (the level stat is put back at once), next to 1.13c's formula.
auto CmdMercPrice(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	Unit* merc = MercOf(c, 1);
	if (merc == nullptr) {
		return Fail(c, "mercprice: the player has no mercenary");
	}
	const int32_t was = Stat(merc, StatLevel);
	long long level = was;
	if (t.n >= 2 && (!hcmd::ParseInt(t.tok[1], &level) || level < 1 || level > 255)) {
		return Fail(c, "usage: mercprice [level 1-255]");
	}
	Fn<SetStatFn>(RvaSetStat)(merc, StatLevel, static_cast<int32_t>(level), 0);
	const int32_t price = Fn<RevivePriceFn>(RvaRevivePrice)(merc, 1, 0);
	Fn<SetStatFn>(RvaSetStat)(merc, StatLevel, was, 0);
	Out("mercprice level=%lld price=%d expected113=%d", level, price, hcmd::RevivePrice113(static_cast<int>(level)));
	return true;
}

// `hire [npc class] [n] [reopen]`: the hire list's button for the n-th free entry of the nearest hirer: packet 0x36 (npc id, list
// index, price, current mercenary id or -1). The list is the one the Hire menu line made (`reopen` makes it again first). The
// player pays the price shown; a player short of gold is refused by the server, as in the game.
auto CmdHire(Ctx* c, const hcmd::Tokens& t) noexcept -> bool {
	long long cls = -1, which = 0;
	const bool reopen = t.n > 3 && hcmd::LowerEq(t.tok[3], "reopen");
	if ((t.n > 1 && !hcmd::ParseInt(t.tok[1], &cls)) || (t.n > 2 && !hcmd::ParseInt(t.tok[2], &which)) || (t.n > 3 && !reopen)) {
		return Fail(c, "usage: hire [npc class] [n] [reopen]");
	}
	Unit* npc = NearestNpc(c, cls);
	if (npc == nullptr) {
		return Fail(c, "hire: no such NPC alive in this area");
	}
	uint8_t scratch[64] = {};
	const uint8_t* list = Fn<MercListFn>(RvaNpcMercList)(c->game, npc, scratch);
	const auto* npcRow = static_cast<const uint8_t*>(Fn<NpcRecordFn>(RvaNpcRecord)(c->dataFlag, ClassOf(npc)));
	if (list == nullptr || npcRow == nullptr) {
		return Fail(c, "hire: the NPC has no mercenary list");
	}
	if (reopen || d2r::At<uint64_t>(list, 0x20) == 0) {
		Fn<void (*)(Game*, void*, Unit*)>(RvaOpenHireList)(c->game, Fn<UnitClientFn>(RvaUnitClientOf)(c->player), npc);
		list = Fn<MercListFn>(RvaNpcMercList)(c->game, npc, scratch);
		if (list == nullptr) {
			return Fail(c, "hire: the NPC has no mercenary list");
		}
	}
	const auto* entries = d2r::At<const uint8_t*>(list, 0x18);
	const uint64_t count = d2r::At<uint64_t>(list, 0x20);
	Out("hire: %llu list entries", static_cast<unsigned long long>(count));
	long long seen = 0;
	for (uint64_t i = 0; entries != nullptr && i < count && i < 64; ++i) {
		const uint8_t* e = entries + i * 0x10;
		const uint32_t hired = d2r::At<uint32_t>(e, 8), avail = d2r::At<uint32_t>(e, 0xc);
		Out("hire: entry %llu index=%u id=%u hired=%u avail=%u", static_cast<unsigned long long>(i), d2r::At<uint16_t>(e, 0), d2r::At<uint32_t>(e, 4), hired, avail);
		if (hired != 0 || avail == 0 || seen++ != which) {
			continue;
		}
		uint32_t out[16] = {};
		if (Fn<HireCostFn>(RvaHireCost)(c->dataFlag != 1 ? 1 : 0, c->player, d2r::At<uint32_t>(e, 4), npcRow[10], d2r::At<uint8_t>(c->game, GameDifficulty), out) == 0) {
			return Fail(c, "hire: price lookup failed");
		}
		Unit* merc = MercOf(c, 1);
		uint8_t pkt[17] = {0x36};
		const uint32_t id = IdOf(npc), index = d2r::At<uint16_t>(e, 0), cost = out[5], mercId = merc != nullptr ? IdOf(merc) : 0xffffffffU;
		std::memcpy(pkt + 1, &id, 4);
		std::memcpy(pkt + 5, &index, 4);
		std::memcpy(pkt + 9, &cost, 4);
		std::memcpy(pkt + 13, &mercId, 4);
		const int32_t gold = Stat(c->player, StatGold);
		Out("hire: entry %llu hireling id=%u price=%u gold=%d bank=%d npc %u at distance %.0f, current mercenary id %u", static_cast<unsigned long long>(i),
		    d2r::At<uint32_t>(e, 4), cost, gold, Stat(c->player, StatGoldBank), id, DistTo(c->player, npc), mercId);
		SendPacket(c, pkt, 17);
		Unit* now = MercOf(c);
		Out("hire: mercenary now %s (class %d id %u), gold %d -> %d", now != nullptr ? "present" : "absent", now != nullptr ? ClassOf(now) : -1,
		    now != nullptr ? IdOf(now) : 0U, gold, Stat(c->player, StatGold));
		return now != nullptr && IdOf(now) != mercId ? true : Fail(c, "hire: the server did not hire");
	}
	return Fail(c, "hire: no free entry %lld", which);
}

using VerbFn = bool (*)(Ctx*, const hcmd::Tokens&) noexcept;
struct Verb {
	const char* name;
	VerbFn fn;
	bool clientSide;  // runs at once on the UI thread; otherwise queued for the game thread
};
const Verb Verbs[] = {
    {"help", CmdHelp, true},          {"echo", CmdEcho, true},           {"frames", CmdFrames, true},
    {"cltdo", CmdCltDo, true},        {"cltst", CmdCltSt, true},         {"slot", CmdSlot, true},          {"watch", CmdWatch, true},
    {"state", CmdState, false},       {"units", CmdUnits, false},        {"stat", CmdStat, false},        {"level", CmdLevel, false},        {"spawn", CmdSpawn, false},
    {"kill", CmdKill, false},         {"skill", CmdSkill, false},        {"setskill", CmdSetSkill, false},
    {"cast", CmdCast, false},         {"mcast", CmdMonsterCast, false},  {"missile", CmdMissile, false},
    {"missiles", CmdMissiles, false}, {"missilescan", CmdMissileScan, false}, {"waypoint", CmdWaypoint, false},
    {"objects", CmdObjects, false},   {"object", CmdObject, false},      {"operate", CmdOperate, false},
    {"objmode", CmdObjMode, false},   {"enter", CmdEnter, false},        {"dump", CmdDump, false},
    {"item", CmdItem, false},         {"identify", CmdIdentify, false},  {"items", CmdItems, false},
    {"equip", CmdItem, false},        {"unequip", CmdUnequip, false},
    {"pkt", CmdPkt, false},           {"pickup", CmdPickup, false},      {"cursor", CmdCursor, false},    {"ground", CmdGround, false},
    {"move", CmdMove, false},         {"packclear", CmdPackclear, false}, {"remove", CmdRemove, false},
    {"istat", CmdIstat, false},
    {"interact", CmdInteract, false}, {"msg", CmdMsg, false},          {"quest", CmdQuest, false},      {"xp", CmdXp, false},
    {"moveto", CmdMoveTo, false},     {"menu", CmdMenu, true}, {"lvlbtn", CmdLvlBtn, true},         {"presets", CmdPresets, false},  {"place", CmdPlace, false},
    {"walkmap", CmdWalkMap, false},   {"find", CmdFind, false},
    {"gold", CmdGold, false},        {"shop", CmdShop, false},        {"gamble", CmdGamble, false},     {"usecheck", CmdUseCheck, false},
    {"tiles", CmdTiles, false}, {"hashscan", CmdHashScan, false},
    {"states", CmdStates, false},     {"cstates", CmdClientStates, true}, {"cistat", CmdClientIstat, true}, {"durwatch", CmdDurWatch, true}, {"asserttrace", CmdAssertTrace, true},
    {"merc", CmdMerc, false},         {"mercprice", CmdMercPrice, false}, {"hire", CmdHire, false},
};

const Verb* FindVerb(const char* name) noexcept {
	for (const Verb& v : Verbs) {
		if (hcmd::LowerEq(name, v.name)) {
			return &v;
		}
	}
	return nullptr;
}

// SEH wrapper: a bad pointer in a game call must not take the whole game down.
auto RunVerb(const Verb* verb, Ctx* c, const hcmd::Tokens& t) noexcept -> int {
	__try {
		return verb->fn(c, t) ? 1 : 0;
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		return -2;
	}
}

void Finish(Ctx* c, int rc) noexcept {
	if (rc == 1) {
		Out("%s OK", c->verb);
	} else if (rc == -2) {
		Out("%s FAIL crashed (exception %s)", c->verb, c->why[0] != '\0' ? c->why : "in the game call");
	} else {
		Out("%s FAIL %s", c->verb, c->why[0] != '\0' ? c->why : "failed");
	}
}

// One queued server-side command (single slot: the mailbox runs one command at a time).
struct Job {
	hcmd::Tokens tokens;
	const Verb* verb = nullptr;
	volatile LONG state = 0;  // 0 idle, 1 queued, 2 running, 3 done
	int rc = 0;
	Ctx ctx;
};
Job g_job;

void RunTracking(Game* game) noexcept {
	__try {
		TrackMissiles(game);
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		InterlockedExchange(&g_trackMissiles, 0);
	}
}

void FrameHook(Game* game) {
	g_frameOriginal(game);
	if (game != nullptr) {
		HarnessGameFrame(game);
	}
}

}  // namespace

// Called by testharness.cpp only while the harness is on: the server frame hook that runs the queued verbs.
void HarnessCmdsContext(const D2RL::PluginContext* context) noexcept {
	g_context = context;
	if (g_frameHooked || context == nullptr) {
		return;
	}
	g_frameHooked = context->InstallInlineHook(RvaFrame, FrameEntry, sizeof(FrameEntry), reinterpret_cast<void*>(&FrameHook),
	                                           reinterpret_cast<void**>(&g_frameOriginal));
	context->LogInfo(g_frameHooked ? "mxl2012-core: test harness server frame hook on (0x406550)"
	                               : "mxl2012-core: test harness server frame hook FAILED (entry bytes differ): server verbs cannot run");
	// `item <code> set|unique <row>`: the generator takes the row asked for (no effect while no verb asks)
	g_itemGenHooked = context->InstallInlineHook(RvaItemGen, ItemGenEntry, sizeof(ItemGenEntry), reinterpret_cast<void*>(&ItemGenHook),
	                                             reinterpret_cast<void**>(&g_itemGenOriginal));
	context->LogInfo(g_itemGenHooked ? "mxl2012-core: test harness item generator hook on (0x43cd50)"
	                                 : "mxl2012-core: test harness item generator hook FAILED (entry bytes differ): no item rows");
}

void HarnessCmdsInit(uint64_t exeBase) noexcept {
	g_base = exeBase;
	d2r::Bind(exeBase);
	InterlockedExchange(&g_ready, 1);
}

// Game thread, after the server frame.
void HarnessGameFrame(void* gamePtr) noexcept {
	InterlockedIncrement(&g_frames);
	g_lastGame = gamePtr != nullptr;
	if (g_ready != 0 && g_trackMissiles != 0 && gamePtr != nullptr) {
		RunTracking(static_cast<Game*>(gamePtr));
	}
	if (g_ready == 0 || g_job.state != 1 || gamePtr == nullptr) {
		return;
	}
	if (InterlockedCompareExchange(&g_job.state, 2, 1) != 1) {
		return;
	}
	Game* game = static_cast<Game*>(gamePtr);
	Ctx& c = g_job.ctx;
	c = Ctx();
	std::snprintf(c.verb, sizeof(c.verb), "%s", g_job.verb->name);
	c.game = game;
	c.dataFlag = d2r::DataFlag(game);
	c.player = FindPlayer(game);
	if (c.player != nullptr) {
		InterlockedExchange(&g_playerId, static_cast<LONG>(IdOf(c.player)));
	}
	if (c.player == nullptr) {
		g_job.rc = 0;
		std::snprintf(c.why, sizeof(c.why), "no player in the game yet");
	} else {
		g_job.rc = RunVerb(g_job.verb, &c, g_job.tokens);
	}
	Finish(&c, g_job.rc);
	if (g_trackMissiles != 0) {  // a missile the verb made this frame may be gone after the next server frame
		RunTracking(game);
	}
	InterlockedExchange(&g_job.state, 3);
}

// UI thread (testharness.cpp ServiceCommands): "h <verb> ...". Returns 1 handled and OK, 0 failed, -2 crashed, -3 timed out.
auto HarnessCommand(const char* line) noexcept -> int {
	if (g_ready == 0) {
		return 0;
	}
	hcmd::Tokens all;
	hcmd::Split(line, &all);
	if (all.n < 2) {
		Out("usage: h <verb> ...   (h help)");
		return 0;
	}
	hcmd::Tokens t;  // the same tokens without the leading "h": t.tok[0] is the verb
	t.n = all.n - 1;
	for (int i = 0; i < t.n; ++i) {
		t.tok[i] = all.tok[i + 1];
	}
	const Verb* verb = FindVerb(t.tok[0]);
	if (verb == nullptr) {
		Out("%s FAIL unknown verb (h help)", t.tok[0]);
		return 0;
	}
	if (verb->clientSide) {
		Ctx c;
		std::snprintf(c.verb, sizeof(c.verb), "%s", verb->name);
		c.dataFlag = 2;
		const int rc = RunVerb(verb, &c, t);
		Finish(&c, rc);
		return rc;
	}
	if (!g_frameHooked) {
		Out("%s FAIL the server frame hook is off (see the log): server verbs cannot run", verb->name);
		return 0;
	}
	if (InterlockedCompareExchange(&g_job.state, 0, 1) == 1 || g_job.state == 3) {  // a never-run or finished job is replaced
		InterlockedExchange(&g_job.state, 0);
	}
	if (g_job.state != 0) {
		Out("%s FAIL previous command still running", verb->name);
		return 0;
	}
	g_job.verb = verb;
	std::memcpy(g_job.tokens.text, all.text, sizeof(all.text));  // the job keeps its own copy of the line
	g_job.tokens.n = t.n;
	for (int i = 0; i < t.n; ++i) {
		g_job.tokens.tok[i] = g_job.tokens.text + (t.tok[i] - all.text);
	}
	g_job.rc = 0;
	// Queued, not waited for: the server frames are driven from this (UI) thread's loop, so blocking here would starve
	// the very frame that runs the job. The game thread ends the command with an "h: <verb> OK|FAIL" line.
	InterlockedExchange(&g_job.state, 1);
	return 1;
}

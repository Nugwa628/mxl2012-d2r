// Akara's unlimited respec up to level 100 (owner request 2026-11-05; docs/plugin-plan.md section 31, off word akararespec).
//
// Median XL 2012 keeps 1.13c's Akara respec (once per difficulty, the Den of Evil reward; docs/median-rules-audit.md SK10), and
// D2R has the same rule in code, not data (akara_respec_logic.h has the bits):
//  - server, packet 0x39 (0x4b2530): the NPC within 50 whose static NPC row has the respec byte, then quest 41 bit 1, then the
//    respec (0x580f20(game, player, 0): skills refunded into stat 5, stat points back to the charstats start values, the
//    equipment re-checked) and the bookkeeping (0x5d9ae0: quest 41 bit 0 set, bit 1 cleared). For a player of level 1-100 the
//    hook finds the NPC and its row the same way and runs the same respec, without the quest test and the bookkeeping; every
//    other packet (and every player above 100) goes to D2R's handler unchanged.
//  - client, Akara's menu: the opener (0x1141d0) adds the line when Den of Evil is done (quest 1 bit 0) and the builder
//    (0x1147a0) keeps it when quest 41 bit 0 is clear and bit 1 set, both on the client's own copy of the record (0x2a48778).
//    While they run for Akara and a local player of level 1-100 the hooks show those bits as set / set / clear and put the real
//    ones back afterwards. The line's handler, its Yes / No page and the packet are D2R's. Above 100 the builder also keeps the
//    line in Hell once Den of Evil is done, with no respec waiting; there the builder hook shows quest 41 bit 0 as set (the
//    builder drops the line), so above 100 the line shows only while the Den's respec is waiting (owner, 2026-11-05).
// Multiplayer: the host's game decides (the server hook runs where the game runs); each player's own plugin shows the line.
#include "akara_respec.h"

#include "akara_respec_logic.h"
#include "d2r.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>

namespace {

using d2r::At;
using d2r::Game;
using d2r::Unit;
using namespace akara_respec;

constexpr uint64_t RvaRespecPacket = 0x4b2530;  // (game, player, packet, size) -> 0 handled, 1 refused
// push rbp / push rbx / push rsi / push rdi / push r14 / lea rbp,[rsp-0x37] / sub rsp,0xc0 (19 bytes; no rip-relative)
constexpr uint8_t RespecPacketEntry[] = {0x40, 0x55, 0x53, 0x56, 0x57, 0x41, 0x56, 0x48, 0x8d, 0x6c,
                                         0x24, 0xc9, 0x48, 0x81, 0xec, 0xc0, 0x00, 0x00, 0x00};
constexpr uint64_t RvaMenuOpener = 0x1141d0;  // (client npc unit, flag)
// push rbp / push rdi / push r13 / push r15 / mov rbp,rsp / sub rsp,0x48 (14 bytes)
constexpr uint8_t MenuOpenerEntry[] = {0x40, 0x55, 0x57, 0x41, 0x55, 0x41, 0x57, 0x48, 0x8b, 0xec, 0x48, 0x83, 0xec, 0x48};
constexpr uint64_t RvaMenuBuilder = 0x1147a0;  // (dataFlag)
// push rbp / push rbx / push rdi / push r12 / push r14 / lea rbp,[rsp-0x3f0] / sub rsp,0x4f0 (23 bytes)
constexpr uint8_t MenuBuilderEntry[] = {0x40, 0x55, 0x53, 0x57, 0x41, 0x54, 0x41, 0x56, 0x48, 0x8d, 0xac, 0x24,
                                        0x10, 0xfc, 0xff, 0xff, 0x48, 0x81, 0xec, 0xf0, 0x04, 0x00, 0x00};

constexpr uint64_t RvaNpcInRange = 0x53b8f0;   // (player, unit id, distance) -> the NPC unit or null
constexpr uint64_t RvaUnitClass = 0x349860;    // (unit, file, line) -> class id
constexpr uint64_t RvaNpcRow = 0x3971a0;       // (dataFlag, class) -> static NPC table row or null
constexpr uint64_t RvaRespec = 0x580f20;       // (game, player, 0)
constexpr uint64_t RvaGetStat = 0x2f5020;      // (unit, stat, layer)
constexpr uint64_t RvaLocalPlayerId = 0x8b2d0;  // () -> the local player's unit id (client)
constexpr uint64_t RvaPlayerById = 0x9a480;     // (id) -> the client's player unit
constexpr uint64_t RvaClientRecord = 0x2a48778;  // the client's quest record of the game
constexpr uint64_t RvaMenuNpcClass = 0x2a48764;  // u16: class of the NPC whose menu is up
constexpr uint64_t RvaMenuNpcId = 0x2a4875c;     // u32: unit id of the NPC whose menu is up
constexpr uint64_t RvaClientUnit = 0x9a5d0;      // (id, unit type) -> the client's unit
constexpr uint64_t RvaQuestTest = 0x325c50;     // (record, quest, bit)
constexpr uint64_t RvaQuestSet = 0x325c00;
constexpr uint64_t RvaQuestClear = 0x325990;
constexpr int32_t StatLevel = 12;

using PacketFn = int32_t (*)(Game*, Unit*, const uint8_t*, int32_t);
using OpenerFn = uint64_t (*)(Unit*, uint32_t);
using BuilderFn = uint64_t (*)(uint8_t);
using NpcInRangeFn = Unit* (*)(Unit*, uint32_t, int32_t);
using UnitClassFn = int32_t (*)(Unit*, const char*, int32_t);
using NpcRowFn = const uint8_t* (*)(uint32_t, int32_t);
using RespecFn = void (*)(Game*, Unit*, int32_t);
using GetStatFn = int32_t (*)(Unit*, int32_t, int32_t);
using LocalIdFn = uint32_t (*)();
using PlayerByIdFn = Unit* (*)(uint32_t);
using ClientUnitFn = Unit* (*)(uint32_t, int32_t);
using QuestFn = int32_t (*)(void*, int32_t, int32_t);

uint64_t g_base = 0;
PacketFn g_packet = nullptr;
OpenerFn g_opener = nullptr;
BuilderFn g_builder = nullptr;
volatile LONG g_respecs = 0;
volatile LONG g_toD2r = 0;
volatile LONG g_menus = 0;
volatile LONG g_hidden = 0;     // Akara menus built above 100 without the line (no respec waiting)
volatile LONG g_noRecord = 0;   // Akara menus built before the client had its quest record
volatile LONG g_lastLevel = -1;  // the local player's level at the last Akara menu
volatile LONG g_openerCalls = 0;
volatile LONG g_builderCalls = 0;
volatile LONG g_builderClass = -1;  // the menu NPC class the last builder call saw (global / by unit id)
volatile LONG g_builderUnitClass = -1;

template <typename F>
auto Fn(uint64_t rva) noexcept -> F {
	return reinterpret_cast<F>(g_base + rva);
}

auto Level(Unit* unit) noexcept -> int32_t {
	return unit != nullptr ? Fn<GetStatFn>(RvaGetStat)(unit, StatLevel, 0) : 0;
}

auto RespecPacket(Game* game, Unit* player, const uint8_t* packet, int32_t size) noexcept -> int32_t {
	const uint32_t id = packet != nullptr && size == PacketSize ? *reinterpret_cast<const uint32_t*>(packet + 1) : 0xffffffffu;
	bool offers = false;
	if (game != nullptr && player != nullptr && id != 0xffffffffu && Unlimited(Level(player))) {
		if (Unit* npc = Fn<NpcInRangeFn>(RvaNpcInRange)(player, id, NpcRange)) {
			const uint8_t* row = Fn<NpcRowFn>(RvaNpcRow)(d2r::DataFlag(game), Fn<UnitClassFn>(RvaUnitClass)(npc, "akara_respec", __LINE__));
			offers = row != nullptr && row[RowRespec] != 0;
		}
	}
	if (DecideServer(size, id, Level(player), offers) == Server::D2R) {
		InterlockedIncrement(&g_toD2r);
		return g_packet(game, player, packet, size);
	}
	Fn<RespecFn>(RvaRespec)(game, player, 0);
	InterlockedIncrement(&g_respecs);
	return 0;
}

// Runs `call` with the client's respec bits shown as "Den done, respec waiting, not used" when `npcClass` is Akara and the local
// player is level 1-100; for the builder (`builder`) and a player above 100 without a respec waiting, with quest 41 bit 0 shown
// as set. The real bits are put back afterwards (an inner call restores what the outer one showed).
template <typename Call>
auto WithBits(int32_t npcClass, bool builder, Call call) noexcept -> uint64_t {
	void* record = *reinterpret_cast<void* const*>(g_base + RvaClientRecord);
	if (npcClass != AkaraClass) {
		return call();
	}
	const int32_t level = Level(Fn<PlayerByIdFn>(RvaPlayerById)(Fn<LocalIdFn>(RvaLocalPlayerId)()));
	InterlockedExchange(&g_lastLevel, level);
	if (record == nullptr) {
		InterlockedIncrement(&g_noRecord);
	}
	if (record == nullptr) {
		return call();
	}
	const auto test = Fn<QuestFn>(RvaQuestTest);
	const auto put = [](void* rec, int32_t quest, int32_t bit, bool on) {
		Fn<QuestFn>(on ? RvaQuestSet : RvaQuestClear)(rec, quest, bit);
	};
	if (builder && HideLine(npcClass, level, test(record, RespecQuest, RespecReadyBit) != 0)) {
		const bool used = test(record, RespecQuest, RespecUsedBit) != 0;
		put(record, RespecQuest, RespecUsedBit, true);
		InterlockedIncrement(&g_hidden);
		const uint64_t result = call();
		put(record, RespecQuest, RespecUsedBit, used);
		return result;
	}
	if (!FakeClient(npcClass, level)) {
		return call();
	}
	const Bits real{test(record, DenQuest, DenDoneBit) != 0, test(record, RespecQuest, RespecReadyBit) != 0,
	                test(record, RespecQuest, RespecUsedBit) != 0};
	const Bits shown = Shown();
	put(record, DenQuest, DenDoneBit, shown.denDone);
	put(record, RespecQuest, RespecReadyBit, shown.ready);
	put(record, RespecQuest, RespecUsedBit, shown.used);
	InterlockedIncrement(&g_menus);
	const uint64_t result = call();
	put(record, DenQuest, DenDoneBit, real.denDone);
	put(record, RespecQuest, RespecReadyBit, real.ready);
	put(record, RespecQuest, RespecUsedBit, real.used);
	return result;
}

auto MenuOpener(Unit* npc, uint32_t flag) noexcept -> uint64_t {
	InterlockedIncrement(&g_openerCalls);
	return WithBits(npc != nullptr ? At<int32_t>(npc, d2r::UnitClass) : -1, false, [&] { return g_opener(npc, flag); });
}

auto MenuBuilder(uint8_t dataFlag) noexcept -> uint64_t {
	const int32_t npcClass = *reinterpret_cast<const int16_t*>(g_base + RvaMenuNpcClass);
	Unit* npc = Fn<ClientUnitFn>(RvaClientUnit)(*reinterpret_cast<const uint32_t*>(g_base + RvaMenuNpcId), 1);
	InterlockedIncrement(&g_builderCalls);
	InterlockedExchange(&g_builderClass, npcClass);
	InterlockedExchange(&g_builderUnitClass, npc != nullptr ? At<int32_t>(npc, d2r::UnitClass) : -1);
	return WithBits(npcClass, true, [&] { return g_builder(dataFlag); });
}

}  // namespace

auto InstallAkaraRespec(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int {
	g_base = context->exeBase;
	const bool server = context->InstallInlineHook(RvaRespecPacket, RespecPacketEntry, sizeof(RespecPacketEntry), reinterpret_cast<void*>(&RespecPacket),
	                                               reinterpret_cast<void**>(&g_packet));
	const bool opener = context->InstallInlineHook(RvaMenuOpener, MenuOpenerEntry, sizeof(MenuOpenerEntry), reinterpret_cast<void*>(&MenuOpener),
	                                               reinterpret_cast<void**>(&g_opener));
	const bool builder = context->InstallInlineHook(RvaMenuBuilder, MenuBuilderEntry, sizeof(MenuBuilderEntry), reinterpret_cast<void*>(&MenuBuilder),
	                                               reinterpret_cast<void**>(&g_builder));
	std::snprintf(report, reportSize, "Akara's respec without the Den of Evil limit up to level %d (packet 0x39 0x4b2530%s, menu opener 0x1141d0%s, builder 0x1147a0%s)",
	              MaxLevel, server ? "" : " FAILED", opener ? "" : " FAILED", builder ? "" : " FAILED");
	return (server ? 1 : 0) + (opener ? 1 : 0) + (builder ? 1 : 0);
}

void AkaraRespecCounts(long* respecs, long* toD2r, long* menus, long* noRecord, long* lastLevel) noexcept {
	*respecs = g_respecs;
	*toD2r = g_toD2r;
	*menus = g_menus;
	*noRecord = g_noRecord;
	*lastLevel = g_lastLevel;
}

void AkaraRespecTrace(char* out, size_t size) noexcept {
	std::snprintf(out, size, "menus without the line above 100 %ld; opener calls %ld, builder calls %ld, builder class %ld / by unit id %ld", g_hidden,
	              g_openerCalls, g_builderCalls, g_builderClass, g_builderUnitClass);
}

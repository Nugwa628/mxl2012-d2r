// The developer menu (docs/dev-menu.md; off word devmenu). Ctrl+F12 (the rebindable Controls action "Developer Menu", mxl_dev_menu) opens the
// native panel `mxl2012-core/DevMenu` (tools/devmenu_layout.py, HD and classic): searchable item spawning (uniques, sets, charms, quest / misc,
// bases, runeword kits), area travel, a level raise, waypoint unlocks on all three difficulties and the advanced quests action.
//
// Layering: the UI runs on the UI thread (ThreadService, WidgetService); buttons are native and their PanelManager messages name registered
// panels (send_stash.cpp); result names, the page line and the status are native text boxes the plugin fills through D2R's own text setter
// (WidgetService has none, and D2RLoader's overlay text does not show on this game). The button routing, the text setter and the search box
// typing fix are shared with the wiki panel: panel_shared.cpp.
// Every action is gated twice: by the UI on the press, and again on the game thread in Execute(). Nothing is built from free text: the input
// box only filters the catalog and gives a level number; an action names a catalog row, a level id or a fixed console command.
//
// The gate (devmenu_logic.h Gate): the catalog is loaded, a client player exists, a server frame of this process found that player (false on
// a joiner's client: there is no local server), and the local server has exactly one client and this process has no listening TCP socket
// (GetExtendedTcpTable; a host listens as soon as the TCP game exists). The socket table is read when the action is queued and again when it
// runs; when it cannot be read the gate treats it as listening. Each failure refuses the action.
//
// Mutations happen only in a loader game-thread callback (runOnGameThread). Items go through ItemService (D2R's creator, its placement and
// socket rules): backpack, else Cube, else personal stash; what fits nowhere is not created and the panel says so. Level raises go through D2R's experience award, which applies the level-ups and the stat and skill points, and verify the
// level. Travel is D2R's own warp moves (via the town of the target act when the act changes) and waits for the server to report arrival.
// Waypoints use D2R's waypoint setter on each difficulty's record and the act-tab quest words. The quests action is the loader's `quests`
// cheat through its ExecuteConsoleCommand export, with the fixed command text. Nothing is written to the save except what the game saves.
//
// The catalog (work/mod/data/mxl2012-devmenu/catalog.tsv, tools/devmenu_catalog.py) is the mod's own file beside its tables.
#include "devmenu.h"

#include "d2r.h"
#include "devmenu_logic.h"
#include "mxl_devmenu_layout.h"
#include "panel_shared.h"
#include "server_frame.h"

#include <D2RLPlugin/core_exports.h>
#include <D2RLPlugin/input.h>
#include <D2RLPlugin/inventory.h>
#include <D2RLPlugin/item.h>
#include <D2RLPlugin/panels.h>
#include <D2RLPlugin/threads.h>
#include <D2RLPlugin/widgets.h>

#include <winsock2.h>
#include <windows.h>

#include <ws2ipdef.h>
#include <iphlpapi.h>

#include <algorithm>
#include <atomic>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>

namespace {

using namespace devmenu;
namespace layout = devmenu_layout;

// game functions (image 0x6ab3782c; the plugin's image check guards all of them)
constexpr uint64_t RvaLocalId = 0x8b2d0;         // () -> the client's own player id
constexpr uint64_t RvaClientPlayer = 0x9a480;    // (id) -> the client's player unit
constexpr uint64_t RvaServerUnit = 0x48fe80;     // (game, type, id) -> server unit
constexpr uint64_t RvaGetStat = 0x2f5020;        // (unit, stat, layer)
constexpr uint64_t RvaAddExperience = 0x44f2e0;  // (game, unit, old level, amount)
constexpr uint64_t RvaPlayerData = 0x34b240;     // (player) -> player data: +0x40 / +0x58 + difficulty * 8 = quest / waypoint record
constexpr uint64_t RvaWaypointSet = 0x3d6890;    // (record, number)
constexpr uint64_t RvaQuestSet = 0x325c00;       // (record, word, bit)
constexpr uint64_t RvaUnitRoom = 0x34b440;       // (unit) -> room
constexpr uint64_t RvaRoomLevel = 0x2efc10;      // (room) -> level id
constexpr uint64_t RvaTravel = 0x4f2e40;         // (game, player, level, 0): NPC travel, across acts
constexpr uint64_t RvaLevelWarp = 0x488180;      // (game, player, level, 0): the warp inside an act
constexpr uint64_t RvaItemData = 0x34a500;       // (item) -> item data, +0x18 the flag word (cube_dupe.cpp, harness_cmds.cpp)
constexpr int ItemDataFlags = 0x18;
constexpr int UnitIdOffset = 0x08;
constexpr int GameClients = 0x138, ClientNext = 0x628;
constexpr int StatLevel = 12, StatExperience = 13;
constexpr int Difficulties = 3;
constexpr int ForcedRowTries = 64;
constexpr uint32_t ItemLevel = 99;
constexpr uint32_t ForcedRowItemLevel = 127;  // Median set and unique rows have levels above 99; the item level field is 7 bits
constexpr unsigned TcpGamePort = 4000;
constexpr uint64_t TravelTimeoutMs = 15000;
constexpr uint64_t HopSettleMs = 2000;  // the client loads the new act before the second move (a warp during the load ends the game)
constexpr int ListWalkLimit = 64;

using GetStatFn = int32_t (*)(d2r::Unit*, int32_t, int32_t);
using ItemDataFn = uint8_t* (*)(d2r::Unit*);
using AddExperienceFn = void (*)(d2r::Game*, d2r::Unit*, int32_t, int32_t);
using PlayerDataFn = uint8_t* (*)(d2r::Unit*);
using WaypointSetFn = int32_t (*)(void*, int32_t);
using QuestSetFn = int32_t (*)(void*, int32_t, int32_t);
using UnitRoomFn = void* (*)(d2r::Unit*);
using RoomLevelFn = int32_t (*)(void*);
using TravelFn = void (*)(d2r::Game*, d2r::Unit*, int32_t, int32_t);
using ServerUnitFn = d2r::Unit* (*)(d2r::Game*, int32_t, uint32_t);
using LocalIdFn = uint32_t (*)();
using ClientPlayerFn = void* (*)(uint32_t);
using ExtTcpFn = DWORD(WINAPI*)(PVOID, PDWORD, BOOL, ULONG, TCP_TABLE_CLASS, ULONG);

const D2RL::PluginContext* g_context = nullptr;
const D2RL::ThreadService* g_threads = nullptr;
const D2RL::WidgetService* g_widgets = nullptr;
const D2RL::PanelService* g_panels = nullptr;
const D2RL::ItemService* g_items = nullptr;
const D2RL::InventoryService* g_inventory = nullptr;
const D2RL::InputService* g_input = nullptr;
D2RL::Panels::RegistrationHandle g_panel = 0;
D2RL::Input::ActionHandle g_action = D2RL::Input::InvalidHandle;
uint64_t g_base = 0;
bool g_on = false;
ExtTcpFn g_extTcp = nullptr;

template <class F>
auto Fn(uint64_t rva) noexcept -> F {
	return reinterpret_cast<F>(g_base + rva);
}

// --- catalog ------------------------------------------------------------------------------------------------------------------
Catalog g_catalog;  // read once at load, read-only afterwards

// --- state shared across threads ----------------------------------------------------------------------------------------------
panel_shared::Client g_client;              // the menu's part of the shared panel code (panel_shared.h)
std::atomic<bool>& g_open = g_client.open;  // the panel is open
std::atomic<bool> g_tickQueued{false};
std::atomic<bool> g_toggleQueued{false};
std::atomic<bool> g_busy{false};             // an action is in flight (one at a time, travel included)
std::atomic<uint32_t> g_clientPlayer{0};     // the client's own player unit id (UI tick; 0 can be a real id)
std::atomic<bool> g_hasClient{false};        // a client player exists
std::atomic<uint32_t> g_hostPlayer{0};       // that player, when a server frame of this process found it
std::atomic<bool> g_hostFound{false};
std::atomic<int> g_clients{0};               // clients of the local server game
std::atomic<d2r::Game*> g_game{nullptr};     // the local server game of the last frame
std::atomic<long> g_presses{0}, g_actions{0}, g_refused{0}, g_faults{0}, g_listenChecks{0}, g_listeners{0}, g_gameOps{0}, g_taken{0}, g_done{0};

std::atomic<long>& g_textsSet = g_client.textsSet;
std::atomic<long>& g_textFails = g_client.textFails;
std::atomic<long> g_socketFails{0};                       // spawned items whose sockets did not read back as real
std::atomic<uint32_t> g_lastItemFlags{0};                 // the native flag word of the last spawned item that asked for sockets
std::string g_portsSeen;
std::mutex g_uiMutex;          // guards the strings the native text boxes show
std::string g_rowTexts[layout::MaxRows];
int g_rowCount = 0;
std::string g_header, g_status = "Ready. Ctrl+F12 closes this menu.";
std::string g_queryShown;      // the input box's text, for the harness's status line
std::atomic<bool>& g_boxFocus = g_client.boxFocus;      // the box has the UI focus (keys type into it), as of the last UI tick
std::atomic<bool>& g_boxClicked = g_client.boxClicked;  // the last left click while the menu was open was on the box
std::atomic<bool> g_drawHd{true};

// UI-thread-only state
int g_tab = 0;
Category g_cat = Category::All;
std::string g_query;
std::string g_testInput;    // the harness's "input" verb (unset: the input box)
bool g_testInputSet = false;
int g_pageIndex = 0;
std::vector<Hit> g_itemHits;
std::vector<TravelRow> g_travelHits;
bool g_rowHeading[layout::MaxRows] = {};  // the row is a heading: no arrow
char g_rowKinds[layout::MaxRows + 1] = {};  // per shown row: I item, H heading, U uber level, A area (the harness's status line; g_uiMutex)
bool g_dirty = true;
bool g_questArmed = false;  // the Quests tab: warning shown, Confirm visible
std::string g_shownRows[layout::MaxRows], g_shownHeader[layout::HeaderLines], g_shownStatus[layout::StatusLines];  // what the text boxes hold
bool g_shownValid = false;  // false: resend every line (a new panel or graphics mode)
std::vector<int> g_presses_q;  // queued button indices
std::mutex g_pressMutex;

enum class ActionKind : uint8_t { Item, Kit, Travel, UberTravel, Raise, Unlock };

struct Action {
	ActionKind kind = ActionKind::Item;
	int index = 0;  // Catalog::items / kits / levels / ubers index, or the target level
};

Action g_pending;

// travel in flight (game thread: Execute starts it, the server frame ends it)
struct Travel {
	bool on = false;
	int target = 0;        // level id
	int current = 0;       // the id the current hop aims at
	int hopWarp = 0;       // 0 waits for current == target; a level id to warp to next once in the act's town
	uint64_t start = 0;
	uint64_t hopAt = 0;    // when the player reached the town (0: not yet)
	int uber = -1;         // Catalog::ubers index when the travel goes to the area right before that uber level
} g_travel;

constexpr int ActTowns[] = {1, 40, 75, 103, 109};

void SetStatus(const std::string& text) {
	const std::lock_guard<std::mutex> lock(g_uiMutex);
	g_status = text;
}

void LogLine(const char* text) {
	if (g_context != nullptr) {
		char line[320];
		std::snprintf(line, sizeof(line), "devmenu: %s", text);
		g_context->LogInfo(line);
	}
}

auto Fmt(const char* format, ...) -> std::string {
	char buf[320];
	va_list args;
	va_start(args, format);
	std::vsnprintf(buf, sizeof(buf), format, args);
	va_end(args);
	return buf;
}

// --- the multiplayer gate -------------------------------------------------------------------------------------------------------
// True when this process listens on the D2 TCP/IP game port (4000), or the socket table cannot be read (fail closed). Single player does
// listen on other ports (seen in game: `ports=` of the status line), so only the game port counts.
auto ProcessListens() noexcept -> bool {
	g_listenChecks.fetch_add(1);
	if (g_extTcp == nullptr) {
		return true;
	}
	const DWORD self = GetCurrentProcessId();
	bool hosting = false;
	char ports[96] = "";
	size_t used = 0;
	const auto note = [&](DWORD pid, DWORD rawPort) {
		if (pid != self) {
			return;
		}
		const unsigned port = ((rawPort & 0xff) << 8) | ((rawPort >> 8) & 0xff);
		hosting = hosting || port == TcpGamePort;
		if (used + 8 < sizeof(ports)) {
			used += static_cast<size_t>(std::snprintf(ports + used, sizeof(ports) - used, "%u,", port));
		}
	};
	for (ULONG family : {AF_INET, AF_INET6}) {
		DWORD size = 0;
		DWORD rc = g_extTcp(nullptr, &size, FALSE, family, TCP_TABLE_OWNER_PID_LISTENER, 0);
		if (rc != ERROR_INSUFFICIENT_BUFFER && rc != NO_ERROR) {
			return true;
		}
		std::vector<BYTE> buf(size + 256);
		size = static_cast<DWORD>(buf.size());
		rc = g_extTcp(buf.data(), &size, FALSE, family, TCP_TABLE_OWNER_PID_LISTENER, 0);
		if (rc != NO_ERROR) {
			return true;
		}
		if (family == AF_INET) {
			const auto* table = reinterpret_cast<const MIB_TCPTABLE_OWNER_PID*>(buf.data());
			for (DWORD i = 0; i < table->dwNumEntries; ++i) {
				note(table->table[i].dwOwningPid, table->table[i].dwLocalPort);
			}
		} else {
			const auto* table = reinterpret_cast<const MIB_TCP6TABLE_OWNER_PID*>(buf.data());
			for (DWORD i = 0; i < table->dwNumEntries; ++i) {
				note(table->table[i].dwOwningPid, table->table[i].dwLocalPort);
			}
		}
	}
	if (hosting) {
		g_listeners.fetch_add(1);
	}
	{
		const std::lock_guard<std::mutex> lock(g_uiMutex);
		g_portsSeen = ports;
	}
	return hosting;
}

auto CurrentGate(bool includeBusy) noexcept -> Refusal {
	GateState s;
	s.catalogOk = g_catalog.ok;
	const uint32_t id = g_clientPlayer.load();
	s.inGame = g_hasClient.load();
	s.localServer = s.inGame && g_hostFound.load() && g_hostPlayer.load() == id;
	s.clients = g_clients.load();
	s.listening = ProcessListens();
	s.busy = includeBusy && g_busy.load();
	return Gate(s);
}

auto Refuse(Refusal r) noexcept -> bool {
	if (r == Refusal::None) {
		return false;
	}
	g_refused.fetch_add(1);
	SetStatus(RefusalText(r));
	return true;
}

// --- game-thread actions -------------------------------------------------------------------------------------------------------
auto ServerPlayer(d2r::Game* game) noexcept -> d2r::Unit* {
	return game != nullptr && g_hasClient.load() ? Fn<ServerUnitFn>(RvaServerUnit)(game, 0, g_clientPlayer.load()) : nullptr;
}

auto LevelOf(d2r::Unit* player) noexcept -> int {
	void* room = Fn<UnitRoomFn>(RvaUnitRoom)(player);
	return room != nullptr ? Fn<RoomLevelFn>(RvaRoomLevel)(room) : -1;
}

auto ClassOf(d2r::Unit* player) noexcept -> int {
	return d2r::At<int32_t>(player, d2r::UnitClass);
}

auto Stat(d2r::Unit* player, int stat) noexcept -> int32_t {
	return Fn<GetStatFn>(RvaGetStat)(player, stat, 0);
}

// The new item's sockets read back from the native item (devmenu_logic.h SocketsReal): count and flag word, for the status and the check.
// Read only: the item service sets both, and a change here would not reach the client's copy. Game thread.
struct NativeSockets {
	uint32_t flags = 0;
	int32_t count = 0;
};

void __cdecl ReadSockets(const D2RL::PluginContext*, void* native, void* user) noexcept {
	auto* s = static_cast<NativeSockets*>(user);
	auto* item = static_cast<d2r::Unit*>(native);
	const uint8_t* data = item != nullptr ? Fn<ItemDataFn>(RvaItemData)(item) : nullptr;
	if (data != nullptr) {
		s->flags = d2r::At<uint32_t>(data, ItemDataFlags);
		s->count = Fn<GetStatFn>(RvaGetStat)(item, StatNumSockets, 0);
	}
}

void CheckSockets(D2RL::ItemHandle item, uint32_t sockets) noexcept {
	NativeSockets s;
	const D2RL::Items::Result rc =
	    g_items->editNativeItem != nullptr ? g_items->editNativeItem(g_context, item, &ReadSockets, &s) : D2RL::Items::Result::Unavailable;
	g_lastItemFlags.store(s.flags);
	if (rc != D2RL::Items::Result::Success || !SocketsReal(sockets, s.flags, s.count)) {
		g_socketFails.fetch_add(1);
		LogLine(Fmt("sockets: asked %u, count %d, flags 0x%x, read %u", sockets, s.count, s.flags, static_cast<unsigned>(rc)).c_str());
	}
}

// One created item in `container`; returns the handle or 0.
auto CreateOne(D2RL::PlayerHandle player, uint32_t code, uint32_t quality, int32_t row, uint32_t sockets, D2RL::Items::ItemContainer container,
               D2RL::Items::Result* rc, D2RL::Items::ItemInfo* info) noexcept -> D2RL::ItemHandle {
	D2RL::Items::ItemCreateSpec spec{};
	spec.structSize = D2RL::Items::ItemCreateSpecSize;
	spec.code = code;
	spec.quality = static_cast<D2RL::Items::Quality>(quality);
	spec.qualityRecordId = row >= 0 ? static_cast<uint32_t>(row) : D2RL::Items::RandomQualityRecord;
	spec.itemLevel = row >= 0 ? ForcedRowItemLevel : ItemLevel;
	spec.quantity = D2RL::Items::DefaultValue;
	spec.durability = D2RL::Items::DefaultValue;
	spec.socketCount = sockets;
	spec.stateFlags = SpawnIdentified(quality) ? D2RL::Items::ItemStateIdentified : 0;  // "Socketed (N)", not "Max Sockets: N"
	spec.flags = quality == QualityUnique ? D2RL::Items::ItemCreateFlagBit(D2RL::Items::ItemCreateFlag::AllowDuplicateUnique) : 0;
	spec.destination.structSize = D2RL::Items::ItemDestinationSize;
	spec.destination.container = container;
	spec.destination.placement = D2RL::Items::Placement::Automatic;
	D2RL::ItemHandle item = D2RL::InvalidItemHandle;
	*rc = g_items->createItem(g_context, player, &spec, &item);
	if (*rc == D2RL::Items::Result::Success && sockets > 0) {
		CheckSockets(item, sockets);
	}
	if (*rc == D2RL::Items::Result::Success && info != nullptr) {
		info->structSize = D2RL::Items::ItemInfoSize;
		(void)g_items->getItemInfo(g_context, item, info);
	}
	return *rc == D2RL::Items::Result::Success ? item : D2RL::InvalidItemHandle;
}

auto LocalPlayerHandle() noexcept -> D2RL::PlayerHandle {
	D2RL::PlayerHandle player = D2RL::InvalidPlayerHandle;
	(void)g_inventory->getLocalPlayer(g_context, &player);
	return player;
}

// Backpack, else Cube, else personal stash: an item that fits nowhere is not created at all, and the caller says so. (ItemService's ground
// placement ends in a crash on this build, with Automatic and with Exact at the player's feet.)
struct Placed {
	D2RL::ItemHandle handle = D2RL::InvalidItemHandle;
	const char* where = "";
	D2RL::Items::Result rc = D2RL::Items::Result::Unavailable;
};

auto PlaceSomewhere(D2RL::PlayerHandle player, uint32_t code, uint32_t quality, int32_t row, uint32_t sockets, D2RL::Items::ItemInfo* info) noexcept -> Placed {
	static constexpr struct {
		D2RL::Items::ItemContainer container;
		const char* text;
	} Order[] = {{D2RL::Items::ItemContainer::Inventory, "in your backpack"},
	             {D2RL::Items::ItemContainer::Cube, "in your Horadric Cube (the backpack could not take it)"},
	             {D2RL::Items::ItemContainer::PersonalStash, "in your stash (the backpack and Cube could not take it)"}};
	Placed out;
	bool first = true;
	for (const auto& o : Order) {
		D2RL::Items::Result rc = D2RL::Items::Result::Unavailable;
		// the item service often answers Unsupported for a forced set amulet row; the same row is created on a later try
		for (int attempt = 0; attempt < (row >= 0 ? ForcedRowTries : 1); ++attempt) {
			out.handle = CreateOne(player, code, quality, row, sockets, o.container, &rc, info);
			if (out.handle != D2RL::InvalidItemHandle || rc != D2RL::Items::Result::Unsupported) {
				break;
			}
		}
		if (out.handle != D2RL::InvalidItemHandle) {
			out.where = o.text;
			out.rc = rc;
			return out;
		}
		LogLine(Fmt("item %08x quality %u row %d not placed %s: result %u", code, quality, row, o.text, static_cast<unsigned>(rc)).c_str());
		if (first) {
			out.rc = rc;  // the backpack's answer says why: the later containers only repeat or refuse the fallback
			first = false;
		}
	}
	return out;
}

void DoItem(const Item& item) noexcept {
	const D2RL::PlayerHandle player = LocalPlayerHandle();
	if (player == D2RL::InvalidPlayerHandle) {
		SetStatus("No local player.");
		return;
	}
	D2RL::Items::ItemInfo info{};
	const uint32_t sockets = SpawnSockets(item);
	const Placed placed = PlaceSomewhere(player, item.code, item.quality, item.row, sockets, &info);
	if (placed.handle == D2RL::InvalidItemHandle) {
		SetStatus(Fmt("%s was not created: no room or refused (item service result %u). Nothing was lost.", item.name.c_str(), static_cast<unsigned>(placed.rc)));
		return;
	}
	if (item.row >= 0 && (info.qualityRecordId != item.row || info.code != item.code)) {
		SetStatus(Fmt("%s: the game made another item (row %d, wanted %d).", item.name.c_str(), info.qualityRecordId, item.row));
		return;
	}
	SetStatus(sockets > 0 ? Fmt("Spawned %s with %u of %u sockets %s.", item.name.c_str(), info.socketCount, sockets, placed.where)
	                      : Fmt("Spawned %s %s.", item.name.c_str(), placed.where));
	g_gameOps.fetch_add(1);
}

void DoKit(const Kit& kit) noexcept {
	const D2RL::PlayerHandle player = LocalPlayerHandle();
	if (player == D2RL::InvalidPlayerHandle) {
		SetStatus("No local player.");
		return;
	}
	D2RL::Items::ItemInfo info{};
	const Placed base = PlaceSomewhere(player, kit.base, QualityNormal, -1, static_cast<uint32_t>(kit.sockets), &info);
	if (base.handle == D2RL::InvalidItemHandle) {
		SetStatus(Fmt("Kit for %s: the base was not created (item service result %u). Nothing was made.", kit.name.c_str(), static_cast<unsigned>(base.rc)));
		return;
	}
	size_t made = 0;
	for (uint32_t rune : kit.runes) {
		if (PlaceSomewhere(player, rune, QualityNormal, -1, 0, nullptr).handle != D2RL::InvalidItemHandle) {
			++made;
		}
	}
	if (made == kit.runes.size()) {
		SetStatus(Fmt("Kit for %s: the base (%u of %d sockets, %s) and %zu runes. Socket the runes in order.", kit.name.c_str(), info.socketCount, kit.sockets, base.where, made));
		g_gameOps.fetch_add(1);
	} else {
		SetStatus(Fmt("Kit for %s is incomplete: the base and %zu of %zu runes (no room). Free some space for the rest.", kit.name.c_str(), made, kit.runes.size()));
	}
}

void DoRaise(d2r::Game* game, d2r::Unit* player, int target) noexcept {
	const int level = Stat(player, StatLevel), cls = ClassOf(player);
	const bool table = ClassOk(cls) && g_catalog.thresholds[cls][MaxLevel - 1] > 0;
	const Raise check = CheckRaise(level, target, MaxLevel, table);
	if (check != Raise::Ok) {
		SetStatus(check == Raise::NotHigher ? Fmt("Already level %d.", level) : check == Raise::TooHigh ? Fmt("The level limit is %d.", MaxLevel) : std::string("No experience table for this class."));
		return;
	}
	long long remaining = XpToReach(g_catalog.thresholds[cls], target, static_cast<uint32_t>(Stat(player, StatExperience)));
	for (int attempts = 0; remaining > 0 && attempts < 8 && Stat(player, StatLevel) < target; ++attempts) {
		const int32_t amount = static_cast<int32_t>(remaining > 2147483647LL ? 2147483647LL : remaining);
		Fn<AddExperienceFn>(RvaAddExperience)(game, player, Stat(player, StatLevel), amount);
		remaining = XpToReach(g_catalog.thresholds[cls], target, static_cast<uint32_t>(Stat(player, StatExperience)));
	}
	const int reached = Stat(player, StatLevel);
	SetStatus(reached >= target ? Fmt("You are now level %d. Your points are on the character screen.", reached) : Fmt("Reached level %d of %d.", reached, target));
	g_gameOps.fetch_add(1);
}

void DoUnlock(d2r::Game*, d2r::Unit* player) noexcept {
	uint8_t* data = Fn<PlayerDataFn>(RvaPlayerData)(player);
	if (data == nullptr) {
		SetStatus("No player data.");
		return;
	}
	const auto numbers = WaypointNumbers(g_catalog);
	int records = 0;
	for (int d = 0; d < Difficulties; ++d) {
		auto* waypoints = d2r::At<void*>(data, 0x58 + d * 8);
		auto* quests = d2r::At<void*>(data, 0x40 + d * 8);
		if (waypoints == nullptr) {
			continue;
		}
		++records;
		for (int n : numbers) {
			Fn<WaypointSetFn>(RvaWaypointSet)(waypoints, n);
		}
		if (quests != nullptr) {
			for (int word : ActWords) {
				for (int bit : ActWordBits) {
					Fn<QuestSetFn>(RvaQuestSet)(quests, word, bit);
				}
			}
		}
	}
	SetStatus(Fmt("Waypoints unlocked on %d of %d difficulties (%zu numbers, act tabs included). Open a waypoint to see them.", records, Difficulties, numbers.size()));
	g_gameOps.fetch_add(1);
}

auto TownOfAct(int act) noexcept -> int {
	return act >= 0 && act < 5 ? ActTowns[act] : -1;
}

void Warp(d2r::Game* game, d2r::Unit* player, int level, bool npc) noexcept {
	Fn<TravelFn>(npc ? RvaTravel : RvaLevelWarp)(game, player, level, 0);
}

void DoTravel(d2r::Game* game, d2r::Unit* player, const Level& target) noexcept {
	const int from = LevelOf(player);
	const Level* fromLevel = from > 0 ? FindLevel(g_catalog, from) : nullptr;
	if (fromLevel == nullptr) {
		SetStatus("Cannot travel from here (no room yet).");
		g_busy.store(false);
		return;
	}
	const int actTo = target.act;
	g_travel.target = target.id;
	g_travel.start = GetTickCount64();
	g_travel.hopAt = 0;
	if (UseNpcTravel(fromLevel->act, actTo)) {
		const int town = TownOfAct(actTo);
		if (town < 0) {
			SetStatus("No town for that act.");
			g_busy.store(false);
			return;
		}
		if (target.id == town) {
			g_travel.current = town;
			g_travel.hopWarp = 0;
		} else {
			g_travel.current = town;
			g_travel.hopWarp = target.id;
		}
		Warp(game, player, town, true);
	} else {
		g_travel.current = target.id;
		g_travel.hopWarp = 0;
		Warp(game, player, target.id, false);
	}
	g_travel.on = true;
	g_travel.uber = -1;
	SetStatus(Fmt("Traveling to %s...", target.name.c_str()));
}

void TravelDone(const std::string& text) noexcept {
	g_travel.on = false;
	SetStatus(text);
	g_gameOps.fetch_add(1);
	g_busy.store(false);
}

void ExecuteInner() {
	d2r::Game* game = g_game.load();
	d2r::Unit* player = ServerPlayer(game);
	const Refusal r = player == nullptr ? Refusal::NotInGame : CurrentGate(false);
	if (r != Refusal::None) {
		Refuse(r);
		g_busy.store(false);
		return;
	}
	g_taken.fetch_add(1);
	const Action a = g_pending;
	switch (a.kind) {
	case ActionKind::Item:
		DoItem(g_catalog.items[static_cast<size_t>(a.index)]);
		break;
	case ActionKind::Kit:
		DoKit(g_catalog.kits[static_cast<size_t>(a.index)]);
		break;
	case ActionKind::Raise:
		DoRaise(game, player, a.index);
		break;
	case ActionKind::Unlock:
		DoUnlock(game, player);
		break;
	case ActionKind::Travel:
		DoTravel(game, player, g_catalog.levels[static_cast<size_t>(a.index)]);
		return;  // ends in the frame callback
	case ActionKind::UberTravel: {
		const Uber& u = g_catalog.ubers[static_cast<size_t>(a.index)];
		const Level* entry = FindLevel(g_catalog, u.entry);
		if (entry == nullptr) {
			SetStatus(Fmt("No area %d in the catalog.", u.entry));
			break;
		}
		DoTravel(game, player, *entry);
		if (g_travel.on) {
			g_travel.uber = a.index;
			SetStatus(Fmt("Traveling to %s, right before %s...", entry->name.c_str(), u.name.c_str()));
		}
		return;  // ends in the frame callback
	}
	}
	g_busy.store(false);
}

void __cdecl Execute(const D2RL::PluginContext*, void*) noexcept {
	__try {
		ExecuteInner();
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		g_faults.fetch_add(1);
		g_busy.store(false);
	}
}

auto Enqueue(ActionKind kind, int index) -> void {
	if (Refuse(CurrentGate(true))) {
		return;
	}
	g_busy.store(true);
	g_pending = Action{kind, index};
	g_actions.fetch_add(1);
	if (g_threads->runOnGameThread(g_context, &Execute, nullptr) != D2RL::Threads::Result::Success) {
		g_busy.store(false);
		Refuse(Refusal::NoGameThread);
	}
}

// Every server frame: records the local game's clients and player; ends a travel when the server reports arrival.
void FrameInner(d2r::Game* game) {
	const uint32_t id = g_clientPlayer.load();
	int clients = 0;
	for (auto* client = d2r::At<uint8_t*>(game, GameClients); client != nullptr && clients < ListWalkLimit; client = d2r::At<uint8_t*>(client, ClientNext)) {
		++clients;
	}
	g_clients.store(clients);
	g_game.store(game);
	if (g_hasClient.load() && Fn<ServerUnitFn>(RvaServerUnit)(game, 0, id) != nullptr) {
		g_hostPlayer.store(id);
		g_hostFound.store(true);
	}
	if (!g_travel.on) {
		return;
	}
	d2r::Unit* player = ServerPlayer(game);
	if (player == nullptr) {
		TravelDone("Lost the player during travel.");
		return;
	}
	if (GetTickCount64() - g_travel.start > TravelTimeoutMs) {
		TravelDone(Fmt("No arrival in level %d.", g_travel.target));
		return;
	}
	if (LevelOf(player) != g_travel.current) {
		return;
	}
	if (g_travel.hopWarp != 0) {
		const uint64_t now = GetTickCount64();
		if (g_travel.hopAt == 0) {
			g_travel.hopAt = now;
			return;
		}
		if (now - g_travel.hopAt < HopSettleMs) {
			return;
		}
		const int target = g_travel.hopWarp;
		g_travel.hopWarp = 0;
		g_travel.current = target;
		g_travel.start = now;
		Warp(game, player, target, false);
		return;
	}
	if (g_travel.uber >= 0 && g_travel.uber < static_cast<int>(g_catalog.ubers.size())) {
		TravelDone(UberArrivalText(g_catalog, g_catalog.ubers[static_cast<size_t>(g_travel.uber)]));
		return;
	}
	const Level* level = FindLevel(g_catalog, g_travel.target);
	TravelDone(Fmt("You arrived in %s.%s", level != nullptr ? level->name.c_str() : "?", level != nullptr && level->note == 1 ? " Map only: the fight needs its normal summon." : ""));
}

void Frame(d2r::Game* game) noexcept {
	__try {
		FrameInner(game);
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		g_faults.fetch_add(1);
		g_travel.on = false;
		g_busy.store(false);
	}
}

// --- native text ------------------------------------------------------------------------------------------------------------
// The result names, page line and status are TextBoxWidgets of the panel, filled with D2R's own text setter (panel_shared.cpp).
void SetLine(void* panel, const char* name, std::string& shown, const std::string& want, bool force) {
	panel_shared::SetLine(g_client, panel, name, shown, want, force);
}

void ApplyTexts() {
	void* panel = panel_shared::NativePanel(g_client);
	if (panel == nullptr) {
		return;
	}
	const auto& m = g_drawHd.load() ? layout::Hd : layout::Sd;
	std::string rows[layout::MaxRows], header, status;
	int count = 0;
	{
		const std::lock_guard<std::mutex> lock(g_uiMutex);
		count = g_rowCount;
		for (int i = 0; i < count && i < m.rows; ++i) {
			rows[i] = g_rowTexts[i];
		}
		header = g_header;
		status = g_status;
	}
	const bool force = !g_shownValid;
	g_shownValid = true;
	for (int i = 0; i < m.rows; ++i) {
		SetLine(panel, Fmt("RowText%d", i).c_str(), g_shownRows[i], i < count ? Ellipsize(rows[i], static_cast<size_t>(m.rowChars)) : std::string(), force);
	}
	const auto chars = [](const std::string& text) { return static_cast<float>(text.size()); };
	const auto headerLines = WrapText(header, static_cast<float>(m.headerChars), static_cast<size_t>(layout::HeaderLines), chars);
	for (int i = 0; i < layout::HeaderLines; ++i) {
		SetLine(panel, Fmt("HeaderText%d", i).c_str(), g_shownHeader[i], static_cast<size_t>(i) < headerLines.size() ? headerLines[static_cast<size_t>(i)] : std::string(), force);
	}
	const auto lines = WrapText(status, static_cast<float>(m.statusChars), static_cast<size_t>(layout::StatusLines), chars);
	for (int i = 0; i < layout::StatusLines; ++i) {
		SetLine(panel, Fmt("StatusText%d", i).c_str(), g_shownStatus[i], static_cast<size_t>(i) < lines.size() ? lines[static_cast<size_t>(i)] : std::string(), force);
	}
}

// --- typing into the search / level box --------------------------------------------------------------------------------------
// The typing fix (bound keys type into the focused box instead of running their commands) is panel_shared.cpp "typing"; the menu says where its
// box is, so a left click on it gives it the keyboard and a click anywhere else takes it away.
std::atomic<long>& g_keysTaken = g_client.keysTaken;
std::atomic<long>& g_keysHeld = g_client.keysHeld;

auto InputBox(panel_shared::BoxRect* box) noexcept -> bool {
	const bool hd = g_drawHd.load();
	const auto& m = hd ? layout::Hd : layout::Sd;
	*box = panel_shared::BoxRect{hd, m.panelX, m.panelY, m.inputX, m.inputY, m.inputW, m.inputH};
	return true;
}

// --- UI ---------------------------------------------------------------------------------------------------------------------
auto FindPanel() noexcept -> D2RL::Widgets::WidgetHandle {
	D2RL::Widgets::WidgetHandle panel = D2RL::Widgets::InvalidHandle;
	(void)g_widgets->findPanel(g_context, layout::PanelName, &panel);
	return panel;
}

void Show(D2RL::Widgets::WidgetHandle panel, const std::string& name, bool visible) noexcept {
	D2RL::Widgets::WidgetHandle w = D2RL::Widgets::InvalidHandle;
	if (g_widgets->findWidget(g_context, panel, name.c_str(), &w) == D2RL::Widgets::Result::Success) {
		(void)g_widgets->setWidgetVisible(g_context, w, visible);
		(void)g_widgets->setWidgetEnabled(g_context, w, visible);
	}
}

auto ButtonId(const char* name) noexcept -> int {
	for (int i = 0; i < layout::ButtonCount; ++i) {
		if (std::strcmp(layout::ButtonNames[i], name) == 0) {
			return i;
		}
	}
	return -1;
}

void ApplyTabWidgets() noexcept {
	const auto panel = FindPanel();
	if (panel == D2RL::Widgets::InvalidHandle) {
		return;
	}
	const bool list = g_tab == 0 || g_tab == 1;
	for (int i = 0; i < layout::CategoryCount; ++i) {
		Show(panel, Fmt("Btn_cat%d", i), g_tab == 0);
	}
	for (int i = 0; i < layout::MaxRows; ++i) {
		Show(panel, Fmt("Btn_row%d", i), list && i < g_rowCount && !(g_tab == 1 && g_rowHeading[i]));
	}
	Show(panel, "Btn_prev", list);
	Show(panel, "Btn_next", list);
	Show(panel, "Btn_raise", g_tab == 2);
	Show(panel, "Btn_unlock", g_tab == 3);
	Show(panel, "Btn_quests", g_tab == 4);
	Show(panel, "Btn_confirm", g_tab == 4 && g_questArmed);
	(void)panel;
}

void RebuildList() noexcept {
	const int perPage = g_drawHd.load() ? layout::Hd.rows : layout::Sd.rows;
	if (g_tab == 0) {
		g_itemHits = SearchItems(g_catalog, g_cat, g_query);
	} else if (g_tab == 1) {
		g_travelHits = SearchTravel(g_catalog, g_query);
	}
	const int total = g_tab == 0 ? static_cast<int>(g_itemHits.size()) : g_tab == 1 ? static_cast<int>(g_travelHits.size()) : 0;
	const Page page = PageOf(total, g_pageIndex, perPage);
	g_pageIndex = page.page;
	const std::lock_guard<std::mutex> lock(g_uiMutex);
	g_rowCount = 0;
	std::fill(std::begin(g_rowKinds), std::end(g_rowKinds), '\0');
	if (g_tab == 0) {
		for (int i = 0; i < page.count; ++i) {
			const Hit& h = g_itemHits[static_cast<size_t>(page.first + i)];
			g_rowKinds[g_rowCount] = 'I';
			if (h.kit) {
				const Kit& k = g_catalog.kits[static_cast<size_t>(h.index)];
				g_rowTexts[g_rowCount++] = Fmt("[Kit] %s: base + %zu runes, socket in order", k.name.c_str(), k.runes.size());
			} else {
				const Item& it = g_catalog.items[static_cast<size_t>(h.index)];
				g_rowTexts[g_rowCount++] = it.tag.empty() ? it.name : Fmt("%s  (%s)", it.name.c_str(), it.tag.c_str());
			}
		}
		g_header = Fmt("Items: %d found, page %d / %d. An arrow spawns the row.", total, page.page + 1, page.pages);
	} else if (g_tab == 1) {
		for (int i = 0; i < page.count; ++i) {
			const TravelRow& t = g_travelHits[static_cast<size_t>(page.first + i)];
			g_rowHeading[g_rowCount] = t.kind == TravelRow::Heading;
			g_rowKinds[g_rowCount] = t.kind == TravelRow::Heading ? 'H' : t.kind == TravelRow::UberLevel ? 'U' : 'A';
			if (t.kind == TravelRow::Heading) {
				g_rowTexts[g_rowCount++] = Fmt("-- %s --", TravelHeadings[t.index]);
			} else if (t.kind == TravelRow::UberLevel) {
				g_rowTexts[g_rowCount++] = UberRowText(g_catalog, g_catalog.ubers[static_cast<size_t>(t.index)]);
			} else {
				const Level& l = g_catalog.levels[static_cast<size_t>(t.index)];
				const char* note = l.note == 1 ? "  [map only, the fight needs its normal summon]" : l.note == 2 ? "  [portal area]" : "";
				g_rowTexts[g_rowCount++] = Fmt("%s  (Act %d)%s", l.name.c_str(), l.act + 1, note);
			}
		}
		g_header = Fmt("Travel: %d rows, page %d / %d. An arrow goes there; \"uber\" lists the uber levels.", total, page.page + 1, page.pages);
	} else if (g_tab == 2) {
		g_header = "Character: type a level in the box, then Raise to level. Raises only.";
	} else if (g_tab == 3) {
		g_header = "Unlocks: every waypoint on Normal, Nightmare and Hell, with the act tabs.";
	} else {
		g_header = g_questArmed ? "Sure? Completes this difficulty's quests with the loader's cheat. REWARDS ARE NOT GUARANTEED."
		                        : "Advanced: complete quests with the loader's cheat. Rewards are not guaranteed.";
	}
}

void OnPress(int button) noexcept {
	g_presses.fetch_add(1);
	const char* name = layout::ButtonNames[button];
	const auto startsWith = [&](const char* prefix) { return std::strncmp(name, prefix, std::strlen(prefix)) == 0; };
	if (startsWith("tab")) {
		g_tab = name[3] - '0';
		g_pageIndex = 0;
		g_questArmed = false;
		g_dirty = true;
	} else if (startsWith("cat")) {
		g_cat = static_cast<Category>(name[3] - '0');
		g_pageIndex = 0;
		g_dirty = true;
	} else if (std::strcmp(name, "prev") == 0) {
		if (g_pageIndex > 0) {
			--g_pageIndex;
			g_dirty = true;
		}
	} else if (std::strcmp(name, "next") == 0) {
		++g_pageIndex;
		g_dirty = true;
	} else if (std::strcmp(name, "close") == 0) {
		(void)g_panels->closePanel(g_context, g_panel);
	} else if (startsWith("row")) {
		const int row = std::atoi(name + 3);
		if (row >= g_rowCount) {
			return;
		}
		const int perPage = g_drawHd.load() ? layout::Hd.rows : layout::Sd.rows;
		const int offset = PageOf(g_tab == 0 ? static_cast<int>(g_itemHits.size()) : static_cast<int>(g_travelHits.size()), g_pageIndex, perPage).first + row;
		if (g_tab == 0) {
			if (offset >= static_cast<int>(g_itemHits.size())) {
				return;
			}
			const Hit h = g_itemHits[static_cast<size_t>(offset)];
			Enqueue(h.kit ? ActionKind::Kit : ActionKind::Item, h.index);
		} else if (g_tab == 1) {
			if (offset < static_cast<int>(g_travelHits.size())) {
				const TravelRow& t = g_travelHits[static_cast<size_t>(offset)];
				if (t.kind == TravelRow::Area) {
					Enqueue(ActionKind::Travel, t.index);
				} else if (t.kind == TravelRow::UberLevel) {
					Enqueue(ActionKind::UberTravel, t.index);
				}
			}
		}
	} else if (std::strcmp(name, "raise") == 0) {
		const int target = ToInt(std::string_view(g_query), -1);
		if (target <= 0 || target > MaxLevel) {
			SetStatus(Fmt("Type a level from 1 to %d in the box first.", MaxLevel));
			return;
		}
		Enqueue(ActionKind::Raise, target);
	} else if (std::strcmp(name, "unlock") == 0) {
		Enqueue(ActionKind::Unlock, 0);
	} else if (std::strcmp(name, "quests") == 0) {
		if (Refuse(CurrentGate(true))) {
			return;
		}
		g_questArmed = true;
		g_dirty = true;
	} else if (std::strcmp(name, "confirm") == 0) {
		if (!g_questArmed || Refuse(CurrentGate(true))) {
			return;
		}
		g_questArmed = false;
		g_dirty = true;
		HMODULE core = GetModuleHandleA(D2RL::CoreExports::CoreDllName);
		const auto execute = core != nullptr ? reinterpret_cast<D2RL::CoreExports::ExecuteConsoleCommandFn>(GetProcAddress(core, D2RL::CoreExports::ExecuteConsoleCommandInfo.name)) : nullptr;
		const auto debug = core != nullptr ? reinterpret_cast<D2RL::CoreExports::IsDebugModeEnabledFn>(GetProcAddress(core, D2RL::CoreExports::IsDebugModeEnabledInfo.name)) : nullptr;
		if (execute == nullptr || debug == nullptr) {
			SetStatus("The loader's console is not available.");
			return;
		}
		const bool wasOn = debug();
		if (!wasOn) {
			(void)execute("debug_mode");
		}
		const bool ok = execute("cheat quests");
		if (!wasOn) {
			(void)execute("debug_mode");
		}
		SetStatus(ok ? "Quests completed on this difficulty with the loader's cheat. Rewards are not guaranteed." : "The loader refused the quests command.");
		LogLine(ok ? "quests cheat run" : "quests cheat refused");
	}
}

void TickInner() {
	auto* player = reinterpret_cast<uint8_t*>(Fn<ClientPlayerFn>(RvaClientPlayer)(Fn<LocalIdFn>(RvaLocalId)()));
	g_hasClient.store(player != nullptr);
	g_clientPlayer.store(player != nullptr ? d2r::At<uint32_t>(player, UnitIdOffset) : 0);
	if (player == nullptr) {
		g_hostFound.store(false);
		g_hostPlayer.store(0);
		g_clients.store(0);
		g_game.store(nullptr);
	}
	if (g_toggleQueued.exchange(false)) {
		(void)g_panels->togglePanel(g_context, g_panel);
		g_dirty = true;
	}
	D2RL::Panels::PanelInfo info{};
	info.structSize = D2RL::Panels::PanelInfoSize;
	const bool open = g_panels->getPanelInfo(g_context, g_panel, &info) == D2RL::Panels::Result::Success && info.presentationState == D2RL::Panels::PresentationState::Open;
	if (open && !g_open.load()) {
		g_dirty = true;
		g_shownValid = false;
	}
	g_open.store(open);
	if (!open) {
		g_boxFocus.store(false);
		g_boxClicked.store(false);
		const std::lock_guard<std::mutex> lock(g_pressMutex);
		g_presses_q.clear();  // a press never waits for the next opening
		return;
	}
	if (panel_shared::IsHd() != g_drawHd.load()) {
		g_drawHd.store(!g_drawHd.load());
		g_dirty = true;
		g_shownValid = false;
	}
	std::vector<int> presses;
	{
		const std::lock_guard<std::mutex> lock(g_pressMutex);
		presses.swap(g_presses_q);
	}
	for (int b : presses) {
		OnPress(b);
	}
	panel_shared::HookGameWindow();
	g_boxFocus.store(panel_shared::BoxFocused(g_client));
	char input[64] = "";
	if (g_testInputSet) {
		std::snprintf(input, sizeof(input), "%s", g_testInput.c_str());
	} else {
		const auto panel = FindPanel();
		D2RL::Widgets::WidgetHandle box = D2RL::Widgets::InvalidHandle;
		uint32_t need = 0;
		if (panel != D2RL::Widgets::InvalidHandle && g_widgets->findWidget(g_context, panel, layout::InputName, &box) == D2RL::Widgets::Result::Success) {
			(void)g_widgets->getInputText(g_context, box, input, sizeof(input), &need);
		}
	}
	if (g_query != input) {
		g_query = input;
		g_pageIndex = 0;
		g_dirty = true;
		const std::lock_guard<std::mutex> lock(g_uiMutex);
		g_queryShown = g_query;
	}
	if (g_dirty) {
		g_dirty = false;
		RebuildList();
		ApplyTabWidgets();
	}
	// The gate's answer is shown while nothing else is being reported.
	const Refusal gate = CurrentGate(false);
	if (gate != Refusal::None && gate != Refusal::NotInGame) {
		SetStatus(RefusalText(gate));
	}
	ApplyTexts();
}

void __cdecl TickOnUi(const D2RL::PluginContext*, void*) noexcept {
	g_tickQueued.store(false);
	__try {
		TickInner();
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		g_faults.fetch_add(1);
	}
}

void QueueTick() noexcept {
	if (!g_tickQueued.exchange(true) && g_threads->runOnUiThread(g_context, &TickOnUi, nullptr) != D2RL::Threads::Result::Success) {
		g_tickQueued.store(false);
	}
}

DWORD WINAPI TimerThread(LPVOID) {
	for (;;) {
		Sleep(g_open.load() || g_toggleQueued.load() ? 100 : 400);
		QueueTick();
	}
}

auto __cdecl OnAction(const D2RL::PluginContext*, const D2RL::Input::ActionEvent* event, void*) noexcept -> D2RL::Input::ActionResult {
	if (event == nullptr || !D2RL::Input::HasActionEventField(event, D2RL::Input::ActionEventRequiredSize) || event->kind != D2RL::Input::ActionEventKind::Pressed) {
		return D2RL::Input::ActionResult::Ignored;
	}
	g_toggleQueued.store(true);
	QueueTick();
	return D2RL::Input::ActionResult::Handled;
}

// UI listener (panel_shared.cpp): a button of the menu was clicked. The work runs on the next UI tick.
void OnButton(int button) noexcept {
	{
		const std::lock_guard<std::mutex> lock(g_pressMutex);
		g_presses_q.push_back(button);
	}
	QueueTick();
}

auto LoadCatalog(const char* selfPath) -> std::string {
	std::string text;
	switch (panel_shared::ReadModFile(g_context, selfPath, L"data\\mxl2012-devmenu\\catalog.tsv", 8 * 1024 * 1024, &text)) {
	case panel_shared::FileResult::Ok:
		break;
	case panel_shared::FileResult::NoPath:
		return "the plugin path could not be read";
	case panel_shared::FileResult::NotFound:
		return "no catalog file in the mod (data/mxl2012-devmenu/catalog.tsv)";
	case panel_shared::FileResult::BadSize:
		return "the catalog file has a bad size";
	case panel_shared::FileResult::ReadFailed:
		return "the catalog file could not be read";
	}
	g_catalog = ParseCatalog(text);
	return g_catalog.ok ? "" : g_catalog.error;
}

}  // namespace

auto InstallDevMenu(const D2RL::PluginContext* context, const char* selfPath, char* report, size_t reportSize) noexcept -> bool {
	g_context = context;
	g_base = context->exeBase;
	if (context->QueryService(&g_threads) != D2RL::ServiceQueryResult::Success || !D2RL::HasThreadServiceField(g_threads, D2RL::ThreadServiceRequiredSize) ||
	    context->QueryService(&g_widgets) != D2RL::ServiceQueryResult::Success || !D2RL::HasWidgetServiceField(g_widgets, D2RL::WidgetServiceRequiredSize) ||
	    context->QueryService(&g_panels) != D2RL::ServiceQueryResult::Success || !D2RL::HasPanelServiceField(g_panels, D2RL::PanelServiceRequiredSize) ||
	    context->QueryService(&g_items) != D2RL::ServiceQueryResult::Success || !D2RL::HasItemServiceField(g_items, D2RL::ItemServiceRequiredSize) ||
	    context->QueryService(&g_inventory) != D2RL::ServiceQueryResult::Success ||
	    context->QueryService(&g_input) != D2RL::ServiceQueryResult::Success || !D2RL::HasInputServiceField(g_input, D2RL::InputServiceRequiredSize) ||
	    !panel_shared::Init(context)) {
		std::snprintf(report, reportSize, "devmenu off: a loader service is unavailable");
		return false;
	}
	std::string catalogError;
	try {
		catalogError = LoadCatalog(selfPath);
	} catch (...) {
		catalogError = "out of memory reading the catalog";
	}
	if (HMODULE ip = LoadLibraryW(L"iphlpapi.dll")) {
		g_extTcp = reinterpret_cast<ExtTcpFn>(GetProcAddress(ip, "GetExtendedTcpTable"));
	}

	(void)panel_shared::RegisterLayout(context, "DevMenuhd", layout::LayoutHd, std::strlen(layout::LayoutHd));
	(void)panel_shared::RegisterLayout(context, "DevMenu", layout::LayoutSd, std::strlen(layout::LayoutSd));
	D2RL::Panels::PanelRegistration panel{};
	panel.structSize = D2RL::Panels::PanelRegistrationSize;
	panel.flags = D2RL::Panels::PanelFlags::CloseOnEscape;
	panel.localId = layout::PanelLocalId;
	if (g_panels->registerPanel(context, &panel, &g_panel) != D2RL::Panels::Result::Success) {
		std::snprintf(report, reportSize, "devmenu off: the panel could not be registered");
		return false;
	}
	if (const int failed = panel_shared::RegisterButtons(context, "DevMenuB_", layout::ButtonCount); failed >= 0) {
		std::snprintf(report, reportSize, "devmenu off: button panel %d could not be registered", failed);
		return false;
	}
	const D2RL::Input::ActionRegistration reg{
	    .structSize = D2RL::Input::ActionRegistrationSize,
	    .flags = 0,
	    .logicalId = "mxl_dev_menu",
	    .displayName = "Developer Menu",
	    .category = "D2R-XL 2012",
	    .defaultPrimary = {.key = D2RL::Input::Key::F12, .modifier = D2RL::Input::Modifier::Control},
	    .defaultSecondary = {.key = D2RL::Input::Key::None, .modifier = D2RL::Input::Modifier::None},
	    .callback = &OnAction,
	    .userData = nullptr,
	};
	const auto rc = g_input->registerAction(context, &reg, &g_action);
	if (rc != D2RL::Input::Result::Success) {
		std::snprintf(report, reportSize, "devmenu off: the Controls action could not be registered (result %u)", static_cast<unsigned>(rc));
		return false;
	}
	g_client.panelName = layout::PanelName;
	g_client.inputName = layout::InputName;
	g_client.buttonPrefix = "mxl2012-core/DevMenuB_";
	g_client.buttonCount = layout::ButtonCount;
	g_client.onPress = &OnButton;
	g_client.inputBox = &InputBox;
	if (!panel_shared::AddClient(&g_client) || !InstallServerFrame(context) || !AddServerFrameCallback(&Frame)) {
		std::snprintf(report, reportSize, "devmenu off: listener / server frame unavailable");
		return false;
	}
	if (HANDLE t = CreateThread(nullptr, 0, TimerThread, nullptr, 0, nullptr)) {
		CloseHandle(t);
	}
	g_on = true;
	std::snprintf(report, reportSize, "devmenu on: Controls action mxl_dev_menu (default Ctrl+F12), catalog %s (%zu items, %zu kits, %zu levels), socket table %s, typing keys %s",
	              catalogError.empty() ? "ok" : catalogError.c_str(), g_catalog.items.size(), g_catalog.kits.size(), g_catalog.levels.size(), g_extTcp != nullptr ? "readable" : "unavailable",
	              panel_shared::TypingOk() ? "taken from the bindings while the box has the focus" : "off (entry bytes differ)");
	return true;
}

void DevMenuStatus(char* out, size_t size) noexcept {
	std::string status, ports, query, kinds;
	{
		const std::lock_guard<std::mutex> lock(g_uiMutex);
		kinds = g_rowKinds;
		status = g_status;
		ports = g_portsSeen;
		query = g_queryShown;
	}
	std::snprintf(out, size,
	              "on=%d open=%d tab=%d cat=%d rows=%d busy=%d local=%u host=%u clients=%d presses=%ld actions=%ld taken=%ld ops=%ld refused=%ld faults=%ld listen=%ld/%ld texts=%ld textfails=%ld hasclient=%d found=%d ports=%s boxfocus=%d boxclicked=%d keysheld=%ld keystaken=%ld rowkinds=%s query=\"%s\" status=\"%s\"",
	              g_on ? 1 : 0, g_open.load() ? 1 : 0, g_tab, static_cast<int>(g_cat), g_rowCount, g_busy.load() ? 1 : 0, g_clientPlayer.load(), g_hostPlayer.load(), g_clients.load(),
	              g_presses.load(), g_actions.load(), g_taken.load(), g_gameOps.load(), g_refused.load(), g_faults.load(), g_listeners.load(), g_listenChecks.load(), g_textsSet.load(), g_textFails.load(), g_hasClient.load() ? 1 : 0, g_hostFound.load() ? 1 : 0, ports.empty() ? "-" : ports.c_str(), g_boxFocus.load() ? 1 : 0, g_boxClicked.load() ? 1 : 0, g_keysHeld.load(), g_keysTaken.load(), kinds.empty() ? "-" : kinds.c_str(), query.c_str(), status.c_str());
}

void DevMenuSockets(char* out, size_t size) noexcept {
	std::snprintf(out, size, "sockfails=%ld lastitemflags=0x%x", g_socketFails.load(), g_lastItemFlags.load());
}

auto DevMenuHarness(const char* verb, const char* argument) noexcept -> bool {
	if (!g_on || verb == nullptr) {
		return false;
	}
	if (std::strcmp(verb, "open") == 0 || std::strcmp(verb, "close") == 0) {
		const bool wantOpen = verb[0] == 'o';
		if (wantOpen != g_open.load()) {
			g_toggleQueued.store(true);
			QueueTick();
		}
		return true;
	}
	if (std::strcmp(verb, "input") == 0) {
		g_testInput = argument != nullptr ? argument : "";
		g_testInputSet = true;
		g_dirty = true;
		QueueTick();
		return true;
	}
	if (std::strcmp(verb, "box") == 0) {  // back to the input box's own text (`input` overrides it)
		g_testInputSet = false;
		g_dirty = true;
		QueueTick();
		return true;
	}
	if (std::strcmp(verb, "press") == 0 && argument != nullptr) {
		const int b = ButtonId(argument);
		if (b < 0) {
			return false;
		}
		{
			const std::lock_guard<std::mutex> lock(g_pressMutex);
			g_presses_q.push_back(b);
		}
		QueueTick();
		return true;
	}
	return false;
}

// Pity map reveal (owner idea 2026-11-06; off word mapreveal; docs/plugin-plan.md section 34, docs/map-reveal-research.md).
//
// Once the player has explored the threshold share of the current level (mxl2012-core.toml [mapreveal] threshold, default 70;
// map_reveal_logic.h), the Controls action "Reveal Level Map" (D2RLoader InputService, `mxl_map_level`, default L, rebindable in
// Options > Controls) reveals the rest of that level's automap. One chat line says when the reveal becomes available for a level,
// and each press is answered with a short line (revealed, or the percent explored and the percent needed).
//
// Everything is client side and per player: the automap is the client's own (built from its own copy of the act's DRLG); no
// packet is sent, so a joiner of another player's game reveals only its own map. The part installs no hook:
// - every 250 ms a timer thread asks the UI thread to walk the current level's DRLG rooms (local player 0x9a480(0x8b2d0()),
//   its path's room 0x341c30, active room +0x18 = DRLG room, +0x90 = level; the level's rooms from +0x10, next +0x48, tile w / h
//   at +0x68 / +0x6c) and marks the rooms that are active (+0x58). A room becomes active exactly when D2R adds it to the automap.
// - the reveal (UI thread) activates each room of the level with D2R's own room activation 0x3289a0 and hands it to the DRLG's
//   automap callback (DRLG +0x838, checked to be D2R's 0xd2240), as D2R does for the rooms round the player. The activation
//   takes the data-table flag of the client (the local player's unit byte +0x1bd, read by 0x34a0e0): the same byte the
//   client's level code passes to InitLevel 0x3271c0 and the level record getter 0x32c200. (The research probe passed 0, the
//   server's flag, and the game closed.) D2R frees far rooms again as usual.
// - the chat line goes straight to the client's chat packet handler 0x12c190 (packet 0x26 type 4, map_reveal_logic.h), so it
//   works in a joined game too. A line is held while the client talks to an NPC (0x2a48760 non-zero): a chat line during an
//   NPC's speech freezes the speech (docs/d2r-addresses.md 13); after 60 s it is dropped.
// The per-level marks live for one game (the client DRLG and its map seed name the game); they reset in a new game, as D2R's
// automap does.
#include "map_reveal.h"

#include "d2r.h"
#include "map_reveal_logic.h"

#include <D2RLPlugin/input.h>
#include <D2RLPlugin/threads.h>

#include <windows.h>

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

using namespace map_reveal;

constexpr uint64_t RvaLocalContext = 0x8b2d0;     // () -> local data context (0-7)
constexpr uint64_t RvaLocalPlayer = 0x9a480;      // (context) -> the client's own player unit
constexpr uint64_t RvaPathRoom = 0x341c30;        // (unit path) -> active room
constexpr uint64_t RvaUnitDataFlag = 0x34a0e0;    // (unit) -> data-table flag byte (+0x1bd)
constexpr uint64_t RvaActivateRoom = 0x3289a0;    // (data flag, DRLG room) -> active room (loads tiles and presets once)
constexpr uint64_t RvaAutomapRoom = 0xd2240;      // (active room): D2R's automap callback, DRLG +0x838
constexpr uint64_t RvaClientChat = 0x12c190;      // client handler of packet 0x26 (packet bytes)
constexpr uint64_t RvaMenuNpcValid = 0x2a48760;   // u32, non-zero while the client talks to an NPC
constexpr int UnitPath = 0x38, ActiveRoomDrlgRoom = 0x18, RoomActive = 0x58, RoomNext = 0x48, RoomW = 0x68, RoomH = 0x6c;
constexpr int RoomLevel = 0x90, LevelFirstRoom = 0x10, LevelDrlg = 0x1c8, LevelId = 0x1f8, DrlgAutomapCallback = 0x838,
              DrlgMapSeed = 0x840;
constexpr uint64_t HoldMs = 60000;  // a line held for an NPC talk is dropped after this

// Entry bytes of the functions the part calls (a second guard under the build check; MapSense checks the same ones).
constexpr uint8_t LocalPlayerEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x08, 0x57, 0x48, 0x83, 0xec, 0x20, 0x83, 0xf9, 0x08};
constexpr uint8_t PathRoomEntry[] = {0x48, 0x8b, 0x41, 0x20, 0xc3};
constexpr uint8_t DataFlagEntry[] = {0x48, 0x83, 0xec, 0x28, 0x48, 0x85, 0xc9, 0x75, 0x1a};
constexpr uint8_t ActivateEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x08, 0x57, 0x48, 0x83, 0xec, 0x20, 0x8b, 0x42, 0x50, 0x48, 0x8b, 0xda,
                                     0x0f, 0xb6, 0xf9};
constexpr uint8_t ChatEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x10, 0x48, 0x89, 0x74, 0x24, 0x18, 0x57, 0x48, 0x81, 0xec, 0x90};

using LocalContextFn = int32_t (*)();
using LocalPlayerFn = uint8_t* (*)(int32_t);
using PathRoomFn = uint8_t* (*)(void*);
using DataFlagFn = uint8_t (*)(void*);
using ActivateFn = void* (*)(uint8_t, void*);
using AutomapRoomFn = void (*)(void*);
using ChatFn = void (*)(const uint8_t*);

const D2RL::PluginContext* g_context = nullptr;
const D2RL::ThreadService* g_threads = nullptr;
const D2RL::InputService* g_input = nullptr;
D2RL::Input::ActionHandle g_action = D2RL::Input::InvalidHandle;
uint64_t g_base = 0;
bool g_on = false;
Settings g_settings;

std::atomic<bool> g_tickQueued{false};
std::atomic<bool> g_pressQueued{false};

// UI thread only from here on.
Level g_levels[MaxLevels];
const void* g_gameDrlg = nullptr;  // the game the marks belong to
uint32_t g_gameSeed = 0;
int g_level = 0;                   // the current level id (0: none, out of a game)
int g_percent = 0;
Gate g_gate = Gate::Below;
char g_pending[256] = "";          // a chat line waiting for the end of an NPC talk
uint8_t g_pendingColour = ColourWhite;
uint64_t g_pendingSince = 0;
char g_lastLine[256] = "";

// Counters since load (status line)
std::atomic<long> g_ticks{0}, g_presses{0}, g_reveals{0}, g_refusals{0}, g_announces{0}, g_lines{0}, g_heldLines{0},
    g_droppedLines{0}, g_faults{0}, g_games{0};
std::atomic<long> g_lastMade{0}, g_lastRooms{0}, g_lastRevealMs{0};

template <typename F>
auto Fn(uint64_t rva) noexcept -> F {
	return reinterpret_cast<F>(g_base + rva);
}

auto EntryMatches(uint64_t rva, const uint8_t* bytes, size_t n) noexcept -> bool {
	return std::memcmp(reinterpret_cast<const void*>(g_base + rva), bytes, n) == 0;
}

struct Where {
	uint8_t* player;
	uint8_t* level;
	uint8_t* drlg;
	int levelId;
};

// The local player's client level, or false out of a game / in a level without D2R's automap callback.
auto Locate(Where* w) noexcept -> bool {
	const int32_t ctx = Fn<LocalContextFn>(RvaLocalContext)();
	if (ctx < 0 || ctx >= 8) {
		return false;
	}
	w->player = Fn<LocalPlayerFn>(RvaLocalPlayer)(ctx);
	if (w->player == nullptr || d2r::At<int32_t>(w->player, d2r::UnitType) != 0) {
		return false;
	}
	void* path = d2r::At<void*>(w->player, UnitPath);
	uint8_t* active = path != nullptr ? Fn<PathRoomFn>(RvaPathRoom)(path) : nullptr;
	uint8_t* room = active != nullptr ? d2r::At<uint8_t*>(active, ActiveRoomDrlgRoom) : nullptr;
	w->level = room != nullptr ? d2r::At<uint8_t*>(room, RoomLevel) : nullptr;
	w->drlg = w->level != nullptr ? d2r::At<uint8_t*>(w->level, LevelDrlg) : nullptr;
	if (w->drlg == nullptr || d2r::At<uint64_t>(w->drlg, DrlgAutomapCallback) != g_base + RvaAutomapRoom) {
		return false;
	}
	w->levelId = static_cast<int>(d2r::At<uint32_t>(w->level, LevelId));
	return w->levelId > 0 && w->levelId < MaxLevels;
}

void SendLine(const char* text, uint8_t colour) noexcept {
	uint8_t packet[ChatPacketMax];
	if (BuildChatPacket(packet, sizeof(packet), colour, text) == 0) {
		return;
	}
	Fn<ChatFn>(RvaClientChat)(packet);
	g_lines.fetch_add(1);
}

// A chat line now, or held while the client talks to an NPC (the newest line replaces a held one).
void Say(const char* text, uint8_t colour) noexcept {
	std::snprintf(g_lastLine, sizeof(g_lastLine), "%s", text);
	if (*reinterpret_cast<const uint32_t*>(g_base + RvaMenuNpcValid) != 0) {
		if (g_pending[0] == '\0') {
			g_pendingSince = GetTickCount64();
		}
		std::snprintf(g_pending, sizeof(g_pending), "%s", text);
		g_pendingColour = colour;
		g_heldLines.fetch_add(1);
		return;
	}
	SendLine(text, colour);
}

void FlushHeld() noexcept {
	if (g_pending[0] == '\0') {
		return;
	}
	if (*reinterpret_cast<const uint32_t*>(g_base + RvaMenuNpcValid) == 0) {
		SendLine(g_pending, g_pendingColour);
		g_pending[0] = '\0';
	} else if (GetTickCount64() - g_pendingSince > HoldMs) {
		g_droppedLines.fetch_add(1);
		g_pending[0] = '\0';
	}
}

void BoundKey(char* out, size_t n) noexcept {
	out[0] = '\0';
	D2RL::Input::Binding b{};
	if (g_input != nullptr && g_action != D2RL::Input::InvalidHandle &&
	    g_input->getBinding(g_context, g_action, D2RL::Input::BindingSlot::Primary, &b) == D2RL::Input::Result::Success) {
		KeyName(static_cast<uint32_t>(b.key), static_cast<uint32_t>(b.modifier), out, n);
	}
}

// Walks the current level: marks its active rooms and updates its areas. Returns its record, null out of a game.
auto Sample(Where* w) noexcept -> Level* {
	if (!Locate(w)) {
		g_level = 0;
		return nullptr;
	}
	const uint32_t seed = d2r::At<uint32_t>(w->drlg, DrlgMapSeed);
	if (w->drlg != g_gameDrlg || seed != g_gameSeed) {  // another game: the automap starts empty again
		std::memset(g_levels, 0, sizeof(g_levels));
		g_gameDrlg = w->drlg;
		g_gameSeed = seed;
		g_games.fetch_add(1);
	}
	Level* l = &g_levels[w->levelId];
	const void* first = d2r::At<const void*>(w->level, LevelFirstRoom);
	if (l->first != first) {
		ResetLevel(l, first);
	}
	int i = 0;
	uint64_t total = 0, seen = 0;
	for (const uint8_t* r = static_cast<const uint8_t*>(first); r != nullptr && i < MaxRooms; r = d2r::At<const uint8_t*>(r, RoomNext), ++i) {
		const uint64_t a = static_cast<uint64_t>(d2r::At<uint32_t>(r, RoomW)) * d2r::At<uint32_t>(r, RoomH);
		total += a;
		if (d2r::At<const void*>(r, RoomActive) != nullptr) {
			Mark(l, i);
		}
		if (Seen(*l, i)) {
			seen += a;
		}
	}
	l->rooms = i;
	l->totalArea = total;
	l->seenArea = seen;
	g_level = w->levelId;
	g_percent = Percent(seen, total);
	g_gate = Decide(g_settings.threshold, Excluded(w->levelId, g_settings), seen, total);
	return l;
}

void TickBody() noexcept {
	g_ticks.fetch_add(1);
	FlushHeld();
	Where w{};
	Level* l = Sample(&w);
	if (l != nullptr && ShouldAnnounce(l, g_gate)) {
		char key[24], line[160];
		BoundKey(key, sizeof(key));
		AvailableLine(line, sizeof(line), g_percent, key);
		Say(line, ColourYellow);
		g_announces.fetch_add(1);
	}
}

// Activates each room of the level and hands it to D2R's automap callback. Returns the rooms done.
auto RevealLevel(const Where& w, int* rooms) noexcept -> int {
	const uint8_t flag = Fn<DataFlagFn>(RvaUnitDataFlag)(w.player);
	const auto addToMap = reinterpret_cast<AutomapRoomFn>(d2r::At<uint64_t>(w.drlg, DrlgAutomapCallback));
	int made = 0, i = 0;
	for (uint8_t* r = d2r::At<uint8_t*>(w.level, LevelFirstRoom); r != nullptr && i < MaxRooms; r = d2r::At<uint8_t*>(r, RoomNext), ++i) {
		if (void* active = Fn<ActivateFn>(RvaActivateRoom)(flag, r)) {
			addToMap(active);
			++made;
		}
	}
	*rooms = i;
	return made;
}

void PressBody() noexcept {
	g_presses.fetch_add(1);
	Where w{};
	Level* l = Sample(&w);
	if (l == nullptr) {
		return;  // out of a game: nothing to say
	}
	char line[160];
	if (g_gate != Gate::Ready || l->revealed) {
		RefusedLine(line, sizeof(line), g_gate, g_percent, g_settings.threshold, l->revealed);
		Say(line, ColourWhite);
		g_refusals.fetch_add(1);
		return;
	}
	const int percent = g_percent;
	const uint64_t t0 = GetTickCount64();
	int rooms = 0;
	const int made = RevealLevel(w, &rooms);
	g_lastRevealMs.store(static_cast<long>(GetTickCount64() - t0));
	g_lastMade.store(made);
	g_lastRooms.store(rooms);
	l->revealed = made == rooms;
	l->announced = true;
	g_reveals.fetch_add(1);
	RevealedLine(line, sizeof(line), percent, made, rooms);
	Say(line, ColourWhite);
}

void TickGuarded() noexcept {
	__try {
		TickBody();
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		g_faults.fetch_add(1);
	}
}

void PressGuarded() noexcept {
	__try {
		PressBody();
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		g_faults.fetch_add(1);
	}
}

void __cdecl TickOnUi(const D2RL::PluginContext*, void*) noexcept {
	g_tickQueued.store(false);
	TickGuarded();
	if (g_pressQueued.exchange(false)) {
		PressGuarded();
	}
}

void QueueTick() noexcept {
	if (!g_tickQueued.exchange(true) && g_threads->runOnUiThread(g_context, &TickOnUi, nullptr) != D2RL::Threads::Result::Success) {
		g_tickQueued.store(false);
	}
}

DWORD WINAPI TimerThread(LPVOID) {
	for (;;) {
		Sleep(250);
		QueueTick();
	}
}

auto __cdecl OnAction(const D2RL::PluginContext*, const D2RL::Input::ActionEvent* event, void*) noexcept -> D2RL::Input::ActionResult {
	if (!D2RL::Input::HasActionEventField(event, D2RL::Input::ActionEventRequiredSize) || event->kind != D2RL::Input::ActionEventKind::Pressed) {
		return D2RL::Input::ActionResult::Ignored;
	}
	g_pressQueued.store(true);
	QueueTick();
	return D2RL::Input::ActionResult::Handled;
}

void ReadSettings(char* note, size_t n) noexcept {
	static char toml[16384];
	uint32_t need = 0;
	if (!g_context->ReadConfig(toml, sizeof(toml), &need)) {
		g_settings = Settings{};
		std::snprintf(note, n, "mxl2012-core.toml not read: defaults");
		return;
	}
	const bool found = ParseSettings(toml, &g_settings);
	std::snprintf(note, n, "%s", found ? "mxl2012-core.toml" : "no [mapreveal] in mxl2012-core.toml: defaults");
}

}  // namespace

auto InstallMapReveal(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	g_context = context;
	g_base = context->exeBase;
	if (!EntryMatches(RvaLocalPlayer, LocalPlayerEntry, sizeof(LocalPlayerEntry)) || !EntryMatches(RvaPathRoom, PathRoomEntry, sizeof(PathRoomEntry)) ||
	    !EntryMatches(RvaUnitDataFlag, DataFlagEntry, sizeof(DataFlagEntry)) || !EntryMatches(RvaActivateRoom, ActivateEntry, sizeof(ActivateEntry)) ||
	    !EntryMatches(RvaClientChat, ChatEntry, sizeof(ChatEntry))) {
		std::snprintf(report, reportSize, "mapreveal off: entry bytes differ (0x9a480 / 0x341c30 / 0x34a0e0 / 0x3289a0 / 0x12c190)");
		return false;
	}
	if (context->QueryService(&g_threads) != D2RL::ServiceQueryResult::Success || !D2RL::HasThreadServiceField(g_threads, D2RL::ThreadServiceRequiredSize) ||
	    context->QueryService(&g_input) != D2RL::ServiceQueryResult::Success || !D2RL::HasInputServiceField(g_input, D2RL::InputServiceRequiredSize)) {
		std::snprintf(report, reportSize, "mapreveal off: ThreadService / InputService unavailable");
		return false;
	}
	char note[96];
	ReadSettings(note, sizeof(note));
	const D2RL::Input::ActionRegistration reg{
	    .structSize = D2RL::Input::ActionRegistrationSize,
	    .flags = 0,
	    .logicalId = "mxl_map_level",
	    .displayName = "Reveal Level Map",
	    .category = "D2R-XL 2012",
	    .defaultPrimary = {.key = D2RL::Input::Key::L, .modifier = D2RL::Input::Modifier::None},
	    .defaultSecondary = {.key = D2RL::Input::Key::None, .modifier = D2RL::Input::Modifier::None},
	    .callback = &OnAction,
	    .userData = nullptr,
	};
	const auto rc = g_input->registerAction(context, &reg, &g_action);
	if (rc != D2RL::Input::Result::Success || g_action == D2RL::Input::InvalidHandle) {
		std::snprintf(report, reportSize, "mapreveal off: the Controls action could not be registered (InputService result %u)", static_cast<unsigned>(rc));
		return false;
	}
	if (HANDLE t = CreateThread(nullptr, 0, TimerThread, nullptr, 0, nullptr)) {
		CloseHandle(t);
	}
	g_on = true;
	char ex[MaxExclude * 5 + 8] = "";
	for (int i = 0; i < g_settings.nExclude; ++i) {
		const size_t len = std::strlen(ex);
		std::snprintf(ex + len, sizeof(ex) - len, "%s%d", i ? " " : "", g_settings.exclude[i]);
	}
	std::snprintf(report, reportSize, "mapreveal on: Controls action mxl_map_level (default L) reveals the rest of the level at %d%% explored "
	              "(%s; 0 = always, 101 = off), towns%s%s excluded; no hook",
	              g_settings.threshold, note, g_settings.nExclude ? " and " : "", ex);
	return true;
}

void MapRevealStatus(char* out, size_t size) noexcept {
	const Level* l = g_level > 0 ? &g_levels[g_level] : nullptr;
	char key[24] = "";
	if (g_on) {
		BoundKey(key, sizeof(key));
	}
	static const char* const Gates[] = {"off", "excluded", "below", "ready"};
	std::snprintf(out, size,
	              "on=%d level=%d rooms=%d area=%llu seenarea=%llu percent=%d threshold=%d gate=%s announced=%d revealed=%d key=%s "
	              "npc=%u held=%d ticks=%ld presses=%ld reveals=%ld refusals=%ld announces=%ld lines=%ld heldlines=%ld dropped=%ld "
	              "faults=%ld games=%ld lastmade=%ld lastrooms=%ld lastms=%ld",
	              g_on ? 1 : 0, g_level, l ? l->rooms : 0, static_cast<unsigned long long>(l ? l->totalArea : 0),
	              static_cast<unsigned long long>(l ? l->seenArea : 0), g_percent, g_settings.threshold, Gates[static_cast<int>(g_gate)],
	              l && l->announced ? 1 : 0, l && l->revealed ? 1 : 0, key[0] ? key : "-",
	              g_base ? *reinterpret_cast<const uint32_t*>(g_base + RvaMenuNpcValid) : 0u, g_pending[0] ? 1 : 0, g_ticks.load(),
	              g_presses.load(), g_reveals.load(), g_refusals.load(), g_announces.load(), g_lines.load(), g_heldLines.load(),
	              g_droppedLines.load(), g_faults.load(), g_games.load(), g_lastMade.load(), g_lastRooms.load(), g_lastRevealMs.load());
}

auto MapRevealPress() noexcept -> bool {
	if (!g_on) {
		return false;
	}
	PressGuarded();
	return true;
}

void MapRevealSetThreshold(int threshold) noexcept {
	g_settings.threshold = ClampThreshold(threshold);
}

auto MapRevealLastLine() noexcept -> const char* {
	return g_lastLine;
}

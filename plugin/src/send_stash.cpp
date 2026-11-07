// "Send storable/stackable items to stash" (owner request 2026-11-05; off word sendstash).
//
// A button on the inventory panel (tools/send_stash.py writes it into the four inventory layouts) sends every backpack item that
// has a slot on a Reign of the Warlock stash page (Gems / Materials / Runes) into that slot, stash open or closed, anywhere in the
// game. Each item goes with D2R's own deposit packet 0x63 sub 0 (send_stash_logic.h), the one its Ctrl+click into those pages
// sends, so the server's checks, stacking and saving are D2R's. The codes are the slot widgets' of the mod's HD stash layout
// (mxl_send_stash.h): the server also takes a flagged code with no widget, which would be stored but never shown.
//
// The click's PanelManager message is taken by the UI message listener, which queues the run on the UI thread (D2R hands a
// button's message to the listeners only for a known panel, so an empty panel of that name is registered). A run sends one item
// at a time and the next only once the previous has left the backpack. An item still there after 1 s was refused: the server's
// only refusal for a slot item is a full slot (99), so it is listed as "stack full". The slot counts are not read: the client's
// stack items carry none that the part could find (no stat, the server's count thunk 0x3e2b118 reads 0; game run 2026-11-06).
// The run takes no other click while it goes. At the end one line goes to the message log (server chat packet 0x26 to the local client, from the
// next server frame).
//
// A timer thread asks the UI thread every 250 ms (50 ms during a run) which of the three buttons shows: the button; greyed in a
// game without the RotW stash unit (classic / expansion games); greyed for a joiner of another player's game (send_stash_logic.h
// JoinersOn). The two others are hidden and disabled (D2R hit-tests a hidden widget), and the greyed ones send the same message:
// a click on one puts the reason into the message log (bug #554). A joiner is a client whose local player no server game of this process has (the server frame callback records the
// local player when it finds it).
#include "send_stash.h"

#include "mxl_send_stash.h"
#include "send_stash_logic.h"
#include "server_frame.h"

#include <D2RLPlugin/localization.h>
#include <D2RLPlugin/panels.h>
#include <D2RLPlugin/resources.h>
#include <D2RLPlugin/shared_events.h>
#include <D2RLPlugin/threads.h>
#include <D2RLPlugin/widgets.h>

#include <windows.h>

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

using namespace send_stash;

using SendFn = void (*)(uint32_t op, uint32_t sub, uint32_t a, uint32_t b, uint32_t c, uint32_t d, uint32_t e);
using LocalIdFn = uint32_t (*)();
using PlayerByIdFn = void* (*)(uint32_t);
using ClientUnitFn = void* (*)(uint32_t id, uint32_t type);
using InventoryFn = uint8_t* (*)(void* unit, const char* file, int32_t line);
using InvFirstFn = void* (*)(void*);
using InvNextFn = void* (*)(void*);
using UnitFieldFn = int32_t (*)(void* unit, const char* file, int32_t line);
using DataFlagFn = uint8_t (*)(void* unit);
using ItemRecordFn = const uint8_t* (*)(uint32_t dataFlag, int32_t cls);
using ItemPageFn = uint8_t (*)(void* item);
using HasStateFn = uint64_t (*)(void* unit, int32_t state);
using ServerUnitFn = void* (*)(d2r::Game* game, int32_t type, uint32_t id);
using ClientOfFn = void* (*)(void* player);
using SendChatFn = void (*)(void* client, const uint8_t* record);

constexpr char File[] = "mxl2012-core/send_stash.cpp";

const D2RL::PluginContext* g_context = nullptr;
const D2RL::ThreadService* g_threads = nullptr;
const D2RL::WidgetService* g_widgets = nullptr;
const D2RL::LocalizationService* g_strings = nullptr;
bool g_ready = false;
bool g_frame = false;

SendFn g_send = nullptr;
LocalIdFn g_localId = nullptr;
PlayerByIdFn g_playerById = nullptr;
ClientUnitFn g_clientUnit = nullptr;
InventoryFn g_inventory = nullptr;
InvFirstFn g_invFirst = nullptr;
InvNextFn g_invNext = nullptr;
UnitFieldFn g_unitClass = nullptr;
UnitFieldFn g_unitId = nullptr;
DataFlagFn g_dataFlag = nullptr;
ItemRecordFn g_itemRecord = nullptr;
ItemPageFn g_itemPage = nullptr;
HasStateFn g_hasState = nullptr;
ServerUnitFn g_serverUnit = nullptr;
ClientOfFn g_clientOf = nullptr;
SendChatFn g_sendChat = nullptr;

std::atomic<uint32_t> g_hostPlayer{0};    // the local player id a server frame of this process found (0: none yet)
std::atomic<uint32_t> g_clientPlayer{0};  // the client's own player unit id (UI thread)
std::atomic<bool> g_tickQueued{false};
std::atomic<bool> g_clickQueued{false};
std::atomic<int> g_show{-1};              // the last Show set on a panel
std::atomic<bool> g_running{false};
std::atomic<long> g_frames{0}, g_clicks{0}, g_runs{0}, g_sent{0}, g_full{0}, g_notTaken{0}, g_lines{0}, g_lineFails{0}, g_faults{0}, g_busy{0}, g_refused{0};

// the run (UI thread only)
struct Run {
	Candidate items[MaxItems];
	Verdict verdict[MaxItems];
	size_t n = 0, next = 0;
	uint32_t waitingId = 0;
	uint64_t sentAt = 0;
	int sent = 0, notTaken = 0;
	Stayed stayed[24];
	size_t nStayed = 0;
} g_run;

// the summary line handed to the server frame (UI thread writes, game thread sends)
char g_line[ChatTextSize] = {};
std::atomic<bool> g_linePending{false};
char g_lastLine[ChatTextSize] = {};

D2RL::Widgets::WidgetHandle g_lastPanel = 0;
uint64_t g_lastSetAt = 0;

auto EntryMatches(uint64_t rva, const uint8_t* bytes, size_t n) noexcept -> bool {
	return std::memcmp(reinterpret_cast<const void*>(g_context->exeBase + rva), bytes, n) == 0;
}

template <class F>
auto At(uint64_t rva) noexcept -> F {
	return reinterpret_cast<F>(g_context->exeBase + rva);
}

auto LocalPlayer() noexcept -> void* {
	return g_playerById(g_localId());
}

auto InventoryOf(void* unit) noexcept -> uint8_t* {
	uint8_t* inv = unit != nullptr ? g_inventory(unit, File, __LINE__) : nullptr;
	return inv != nullptr && *reinterpret_cast<const uint32_t*>(inv) == InventoryMagic ? inv : nullptr;
}

// The player's RotW stash unit: a player unit in the inventory's link list with state 0xd1.
auto StashUnit(void* player) noexcept -> void* {
	const uint8_t* inv = InventoryOf(player);
	if (inv == nullptr) {
		return nullptr;
	}
	const uint8_t* node = *reinterpret_cast<const uint8_t* const*>(inv + InventoryLinks);
	for (unsigned i = 0; node != nullptr && i < MaxLinks; ++i) {
		void* unit = g_clientUnit(*reinterpret_cast<const uint32_t*>(node + LinkUnitId), 0);
		if (unit != nullptr && unit != player && g_hasState(unit, StateAdvancedStash) != 0) {
			return unit;
		}
		node = *reinterpret_cast<const uint8_t* const*>(node + LinkNext);
	}
	return nullptr;
}

auto CodeOfItem(void* item) noexcept -> uint32_t {
	const uint8_t* rec = g_itemRecord(g_dataFlag(item), g_unitClass(item, File, __LINE__));
	return rec != nullptr ? *reinterpret_cast<const uint32_t*>(rec + RecordCode) : 0;
}

// The backpack items with a slot code, in the inventory's order (the item on the cursor is not one).
auto Candidates(void* player, Candidate* out, size_t cap) noexcept -> size_t {
	uint8_t* inv = InventoryOf(player);
	if (inv == nullptr) {
		return 0;
	}
	void* cursor = *reinterpret_cast<void**>(inv + InventoryCursor);
	size_t n = 0;
	for (void* item = g_invFirst(inv); item != nullptr && n < cap; item = g_invNext(item)) {
		if (item == cursor || g_itemPage(item) != PageBackpack) {
			continue;
		}
		const uint32_t code = CodeOfItem(item);
		if (!IsSlotCode(code, mxl_send_stash::Codes)) {
			continue;
		}
		const int32_t cls = g_unitClass(item, File, __LINE__);
		out[n++] = {static_cast<uint32_t>(g_unitId(item, File, __LINE__)), code, cls, 0};
	}
	return n;
}

// The item is still in the backpack.
auto InBackpack(void* player, uint32_t id) noexcept -> bool {
	uint8_t* inv = InventoryOf(player);
	if (inv == nullptr) {
		return false;
	}
	for (void* item = g_invFirst(inv); item != nullptr; item = g_invNext(item)) {
		if (static_cast<uint32_t>(g_unitId(item, File, __LINE__)) == id) {
			return g_itemPage(item) == PageBackpack;
		}
	}
	return false;
}

// The item's name as the game shows it (string key = its code), else the code.
void NameOf(uint32_t code, char* out, size_t size) noexcept {
	char text[5];
	CodeText(code, text);
	char key[16];
	std::snprintf(key, sizeof(key), "d2r:%s", text);
	uint32_t need = 0;
	if (g_strings == nullptr ||
	    g_strings->getStringByKey(g_context, key, out, static_cast<uint32_t>(size), &need) != D2RL::Localization::Result::Success || out[0] == '\0') {
		std::snprintf(out, size, "%s", text);
	}
	const char* plain = PlainName(out);
	if (plain != out) {
		std::memmove(out, plain, std::strlen(plain) + 1);
	}
}

void QueueLine(const char* text) noexcept {
	std::snprintf(g_lastLine, sizeof(g_lastLine), "%s", text);
	if (g_frame && !g_linePending.load()) {
		std::snprintf(g_line, sizeof(g_line), "%s", text);
		g_linePending.store(true);
	}
}

void Finish() noexcept {
	char line[ChatTextSize];
	Summary(line, sizeof(line), g_run.sent, g_run.stayed, g_run.nStayed, g_run.notTaken);
	g_sent.fetch_add(g_run.sent);
	g_notTaken.fetch_add(g_run.notTaken);
	QueueLine(line);
	g_running.store(false);
}

// The next planned item that is still in the backpack goes; none left: the run ends.
void SendNext(void* player) noexcept {
	while (g_run.next < g_run.n) {
		const size_t i = g_run.next++;
		if (g_run.verdict[i] != Verdict::Send || !InBackpack(player, g_run.items[i].id)) {
			continue;
		}
		void* stash = StashUnit(player);
		if (stash == nullptr) {
			break;
		}
		g_send(OpAdvancedStash, SubDeposit, g_run.items[i].id, static_cast<uint32_t>(g_unitId(stash, File, __LINE__)), 0, 0, 0);
		g_run.waitingId = g_run.items[i].id;
		g_run.sentAt = GetTickCount64();
		return;
	}
	g_run.waitingId = 0;
	Finish();
}

void StartRun() noexcept {
	void* player = LocalPlayer();
	void* stash = player != nullptr ? StashUnit(player) : nullptr;
	const bool joined = player != nullptr && g_hostPlayer.load() != g_clientPlayer.load();
	const Show show = Decide(player != nullptr, joined, stash != nullptr);
	if (show != Show::Button) {
		if (const char* why = RefusalLine(show)) {  // a click on the greyed button: one line saying why
			g_refused.fetch_add(1);
			QueueLine(why);
		}
		return;
	}
	g_runs.fetch_add(1);
	g_run.n = Candidates(player, g_run.items, MaxItems);
	Plan(g_run.items, g_run.n, g_run.verdict);
	g_run.next = 0;
	g_run.sent = g_run.notTaken = 0;
	g_run.nStayed = 0;
	for (size_t i = 0; i < g_run.n; ++i) {
		if (g_run.verdict[i] == Verdict::Full) {
			char name[48];
			NameOf(g_run.items[i].code, name, sizeof(name));
			g_run.nStayed = AddStayed(g_run.stayed, g_run.nStayed, sizeof(g_run.stayed) / sizeof(g_run.stayed[0]), name);
			g_full.fetch_add(1);
		}
	}
	g_running.store(true);
	SendNext(player);
}

void StepRun() noexcept {
	void* player = LocalPlayer();
	if (player == nullptr) {  // the game ended during the run
		g_running.store(false);
		return;
	}
	if (g_run.waitingId == 0) {
		SendNext(player);
		return;
	}
	if (InBackpack(player, g_run.waitingId)) {
		if (GetTickCount64() - g_run.sentAt < TakenTimeoutMs) {
			return;
		}
		char name[48];  // refused: the slot is full
		NameOf(g_run.items[g_run.next - 1].code, name, sizeof(name));
		g_run.nStayed = AddStayed(g_run.stayed, g_run.nStayed, sizeof(g_run.stayed) / sizeof(g_run.stayed[0]), name);
		g_full.fetch_add(1);
	} else {
		++g_run.sent;
	}
	SendNext(player);
}

void SetShown(D2RL::Widgets::WidgetHandle panel, Show show) noexcept {
	const struct {
		const char* name;
		Show when;
	} buttons[] = {{mxl_send_stash::Button, Show::Button}, {mxl_send_stash::NoSlots, Show::NoSlots}, {mxl_send_stash::Joined, Show::Joined}};
	for (const auto& b : buttons) {
		D2RL::Widgets::WidgetHandle w = 0;
		if (g_widgets->findWidget(g_context, panel, b.name, &w) == D2RL::Widgets::Result::Success) {
			(void)g_widgets->setWidgetVisible(g_context, w, ButtonActive(b.when, show));
			(void)g_widgets->setWidgetEnabled(g_context, w, ButtonActive(b.when, show));
		}
	}
}

// Which button the open inventory panel shows (set again when the panel or the answer changes, and every 2 s).
void Refresh() noexcept {
	D2RL::Widgets::WidgetHandle panel = 0;
	if (g_widgets->findPanel(g_context, mxl_send_stash::Panel0, &panel) != D2RL::Widgets::Result::Success &&
	    g_widgets->findPanel(g_context, mxl_send_stash::Panel1, &panel) != D2RL::Widgets::Result::Success) {
		g_lastPanel = 0;
		return;
	}
	void* player = LocalPlayer();
	const bool joined = player != nullptr && g_hostPlayer.load() != g_clientPlayer.load();
	const Show show = Decide(player != nullptr, joined, player != nullptr && StashUnit(player) != nullptr);
	const uint64_t now = GetTickCount64();
	if (show == Show::None || (panel == g_lastPanel && static_cast<int>(show) == g_show.load() && now - g_lastSetAt < 2000)) {
		return;
	}
	SetShown(panel, show);
	g_lastPanel = panel;
	g_lastSetAt = now;
	g_show.store(static_cast<int>(show));
}

void __cdecl TickOnUi(const D2RL::PluginContext*, void*) noexcept {
	__try {
		void* player = LocalPlayer();
		if (player == nullptr) {
			g_hostPlayer.store(0);  // between games: the next game's server frame records its player again
			g_clientPlayer.store(0);
		} else {
			g_clientPlayer.store(static_cast<uint32_t>(g_unitId(player, File, __LINE__)));
		}
		if (g_clickQueued.exchange(false)) {
			if (g_running.load()) {
				g_busy.fetch_add(1);
			} else {
				StartRun();
			}
		} else if (g_running.load()) {
			StepRun();
		}
		Refresh();
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		g_faults.fetch_add(1);
		g_running.store(false);
	}
	g_tickQueued.store(false);
}

void QueueTick() noexcept {
	if (!g_tickQueued.exchange(true) && g_threads->runOnUiThread(g_context, &TickOnUi, nullptr) != D2RL::Threads::Result::Success) {
		g_tickQueued.store(false);
	}
}

DWORD WINAPI Timer(LPVOID) {
	for (;;) {
		Sleep(g_running.load() || g_clickQueued.load() ? 50 : 250);
		QueueTick();
	}
}

// Every server frame (game thread): records the local player when this game has it (a host or single player), and sends the
// summary line to that player's client.
void Frame(d2r::Game* game) noexcept {
	__try {
		g_frames.fetch_add(1);
		const uint32_t id = g_clientPlayer.load();
		void* player = id != 0 ? g_serverUnit(game, 0, id) : nullptr;
		if (player == nullptr) {
			return;
		}
		g_hostPlayer.store(id);
		if (!g_linePending.load()) {
			return;
		}
		void* client = g_clientOf(player);
		if (client != nullptr) {
			uint8_t record[ChatRecordSize];
			BuildChat(record, ChatLogLine, ChatWhite, g_line);
			g_sendChat(client, record);
			g_lines.fetch_add(1);
		} else {
			g_lineFails.fetch_add(1);
		}
		g_linePending.store(false);
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		g_faults.fetch_add(1);
		g_linePending.store(false);
	}
}

auto __cdecl OnUiMessage(const D2RL::PluginContext*, const D2RL::SharedEvents::UiMessageEvent* event, void*) noexcept -> D2RL::SharedEvents::UiMessageAction {
	if (event == nullptr || event->target == nullptr || event->command == nullptr || event->text == nullptr ||
	    std::strcmp(event->target, "PanelManager") != 0 || std::strcmp(event->command, "OpenPanel") != 0 ||
	    std::strcmp(event->text, mxl_send_stash::MessagePanel) != 0) {
		return D2RL::SharedEvents::UiMessageAction::Continue;
	}
	g_clicks.fetch_add(1);
	(void)SendStashPress();
	return D2RL::SharedEvents::UiMessageAction::Consume;
}

}  // namespace

auto InstallSendStash(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	g_context = context;
	const struct {
		uint64_t rva;
		const uint8_t* bytes;
		size_t n;
	} entries[] = {{RvaSend, SendEntry, sizeof(SendEntry)},           {RvaLocalId, LocalIdEntry, sizeof(LocalIdEntry)},
	               {RvaPlayerById, PlayerByIdEntry, sizeof(PlayerByIdEntry)}, {RvaClientUnit, ClientUnitEntry, sizeof(ClientUnitEntry)},
	               {RvaInventory, InventoryEntry, sizeof(InventoryEntry)}, {RvaInvFirst, InvFirstEntry, sizeof(InvFirstEntry)},
	               {RvaInvNext, InvNextEntry, sizeof(InvNextEntry)},       {RvaUnitClass, UnitFieldEntry, sizeof(UnitFieldEntry)},
	               {RvaUnitId, UnitFieldEntry, sizeof(UnitFieldEntry)},    {RvaItemPage, ItemPageEntry, sizeof(ItemPageEntry)},
	               {RvaHasState, HasStateEntry, sizeof(HasStateEntry)},    {RvaClientOf, ClientOfEntry, sizeof(ClientOfEntry)},
	               {RvaSendChat, SendChatEntry, sizeof(SendChatEntry)}};
	for (const auto& e : entries) {
		if (!EntryMatches(e.rva, e.bytes, e.n)) {
			std::snprintf(report, reportSize, "sendstash off: the bytes of 0x%llx differ", static_cast<unsigned long long>(e.rva));
			return false;
		}
	}
	const D2RL::SharedEventService* events = nullptr;
	if (context->QueryService(&g_threads) != D2RL::ServiceQueryResult::Success || !D2RL::HasThreadServiceField(g_threads, D2RL::ThreadServiceRequiredSize) ||
	    context->QueryService(&g_widgets) != D2RL::ServiceQueryResult::Success || !D2RL::HasWidgetServiceField(g_widgets, D2RL::WidgetServiceRequiredSize) ||
	    context->QueryService(&events) != D2RL::ServiceQueryResult::Success || !D2RL::HasSharedEventServiceField(events, D2RL::SharedEventServiceRequiredSize)) {
		std::snprintf(report, reportSize, "sendstash off: ThreadService / WidgetService / SharedEventService unavailable");
		return false;
	}
	if (context->QueryService(&g_strings) != D2RL::ServiceQueryResult::Success ||
	    !D2RL::HasLocalizationServiceField(g_strings, D2RL::LocalizationServiceRequiredSize)) {
		g_strings = nullptr;  // the summary names items by code
	}
	g_send = At<SendFn>(RvaSend);
	g_localId = At<LocalIdFn>(RvaLocalId);
	g_playerById = At<PlayerByIdFn>(RvaPlayerById);
	g_clientUnit = At<ClientUnitFn>(RvaClientUnit);
	g_inventory = At<InventoryFn>(RvaInventory);
	g_invFirst = At<InvFirstFn>(RvaInvFirst);
	g_invNext = At<InvNextFn>(RvaInvNext);
	g_unitClass = At<UnitFieldFn>(RvaUnitClass);
	g_unitId = At<UnitFieldFn>(RvaUnitId);
	g_dataFlag = At<DataFlagFn>(RvaDataFlag);
	g_itemRecord = At<ItemRecordFn>(RvaItemRecord);
	g_itemPage = At<ItemPageFn>(RvaItemPage);
	g_hasState = At<HasStateFn>(RvaHasState);
	g_serverUnit = At<ServerUnitFn>(RvaServerUnit);
	g_clientOf = At<ClientOfFn>(RvaClientOf);
	g_sendChat = At<SendChatFn>(RvaSendChat);

	// an empty panel named as the button's message: D2R hands a button's PanelManager message to the listeners only for a known panel
	const D2RL::ResourceService* resources = nullptr;
	const D2RL::PanelService* panels = nullptr;
	bool panel = context->QueryService(&resources) == D2RL::ServiceQueryResult::Success &&
	             context->QueryService(&panels) == D2RL::ServiceQueryResult::Success && D2RL::HasPanelServiceField(panels, D2RL::PanelServiceRequiredSize);
	for (const char* suffix : {"hd", ""}) {
		char path[96];
		std::snprintf(path, sizeof(path), "data/global/ui/layouts/mxl2012-core/%s%s.json", PanelLocalId, suffix);
		D2RL::Resources::ResourceRegistration resource{};
		resource.structSize = D2RL::Resources::ResourceRegistrationSize;
		resource.path = path;
		resource.bytes = PanelLayout;
		resource.byteCount = std::strlen(PanelLayout);
		D2RL::Resources::RegistrationHandle handle = D2RL::Resources::InvalidHandle;
		panel = panel && resources->registerResource(context, &resource, &handle) == D2RL::Resources::Result::Success;
	}
	if (panel) {
		D2RL::Panels::PanelRegistration registration{};
		registration.structSize = D2RL::Panels::PanelRegistrationSize;
		registration.flags = D2RL::Panels::PanelFlags::CloseOnEscape;
		registration.localId = PanelLocalId;
		D2RL::Panels::RegistrationHandle handle = 0;
		panel = panels->registerPanel(context, &registration, &handle) == D2RL::Panels::Result::Success;
	}

	D2RL::SharedEvents::UiMessageListener listener{};
	listener.structSize = D2RL::SharedEvents::UiMessageListenerSize;
	listener.callback = &OnUiMessage;
	D2RL::SharedEvents::ListenerHandle handle = 0;
	if (events->registerUiMessageListener(context, &listener, &handle) != D2RL::SharedEvents::Result::Success) {
		std::snprintf(report, reportSize, "sendstash off: registerUiMessageListener failed");
		return false;
	}
	g_frame = InstallServerFrame(context) && AddServerFrameCallback(&Frame);
	HANDLE timer = CreateThread(nullptr, 0, Timer, nullptr, 0, nullptr);
	if (timer == nullptr) {
		std::snprintf(report, reportSize, "sendstash off: no timer thread");
		return false;
	}
	CloseHandle(timer);
	g_ready = true;
	std::snprintf(report, reportSize, "sendstash on: inventory button (panel %s), %u slot codes, packet 0x63 per item; summary line %s; joiners %s",
	              panel ? "registered" : "NOT registered", mxl_send_stash::CodeCount, g_frame ? "on" : "off (no server frame hook)", JoinersOn ? "on" : "off");
	return true;
}

void SendStashStatus(char* out, size_t size) noexcept {
	static const char* const shows[] = {"none", "button", "noslots", "joined"};
	const int show = g_show.load();
	std::snprintf(out, size, "show=%s host=%u local=%u frames=%ld running=%d clicks=%ld runs=%ld sent=%ld full=%ld nottaken=%ld busy=%ld refused=%ld lines=%ld linefails=%ld faults=%ld",
	              show >= 0 && show < 4 ? shows[show] : "-", g_hostPlayer.load(), g_ready ? g_localId() : 0u, g_frames.load(), g_running.load() ? 1 : 0, g_clicks.load(), g_runs.load(),
	              g_sent.load(), g_full.load(), g_notTaken.load(), g_busy.load(), g_refused.load(), g_lines.load(), g_lineFails.load(), g_faults.load());
}

auto SendStashLastLine() noexcept -> const char* {
	return g_lastLine;
}

auto SendStashPress() noexcept -> bool {
	if (!g_ready || g_running.load()) {
		if (g_ready) {
			g_busy.fetch_add(1);
		}
		return false;
	}
	g_clickQueued.store(true);
	QueueTick();
	return true;
}

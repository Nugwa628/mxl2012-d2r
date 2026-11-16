// Stat Book: a D2RLoader plugin that turns D2R's character sheet into a book with folder tabs (docs/statbook.md).
// Parts, each with a switch in statbook.toml:
//  - sheetres (sheet_resist.cpp): the Magic / Physical Resistance rows of page 1, in layouts that have them;
//  - advstats (advstats.cpp): D2R's Advanced Stats panel in groups;
//  - the book: the themed pages and All Stats from the book file (the mod's data/statbook/statbook.txt, else the plain D2R
//    book compiled in), filled by book_logic.h into the host's widgets; Chance to Block from D2R's GetBlockRate; the gamepad
//    tab buttons on the gamepad Character page (a hook on the gamepad menu's input handler, see "gamepad tabs" below).
// The sheet host (the widgets the pages are filled into) binds to the layout contract of docs/statbook-layout.md; until that
// layout is served, the book is only filled on request: console command `statbook page <n>` prints a page's lines.
// Console command `statbook`: one status line per part (the game checks read them).
// All game addresses are of one D2R image (0x6ab3782c, D2RLoader 1.3.1); on another image nothing is hooked or called.
#include <D2RLPlugin/api.h>
#include <D2RLPlugin/input.h>
#include <D2RLPlugin/threads.h>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>

#include <atomic>
#include <cstdio>
#include <cstring>
#include <string>

#include "../../plugin/src/block_rate_logic.h"
#include "../../plugin/src/panel_shared.h"
#include "advstats.h"
#include "book_logic.h"
#include "sheet_host.h"
#include "sheet_resist.h"
#include "statbook_config.h"
#ifdef STATBOOK_TEST_HARNESS
#include "testharness.h"
#endif

namespace {

constexpr const char* PluginVersion = "0.1.2";
constexpr uint32_t SupportedImage = 0x6ab3782cU;

constexpr D2RL::PluginInfo Info{
    .infoSize = D2RL::PluginInfoSize,
    .abiVersion = D2RL_PLUGIN_ABI_VERSION,
    .id = "statbook",
    .name = "Stat Book",
    .version = PluginVersion,
    .author = "D2R-XL 2012",
    .description = "The character sheet as a book: themed stat pages and a searchable list of all stats.",
    .flags = D2RL::PluginFlags::Client | D2RL::PluginFlags::NativeHooks,
};

constexpr const char* DefaultBook =
#include "default_book.inc"
    ;

// game functions (image 0x6ab3782c)
constexpr uint64_t RvaLocalId = 0x8b2d0;       // () -> the client's own player id
constexpr uint64_t RvaClientPlayer = 0x9a480;  // (id) -> the client's player unit
constexpr uint64_t RvaTypeId = 0x80d70;        // (name + 1, hash) -> the registered id of a message type, 0 when none yet
// The gamepad menu (UISwitcher, layouts/controller/uiswitcherhd.json: Quest Log, Character, Inventory, ... with its tab strip)
// gets the controller actions while it is open; the page panels (CharacterStatsPanel among them) do not (lane sbresearch,
// docs/statbook.md "Gamepad"). Its vtable slot 4 (0x1cef450) is its input handler: D2R's 0x27e620 (InputMessage check, then
// 0x27df80: actions 19 / 20 page the menu, 9 / 23 close it, the rest goes to the children). D2RLoader routes the slot
// through D2RCore (plugin controller routes) and Controller QOL Updates wraps it (triggers page, bumpers dropped), so the hook
// chains whatever the slot holds and sees the raw buttons first. ControllerActionBegin messages: [msg] the InputMessage type,
// [msg + 0x88] the ControllerActionBegin type, [msg + 0x110] the payload: action id at +0x10, repeat byte at +0x18.
// Menu fields: +0x168 int32 panel id of each page (8), +0x188 page count, +0x1b8 current page; 0x846190(id) -> the page's
// panel widget (its name, const char*, at +8).
constexpr uint64_t RvaMenuInputSlot = 0x1cef450;
constexpr uint64_t RvaMenuInput = 0x27e620;
constexpr uint8_t MenuInputEntry[] = {0x4c, 0x8b, 0xdc, 0x55, 0x56, 0x41, 0x56, 0x49, 0x8d, 0x6b, 0xa1, 0x48, 0x81, 0xec, 0xe0, 0x00, 0x00, 0x00};
constexpr uint64_t RvaPanelById = 0x846190;
constexpr uint64_t RvaInputMessageName = 0x1cbb628;         // "InputMessage"
constexpr uint64_t InputMessageHash = 0xaf64044c86023084ULL;
constexpr uint64_t RvaActionBeginName = 0x1cd1210;          // "ControllerActionBegin"
constexpr uint64_t ActionBeginHash = 0xaf63fe4c86022652ULL;
constexpr const char* SheetPanelName = "CharacterStatsPanel";

using LocalIdFn = uint32_t (*)();
using ClientPlayerFn = void* (*)(uint32_t);
using TypeIdFn = uint64_t (*)(const char*, uint64_t);
using InputFn = uint64_t (*)(void*, uint8_t*);
using PanelByIdFn = uint8_t* (*)(int32_t);
using IsClassicFn = uint8_t (*)();

const D2RL::PluginContext* g_context = nullptr;
uint64_t g_base = 0;
bool g_imageOk = false;
char g_selfPath[MAX_PATH * 3] = "";
statbook::Config g_config;
statbook::Book g_book;
char g_bookFrom[160] = "not read";
bool g_modBook = false;  // the mod's own book file: the mod is D2R-XL 2012 (its stat ids), not plain D2R
char g_sheetResReport[192] = "sheetres off: not installed";
char g_advStatsReport[192] = "advstats off: not installed";
char g_blockReport[160] = "block off: not installed";
char g_padReport[256] = "pad off: not installed";
bool g_statsOk = false;
bool g_blockOk = false;
statbook::Tabs g_tabs;
statbook::PadButtons g_padChoice = statbook::PadButtons::Off;
InputFn volatile g_menuInput = nullptr;
std::atomic<long> g_padActions{0}, g_padSteps{0}, g_padMatched{0}, g_padCalls{0};
std::atomic<int> g_lastAction{-1};
std::atomic<int> g_lastBlock{-1000};

template <class F>
auto Fn(uint64_t rva) noexcept -> F {
	return reinterpret_cast<F>(g_base + rva);
}

void Log(const char* line) {
	g_context->LogInfo(line);
}

auto ImageStamp(uint64_t base) noexcept -> uint32_t {
	if (base == 0) {
		return 0;
	}
	const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
	return reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + dos->e_lfanew)->FileHeader.TimeDateStamp;
}

void FindSelf() noexcept {
	HMODULE self = nullptr;
	GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, reinterpret_cast<LPCWSTR>(&FindSelf), &self);
	wchar_t wide[MAX_PATH];
	const DWORD n = GetModuleFileNameW(self, wide, MAX_PATH);
	if (n > 0 && n < MAX_PATH) {
		WideCharToMultiByte(CP_UTF8, 0, wide, -1, g_selfPath, sizeof(g_selfPath), nullptr, nullptr);
	}
}

// A file next to statbook.dll (the test harness switch).
auto Beside(const char* name, char* out, size_t size) noexcept -> bool {
	const char* slash = std::strrchr(g_selfPath, '\\');
	if (slash == nullptr) {
		return false;
	}
	std::snprintf(out, size, "%.*s\\%s", static_cast<int>(slash - g_selfPath), g_selfPath, name);
	return true;
}

// Console line; with the mod's test harness on (mxl2012-testharness.txt beside the DLL) also appended to
// mxl2012-testharness-console.txt, which tools/game_ctl.py console_text reads.
void Say(const D2RL::ConsoleCommandContext* command, const char* text) noexcept {
	command->plugin->WriteConsoleMessage(text);
	char sw[MAX_PATH * 3], out[MAX_PATH * 3];
	// mxl2012-core's harness switch, or (plain D2R, test builds only) statbook's own: the same console file for game_ctl.py
	bool on = Beside("mxl2012-testharness.txt", sw, sizeof(sw)) && GetFileAttributesA(sw) != INVALID_FILE_ATTRIBUTES;
#ifdef STATBOOK_TEST_HARNESS
	on = on || (Beside("statbook-testharness.txt", sw, sizeof(sw)) && GetFileAttributesA(sw) != INVALID_FILE_ATTRIBUTES);
#endif
	if (!on || !Beside("mxl2012-testharness-console.txt", out, sizeof(out))) {
		return;
	}
	char buf[1024];
	const int len = std::snprintf(buf, sizeof(buf), "%s\n", text);
	if (len <= 0) {
		return;
	}
	for (int attempt = 0; attempt < 500; ++attempt) {
		HANDLE h = CreateFileA(out, FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
		if (h != INVALID_HANDLE_VALUE) {
			DWORD written = 0;
			WriteFile(h, buf, static_cast<DWORD>(len < static_cast<int>(sizeof(buf)) ? len : static_cast<int>(sizeof(buf)) - 1), &written, nullptr);
			CloseHandle(h);
			return;
		}
		Sleep(1);
	}
}

void LoadBook() {
	std::string text;
	const auto r = panel_shared::ReadModFile(g_context, g_selfPath, L"data\\statbook\\statbook.txt", 1024 * 1024, &text);
	if (r == panel_shared::FileResult::Ok) {
		g_book = statbook::ParseBook(text);
		if (g_book.error.empty()) {
			std::snprintf(g_bookFrom, sizeof(g_bookFrom), "the mod's data/statbook/statbook.txt");
			g_modBook = true;
			return;
		}
		char line[300];
		std::snprintf(line, sizeof(line), "statbook: the mod's book is bad (%s); the plain D2R book instead", g_book.error.c_str());
		g_context->LogWarn(line);
	}
	g_book = statbook::ParseBook(DefaultBook);
	std::snprintf(g_bookFrom, sizeof(g_bookFrom), "%s", g_book.error.empty() ? "the plain D2R book (built in)" : "none: the built-in book is bad");
}

auto Player() noexcept -> void* {
	return Fn<ClientPlayerFn>(RvaClientPlayer)(Fn<LocalIdFn>(RvaLocalId)());
}

// D2R's Chance to Block for the client's player, as the sheet's defense tooltip asks it (expansion = not a classic game).
auto BlockRate(void* player) noexcept -> int32_t {
	if (!g_blockOk || player == nullptr) {
		return 0;
	}
	const bool classic = Fn<IsClassicFn>(block_rate::ClientIsClassicRva)() != 0;
	const int32_t rate = Fn<block_rate::GetBlockRateFn>(block_rate::GetBlockRateRva)(player, classic ? 0 : 1);
	g_lastBlock.store(rate);
	return rate;
}

// The player's class id (unit +4) for `:c` stats.
auto ClassId(void* player) noexcept -> int32_t {
	return *reinterpret_cast<const int32_t*>(static_cast<const uint8_t*>(player) + 4);
}

auto ValuesOf(void* player) {
	return [player](uint16_t id, bool classParam) -> int32_t {
		if (id == statbook::BlockRateStat) {
			return BlockRate(player);
		}
		return ShiftedStat(player, id, classParam ? ClassId(player) : 0);
	};
}

// ---- gamepad tabs ----------------------------------------------------------------------------------------------------

auto TypeId(uint64_t nameRva, uint64_t hash) noexcept -> uint64_t {
	return Fn<TypeIdFn>(RvaTypeId)(reinterpret_cast<const char*>(g_base + nameRva + 1), hash);
}

// The sheet host is present when it has bound the served sheet (the layout has the book's widgets, docs/statbook-layout.md);
// until then the buttons are left to D2R.
auto HostPresent() noexcept -> bool {
	return SheetHostBound();
}

// Test installs (the harness switch beside the DLL, as Say() reads it) stand in for the sheet host: the tab buttons step the
// book's tab and are taken from D2R, so a game check can prove the route before the host is bound.
auto TestTakesTabs() noexcept -> bool {
	char sw[MAX_PATH * 3];
	bool on = Beside("mxl2012-testharness.txt", sw, sizeof(sw)) && GetFileAttributesA(sw) != INVALID_FILE_ATTRIBUTES;
#ifdef STATBOOK_TEST_HARNESS
	on = on || (Beside("statbook-testharness.txt", sw, sizeof(sw)) && GetFileAttributesA(sw) != INVALID_FILE_ATTRIBUTES);
#endif
	return on;
}

// A loaded D2RLoader plugin with this id (its D2RLoaderGetPluginInfo export), whatever its file is called.
auto PluginLoaded(const char* id) noexcept -> bool {
	HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, GetCurrentProcessId());
	if (snap == INVALID_HANDLE_VALUE) {
		return false;
	}
	bool found = false;
	MODULEENTRY32W m{};
	m.dwSize = sizeof(m);
	for (BOOL ok = Module32FirstW(snap, &m); ok && !found; ok = Module32NextW(snap, &m)) {
		const auto info = reinterpret_cast<D2RL::GetPluginInfoFn>(GetProcAddress(m.hModule, D2RL_PLUGIN_GET_INFO_EXPORT));
		if (info == nullptr) {
			continue;
		}
		__try {
			const D2RL::PluginInfo* pi = info();
			found = pi != nullptr && D2RL::HasPluginInfoField(pi, D2RL::PluginInfoAbiVersionSize + sizeof(const char*)) && pi->id != nullptr &&
			        std::strcmp(pi->id, id) == 0;
		} __except (EXCEPTION_EXECUTE_HANDLER) {
			found = false;
		}
	}
	CloseHandle(snap);
	return found;
}

// Controller QOL Updates may load after this plugin: asked at the press (by its plugin id, at most every 2 s while not seen),
// kept once seen.
auto PadChoiceNow() noexcept -> statbook::PadButtons {
	static std::atomic<bool> qolSeen{false};
	static std::atomic<unsigned long long> lastScan{0};
	if (!qolSeen.load()) {
		const unsigned long long now = GetTickCount64();
		if (GetModuleHandleW(L"Controller QOL Updates.dll") != nullptr) {
			qolSeen.store(true);
		} else if (now - lastScan.load() >= 2000) {
			lastScan.store(now);
			qolSeen.store(PluginLoaded("controller-qol-updates"));
		}
	}
	g_padChoice = statbook::PadChoice(g_config.pad, qolSeen.load());
	return g_padChoice;
}

// The name of the gamepad menu's current page panel ("CharacterStatsPanel" on the Character page), nullptr when none.
auto MenuPageName(const uint8_t* menu, int32_t* page) noexcept -> const char* {
	const int32_t count = *reinterpret_cast<const int32_t*>(menu + 0x188), current = *reinterpret_cast<const int32_t*>(menu + 0x1b8);
	*page = current;
	if (current < 0 || current >= count || current >= 8) {
		return nullptr;
	}
	const uint8_t* panel = Fn<PanelByIdFn>(RvaPanelById)(*reinterpret_cast<const int32_t*>(menu + 0x168 + current * 4));
	return panel != nullptr ? *reinterpret_cast<const char* const*>(panel + 8) : nullptr;
}

uint64_t MenuInputHook(void* menu, uint8_t* msg) {
	int32_t action = -1, page = -1;
	bool repeat = false, sheet = false;
	const char* name = nullptr;
	g_padCalls.fetch_add(1);
	__try {
		const uint64_t input = TypeId(RvaInputMessageName, InputMessageHash);
		const uint64_t begin = TypeId(RvaActionBeginName, ActionBeginHash);
		if (msg != nullptr && input != 0 && begin != 0 && *reinterpret_cast<uint64_t*>(msg) == input &&
		    *reinterpret_cast<uint64_t*>(msg + 0x88) == begin) {
			const uint8_t* rec = *reinterpret_cast<uint8_t**>(msg + 0x110);
			if (rec != nullptr) {
				action = *reinterpret_cast<const int32_t*>(rec + 0x10);
				repeat = rec[0x18] != 0;
				name = MenuPageName(static_cast<const uint8_t*>(menu), &page);
				sheet = name != nullptr && std::strcmp(name, SheetPanelName) == 0;
			}
		}
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		action = -1;
		sheet = false;
	}
	if (action >= 0) {
		g_padActions.fetch_add(1);
		g_lastAction.store(action);
		const int step = sheet ? statbook::PadStep(g_config, PadChoiceNow(), action) : 0;
		const bool take = step != 0 && (HostPresent() || TestTakesTabs());
		if (g_config.padLog) {
			char line[200];
			std::snprintf(line, sizeof(line), "statbook: menu controller action %d%s on page %d (%s)%s", action, repeat ? " (repeat)" : "", page,
			              name != nullptr ? name : "?", step == 0 ? "" : take ? ": tab button, taken" : ": tab button (no sheet host yet: left to D2R)");
			Log(line);
		}
		if (step != 0) {
			g_padMatched.fetch_add(1);
		}
		if (take) {
			if (!repeat) {
				g_tabs.Step(step);
				if (SheetHostBound()) {
					SheetHostStep(step);
				}
				g_padSteps.fetch_add(1);
			}
			return 0;
		}
	}
	return g_menuInput(menu, msg);
}

void InstallPad() noexcept {
	if (g_config.pad == statbook::PadButtons::Off) {
		std::snprintf(g_padReport, sizeof(g_padReport), "pad off: pad_tabs = off");
		return;
	}
	// The slot holds D2R's handler, D2RLoader's route thunk or another plugin's wrapper: any of them is chained. D2R's own
	// handler must still be the one of this image.
	const uint64_t slot = *reinterpret_cast<const uint64_t*>(g_base + RvaMenuInputSlot);
	if (slot == 0 || std::memcmp(reinterpret_cast<const void*>(g_base + RvaMenuInput), MenuInputEntry, sizeof(MenuInputEntry)) != 0) {
		std::snprintf(g_padReport, sizeof(g_padReport), "pad off: the gamepad menu's input handler 0x%llx differs",
		              static_cast<unsigned long long>(RvaMenuInput));
		return;
	}
	g_menuInput = reinterpret_cast<InputFn>(slot);
	if (!g_context->PatchWriteU64(RvaMenuInputSlot, &slot, sizeof(slot), reinterpret_cast<uint64_t>(&MenuInputHook))) {
		std::snprintf(g_padReport, sizeof(g_padReport), "pad off: the slot write was refused");
		return;
	}
	const bool bumpers = PadChoiceNow() == statbook::PadButtons::Bumpers;
	const int32_t left = bumpers ? g_config.bumperLeft : g_config.triggerLeft, right = bumpers ? g_config.bumperRight : g_config.triggerRight;
	const uint64_t chained = slot - g_base;
	std::snprintf(g_padReport, sizeof(g_padReport), "pad on: tabs on the %s at load (Controller QOL %s), actions %d / %d, menu slot chained to %s 0x%llx",
	              bumpers ? "bumpers" : "triggers", bumpers ? "in the game" : "not loaded yet, asked again at the presses", left, right,
	              slot == g_base + RvaMenuInput ? "D2R" : chained < 0x4000000 ? "D2R image" : "module", static_cast<unsigned long long>(chained < 0x4000000 ? chained : slot));
}

// ---- sheet host --------------------------------------------------------------------------------------------------------

auto HostPadTriggers() noexcept -> bool {
	return PadChoiceNow() == statbook::PadButtons::Triggers;
}

auto HostPlayer() noexcept -> void* {
	return g_imageOk && g_statsOk ? Player() : nullptr;
}

auto HostValue(void* player, uint16_t id, bool classParam) noexcept -> int32_t {
	return ValuesOf(player)(id, classParam);
}

char g_hostReport[400] = "host off: not installed";

// ---- console -----------------------------------------------------------------------------------------------------------

const char* const ToneNames[] = {"white", "grey", "red", "blue", "yellow", "purple", "magic", "gold", "itemblue", "green"};

void SayPage(const D2RL::ConsoleCommandContext* command, int page) {
	char line[512];
	if (page < 0 || page >= static_cast<int>(g_book.pages.size())) {
		std::snprintf(line, sizeof(line), "statbook page: 0 .. %zu", g_book.pages.size() - 1);
		Say(command, line);
		return;
	}
	void* player = g_imageOk && g_statsOk ? Player() : nullptr;
	if (player == nullptr) {
		Say(command, "statbook page: no player (in a game?)");
		return;
	}
	statbook::Line lines[40];
	const size_t total = statbook::PageLines(g_book.pages[static_cast<size_t>(page)], ValuesOf(player), 0, lines, 40);
	std::snprintf(line, sizeof(line), "statbook page %d %s: %zu lines", page, g_book.pages[static_cast<size_t>(page)].title.c_str(), total);
	Say(command, line);
	for (size_t i = 0; i < total && i < 40; ++i) {
		const statbook::Line& l = lines[i];
		if (l.kind == statbook::Line::Kind::Heading) {
			std::snprintf(line, sizeof(line), "sbline %zu heading | %s", i, l.heading.c_str());
		} else {
			const statbook::Cell& a = l.cell[0];
			const statbook::Cell& b = l.cell[1];
			std::snprintf(line, sizeof(line), "sbline %zu %s | %s = %s (%s)%s%s%s%s%s", i, l.kind == statbook::Line::Kind::Full ? "full" : "pair", a.label.c_str(),
			              a.value.c_str(), ToneNames[static_cast<int>(a.tone)], l.right ? " | " : "", l.right ? b.label.c_str() : "", l.right ? " = " : "",
			              l.right ? b.value.c_str() : "", l.right ? (std::string(" (") + ToneNames[static_cast<int>(b.tone)] + ")").c_str() : "");
		}
		Say(command, line);
	}
}

// ---- top / side tabs: the book's toggle button, the Controls action, `statbook tabs` -------------------------------------------
// D2R's Options menu has no plugin API (docs/legacy-hd-text-research.md section 3), so the setting is switched in the game by the
// toggle on the book and by the rebindable action "Stat Book: Top/Side Tabs" (Options > Controls, category Advanced Stats), and
// written back to statbook.toml ([statbook] tabs) so it holds for the next game.

std::atomic<long> g_tabsWrites{0}, g_tabsWriteFails{0}, g_tabsActions{0};
D2RL::Input::ActionHandle g_tabsAction = D2RL::Input::InvalidHandle;
char g_tabsActionReport[96] = "not registered";

void WriteTabs(bool side) noexcept {
	static char toml[16384];
	static char out[16384 + 64];
	uint32_t need = 0;
	if (!g_context->ReadConfig(toml, sizeof(toml), &need)) {
		toml[0] = '\0';
	}
	if (statbook::WithTabs(toml, side, out, sizeof(out)) && g_context->WriteConfig(out)) {
		g_tabsWrites.fetch_add(1);
	} else {
		g_tabsWriteFails.fetch_add(1);
	}
	char line[96];
	std::snprintf(line, sizeof(line), "statbook: tabs = \"%s\"", side ? "side" : "top");
	Log(line);
}

void __cdecl TabsChanged(bool side) noexcept {
	WriteTabs(side);
}

void SetTabs(bool side) noexcept {
	SheetHostSetSide(side);
	WriteTabs(side);
}

auto __cdecl OnTabsAction(const D2RL::PluginContext*, const D2RL::Input::ActionEvent* event, void*) noexcept -> D2RL::Input::ActionResult {
	if (!D2RL::Input::HasActionEventField(event, D2RL::Input::ActionEventRequiredSize) || event->kind != D2RL::Input::ActionEventKind::Pressed) {
		return D2RL::Input::ActionResult::Ignored;
	}
	g_tabsActions.fetch_add(1);
	SetTabs(!SheetHostSide());
	return D2RL::Input::ActionResult::Handled;
}

void RegisterTabsAction(const D2RL::PluginContext* context) noexcept {
	const D2RL::InputService* input = nullptr;
	if (context->QueryService(&input) != D2RL::ServiceQueryResult::Success || !D2RL::HasInputServiceField(input, D2RL::InputServiceRequiredSize)) {
		std::snprintf(g_tabsActionReport, sizeof(g_tabsActionReport), "no InputService");
		return;
	}
	const D2RL::Input::ActionRegistration reg{
	    .structSize = D2RL::Input::ActionRegistrationSize,
	    .flags = 0,
	    .logicalId = "mxl_statbook_tabs",
	    .displayName = "Stat Book: Top/Side Tabs",
	    .category = "Advanced Stats",
	    .defaultPrimary = {.key = D2RL::Input::Key::None, .modifier = D2RL::Input::Modifier::None},
	    .defaultSecondary = {.key = D2RL::Input::Key::None, .modifier = D2RL::Input::Modifier::None},
	    .callback = &OnTabsAction,
	    .userData = nullptr,
	};
	const bool ok = input->registerAction(context, &reg, &g_tabsAction) == D2RL::Input::Result::Success && g_tabsAction != D2RL::Input::InvalidHandle;
	std::snprintf(g_tabsActionReport, sizeof(g_tabsActionReport), "%s", ok ? "mxl_statbook_tabs (unbound by default)" : "NOT registered");
}

auto __cdecl StatusCommand(D2R::Game::Client*, const D2RL::ConsoleCommandContext* command, void*) noexcept -> D2RL::ConsoleCommandResult {
	char line[700];
	const char* args = command->args != nullptr ? command->args : "";
	while (*args == ' ') {
		++args;
	}
	if (std::strncmp(args, "tab ", 4) == 0) {
		SheetHostSelect(std::atoi(args + 4));
		Say(command, "statbook tab: queued");
		return D2RL::ConsoleCommandResult::Handled;
	}
	if (std::strncmp(args, "find", 4) == 0) {
		const char* q = args + 4;
		while (*q == ' ') {
			++q;
		}
		SheetHostFind(q);
		Say(command, "statbook find: queued");
		return D2RL::ConsoleCommandResult::Handled;
	}
	if (std::strncmp(args, "vis ", 4) == 0) {
		char name[96] = {};
		int on = -1;
		if (std::sscanf(args + 4, "%95s %d", name, &on) >= 1) {
			SheetHostHold(name, on);
		}
		Say(command, "statbook vis: queued");
		return D2RL::ConsoleCommandResult::Handled;
	}
	if (std::strncmp(args, "tabs", 4) == 0) {
		const char* v = args + 4;
		while (*v == ' ') {
			++v;
		}
		if (std::strncmp(v, "side", 4) == 0 || std::strncmp(v, "top", 3) == 0 || std::strncmp(v, "toggle", 6) == 0) {
			SetTabs(v[0] == 's' ? true : v[1] == 'o' && v[2] == 'p' ? false : !SheetHostSide());
		}
		std::snprintf(line, sizeof(line), "statbook tabs: %s (side panel %s; written %ld, write fails %ld; action %s, presses %ld)", SheetHostSide() ? "side" : "top",
		              SheetHostSideReady() ? "ready" : "none: top tabs only", g_tabsWrites.load(), g_tabsWriteFails.load(), g_tabsActionReport, g_tabsActions.load());
		Say(command, line);
		return D2RL::ConsoleCommandResult::Handled;
	}
	if (std::strncmp(args, "host", 4) == 0) {
		char status[1024];
		SheetHostStatus(status, sizeof(status));
		std::snprintf(line, sizeof(line), "host %s", status);
		Say(command, line);
		return D2RL::ConsoleCommandResult::Handled;
	}
	if (std::strncmp(args, "page", 4) == 0) {
		__try {
			SayPage(command, std::atoi(args + 4));
		} __except (EXCEPTION_EXECUTE_HANDLER) {
			Say(command, "statbook page: fault");
		}
		return D2RL::ConsoleCommandResult::Handled;
	}
	std::snprintf(line, sizeof(line), "statbook %s: image %s, mod %s, file %s", PluginVersion, g_imageOk ? "supported" : "other (nothing hooked)",
	              g_context->activeMod != nullptr && g_context->activeMod[0] != '\0' ? g_context->activeMod : "-", g_selfPath);
	Say(command, line);
	char status[256];
	SheetResistStatus(status, sizeof(status));
	std::snprintf(line, sizeof(line), "sheetres %s | %s", g_sheetResReport, status);
	Say(command, line);
	long builds = 0, rebuilds = 0, texts = 0, rows = 0;
	int from = 0;
	AdvancedStatsCounts(&builds, &rebuilds, &texts, &rows, &from);
	std::snprintf(line, sizeof(line), "advstats %s; lists built %ld (rebuilt on a change %ld), own row texts %ld, rows last listed %ld, strings %s", g_advStatsReport,
	              builds, rebuilds, texts, rows, from == 1 ? "mxl2012" : from == 2 ? "English fallback" : "not read yet");
	Say(command, line);
	size_t rowCount = 0, allCount = 0;
	for (const auto& p : g_book.pages) {
		for (const auto& s : p.sections) {
			rowCount += s.rows.size();
		}
	}
	for (const auto& g : g_book.all) {
		allCount += g.rows.size();
	}
	std::snprintf(line, sizeof(line), "book %s: %zu pages, %zu rows, %zu All Stats rows from %s; tab %d of %d; %s, bound %d",
	              g_config.book ? "on" : "off", g_book.pages.size(), rowCount, allCount, g_bookFrom, SheetHostTab(), g_tabs.Count(), g_hostReport,
	              SheetHostBound() ? 1 : 0);
	Say(command, line);
	std::snprintf(line, sizeof(line), "%s; last rate %d", g_blockReport, g_lastBlock.load());
	Say(command, line);
	std::snprintf(line, sizeof(line), "%s; menu messages %ld, actions %ld, last %d, tab buttons %ld, tab steps %ld", g_padReport, g_padCalls.load(), g_padActions.load(), g_lastAction.load(),
	              g_padMatched.load(), g_padSteps.load());
	Say(command, line);
	return D2RL::ConsoleCommandResult::Handled;
}

}  // namespace

D2RL_PLUGIN_EXPORT auto D2RLoaderGetPluginInfo() noexcept -> const D2RL::PluginInfo* {
	return &Info;
}

D2RL_PLUGIN_EXPORT auto D2RLoaderLoadPlugin(const D2RL::PluginContext* context) noexcept -> bool {
	if (context == nullptr) {
		return false;
	}
	g_context = context;
	g_base = context->exeBase;
	FindSelf();
	char text[4096];
	uint32_t need = 0;
	text[0] = '\0';
	g_config = statbook::ParseConfig(context->ReadConfig(text, sizeof(text), &need) ? text : nullptr);
	const uint32_t stamp = ImageStamp(g_base);
	g_imageOk = stamp == SupportedImage;
	char line[512];
	std::snprintf(line, sizeof(line), "statbook %s loaded (%s scope, mod %s, D2R %s, image 0x%08x %s)", PluginVersion,
	              context->loadScope == D2RL::LoadScope::Mod ? "mod" : "global", context->activeMod ? context->activeMod : "-",
	              context->buildVersion ? context->buildVersion : "?", stamp, g_imageOk ? "supported" : "NOT supported: nothing hooked");
	Log(line);
#ifdef STATBOOK_TEST_HARNESS
	char harness[256];
	InstallTestHarness(harness, sizeof(harness));
	context->LogWarn(harness);
#endif
	LoadBook();
	g_tabs.pages = static_cast<int>(g_book.pages.size());
	std::snprintf(line, sizeof(line), "statbook: book from %s: %zu pages", g_bookFrom, g_book.pages.size());
	Log(line);
	if (g_imageOk) {
		if (g_config.sheetRows) {
			InstallSheetResist(context, g_sheetResReport, sizeof(g_sheetResReport));
		} else {
			std::snprintf(g_sheetResReport, sizeof(g_sheetResReport), "off: sheet_rows = false");
		}
		Log(g_sheetResReport);
		if (g_config.advancedStats && !g_modBook) {
			// the grouped list (advstats_table.h) holds D2R-XL 2012's stat ids; plain D2R keeps its own panel
			std::snprintf(g_advStatsReport, sizeof(g_advStatsReport), "advstats off: no mod book (plain D2R): D2R's own Advanced Stats panel");
		} else if (g_config.advancedStats) {
			InstallAdvancedStats(context, g_advStatsReport, sizeof(g_advStatsReport));
		} else {
			std::snprintf(g_advStatsReport, sizeof(g_advStatsReport), "off: advanced_stats = false");
		}
		Log(g_advStatsReport);
		g_statsOk = InitStatReader(context);
		g_blockOk = std::memcmp(reinterpret_cast<const void*>(g_base + block_rate::GetBlockRateRva), block_rate::GetBlockRateEntry,
		                        sizeof(block_rate::GetBlockRateEntry)) == 0;
		std::snprintf(g_blockReport, sizeof(g_blockReport), "block %s", g_blockOk ? "on: D2R's GetBlockRate 0x347da0" : "off: GetBlockRate bytes differ");
		Log(g_blockReport);
		InstallPad();
		Log(g_padReport);
		if (g_config.book && g_statsOk) {
			SheetHostServices services;
			services.player = &HostPlayer;
			services.value = &HostValue;
			services.padTriggers = &HostPadTriggers;
			services.tabsChanged = &TabsChanged;
			SheetHostSetSide(g_config.sideTabs);
			if (InstallSheetHost(context, &g_book, g_selfPath, g_padChoice == statbook::PadButtons::Triggers, services, g_hostReport, sizeof(g_hostReport)) &&
			    SheetHostSideReady()) {
				RegisterTabsAction(context);  // only with a side panel (the mod's or plain D2R's compiled-in one)
			}
			std::snprintf(line, sizeof(line), "statbook: tabs = \"%s\" (side panel %s), Controls action %s", g_config.sideTabs ? "side" : "top",
			              SheetHostSideReady() ? "ready" : "none: top tabs only", g_tabsActionReport);
			Log(line);
		} else {
			std::snprintf(g_hostReport, sizeof(g_hostReport), "host off: %s", g_config.book ? "no stat reader" : "book = false");
		}
		Log(g_hostReport);
	}
	if (!context->RegisterConsoleCommand("statbook", &StatusCommand, "Stat Book status; `statbook page <n>` prints a page; `statbook host`, `tab <n>`, `find <text>`, `vis <widget> 0|1|-1`, `tabs [top|side|toggle]`.")) {
		context->LogWarn("statbook: console command not registered");
	}
	return true;
}

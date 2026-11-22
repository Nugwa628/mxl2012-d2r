// The health bar and damage number keys (owner, 2026-11-22; off word overlaykeys; docs/bundled-plugins.md "Keys for the
// health bars and damage numbers").
//
// Two actions in Options > Controls, category "D2R-XL 2012", rebindable and with no default key (D2RLoader InputService):
// - "Enemy Health Bars Mode" (`mxl_health_bars_mode`): each press moves the bundled Enemy Health Bars to its next mode,
//   Off -> Always, all monsters -> Always, uniques/bosses -> When damaged, all monsters -> When damaged, uniques/bosses -> Off
//   (overlay_keys_logic.h). "Uniques/bosses" is the plugin's own unique rarity (orange outline): unique, super unique and
//   boss monsters; champions do not count.
// - "Floating Damage Numbers" (`mxl_damage_numbers`): each press turns the bundled Floating Damage's numbers (and its DPS
//   counter) on or off.
// The plugins own their settings: each press calls the plugin's export (Enemy Health Bars patch 0005
// Mxl2012EnemyBarsModeV1 / Mxl2012EnemyBarsSetModeV1, Floating Damage patch 0006 Mxl2012FloatingDamageShownV1 /
// Mxl2012FloatingDamageSetShownV1), found by GetProcAddress on the loaded DLL at the press, so the load order does not matter
// and a player who deleted a plugin gets a line that says so. The plugin applies the setting at once and saves it in its own
// TOML (a `preserve` file of the package, so Update and Repair keep it).
//
// The answer is a yellow line in the message log, sent straight to the client's chat packet handler 0x12c190 (packet 0x26
// type 4, map_reveal_logic.h BuildChatPacket), so it fades like D2R's own notices and works in a joined game. A chat line
// during an NPC's speech freezes the speech (docs/d2r-addresses.md 13): while the client talks to an NPC (0x2a48760 non-zero)
// or the NPC menu state 0x2a486a4 is set, the setting is changed and the line is skipped. No hook, nothing sent to the server.
#include "overlay_keys.h"

#include "d2r.h"
#include "map_reveal_logic.h"
#include "overlay_keys_logic.h"

#include <D2RLPlugin/input.h>
#include <D2RLPlugin/threads.h>

#include <windows.h>

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

using namespace overlay_keys;

constexpr uint64_t RvaLocalContext = 0x8b2d0;     // () -> local data context (0-7)
constexpr uint64_t RvaLocalPlayer = 0x9a480;      // (context) -> the client's own player unit
constexpr uint64_t RvaClientChat = 0x12c190;      // client handler of packet 0x26 (packet bytes)
constexpr uint64_t RvaMenuNpcValid = 0x2a48760;   // u32, non-zero while the client talks to an NPC
constexpr uint64_t RvaNpcMenuState = 0x2a486a4;   // u32, the client's NPC menu state (npc_greet_logic.h)

constexpr uint8_t LocalPlayerEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x08, 0x57, 0x48, 0x83, 0xec, 0x20, 0x83, 0xf9, 0x08};
constexpr uint8_t ChatEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x10, 0x48, 0x89, 0x74, 0x24, 0x18, 0x57, 0x48, 0x81, 0xec, 0x90};

constexpr wchar_t EhbDll[] = L"d2rl-enemy-health-bars.dll";
constexpr wchar_t FdDll[] = L"d2rl-ruffneckk-floating-damage.dll";

using LocalContextFn = int32_t (*)();
using LocalPlayerFn = uint8_t* (*)(int32_t);
using ChatFn = void (*)(const uint8_t*);
using BarsModeFn = uint32_t(__cdecl*)();
using BarsSetFn = int(__cdecl*)(uint32_t);
using ShownFn = int(__cdecl*)();
using SetShownFn = int(__cdecl*)(int);

const D2RL::PluginContext* g_context = nullptr;
const D2RL::ThreadService* g_threads = nullptr;
const D2RL::InputService* g_input = nullptr;
D2RL::Input::ActionHandle g_barsAction = D2RL::Input::InvalidHandle;
D2RL::Input::ActionHandle g_damageAction = D2RL::Input::InvalidHandle;
uint64_t g_base = 0;
bool g_on = false;

std::atomic<bool> g_uiQueued{false};
std::atomic<int> g_barsPresses{0}, g_damagePresses{0};  // presses waiting for the UI thread

// UI thread only
char g_lastLine[160] = "";
int g_lastResult = 9;

std::atomic<long> g_presses{0}, g_lines{0}, g_skipped{0}, g_noPlayer{0}, g_notSaved{0}, g_missing{0}, g_faults{0};

template <typename F>
auto Fn(uint64_t rva) noexcept -> F {
	return reinterpret_cast<F>(g_base + rva);
}

auto EntryMatches(uint64_t rva, const uint8_t* bytes, size_t n) noexcept -> bool {
	return std::memcmp(reinterpret_cast<const void*>(g_base + rva), bytes, n) == 0;
}

template <typename F>
auto Export(const wchar_t* dll, const char* name) noexcept -> F {
	HMODULE m = GetModuleHandleW(dll);
	return m != nullptr ? reinterpret_cast<F>(GetProcAddress(m, name)) : nullptr;
}

auto InGame() noexcept -> bool {
	const int32_t ctx = Fn<LocalContextFn>(RvaLocalContext)();
	if (ctx < 0 || ctx >= 8) {
		return false;
	}
	const uint8_t* player = Fn<LocalPlayerFn>(RvaLocalPlayer)(ctx);
	return player != nullptr && d2r::At<int32_t>(player, d2r::UnitType) == 0;
}

auto Global(uint64_t rva) noexcept -> uint32_t {
	return *reinterpret_cast<const uint32_t*>(g_base + rva);
}

void Say(const char* text) noexcept {
	std::snprintf(g_lastLine, sizeof(g_lastLine), "%s", text);
	if (!LineAllowed(Global(RvaMenuNpcValid), Global(RvaNpcMenuState))) {
		g_skipped.fetch_add(1);  // an NPC talks: the setting is changed, the line would freeze the speech
		return;
	}
	if (!InGame()) {
		g_noPlayer.fetch_add(1);
		return;
	}
	uint8_t packet[map_reveal::ChatPacketMax];
	if (map_reveal::BuildChatPacket(packet, sizeof(packet), map_reveal::ColourYellow, text) == 0) {
		return;
	}
	Fn<ChatFn>(RvaClientChat)(packet);
	g_lines.fetch_add(1);
}

void Count(int result) noexcept {
	g_lastResult = result;
	if (result == ApplyNotSaved) {
		g_notSaved.fetch_add(1);
	} else if (result == ApplyMissing) {
		g_missing.fetch_add(1);
	}
}

void BarsPress() noexcept {
	g_presses.fetch_add(1);
	char line[160];
	const auto get = Export<BarsModeFn>(EhbDll, "Mxl2012EnemyBarsModeV1");
	const auto set = Export<BarsSetFn>(EhbDll, "Mxl2012EnemyBarsSetModeV1");
	const uint32_t old = get != nullptr && set != nullptr ? get() : 0;
	if ((old & BarsValid) == 0) {
		Count(ApplyMissing);
		BarsLine(line, sizeof(line), BarsMode::Off, ApplyMissing);
		Say(line);
		return;
	}
	const BarsMode next = NextMode(ModeOf(old));
	const int r = set(BitsOf(next, old));
	Count(r);
	const uint32_t now = get();
	BarsLine(line, sizeof(line), (now & BarsValid) != 0 ? ModeOf(now) : next, r);
	Say(line);
}

void DamagePress() noexcept {
	g_presses.fetch_add(1);
	char line[160];
	const auto get = Export<ShownFn>(FdDll, "Mxl2012FloatingDamageShownV1");
	const auto set = Export<SetShownFn>(FdDll, "Mxl2012FloatingDamageSetShownV1");
	if (get == nullptr || set == nullptr) {
		Count(ApplyMissing);
		DamageLine(line, sizeof(line), false, ApplyMissing);
		Say(line);
		return;
	}
	const int shown = get();
	if (shown < 0) {
		Count(ApplyRefused);
		DamageLine(line, sizeof(line), false, ApplyRefused);
		Say(line);
		return;
	}
	const int r = set(shown == 0 ? 1 : 0);
	Count(r);
	const int now = get();
	DamageLine(line, sizeof(line), now >= 0 ? now == 1 : shown == 0, r);
	Say(line);
}

void Guarded(void (*body)()) noexcept {
	__try {
		body();
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		g_faults.fetch_add(1);
	}
}

void __cdecl RunOnUi(const D2RL::PluginContext*, void*) noexcept {
	g_uiQueued.store(false);
	for (int n = g_barsPresses.exchange(0); n > 0; --n) {
		Guarded(&BarsPress);
	}
	for (int n = g_damagePresses.exchange(0); n > 0; --n) {
		Guarded(&DamagePress);
	}
}

void QueueUi() noexcept {
	if (!g_uiQueued.exchange(true) && g_threads->runOnUiThread(g_context, &RunOnUi, nullptr) != D2RL::Threads::Result::Success) {
		g_uiQueued.store(false);
	}
}

auto Pressed(const D2RL::Input::ActionEvent* event) noexcept -> bool {
	return D2RL::Input::HasActionEventField(event, D2RL::Input::ActionEventRequiredSize) && event->kind == D2RL::Input::ActionEventKind::Pressed;
}

auto __cdecl OnBars(const D2RL::PluginContext*, const D2RL::Input::ActionEvent* event, void*) noexcept -> D2RL::Input::ActionResult {
	if (!Pressed(event)) {
		return D2RL::Input::ActionResult::Ignored;
	}
	g_barsPresses.fetch_add(1);
	QueueUi();
	return D2RL::Input::ActionResult::Handled;
}

auto __cdecl OnDamage(const D2RL::PluginContext*, const D2RL::Input::ActionEvent* event, void*) noexcept -> D2RL::Input::ActionResult {
	if (!Pressed(event)) {
		return D2RL::Input::ActionResult::Ignored;
	}
	g_damagePresses.fetch_add(1);
	QueueUi();
	return D2RL::Input::ActionResult::Handled;
}

auto Register(const char* id, const char* name, D2RL::Input::ActionCallback cb, D2RL::Input::ActionHandle* handle) noexcept -> D2RL::Input::Result {
	D2RL::Input::Binding none{};
	none.key = D2RL::Input::Key::None;  // no default key (owner): the player binds it in Options > Controls
	none.modifier = D2RL::Input::Modifier::None;
	D2RL::Input::ActionRegistration reg{};
	reg.structSize = D2RL::Input::ActionRegistrationSize;
	reg.flags = 0;
	reg.logicalId = id;
	reg.displayName = name;
	reg.category = "D2R-XL 2012";
	reg.defaultPrimary = none;
	reg.defaultSecondary = none;
	reg.callback = cb;
	reg.userData = nullptr;
	return g_input->registerAction(g_context, &reg, handle);
}

void BoundKey(D2RL::Input::ActionHandle action, char* out, size_t n) noexcept {
	std::snprintf(out, n, "-");
	D2RL::Input::Binding b{};
	if (g_input != nullptr && action != D2RL::Input::InvalidHandle &&
	    g_input->getBinding(g_context, action, D2RL::Input::BindingSlot::Primary, &b) == D2RL::Input::Result::Success &&
	    b.key != D2RL::Input::Key::None) {
		map_reveal::KeyName(static_cast<uint32_t>(b.key), static_cast<uint32_t>(b.modifier), out, n);
	}
}

}  // namespace

auto InstallOverlayKeys(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	g_context = context;
	g_base = context->exeBase;
	if (!EntryMatches(RvaLocalPlayer, LocalPlayerEntry, sizeof(LocalPlayerEntry)) || !EntryMatches(RvaClientChat, ChatEntry, sizeof(ChatEntry))) {
		std::snprintf(report, reportSize, "overlaykeys off: entry bytes differ (0x9a480 / 0x12c190)");
		return false;
	}
	if (context->QueryService(&g_threads) != D2RL::ServiceQueryResult::Success || !D2RL::HasThreadServiceField(g_threads, D2RL::ThreadServiceRequiredSize) ||
	    context->QueryService(&g_input) != D2RL::ServiceQueryResult::Success || !D2RL::HasInputServiceField(g_input, D2RL::InputServiceRequiredSize)) {
		std::snprintf(report, reportSize, "overlaykeys off: ThreadService / InputService unavailable");
		return false;
	}
	const auto a = Register("mxl_health_bars_mode", "Enemy Health Bars Mode", &OnBars, &g_barsAction);
	const auto b = Register("mxl_damage_numbers", "Floating Damage Numbers", &OnDamage, &g_damageAction);
	g_on = a == D2RL::Input::Result::Success || b == D2RL::Input::Result::Success;
	if (a != D2RL::Input::Result::Success || b != D2RL::Input::Result::Success) {
		std::snprintf(report, reportSize, "overlaykeys %s: a Controls action could not be registered (InputService results %u, %u)",
		              g_on ? "in part" : "off", static_cast<unsigned>(a), static_cast<unsigned>(b));
		return g_on;
	}
	std::snprintf(report, reportSize, "overlaykeys on: Controls actions mxl_health_bars_mode and mxl_damage_numbers (no default keys) "
	              "drive Enemy Health Bars and Floating Damage through their exports; no hook");
	return true;
}

void OverlayKeysStatus(char* out, size_t size) noexcept {
	char bars[24], damage[24];
	BoundKey(g_barsAction, bars, sizeof(bars));
	BoundKey(g_damageAction, damage, sizeof(damage));
	const auto get = Export<BarsModeFn>(EhbDll, "Mxl2012EnemyBarsModeV1");
	const auto shown = Export<ShownFn>(FdDll, "Mxl2012FloatingDamageShownV1");
	const uint32_t mode = get != nullptr ? get() : 0;
	std::snprintf(out, size,
	              "on=%d barskey=%s damagekey=%s barsmode=\"%s\" damage=%d npc=%u npcstate=%u presses=%ld lines=%ld skipped=%ld noplayer=%ld "
	              "notsaved=%ld missing=%ld faults=%ld lastresult=%d last=\"%s\"",
	              g_on ? 1 : 0, bars, damage, (mode & BarsValid) != 0 ? ModeText(ModeOf(mode)) : "not loaded", shown != nullptr ? shown() : -2,
	              g_base ? Global(RvaMenuNpcValid) : 0u, g_base ? Global(RvaNpcMenuState) : 0u, g_presses.load(), g_lines.load(), g_skipped.load(),
	              g_noPlayer.load(), g_notSaved.load(), g_missing.load(), g_faults.load(), g_lastResult, g_lastLine);
}

auto OverlayKeysPress(int which) noexcept -> bool {
	if (!g_on) {
		return false;
	}
	Guarded(which == 0 ? &BarsPress : &DamagePress);
	return true;
}

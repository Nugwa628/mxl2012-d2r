// The stash's MEDIAN and ORBS tabs and the Materials tab's Vanilla / Median selector (tools/median_tabs.py; off word medtab).
//
// tools/median_tabs.py puts 7 tabs in BankTabs and the new slots as direct children of advancedstash_runes (MEDIAN, ORBS) and
// advancedstash_materials (the Median page): D2R's stash init takes a tab's accepted codes from those direct children only.
// D2R's panel knows 5 pages (the table +0x278, bounds-checked against 5), so:
//   - the tab getter 0x23af50 maps tabs 5 and 6 to 4 (Runes): its read of the tab bar (0x23af9f, mov ebx,[rdi+0x16c4]) calls a
//     stub in the int3 pad 0x23afd2 that reads it and caps it at 4. Every user of the tab (22 callers) sees Runes;
//   - the tab update 0x23e630(panel, ...) runs as D2R, then the real tab (the tab bar's +0x16c4) decides which slot groups of
//     the Runes page are shown (Runes, MEDIAN, ORBS; medtab_names.h; their pictures and the selectors are panel children shown here by tab), and the cube is hidden on tabs 5 and 6. Outside a RotW
//     game tabs 5 and 6 are hidden as D2R hides 2-4 (0x879260) and go back to Personal;
//   - the selector's arrows send PanelManager:OpenPanel:<Toggle>; the UI listener consumes it and flips the Materials page;
//   - the 9 codes with "@" are written with "_" in the layouts (D2R's loader reads "@key" as a string key, "b@b" grew past 4
//     characters and asserted): the slot's code read 0x2ce910 is hooked and puts the "@" back into the widget's own string
//     (+0x5d8 data, +0x5e0 size; 3 characters live in the widget's inline buffer +0x5f0) before D2R reads it.
// Plugin and layout ship together (the 7-tab layout without this part asserts on tab 5). A panel without the layout's mark
// widget (LayoutMark: an older or D2R layout) is left as D2R: 5 tabs, nothing shown or hidden. With the off word medtab the
// hooks stay (the layout needs them) and tabs 5 and 6 are hidden in every game, the Materials page is D2R's.
#include "median_tabs.h"

#include "median_tabs_logic.h"
#include "medtab_names.h"

#include <D2RLPlugin/shared_events.h>
#include <D2RLPlugin/threads.h>
#include <D2RLPlugin/widgets.h>

#include <windows.h>

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

constexpr uint64_t TabReadRva = 0x23af9f;
constexpr uint8_t TabRead[] = {0x8b, 0x9f, 0xc4, 0x16, 0x00, 0x00};  // mov ebx, [rdi+0x16c4]
constexpr uint64_t StubRva = 0x23afd2;
constexpr uint8_t StubPad[14] = {0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc};
// mov ebx, [rdi+0x16c4] / cmp ebx, 4 / jbe +2 / mov bl, 4 / ret (an index above 255 stays for D2R's own check)
constexpr uint8_t Stub[14] = {0x8b, 0x9f, 0xc4, 0x16, 0x00, 0x00, 0x83, 0xfb, 0x04, 0x76, 0x02, 0xb3, 0x04, 0xc3};
constexpr uint8_t TabCall[6] = {0xe8, 0x2e, 0x00, 0x00, 0x00, 0x90};  // call 0x23afd2 / nop
constexpr uint64_t UpdateRva = 0x23e630;
constexpr uint8_t UpdateEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x10, 0x55, 0x56, 0x57, 0x41, 0x54, 0x41, 0x55, 0x41, 0x56, 0x41, 0x57};
constexpr uint64_t ChildByNameRva = 0x855c90;    // (widget, const char* name) -> descendant widget or null
constexpr uint64_t BankTabsNameRva = 0x1ce4ba0;  // "BankTabs"
constexpr size_t TabBarTabOffset = 0x16c4;
constexpr uint64_t HideTabRva = 0x879260;        // (tab bar, index): D2R's own hide of Gems / Materials / Runes outside RotW (0x23dde5)
constexpr uint8_t HideTabEntry[] = {0x89, 0x54, 0x24, 0x10, 0x53, 0x48, 0x83, 0xec, 0x20, 0x48, 0x8b, 0xd9, 0x85, 0xd2};
constexpr size_t CubeOffset = 0x2a0;
constexpr size_t PanelWiredFlag = 0x2a8;         // 1 once the init wired the five pages
constexpr uint64_t RotwGameRva = 0x8d3e0;
constexpr uint8_t RotwGameCode[] = {0x48, 0x8b, 0x05, 0xf9, 0x62, 0x99, 0x02, 0x48, 0x85, 0xc0, 0x74, 0x09};
constexpr char StockPanel[] = "BankExpansionLayout";
constexpr uint64_t CodeReadRva = 0x2ce910;       // AdvancedStashSlotWidget: m_itemCode -> item record (asserts on > 4 characters)
constexpr uint8_t CodeReadEntry[] = {0x40, 0x53, 0x48, 0x83, 0xec, 0x20, 0x48, 0x83, 0xb9, 0xe0, 0x05, 0x00, 0x00, 0x04};
constexpr size_t CodeDataOffset = 0x5d8;
constexpr size_t CodeSizeOffset = 0x5e0;

using UpdateFn = uint64_t (*)(void* panel, uint64_t arg) noexcept;
using CodeReadFn = uint64_t (*)(void* slot) noexcept;
using ChildFn = void* (*)(void* widget, const char* name) noexcept;
using BoolFn = bool (*)() noexcept;
using VisFn = void (*)(void* widget, uint64_t on) noexcept;
using HideTabFn = void (*)(void* tabBar, int index) noexcept;

const D2RL::PluginContext* g_context = nullptr;
const D2RL::ThreadService* g_threads = nullptr;
const D2RL::WidgetService* g_widgets = nullptr;
UpdateFn g_update = nullptr;
CodeReadFn g_codeRead = nullptr;
bool g_tabsOn = true;               // false with the off word: tabs 5 and 6 hidden everywhere
ChildFn g_child = nullptr;
BoolFn g_rotwGame = nullptr;
HideTabFn g_hideTab = nullptr;
uint64_t g_base = 0;
std::atomic<int> g_tab{-1};         // the real tab of the last update
std::atomic<bool> g_median{false};  // the Materials page shows the Median group
std::atomic<void*> g_panel{nullptr};  // the stash panel of the last tab update
std::atomic<uint64_t> g_handle{0};    // WidgetService's handle of the stock stash at the last toggle
std::atomic<uint32_t> g_updates{0}, g_bounces{0}, g_cubeHidden{0}, g_toggles{0}, g_applies{0}, g_missing{0}, g_noPanel{0};
std::atomic<uint32_t> g_codesRestored{0}, g_noMark{0};
std::atomic<bool> g_live{false};    // the last update's panel had the 7-tab layout in a game that shows tabs 5 and 6

// D2R's own show / hide of a page widget (0x23e630: vfuncs +0x50 then +0x48)
void SetVisible(void* w, bool on) noexcept {
	auto* vt = *reinterpret_cast<void***>(w);
	reinterpret_cast<VisFn>(vt[0x50 / 8])(w, on ? 1 : 0);
	reinterpret_cast<VisFn>(vt[0x48 / 8])(w, on ? 1 : 0);
}

template <size_t N>
void Show(void* panel, const char* const (&names)[N], bool on) noexcept {
	for (const char* n : names) {
		if (void* w = g_child(panel, n)) {
			SetVisible(w, on);
		} else {
			g_missing.fetch_add(1);  // the other graphics' names (classic tiles in HD and the reverse)
		}
	}
}

// On the UI thread, `panel` the stash panel of the running tab update (or the last one, for the selector)
void Apply(void* panel) noexcept {
	const median_tabs::Groups v = median_tabs::Visible(g_tab.load(), g_median.load(), g_live.load());
	Show(panel, medtab_names::RunesOwn, v.runesOwn);
	Show(panel, medtab_names::Median, v.median);
	Show(panel, medtab_names::Orbs, v.orbs);
	Show(panel, medtab_names::MatVanilla, v.matVanilla);
	Show(panel, medtab_names::MatMedian, v.matMedian);
	Show(panel, medtab_names::MatPicture, v.matPicture);
	for (const char* n : medtab_names::Selector) {
		if (void* w = g_child(panel, n)) {
			SetVisible(w, std::strcmp(n, "medtab_sel_median") == 0 ? v.selMedian : v.selVanilla);
		} else {
			g_missing.fetch_add(1);
		}
	}
	g_applies.fetch_add(1);
}

uint64_t CodeReadHook(void* slot) noexcept {
	auto* w = static_cast<uint8_t*>(slot);
	char* code = *reinterpret_cast<char**>(w + CodeDataOffset);
	const size_t size = *reinterpret_cast<size_t*>(w + CodeSizeOffset);
	if (code != nullptr && median_tabs::RestoreAtCode(code, size)) {
		g_codesRestored.fetch_add(1);
	}
	return g_codeRead(slot);
}

// The selector: the stash panel of the last tab update when WidgetService still finds the stock stash there
void __cdecl ToggleOnUiThread(const D2RL::PluginContext*, void*) noexcept {
	D2RL::Widgets::WidgetHandle found = 0;
	void* panel = g_panel.load();
	if (panel == nullptr || g_widgets->findPanel(g_context, StockPanel, &found) != D2RL::Widgets::Result::Success) {
		g_noPanel.fetch_add(1);
		return;
	}
	g_handle.store(static_cast<uint64_t>(found));
	Apply(panel);
}

auto RealTab(void* panel) noexcept -> int* {
	auto* tabs = static_cast<uint8_t*>(g_child(panel, reinterpret_cast<const char*>(g_base + BankTabsNameRva)));
	return tabs != nullptr ? reinterpret_cast<int*>(tabs + TabBarTabOffset) : nullptr;
}

uint64_t UpdateHook(void* panel, uint64_t arg) noexcept {
	g_updates.fetch_add(1);
	auto* p = static_cast<uint8_t*>(panel);
	int* tab = panel != nullptr ? RealTab(panel) : nullptr;
	if (tab == nullptr || g_child(panel, medtab_names::LayoutMark) == nullptr) {
		g_noMark.fetch_add(1);  // D2R's or an older layout: 5 tabs, left as D2R
		return g_update(panel, arg);
	}
	const bool live = g_tabsOn && g_rotwGame();
	if (median_tabs::Bounce(*tab, live)) {  // before D2R's update: it must never see 5 or 6 here
		*tab = 0;
		g_bounces.fetch_add(1);
	}
	uint64_t r = g_update(panel, arg);
	if (p[PanelWiredFlag] == 0) {
		return r;
	}
	if (!live) {
		auto* bar = reinterpret_cast<uint8_t*>(tab) - TabBarTabOffset;
		g_hideTab(bar, median_tabs::MedianTab);
		g_hideTab(bar, median_tabs::OrbsTab);
	}
	g_live.store(live);
	g_tab.store(*tab);
	g_panel.store(panel);
	if (*tab > median_tabs::LastD2RTab) {
		if (void* cube = *reinterpret_cast<void**>(p + CubeOffset)) {
			SetVisible(cube, false);
			g_cubeHidden.fetch_add(1);
		}
	}
	Apply(panel);
	return r;
}

auto EqualsNoCase(const char* a, const char* b) noexcept -> bool {
	for (; *a != '\0' && *b != '\0'; ++a, ++b) {
		if ((*a | 0x20) != (*b | 0x20)) {
			return false;
		}
	}
	return *a == *b;
}

auto __cdecl OnUiMessage(const D2RL::PluginContext*, const D2RL::SharedEvents::UiMessageEvent* event, void*) noexcept -> D2RL::SharedEvents::UiMessageAction {
	if (event == nullptr || event->target == nullptr || event->command == nullptr || event->text == nullptr) {
		return D2RL::SharedEvents::UiMessageAction::Continue;
	}
	if (EqualsNoCase(event->target, "PanelManager") && EqualsNoCase(event->command, "OpenPanel") && EqualsNoCase(event->text, medtab_names::Toggle)) {
		if (!g_live.load()) {
			return D2RL::SharedEvents::UiMessageAction::Consume;  // the selector is hidden then; a stray message changes nothing
		}
		g_median.store(!g_median.load());
		g_toggles.fetch_add(1);
		(void)g_threads->runOnUiThread(g_context, &ToggleOnUiThread, nullptr);
		return D2RL::SharedEvents::UiMessageAction::Consume;
	}
	return D2RL::SharedEvents::UiMessageAction::Continue;
}

}  // namespace

auto InstallMedianTabs(const D2RL::PluginContext* context, bool tabsOn, char* report, size_t reportSize) noexcept -> bool {
	g_context = context;
	g_tabsOn = tabsOn;
	g_base = context->exeBase;
	const auto* image = reinterpret_cast<const uint8_t*>(g_base);
	const D2RL::SharedEventService* events = nullptr;
	if (context->QueryService(&g_threads) != D2RL::ServiceQueryResult::Success ||
	    context->QueryService(&g_widgets) != D2RL::ServiceQueryResult::Success || !D2RL::HasWidgetServiceField(g_widgets, D2RL::WidgetServiceRequiredSize) ||
	    context->QueryService(&events) != D2RL::ServiceQueryResult::Success || !D2RL::HasSharedEventServiceField(events, D2RL::SharedEventServiceRequiredSize)) {
		std::snprintf(report, reportSize, "medtab off: ThreadService / WidgetService / SharedEventService unavailable");
		return false;
	}
	if (std::memcmp(image + TabReadRva, TabRead, sizeof(TabRead)) != 0 || std::memcmp(image + StubRva, StubPad, sizeof(StubPad)) != 0 ||
	    std::memcmp(image + RotwGameRva, RotwGameCode, sizeof(RotwGameCode)) != 0 ||
	    std::memcmp(image + HideTabRva, HideTabEntry, sizeof(HideTabEntry)) != 0 ||
	    std::memcmp(image + CodeReadRva, CodeReadEntry, sizeof(CodeReadEntry)) != 0 ||
	    std::strcmp(reinterpret_cast<const char*>(image + BankTabsNameRva), "BankTabs") != 0) {
		std::snprintf(report, reportSize, "medtab off: bytes differ at 0x23af9f / 0x23afd2 / 0x8d3e0 / 0x879260 / 0x2ce910 / 0x1ce4ba0, left as D2R");
		return false;
	}
	g_child = reinterpret_cast<ChildFn>(g_base + ChildByNameRva);
	g_rotwGame = reinterpret_cast<BoolFn>(g_base + RotwGameRva);
	g_hideTab = reinterpret_cast<HideTabFn>(g_base + HideTabRva);
	// the code read and the update hook first (inert while the getter still answers 0-4), then the stub, then the call that
	// makes it live
	const bool ok = context->InstallInlineHook(CodeReadRva, CodeReadEntry, sizeof(CodeReadEntry), reinterpret_cast<void*>(&CodeReadHook),
	                                           reinterpret_cast<void**>(&g_codeRead)) &&
	                context->InstallInlineHook(UpdateRva, UpdateEntry, sizeof(UpdateEntry), reinterpret_cast<void*>(&UpdateHook),
	                                           reinterpret_cast<void**>(&g_update)) &&
	                context->PatchBytes(StubRva, StubPad, sizeof(StubPad), Stub, sizeof(Stub)) &&
	                context->PatchBytes(TabReadRva, TabRead, sizeof(TabRead), TabCall, sizeof(TabCall));
	D2RL::SharedEvents::UiMessageListener listener{};
	listener.structSize = D2RL::SharedEvents::UiMessageListenerSize;
	listener.callback = &OnUiMessage;
	D2RL::SharedEvents::ListenerHandle handle = 0;
	const bool listening = ok && events->registerUiMessageListener(context, &listener, &handle) == D2RL::SharedEvents::Result::Success;
	std::snprintf(report, reportSize, "medtab %s (layout mark %s): tabs 5 / 6 run as Runes (getter 0x23af50 capped through 0x23afd2), groups "
	              "shown after 0x23e630, '@' codes restored at 0x2ce910, selector %s", !ok ? "FAILED" : tabsOn ? "on" : "guard only, Median tabs hidden (off word)",
	              medtab_names::LayoutMark, listening ? "listening" : "not listening");
	return ok;
}

void MedianTabsStatus(char* out, size_t outSize) noexcept {
	std::snprintf(out, outSize, "tab %d (%s), materials %s; updates %u (no layout mark %u), bounces %u, cube hidden %u, toggles %u, applies %u "
	              "(names missing %u, no panel %u), '@' codes restored %u; panel %p, WidgetService handle %llx", g_tab.load(),
	              g_live.load() ? "live" : "tabs 5 / 6 hidden", g_median.load() ? "Median" : "Vanilla", g_updates.load(), g_noMark.load(),
	              g_bounces.load(), g_cubeHidden.load(), g_toggles.load(), g_applies.load(), g_missing.load(), g_noPanel.load(),
	              g_codesRestored.load(), g_panel.load(), static_cast<unsigned long long>(g_handle.load()));
}

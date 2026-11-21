// The Stat Book on D2R's character sheet: folder tabs, the themed pages and All Stats in the widgets of the sheet layouts that
// tools/statbook_layout.py builds (docs/statbook-layout.md is the contract, docs/statbook.md "Sheet host").
//
// A timer thread queues a UI-thread tick every 50 ms. The tick finds the sheet (CharacterStatsPanel) and its StatBookMarker; a
// sheet without the marker (legacy graphics, D2R's own layout) is left alone. For a new sheet widget it
//  - looks the contract names up (0x855c90) for the native pointers (texts are set through D2R's own setter);
//  - finds the byte of a widget's "visible" flag by hiding SbPageBody and StatBookAll (hidden on the Character tab anyway) and
//    comparing their bytes; with it the host sees the sheet open and close. Nothing is shown while the sheet is closed: showing
//    widgets of the closed sheet through their own vfuncs kept the sheet from opening at all (first game run, 2026-11-15);
//  - looks for the sheet's child list (begin / end pointers holding known children) to hide every D2R page-1 widget, the three
//    same-named `separator`s included; without it (so far in game) D2R's widgets are hidden by name.
// D2R shows every widget of the sheet when it opens, whatever the layout's `visible` says, so on each opening (and on every tab
// change) the host sets the visibility of every Stat Book group. Groups are shown and hidden through WidgetService, whose handles
// are limited (about 256 per plugin; ~165 groups): hiding a group hides its children (shot statbook_vis_group_hidden), so leaves
// get no handle, and the value boxes of the other tones hold "". D2R's own widgets are hidden with their vfuncs (+0x50, +0x48,
// as D2R's stash does for its pages; median_tabs.cpp), only while the sheet is open, and shown again on the Character tab.
//
// Clicks: every Stat Book button sends PanelManager:OpenPanel:statbook/StatBook; the click position (panel_shared::LastClick)
// in the sheet's layout units picks the tab or the All Stats row (statbook-layout.json's rectangles). The Advanced Stats arrow
// (CharacterStatsPanelMessage:ToggleAdvancedStats) opens All Stats. The search box types through panel_shared's typing fix (the
// same as the developer menu); the text is read with WidgetService's getInputText each tick. The mouse wheel over the list scrolls it.
//
// Plain D2R (no mod, so no statbook-layout.json and no Stat Book widgets in D2R's sheet): the plugin registers its own panels
// from statbook_plain_layout.h (tools/statbook_layout.py `plain`, written from the mod's layouts): statbook/SbPlainPanel (the
// same widget names at the sheet's rect) and the side panel statbook/SbSidePanel. The Stat Book's own sprites are used when the
// install has them, else D2R's stock ones (the header's Fallback rows); D2R's stock sprites for the rest. The host opens the
// sheet's panel while the sheet is open, closes it with the sheet; D2R's title text under the tab strip is hidden (shown in
// side mode). Legacy graphics: classic layouts of both panels from statbook_plain_legacy.h (tools/statbook_legacy.py
// `plain`, the mod's classic book over D2R's classic sheet), registered when the install has their DC6 art; the panel's
// head covers D2R's name and class, so the host fills its own name and class texts (SbPlainName / SbPlainClass). The Stat Book widgets are that panel's; D2R's widgets hidden on the pages are the sheet's (by name);
// the sheet's visible flag (+0x51 bit 0x01, as calibrated on the mod's sheet) says when it is open. D2R's Advanced Stats arrow
// keeps opening D2R's own panel there with top tabs; in side mode (D2R's panel would sit under the side panel) it opens All Stats.
#include "sheet_host.h"

#include "../../plugin/src/panel_logic.h"
#include "../../plugin/src/panel_shared.h"
#include "advstats.h"
#include "sheet_host_logic.h"
#include "statbook_plain_layout.h"
#include "statbook_plain_legacy.h"

#include <D2RLPlugin/panels.h>
#include <D2RLPlugin/shared_events.h>
#include <D2RLPlugin/threads.h>
#include <D2RLPlugin/widgets.h>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <atomic>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace {

using namespace sheet_host;

constexpr const char* PanelName = "CharacterStatsPanel";
constexpr const char* Marker = "StatBookMarker";
constexpr DWORD TickMs = 50;
// The HD left panel ($LeftPanelRect from $LeftPanelAnchor) at 16:9: its top left in layout units of a 2160-unit-high screen (the
// stash's measured place, tools/game_checks.py SP2_HD / INVTABS_HD_PANEL; the sheet uses the same rect and anchor).
constexpr double PanelLeftUnits = 236.0;
constexpr double PanelTopUnits = 208.4;
// D2R's widgets that stay on every tab (docs/statbook-layout.md "D2R's widgets the plugin hides").
constexpr const char* Keep[] = {"Background", "ClickCatcher", "click_catcher", "LeftHinge", "StatsPanelTitle", "CharacterName", "FullClassInfo",
                                "XpProgress", "CombinedXP", "CloseButton", "LevelUpInfo", "CombinedPointsInfo"};
// Without the child list: D2R's top-level widgets of the PC and gamepad sheets by name (the first of each name only).
constexpr const char* HideByName[] = {
    "StrengthTitle", "StrengthStat", "DexTitle", "DexStat", "VitalityTitle", "VitalityStat", "EnergyTitle", "EnergyStat", "LeftSkillStats",
    "RightSkillStats", "ArmorClassTitle", "ArmorClass", "StaminaTitle", "MaxStamina", "separator", "CurrentStamina", "HPTitle", "MaxHP",
    "CurrentHP", "ManaTitle", "MaxMana", "CurrentMana", "FireResistanceTitle", "FireText", "ColdResistanceTitle", "ColdText",
    "LightningResistanceTitle", "LightningText", "PoisonResistanceTitle", "PoisonText", "MxlMagicResistanceTitle", "MxlMagicText",
    "MxlMagicTextCapped", "MxlMagicTextNegative", "MxlPhysicalResistanceTitle", "MxlPhysicalText", "MxlPhysicalTextCapped",
    "MxlPhysicalTextNegative", "AdvancedStats", "StrengthBG", "DexBG", "VitalityBG", "EnergyBG", "DamageBG_L", "Divider01", "RatingBG_L",
    "Divider02", "DamageBG_R", "Divider03", "RatingBG_R", "Divider04", "Row05", "Divider05", "Row06", "Divider06", "Divider07", "Row07",
    "Divider08", "Divider09", "Row08", "Divider10", "Divider11", "FireResistanceBG", "ColdResistanceBG", "LightningResistanceBG",
    "PoisonResistanceBG", "MxlMagicResistanceBG", "MxlPhysicalResistanceBG", "StrengthPointButton", "DexPointButton", "VitalityPointButton",
    "EnergyPointButton"};
// Legacy graphics (the mod's classic sheet, statbook_legacy.py): D2R's classic header texts and close stay on the pages (the page
// body draws the header boxes); the stat point buttons (LevelUpInfo) go with the rest. Without the child list: by name.
constexpr const char* KeepLegacy[] = {"ClickCatcher", "click_catcher", "background", "CharacterName", "ClassInfo", "LevelTitle", "Level", "CurrentXPTitle",
                                      "CurrentXP", "NextLevelXPText", "NextLevelXP", "CloseButton", "SbLegacyMarker"};
constexpr const char* HideByNameLegacy[] = {
    "StrengthTitle", "StrengthStat", "DexTitle", "DexStat", "VitalityTitle", "VitalityStat", "EnergyTitle", "EnergyStat",
    "LeftSkillStats", "RightSkillStats", "ArmorClassTitle", "ArmorClass", "StaminaTitle", "MaxStamina", "CurrentStamina", "HPTitle", "MaxHP",
    "CurrentHP", "ManaTitle", "MaxMana", "CurrentMana", "FireResistanceTitle", "FireText", "ColdResistanceTitle", "ColdText",
    "LightningResistanceTitle", "LightningText", "PoisonResistanceTitle", "PoisonText", "MxlMagicResistanceTitle", "MxlMagicText",
    "MxlMagicTextCapped", "MxlMagicTextNegative", "MxlPhysicalResistanceTitle", "MxlPhysicalText", "MxlPhysicalTextCapped",
    "MxlPhysicalTextNegative", "LevelUpInfo", "SbAdvanced"};
constexpr const char* LegacyMarker = "SbLegacyMarker";
// D2R's classic screen size (int, int): 800 x 600, 1066 x 600 with Legacy 16:9 (build 93847, as the Legacy 16:9 plugin's table)
constexpr uintptr_t RvaScreenSizeX = 0x22a0d68;
constexpr uintptr_t RvaScreenSizeY = 0x22a0d6c;
// a player unit's player data (its name, char[64], at +0; docs/d2r-addresses.md); a unit's class at +4 (0 Amazon .. 7 Warlock)
constexpr uintptr_t RvaPlayerData = 0x34b240;
constexpr long UnitClassOffset = 4;

using VisFn = void (*)(void* widget, uint64_t on) noexcept;

const D2RL::PluginContext* g_context = nullptr;
const D2RL::ThreadService* g_threads = nullptr;
const D2RL::WidgetService* g_widgets = nullptr;
const D2RL::PanelService* g_panels = nullptr;
// plain D2R: the plugin's own panel over the sheet
bool g_plain = false;
D2RL::Panels::RegistrationHandle g_plainPanel = D2RL::Panels::InvalidHandle;
bool g_plainOpen = false;
bool g_plainPadSheet = false;  // D2R's sheet is the gamepad one: the plain panel stays closed
std::atomic<long> g_plainOpens{0}, g_plainFails{0};
std::string g_plainHd, g_plainGeometry;
std::string g_plainLegacy, g_plainLegacyGeometry, g_sideLegacyJson;  // the classic layouts (statbook_plain_legacy.h)
bool g_plainLegacyReady = false;  // registered: the install has their art
panel_shared::Client g_sheet;  // only its panelName: D2R's sheet (the Stat Book's own panel is g_client)
void* g_sheetPanel = nullptr;
void* g_sheetTitle = nullptr;  // plain D2R: the sheet's title text ("Character"), under the tab strip; hidden while bound
constexpr long SheetVisibleOffset = 0x51;  // the visible flag as calibrated on the mod's sheet (2026-11-15)
constexpr uint8_t SheetVisibleMask = 0x01;
const statbook::Book* g_book = nullptr;
SheetHostServices g_sv;
bool g_padTriggers = false;
Geometry g_pc, g_pad;
Geometry g_legacy, g_legacySide;       // statbook-layout.json "legacy" / "legacyside" (the mod's classic layouts)
std::atomic<bool> g_legacyNow{false};  // the bound sheet is the classic one (SbLegacyMarker)
bool g_sideLegacyReady = false;        // the side panel's classic layout is registered too
char g_geometryFrom[420] = "not read";
panel_shared::Client g_client;
std::atomic<bool> g_tickQueued{false};

// The side host (option B, tabs = "side"): the book as the plugin's panel statbook/SbSidePanel right of the mod's HD PC sheet
// (where D2R puts its Advanced Stats panel), opened while the sheet is open (one open per opening), closed with it. The sheet
// then shows D2R's own page 1 (the top tabs and pages hidden). Its widgets are shown and hidden with D2R's own vfuncs (only
// while it is open: it is filled only then), as WidgetService's handles would not last for two books; the search box alone has
// a handle (its typed text). The fill functions work on it by swapping the view's maps in (SideView).
constexpr const char* SideName = "statbook/SbSidePanel";
constexpr const char* SideLocalId = "SbSidePanel";
constexpr double SideLeftUnits = PanelLeftUnits + 1162.0;  // its rect: x 1398 of the left panel anchor, the sheet's top
D2RL::Panels::RegistrationHandle g_sidePanel = D2RL::Panels::InvalidHandle;
bool g_sideReady = false;
std::atomic<bool> g_sideWanted{false};
std::atomic<bool> g_sideOn{false};  // the side host is showing (UI thread sets it)
std::atomic<bool> g_flip{false};    // the book's toggle was clicked
bool g_sideOpen = false, g_sideTried = false, g_raw = false;
void* g_sideNative = nullptr;
int g_sideApplied = -1;
Geometry g_side;
std::string g_sideJson, g_sideClassicJson;
panel_shared::Client g_sideClient;
std::atomic<long> g_sideOpens{0}, g_sideFails{0}, g_toggles{0};

// requests from other threads
std::atomic<int> g_wantTab{-1}, g_stepBy{0}, g_wheel{0};
std::atomic<bool> g_clicked{false}, g_arrow{false}, g_findSet{false};
std::mutex g_requests;
std::string g_findText;
std::vector<std::pair<std::string, int>> g_holdQueue;

// UI thread state
statbook::Tabs g_tabs;
std::atomic<int> g_tabNow{0};
std::atomic<bool> g_bound{false};
void* g_panel = nullptr;
bool g_isPad = false;
bool g_wasOpen = false;
int g_appliedTab = -1;
int g_plusOn = -1;  // D2R's stat point buttons as last set: 1 on, 0 off (a Stat Book page), -1 not yet (PlusButtonsOn)
std::atomic<long> g_plusSets{0}, g_plusFails{0};
std::string g_query, g_appliedQuery;
// the bound search box changed (G rebinds, a side opening, top / side): the query is read from it again, so the list
// matches the box shown (WidgetService cannot write a box's text)
bool g_syncQuery = false;
int g_lastSideNow = -1;
long g_scroll = 0, g_appliedScroll = -1;
struct Cached {
	void* w = nullptr;                                                    // the native widget (reading its flag, texts)
	D2RL::Widgets::WidgetHandle h = D2RL::Widgets::InvalidHandle;  // WidgetService's handle (showing and hiding)
	int last = -1;
};
D2RL::Widgets::WidgetHandle g_panelHandle = D2RL::Widgets::InvalidHandle;
// WidgetService's handles are paths that stay valid for every load of the sheet, and a plugin gets a limited number of them
// (about 256): kept for the plugin's lifetime, and only groups get one (hiding a group hides its children: the game check's
// statbook_vis_group_hidden shot). Leaves are only written (texts; the value boxes of the other tones hold "").
std::unordered_map<std::string, D2RL::Widgets::WidgetHandle> g_handles;
std::unordered_map<std::string, Cached> g_w;
std::unordered_map<std::string, std::string> g_texts;
std::unordered_map<std::string, int> g_hold;
std::unordered_set<void*> g_ownTop;    // the Stat Book's top-level widgets
std::vector<std::pair<void*, bool>> g_d2r;  // D2R's widgets hidden on the pages, and whether each was visible on the sheet
bool g_d2rHidden = false;
long g_visOff = -1;
uint8_t g_visMask = 0;
size_t g_kidsOff = 0;
std::vector<statbook::ListLine> g_all;
std::vector<uint16_t> g_allStats;
std::unordered_map<uint64_t, std::string> g_statText;
std::unordered_map<std::string, std::string> g_strings;
std::vector<AllSlot> g_slots;
// the side panel's view (swapped with the sheet's for a side fill)
std::unordered_map<std::string, D2RL::Widgets::WidgetHandle> g_sideHandles;
std::unordered_map<std::string, Cached> g_sideW;
std::unordered_map<std::string, std::string> g_sideTexts;
D2RL::Widgets::WidgetHandle g_sidePanelHandle = D2RL::Widgets::InvalidHandle;

std::atomic<long> g_ticks{0}, g_opens{0}, g_tabChanges{0}, g_clicks{0}, g_clickMisses{0}, g_arrows{0}, g_missing{0}, g_faults{0}, g_visSets{0},
    g_visFails{0}, g_handleFails{0}, g_reshown{0}, g_typedReads{0}, g_statLines{0}, g_statLineFails{0};
char g_calib[160] = "not yet";

// D2R's own show / hide (vfuncs +0x50 then +0x48, as the stash's pages; median_tabs.cpp): only for D2R's widgets of the sheet, which
// have no unique names, and only while the sheet is open.
void SetVisibleRaw(void* w, bool on) noexcept {
	auto* vt = *reinterpret_cast<void***>(w);
	reinterpret_cast<VisFn>(vt[0x50 / 8])(w, on ? 1 : 0);
	reinterpret_cast<VisFn>(vt[0x48 / 8])(w, on ? 1 : 0);
}

auto IsVisible(void* w) noexcept -> int {
	if (g_visOff < 0 || w == nullptr) {
		return -1;
	}
	return (static_cast<const uint8_t*>(w)[g_visOff] & g_visMask) != 0 ? 1 : 0;
}

auto Find(const std::string& name) -> Cached& {
	auto it = g_w.find(name);
	if (it == g_w.end()) {
		Cached c;
		c.w = panel_shared::NativeChild(g_panel, name.c_str());
		if (c.w == nullptr) {
			g_missing.fetch_add(1, std::memory_order_relaxed);
		}
		it = g_w.emplace(name, c).first;
	}
	return it->second;
}

// A group's WidgetService handle, looked up below its own group (ParentOf).
auto Group(const std::string& name) -> Cached& {
	Cached& c = Find(name);
	if (c.h != D2RL::Widgets::InvalidHandle || c.w == nullptr) {
		return c;
	}
	const auto known = g_handles.find(name);
	if (known != g_handles.end()) {
		c.h = known->second;
		return c;
	}
	const std::string parent = ParentOf(name);
	const D2RL::Widgets::WidgetHandle in = parent.empty() ? g_panelHandle : Group(parent).h;
	D2RL::Widgets::WidgetHandle h = D2RL::Widgets::InvalidHandle;
	if (in != D2RL::Widgets::InvalidHandle && g_widgets->findWidget(g_context, in, name.c_str(), &h) == D2RL::Widgets::Result::Success) {
		c.h = h;
		g_handles.emplace(name, h);
	} else {
		g_handleFails.fetch_add(1, std::memory_order_relaxed);
	}
	return c;
}

void SetVis(Cached& c, bool on) {
	if (c.h != D2RL::Widgets::InvalidHandle && g_widgets->setWidgetVisible(g_context, c.h, on) == D2RL::Widgets::Result::Success) {
		c.last = on ? 1 : 0;
		g_visSets.fetch_add(1, std::memory_order_relaxed);
	} else {
		g_visFails.fetch_add(1, std::memory_order_relaxed);
	}
}

// `force`: set even when the last set state is the same (an opening: D2R showed everything)
void Vis(const std::string& name, bool on, bool force) {
	if (g_raw) {  // the side panel: D2R's own show / hide, only while it is open
		Cached& c = Find(name);
		if (c.w == nullptr) {
			return;
		}
		const auto h = g_hold.find(name);
		if (h != g_hold.end()) {
			on = h->second != 0;
		}
		if (force || c.last != (on ? 1 : 0)) {
			SetVisibleRaw(c.w, on);
			c.last = on ? 1 : 0;
			g_visSets.fetch_add(1, std::memory_order_relaxed);
		}
		return;
	}
	Cached& c = Group(name);
	if (c.h == D2RL::Widgets::InvalidHandle) {
		return;
	}
	const auto h = g_hold.find(name);
	if (h != g_hold.end()) {
		on = h->second != 0;
	}
	if (force || c.last != (on ? 1 : 0)) {
		SetVis(c, on);
	}
}

void Text(const std::string& name, const std::string& want, bool force) {
	if (Find(name).w == nullptr) {
		return;
	}
	panel_shared::SetLine(g_client, g_panel, name.c_str(), g_texts[name], want, force);
}

// While it lives, Find / Group / Vis / Text work on the side panel (its own name caches, handles and raw visibility).
// Plain D2R in legacy graphics: the plugin's head picture covers D2R's name and class texts, so it draws its own
auto PlayerName(void* player, char* out, size_t size) noexcept -> bool {
	out[0] = '\0';
	__try {
		using Fn = const char* (*)(void*);
		const char* data = reinterpret_cast<Fn>(g_context->exeBase + RvaPlayerData)(player);
		if (data == nullptr) {
			return false;
		}
		size_t n = 0;
		for (; n + 1 < size && n < 64 && data[n] != '\0'; ++n) {
			out[n] = data[n];
		}
		out[n] = '\0';
		return n != 0;
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		out[0] = '\0';
		return false;
	}
}

auto PlayerClass(void* player) noexcept -> int {
	__try {
		return *reinterpret_cast<const int*>(static_cast<const uint8_t*>(player) + UnitClassOffset);
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		return -1;
	}
}

void* g_viewSheet = nullptr;  // the sheet's panel while a SideView lives (a fault inside one is undone on the next tick)

struct SideView {
	void* sheet;
	explicit SideView(void* side) : sheet(g_panel) {
		g_viewSheet = g_panel;
		Swap();
		g_panel = side;
		g_raw = true;
	}
	~SideView() {
		Swap();
		g_panel = sheet;
		g_raw = false;
	}
	SideView(const SideView&) = delete;
	auto operator=(const SideView&) -> SideView& = delete;
	static void Swap() {
		std::swap(g_w, g_sideW);
		std::swap(g_texts, g_sideTexts);
		std::swap(g_handles, g_sideHandles);
		std::swap(g_panelHandle, g_sidePanelHandle);
	}
};

// ---- calibration of a new sheet widget ----------------------------------------------------------------------------------

constexpr size_t Probe = 0x200;

auto CopyBytes(void* w, uint8_t* out) noexcept -> bool {
	__try {
		std::memcpy(out, w, Probe);
		return true;
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		return false;
	}
}

// The visible flag: the byte and bit that hiding `a` clears and hiding `b` clears too (both shown: D2R shows every widget of a
// sheet it loads; both hidden on the Character tab anyway). Nothing is shown here: the sheet may be closed.
void CalibrateVisible(const char* aName, const char* bName) noexcept {
	g_visOff = -1;
	Cached& ca = Group(aName);
	Cached& cb = Group(bName);
	uint8_t before[Probe], hidden[Probe], before2[Probe], hidden2[Probe];
	if (ca.w == nullptr || cb.w == nullptr || ca.h == D2RL::Widgets::InvalidHandle || cb.h == D2RL::Widgets::InvalidHandle || !CopyBytes(ca.w, before) ||
	    !CopyBytes(cb.w, before2)) {
		std::snprintf(g_calib, sizeof(g_calib), "visible flag: no probe widgets");
		return;
	}
	SetVis(ca, false);
	SetVis(cb, false);
	CopyBytes(ca.w, hidden);
	CopyBytes(cb.w, hidden2);
	for (size_t i = 8; i < Probe; ++i) {  // past the vtable
		const uint8_t bits = static_cast<uint8_t>(before[i] & ~hidden[i] & before2[i] & ~hidden2[i]);
		if (bits != 0) {
			g_visOff = static_cast<long>(i);
			g_visMask = static_cast<uint8_t>(bits & (~bits + 1));  // the lowest such bit
			break;
		}
	}
	if (g_visOff >= 0) {
		std::snprintf(g_calib, sizeof(g_calib), "visible flag +0x%lx bit 0x%02x", static_cast<unsigned long>(g_visOff), g_visMask);
	} else {
		std::snprintf(g_calib, sizeof(g_calib), "visible flag not found (every tick sets all)");
	}
}

// The child list: a (begin, end) pointer pair of the widget whose entries hold every one of `known`.
auto FindKids(void* panel, void* const* known, size_t n) noexcept -> size_t {
	__try {
		auto* p = static_cast<uint8_t*>(panel);
		for (size_t off = 8; off < 0x600; off += 8) {
			auto* const* b = *reinterpret_cast<void* const* const*>(p + off);
			auto* const* e = *reinterpret_cast<void* const* const*>(p + off + 8);
			if (b == nullptr || e <= b || e - b > 4096) {
				continue;
			}
			size_t found = 0;
			for (size_t k = 0; k < n; ++k) {
				for (auto* const* it = b; it < e; ++it) {
					if (*it == known[k]) {
						++found;
						break;
					}
				}
			}
			if (found == n) {
				return off;
			}
		}
	} __except (EXCEPTION_EXECUTE_HANDLER) {
	}
	return 0;
}

auto Kids(void* w, std::vector<void*>& out) noexcept -> bool {
	out.clear();
	if (g_kidsOff == 0 || w == nullptr) {
		return false;
	}
	__try {
		auto* p = static_cast<uint8_t*>(w);
		auto* const* b = *reinterpret_cast<void* const* const*>(p + g_kidsOff);
		auto* const* e = *reinterpret_cast<void* const* const*>(p + g_kidsOff + 8);
		if (b == nullptr || e < b || e - b > 4096) {
			return false;
		}
		for (auto* const* it = b; it < e; ++it) {
			if (*it != nullptr) {
				out.push_back(*it);
			}
		}
		return true;
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		out.clear();
		return false;
	}
}

// MSVC RTTI: the class name of a widget (".?AVClickCatcherWidget@@"), "" when it cannot be read.
auto TypeName(void* w, uint64_t imageBase) noexcept -> const char* {
	__try {
		auto* vt = *reinterpret_cast<uint8_t* const* const*>(w);
		const auto* col = reinterpret_cast<const uint8_t*>(vt[-1]);
		const uint32_t td = *reinterpret_cast<const uint32_t*>(col + 0xc);
		return reinterpret_cast<const char*>(imageBase + td + 0x10);
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		return "";
	}
}

void NewPanel(void* panel, void* sheet) {
	g_panel = panel;
	g_w.clear();
	g_texts.clear();
	g_ownTop.clear();
	g_d2r.clear();
	g_d2rHidden = false;
	g_appliedTab = -1;
	g_plusOn = -1;
	g_sheetTitle = g_plain ? panel_shared::NativeChild(sheet, "StatsPanelTitle") : nullptr;
	g_isPad = panel_shared::NativeChild(panel, "SbPadPrevLB") != nullptr;
	const bool legacy = panel_shared::NativeChild(panel, LegacyMarker) != nullptr;
	g_legacyNow.store(legacy);
	for (const char* n : {"StatBookMarker", "StatBookTabs", "SbPageBody", "StatBookPage", "StatBookAll", "SbPadAllHint", "SbPreviewQuery"}) {
		if (void* w = panel_shared::NativeChild(panel, n)) {
			g_ownTop.insert(w);
		}
	}
	if (g_widgets->findPanel(g_context, g_client.panelName, &g_panelHandle) != D2RL::Widgets::Result::Success) {
		g_panelHandle = D2RL::Widgets::InvalidHandle;
	}
	CalibrateVisible("SbPageBody", "StatBookAll");
	if (g_plain && g_visOff < 0) {
		g_visOff = SheetVisibleOffset;
		g_visMask = SheetVisibleMask;
	}
	void* known[] = {Find("StatBookMarker").w, Find("StatBookTabs").w, panel_shared::NativeChild(panel, legacy ? "background" : "Background"),
	                 panel_shared::NativeChild(panel, "CharacterName")};
	g_kidsOff = !g_plain && known[0] && known[1] && known[2] && known[3] ? FindKids(panel, known, 4) : 0;
	// D2R's widgets to hide on the pages: the panel's children that are neither the Stat Book's, kept, nor the click catcher
	std::unordered_set<void*> keep(g_ownTop);
	for (const char* n : Keep) {
		if (void* w = panel_shared::NativeChild(sheet, n); w != nullptr && !legacy) {
			keep.insert(w);
		}
	}
	for (const char* n : KeepLegacy) {
		if (void* w = panel_shared::NativeChild(sheet, n); w != nullptr && legacy) {
			keep.insert(w);
		}
	}
	std::vector<void*> top, sub;
	if (Kids(sheet, top)) {
		for (void* w : top) {
			if (keep.count(w) != 0 || std::strstr(TypeName(w, g_context->exeBase), "ClickCatcher") != nullptr) {
				continue;
			}
			g_d2r.emplace_back(w, true);
			if (Kids(w, sub)) {  // LeftSkillStats / RightSkillStats: their leaves too
				for (void* s : sub) {
					g_d2r.emplace_back(s, true);
				}
			}
		}
	} else {
		for (const char* n : HideByName) {
			if (void* w = panel_shared::NativeChild(sheet, n); w != nullptr && !legacy) {
				g_d2r.emplace_back(w, true);
			}
		}
		for (const char* n : HideByNameLegacy) {
			if (void* w = panel_shared::NativeChild(sheet, n); w != nullptr && legacy) {
				g_d2r.emplace_back(w, true);
			}
		}
	}
	if (g_plain && legacy) {  // plain D2R: the classic arrow is the plugin panel's own (on the mod's sheet one of the sheet's)
		if (void* w = panel_shared::NativeChild(panel, "SbAdvanced")) {
			g_d2r.emplace_back(w, true);
		}
	}
	char line[320];
	std::snprintf(line, sizeof(line), "statbook host: %s %p (%s layout): %s; child list %s; %zu D2R widgets hidden on the pages", g_plain ? "plain panel" : "sheet", panel,
	              g_isPad ? "gamepad" : legacy ? "legacy" : "PC", g_calib, g_kidsOff != 0 ? "found" : "not found (by name)", g_d2r.size());
	g_context->LogInfo(line);
}

// ---- filling ---------------------------------------------------------------------------------------------------------------

auto Str(const std::string& key, const std::string& english) -> std::string {
	auto it = g_strings.find(key);
	if (it != g_strings.end()) {
		return it->second;
	}
	char b[256];
	std::string s = LookupString(key.c_str(), b, sizeof(b)) ? std::string(b) : english;
	g_strings.emplace(key, s);
	return s;
}

void FillPlainName(void* player, bool force) {
	char name[65];
	if (player == nullptr || !PlayerName(player, name, sizeof(name))) {
		name[0] = '\0';
	}
	static constexpr const char* Keys[][2] = {{"partycharama", "Amazon"}, {"partycharsor", "Sorceress"}, {"partycharnec", "Necromancer"},
	                                          {"partycharpal", "Paladin"},  {"partycharbar", "Barbarian"}, {"partychardru", "Druid"},
	                                          {"partycharass", "Assassin"}, {"partycharwar", "Warlock"}};
	const int c = player != nullptr ? PlayerClass(player) : -1;
	Text(statbook_plain::NameText, name, force);
	Text(statbook_plain::ClassText, c >= 0 && c < 8 ? Str(Keys[c][0], Keys[c][1]) : std::string(), force);
}

void BuildAll(void* player) {
	auto value = [&](uint16_t id) { return g_sv.value(player, id, false); };
	auto statText = [&](uint16_t stat, int32_t v) -> std::string {
		const uint64_t key = (static_cast<uint64_t>(stat) << 32) | static_cast<uint32_t>(v);
		auto it = g_statText.find(key);
		if (it != g_statText.end()) {
			return it->second;
		}
		char b[256];
		std::string s;
		if (StatLine(player, stat, b, sizeof(b))) {
			s = b;
			g_statLines.fetch_add(1, std::memory_order_relaxed);
		} else {
			g_statLineFails.fetch_add(1, std::memory_order_relaxed);
		}
		if (g_statText.size() > 4096) {
			g_statText.clear();
		}
		g_statText.emplace(key, s);
		return s;
	};
	auto text = [&](const std::string& key, const std::string& english) { return Str(key, english); };
	AllLines(*g_book, value, statText, text, &g_all, &g_allStats);
}

void FillTabs(bool force) {
	const int n = g_tabs.Count();
	for (int i = 0; i < n && i < MaxTabs; ++i) {
		if (g_raw && i == 0) {  // the side panel has no Character tab
			continue;
		}
		Vis(TabName(i, ""), true, force);
		Vis(TabName(i, "Selected"), i == g_tabs.current, force);
		Vis(TabName(i, "SelectedLabel"), i == g_tabs.current, force);
	}
	if (g_isPad) {
		const bool triggers = g_sv.padTriggers != nullptr ? g_sv.padTriggers() : g_padTriggers;
		Vis("SbPadPrevLB", !triggers, force);
		Vis("SbPadNextRB", !triggers, force);
		Vis("SbPadPrevLT", triggers, force);
		Vis("SbPadNextRT", triggers, force);
		const bool hint = !g_tabs.IsSheet();
		Vis("SbPadAllHint", hint, force);
	}
}

void FillLines(void* player, bool show, bool force) {
	statbook::Line lines[MaxLines];
	const int page = g_tabs.Page();
	if (show && page >= 0 && player != nullptr) {
		statbook::PageLines(g_book->pages[static_cast<size_t>(page)], [&](uint16_t id, bool cls) { return g_sv.value(player, id, cls); }, 0, lines, MaxLines);
	}
	for (int i = 0; i < MaxLines; ++i) {
		const statbook::Line& l = lines[i];
		const LineShow s = show ? ShowFor(l) : LineShow{};
		Vis(Slot("SbLine", i, "Heading"), s.heading, force);
		if (s.heading) {
			Text(Slot("SbLine", i, "HeadingText"), l.heading, force);
		}
		const char* parts[3] = {"Full", "Left", "Right"};
		const bool on[3] = {s.full, s.left, s.right};
		for (int p = 0; p < 3; ++p) {
			const std::string base = Slot("SbLine", i, parts[p]);
			Vis(base, on[p], force);
			const statbook::Cell& c = l.cell[p == 2 ? 1 : 0];
			if (on[p]) {
				Text(base + "Label", p > 0 && g_legacyNow.load() ? ShortLabel(c.label) : c.label, force);
			}
			for (int t = 0; t < ToneCount; ++t) {
				const bool mine = on[p] && static_cast<int>(c.tone) == t;
				if (on[p]) {
					Text(base + "Value" + ToneNames[t], mine ? c.value : std::string(), force);
				}
			}
		}
	}
}

// The geometry of the host shown: the sheet's (`side` false) or the side panel's, in the bound graphics mode.
auto Geo(bool side) -> const Geometry& {
	if (g_legacyNow.load()) {
		return side ? g_legacySide : g_legacy;
	}
	return side ? g_side : g_isPad ? g_pad : g_pc;
}

void FillAll(void* player, bool show, bool force) {
	const Geometry& geo = Geo(g_raw);
	const int rows = geo.ok ? (geo.allRows < MaxAllRows ? geo.allRows : MaxAllRows) : (g_isPad ? 20 : MaxAllRows);
	g_slots.assign(static_cast<size_t>(rows), AllSlot{});
	size_t kept = 0, keptRows = 0;
	if (show && player != nullptr) {
		BuildAll(player);
		AllWindow(g_all, g_query, &g_scroll, g_slots.data(), static_cast<size_t>(rows), &kept, &keptRows);
	}
	Vis("SbPreviewQuery", false, force);
	if (show) {
		char count[32];
		std::snprintf(count, sizeof(count), "%zu/%zu", keptRows, RowCount(g_all));
		Text("SbSearchCount", count, force);
	}
	for (int j = 0; j < rows; ++j) {
		const AllSlot& s = g_slots[static_cast<size_t>(j)];
		const bool head = show && s.kind == AllSlot::Kind::Heading, row = show && s.kind == AllSlot::Kind::Row;
		Vis(Slot("SbAll", j, "Heading"), head, force);
		if (head) {
			Text(Slot("SbAll", j, "HeadingText"), s.text, force);
		}
		Vis(Slot("SbAll", j, "Row"), row, force);
		if (row) {
			Text(Slot("SbAll", j, "Text"), s.text, force);
			Text(Slot("SbAll", j, "Hit"), s.hit, force);
			Text(Slot("SbAll", j, "Pre"), s.pre, force);
		}
	}
}

// D2R's own page-1 widgets: hidden on the other tabs, shown again (as they were) on the Character tab
void D2RWidgets(bool sheet, bool force) {
	if (!sheet) {
		for (auto& [w, was] : g_d2r) {
			if (!g_d2rHidden) {
				const int v = IsVisible(w);
				was = v != 0;
			}
			if (force || IsVisible(w) != 0) {
				if (g_d2rHidden && IsVisible(w) == 1) {
					g_reshown.fetch_add(1, std::memory_order_relaxed);  // D2R showed it again
				}
				SetVisibleRaw(w, false);
			}
		}
		g_d2rHidden = true;
	} else if (g_d2rHidden) {
		for (const auto& [w, was] : g_d2r) {
			if (was) {
				SetVisibleRaw(w, true);
			}
		}
		g_d2rHidden = false;
	}
}

// D2R's stat point buttons on (Character tab) or off (a Stat Book page: D2R hit-tests hidden widgets, so a + under the page body
// would spend a point). Off is set on every tick (cheap, and nothing D2R does turns it on in between); on once per change.
void PlusButtonsOn(bool on, bool force) {
	if (g_plain) {  // the plugin's own panel: D2R's sheet and its buttons are D2R's
		return;
	}
	if (!on || force || g_plusOn != 1) {
		for (const char* n : PlusButtons) {
			const std::string key = std::string("LevelUpInfo/") + n;
			D2RL::Widgets::WidgetHandle h = D2RL::Widgets::InvalidHandle;
			const auto known = g_handles.find(key);
			if (known != g_handles.end()) {
				h = known->second;
			} else {
				D2RL::Widgets::WidgetHandle group = D2RL::Widgets::InvalidHandle;
				const auto g = g_handles.find("LevelUpInfo");
				if (g != g_handles.end()) {
					group = g->second;
				} else if (g_panelHandle != D2RL::Widgets::InvalidHandle &&
				           g_widgets->findWidget(g_context, g_panelHandle, "LevelUpInfo", &group) == D2RL::Widgets::Result::Success) {
					g_handles.emplace("LevelUpInfo", group);
				}
				if (group == D2RL::Widgets::InvalidHandle || g_widgets->findWidget(g_context, group, n, &h) != D2RL::Widgets::Result::Success) {
					g_plusFails.fetch_add(1, std::memory_order_relaxed);
					continue;
				}
				g_handles.emplace(key, h);
			}
			if (g_widgets->setWidgetEnabled(g_context, h, on) == D2RL::Widgets::Result::Success) {
				g_plusSets.fetch_add(1, std::memory_order_relaxed);
			} else {
				g_plusFails.fetch_add(1, std::memory_order_relaxed);
			}
		}
	}
	g_plusOn = on ? 1 : 0;
}

// ---- input ---------------------------------------------------------------------------------------------------------------

// A client pixel in the layout units of the panel whose left edge is `left` (the sheet's or the side panel's).
auto ToUnits(int x, int y, int clientH, double* ux, double* uy, double left = PanelLeftUnits) -> bool {
	if (clientH <= 0) {
		return false;
	}
	const double s = clientH / 2160.0;
	*ux = x / s - left;
	*uy = y / s - PanelTopUnits;
	return true;
}

// D2R's classic screen size now (800 x 600 when it cannot be read or looks wrong).
void ClassicScreen(int* w, int* h) noexcept {
	*w = 800;
	*h = 600;
	__try {
		const int x = *reinterpret_cast<const int*>(g_context->exeBase + RvaScreenSizeX);
		const int y = *reinterpret_cast<const int*>(g_context->exeBase + RvaScreenSizeY);
		if (x >= 640 && x <= 2048 && y >= 480 && y <= 1200) {
			*w = x;
			*h = y;
		}
	} __except (EXCEPTION_EXECUTE_HANDLER) {
	}
}

// A client pixel in the units of the host shown (HD: the sheet's or the side panel's layout units; legacy: classic pixels).
auto PanelUnits(int x, int y, int clientW, int clientH, bool side, double* ux, double* uy) -> bool {
	if (g_legacyNow.load()) {
		int sw = 0, sh = 0;
		ClassicScreen(&sw, &sh);
		return ClassicUnits(clientW, clientH, sw, sh, Geo(side).origin, x, y, ux, uy);
	}
	return ToUnits(x, y, clientH, ux, uy, side ? SideLeftUnits : PanelLeftUnits);
}

void TakeClick() {
	int x = 0, y = 0, w = 0, h = 0;
	const bool side = g_sideOn.load();
	const Geometry& geo = Geo(side);
	if (!panel_shared::LastClick(&x, &y, &w, &h) || g_isPad || !geo.ok) {
		g_clickMisses.fetch_add(1);
		return;
	}
	double ux = 0, uy = 0;
	PanelUnits(x, y, w, h, side, &ux, &uy);
	const ClickHit hit = ClickOn(geo, g_tabs, ux, uy);
	if (hit.kind == ClickHit::Kind::Toggle) {
		g_flip.store(true);
		g_clicks.fetch_add(1);
		return;
	}
	if (hit.kind == ClickHit::Kind::Advanced) {
		g_arrow.store(true);
		g_clicks.fetch_add(1);
		return;
	}
	if (hit.kind == ClickHit::Kind::Tab) {
		g_tabs.Select(side ? SideTab(hit.index) : hit.index);
		g_clicks.fetch_add(1);
		return;
	}
	if (hit.kind == ClickHit::Kind::Row) {
		const int row = hit.index;
		if (row >= 0 && static_cast<size_t>(row) < g_slots.size() && g_slots[static_cast<size_t>(row)].kind == AllSlot::Kind::Row) {
			const size_t src = g_slots[static_cast<size_t>(row)].source;
			const int to = src < g_allStats.size() ? TabOfStat(*g_book, g_allStats[src]) : -1;
			if (to > 0) {
				g_tabs.Select(to);
				g_clicks.fetch_add(1);
				return;
			}
		}
	}
	g_clickMisses.fetch_add(1);
}

auto ReadTyped() -> bool {
	const D2RL::Widgets::WidgetHandle box = Group("SbSearchInput").h;
	if (box == D2RL::Widgets::InvalidHandle) {
		return false;
	}
	char input[96] = {};
	uint32_t need = 0;
	if (g_widgets->getInputText(g_context, box, input, sizeof(input), &need) != D2RL::Widgets::Result::Success) {
		return false;
	}
	g_typedReads.fetch_add(1, std::memory_order_relaxed);
	g_query = Query(input);
	return true;
}

auto SheetFlag(void* sheet) noexcept -> int {
	__try {
		return (static_cast<const uint8_t*>(sheet)[SheetVisibleOffset] & SheetVisibleMask) != 0 ? 1 : 0;
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		return -1;
	}
}

// Plain D2R: the plugin's panel follows the sheet (open while the sheet is open; in legacy graphics only with the classic layout
// registered). The sheet's open state, -1 unknown.
auto PlainFollow() -> int {
	void* sheet = panel_shared::NativePanel(g_sheet);
	// only over the PC sheet (it has a CloseButton; D2R's gamepad sheet in the gamepad menu has none): the gamepad sheet keeps
	// D2R's own sheet
	static void* lastSheet = nullptr;
	if (sheet != lastSheet) {
		lastSheet = sheet;
		g_plainPadSheet = sheet != nullptr && panel_shared::NativeChild(sheet, "CloseButton") == nullptr;
	}
	if (g_plainPadSheet) {
		sheet = nullptr;
	}
	g_sheetPanel = sheet;
	const int open = sheet != nullptr && (panel_shared::IsHd() || g_plainLegacyReady) ? SheetFlag(sheet) : 0;
	static bool tried = false;  // one open per sheet opening: a refused open is not retried until the sheet opens again
	if (open != 1) {
		tried = false;
	}
	if (open == 1 && !g_plainOpen && !tried) {
		tried = true;
		if (g_panels->openPanel(g_context, g_plainPanel) == D2RL::Panels::Result::Success) {
			g_plainOpen = true;
			g_plainOpens.fetch_add(1);
		} else {
			g_plainFails.fetch_add(1);
		}
	} else if (open != 1 && g_plainOpen) {
		(void)g_panels->closePanel(g_context, g_plainPanel);
		g_plainOpen = false;
	}
	return open;
}

// ---- the side host ---------------------------------------------------------------------------------------------------------

// The book's toggle was clicked: top / side flipped, and statbook.toml written back (services.tabsChanged).
void TakeFlip() {
	if (!g_flip.exchange(false)) {
		return;
	}
	const bool s = !g_sideWanted.load();
	g_sideWanted.store(s);
	g_toggles.fetch_add(1);
	if (g_sv.tabsChanged != nullptr) {
		g_sv.tabsChanged(s);
	}
}

// The side panel has a layout for the graphics mode shown (HD: sidepanelhd.json; legacy: sidepanel.json beside the mod's classic sheet).
auto SideReadyNow() -> bool {
	return g_sideReady && (panel_shared::IsHd() ? !g_legacyNow.load() : g_sideLegacyReady && g_legacyNow.load() && g_legacySide.ok);
}

auto SideActive() -> bool {
	return g_sideWanted.load() && SideReadyNow() && !g_isPad;
}

void SideClose() {
	if (g_sideOpen) {
		(void)g_panels->closePanel(g_context, g_sidePanel);
		g_sideOpen = false;
	}
	g_sideTried = false;
	g_sideApplied = -1;
	g_sideClient.open.store(false);
	g_sideClient.boxClicked.store(false);
	g_sideClient.boxFocus.store(false);
}

// The side panel while the sheet is open: opened once per sheet opening, then filled like the sheet's book.
void TickSide(void* player, const PageShow& ps, bool force) {
	if (!g_sideOpen && !g_sideTried) {
		g_sideTried = true;
		if (g_panels->openPanel(g_context, g_sidePanel) == D2RL::Panels::Result::Success) {
			g_sideOpen = true;
			g_sideOpens.fetch_add(1);
		} else {
			g_sideFails.fetch_add(1);
		}
	}
	if (!g_sideOpen) {
		return;
	}
	void* side = panel_shared::NativePanel(g_sideClient);
	if (side == nullptr || panel_shared::NativeChild(side, "StatBookTabs") == nullptr) {
		return;  // not loaded yet
	}
	if (side != g_sideNative || g_sideApplied < 0) {  // a new opening: D2R shows every widget, and may have made new ones
		g_sideNative = side;
		g_syncQuery = true;
		g_sideW.clear();
		g_sideTexts.clear();
		force = true;
	}
	g_sideClient.open.store(true);
	const SideView view(side);
	if (g_panelHandle == D2RL::Widgets::InvalidHandle && g_widgets->findPanel(g_context, SideName, &g_panelHandle) != D2RL::Widgets::Result::Success) {
		g_panelHandle = D2RL::Widgets::InvalidHandle;
	}
	g_sideClient.boxFocus.store(panel_shared::BoxFocused(g_sideClient));
	if (g_syncQuery && ReadTyped()) {
		g_syncQuery = false;
	}
	if (ps.all && g_sideClient.boxClicked.load()) {
		ReadTyped();
	}
	if (g_tabs.current != g_sideApplied) {
		force = true;
	}
	Vis("StatBookTabs", true, force);
	Vis("SbPageBody", false, force);
	Vis("StatBookPage", ps.page, force);
	Vis("StatBookAll", ps.all, force);
	Vis("SbTabsToggle", true, force);
	const int page = g_tabs.Page();
	Text("SbSideHeading", page >= 0 ? g_book->pages[static_cast<size_t>(page)].title : ps.all ? std::string("All Stats") : std::string(), force);
	FillTabs(force);
	FillLines(player, ps.page, force);
	FillAll(player, ps.all, force);
	for (const auto& [name, on] : g_hold) {
		Vis(name, on != 0, false);
	}
	g_sideApplied = g_tabs.current;
}

void TickInner() {
	g_ticks.fetch_add(1, std::memory_order_relaxed);
	if (g_raw) {  // a fault left the side view in: the sheet's view back
		SideView::Swap();
		g_panel = g_viewSheet;
		g_raw = false;
		SideClose();
	}
	const int sheetOpen = g_plain ? PlainFollow() : 1;
	void* panel = panel_shared::NativePanel(g_client);
	if (panel == nullptr || panel_shared::NativeChild(panel, Marker) == nullptr ||
	    !panel_shared::IsHd() && panel_shared::NativeChild(panel, "SbPadPrevLB") == nullptr && (panel_shared::NativeChild(panel, LegacyMarker) == nullptr || !g_legacy.ok)) {
		SideClose();
		g_sideOn.store(false);
		g_bound.store(false);
		g_client.open.store(false);
		g_panel = panel == nullptr ? nullptr : g_panel;
		return;
	}
	bool force = false;
	if (g_plain && (sheetOpen != 1 || g_sheetPanel == nullptr)) {
		g_bound.store(!g_plainPadSheet);  // the gamepad sheet is D2R's own: its tab buttons stay D2R's
		SideClose();
		TakeFlip();  // a toggle click just before the sheet closed
		g_wasOpen = false;
		g_client.open.store(false);
		g_client.boxClicked.store(false);
		g_client.boxFocus.store(false);
		return;
	}
	static void* boundSheet = nullptr;  // plain D2R: D2R's widgets are the sheet's, a new sheet (graphics mode) binds again
	if (panel != g_panel || (g_plain && g_sheetPanel != boundSheet)) {
		boundSheet = g_plain ? g_sheetPanel : nullptr;
		NewPanel(panel, g_plain ? g_sheetPanel : panel);
		force = true;
		g_syncQuery = true;
	}
	g_bound.store(true);
	const int vis = IsVisible(panel);
	const bool open = vis != 0;  // unknown (-1): taken as open
	if (open && !g_wasOpen) {
		g_opens.fetch_add(1);
		force = true;
		g_d2rHidden = false;  // D2R showed its widgets again
	}
	g_wasOpen = open;
	g_client.open.store(open);
	if (!open) {
		g_client.boxClicked.store(false);
		g_client.boxFocus.store(false);
		SideClose();
		TakeFlip();  // a toggle click just before the sheet closed
		return;
	}
	panel_shared::HookGameWindow();
	if (vis < 0) {
		force = true;  // without the visible flag every tick sets everything
	}
	{
		const std::lock_guard<std::mutex> lock(g_requests);
		for (auto& [name, on] : g_holdQueue) {
			if (on < 0) {  // let go: shown again (a leaf has no other setter; a group gets its own state below)
				g_hold.erase(name);
				Cached& c = Group(name);
				if (c.h != D2RL::Widgets::InvalidHandle) {
					SetVis(c, true);
				}
			} else {
				g_hold[name] = on;
			}
			force = true;
		}
		g_holdQueue.clear();
		if (g_findSet.exchange(false)) {
			g_query = Query(g_findText);
			g_syncQuery = false;  // a find wins over the box
		}
	}
	if (g_clicked.exchange(false)) {  // on the host shown until now
		TakeClick();
	}
	TakeFlip();
	const bool sideNow = SideActive();
	if (sideNow != g_sideOn.load()) {  // switched live: the other host's widgets go, this one's come (every group set again)
		g_sideOn.store(sideNow);
		force = true;
		g_appliedTab = -1;
		if (sideNow) {
			g_tabs.current = SideTab(g_tabs.current);
		} else {
			SideClose();
		}
	}
	const int want = g_wantTab.exchange(-1);
	if (want >= 0) {
		g_tabs.Select(sideNow ? SideTab(want) : want);
	}
	if (const int by = g_stepBy.exchange(0); by != 0) {
		if (sideNow) {
			SideStep(g_tabs, by);
		} else {
			g_tabs.Step(by);
		}
	}
	if (g_arrow.exchange(false)) {
		g_tabs.Select(g_tabs.AllStats());
		g_arrows.fetch_add(1);
	}
	if (const int w = g_wheel.exchange(0); w != 0) {
		g_scroll += w;
	}
	g_client.boxFocus.store(!sideNow && panel_shared::BoxFocused(g_client));
	if (g_lastSideNow != (sideNow ? 1 : 0)) {
		g_lastSideNow = sideNow ? 1 : 0;
		g_syncQuery = true;
	}
	if (g_syncQuery && !sideNow && ReadTyped()) {
		g_syncQuery = false;
	}
	const bool all = g_tabs.current == g_tabs.AllStats();
	if (all && !sideNow && g_client.boxClicked.load()) {
		ReadTyped();
	}
	if (g_tabs.current != g_appliedTab) {
		g_tabChanges.fetch_add(1);
		force = true;
	}
	g_tabNow.store(g_tabs.current);
	void* player = g_sv.player != nullptr ? g_sv.player() : nullptr;
	const PageShow ps = ShowForTab(g_tabs);
	if (g_plain && g_legacyNow.load()) {
		FillPlainName(player, force);
	}
	if (sideNow) {
		// the sheet shows D2R's own page 1 under its own title; the book is the side panel
		Vis("StatBookTabs", false, force);
		Vis("SbPageBody", false, force);
		Vis("StatBookPage", false, force);
		Vis("StatBookAll", false, force);
		Vis("SbTabsToggle", false, force);
		D2RWidgets(true, force);
		PlusButtonsOn(PlusButtonsEnabled(ps, true, g_plain), force);
		if (!g_plain) {
			Text("StatsPanelTitle", Str("minipanelchar", "Character"), force);
		} else if (g_sheetTitle != nullptr && IsVisible(g_sheetTitle) != 1) {  // plain D2R: the sheet's own title, hidden under the tabs
			SetVisibleRaw(g_sheetTitle, true);
		}
		TickSide(player, ps, force);
		g_appliedTab = g_tabs.current;
		return;
	}
	if (force && !g_plain && !g_isPad && SideReadyNow()) {
		Text("StatsPanelTitle", std::string(), true);  // the tabs are the title (the mod's PC layout has none; side mode set one)
	}
	Vis("StatBookTabs", true, force);
	Vis("StatBookMarker", true, force);
	Vis("SbPageBody", ps.body && !g_isPad, force);
	Vis("StatBookPage", ps.page, force);
	Vis("StatBookAll", ps.all, force);
	if (!g_isPad) {
		Vis("SbTabsToggle", ps.body && SideReadyNow(), force);
	}
	FillTabs(force);
	FillLines(player, ps.page, force);
	FillAll(player, ps.all, force);
	D2RWidgets(ps.sheet, force);
	PlusButtonsOn(PlusButtonsEnabled(ps, false, g_plain), force);
	if (g_sheetTitle != nullptr && IsVisible(g_sheetTitle) == 1) {  // D2R shows it on every opening
		SetVisibleRaw(g_sheetTitle, false);
	}
	for (const auto& [name, on] : g_hold) {
		Vis(name, on != 0, false);
	}
	g_appliedTab = g_tabs.current;
}

void __cdecl TickOnUi(const D2RL::PluginContext*, void*) noexcept {
	g_tickQueued.store(false);
	__try {
		TickInner();
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		g_faults.fetch_add(1);
	}
}

DWORD WINAPI TimerThread(LPVOID) {
	for (;;) {
		Sleep(TickMs);
		if (!g_tickQueued.exchange(true) && g_threads->runOnUiThread(g_context, &TickOnUi, nullptr) != D2RL::Threads::Result::Success) {
			g_tickQueued.store(false);
		}
	}
}

// ---- panel_shared client callbacks ------------------------------------------------------------------------------------------

void OnPress(int) noexcept {
	g_clicked.store(true);
}

// The search box of the host shown: the sheet's (`side` false) or the side panel's.
auto SearchBox(panel_shared::BoxRect* box, bool side) noexcept -> bool {
	int x = 0, y = 0, w = 0, h = 0;
	const Geometry& geo = Geo(side);
	if (!g_bound.load() || g_isPad || g_sideOn.load() != side || !geo.ok || g_tabNow.load() != g_tabs.AllStats() || !panel_shared::LastClick(&x, &y, &w, &h)) {
		return false;
	}
	if (g_legacyNow.load()) {
		int sw = 0, sh = 0;
		ClassicScreen(&sw, &sh);
		box->hd = false;
		ClassicPlace(sw, sh, geo.origin, &box->panelX, &box->panelY);
		box->x = geo.search.x;
		box->y = geo.search.y;
		box->w = geo.search.w;
		box->h = geo.search.h;
		return true;
	}
	const double s = h / 2160.0;
	box->hd = true;
	box->panelX = static_cast<int>((side ? SideLeftUnits : PanelLeftUnits) - (w / 2.0) / s);
	box->panelY = static_cast<int>(PanelTopUnits - (h / 2.0) / s);
	box->x = geo.search.x;
	box->y = geo.search.y;
	box->w = geo.search.w;
	box->h = geo.search.h;
	return true;
}

auto InputBox(panel_shared::BoxRect* box) noexcept -> bool {
	return SearchBox(box, false);
}

auto SideInputBox(panel_shared::BoxRect* box) noexcept -> bool {
	return SearchBox(box, true);
}

// The wheel over the All Stats list of the host shown (both clients get it; only the shown host's takes it).
auto Wheel(int notches, int x, int y, int clientW, int clientH, bool side) noexcept -> bool {
	const Geometry& geo = Geo(side);
	if (!g_bound.load() || g_isPad || g_sideOn.load() != side || g_tabNow.load() != g_tabs.AllStats() || geo.allRowRects.empty()) {
		return false;
	}
	double ux = 0, uy = 0;
	PanelUnits(x, y, clientW, clientH, side, &ux, &uy);
	const Rect& first = geo.allRowRects.front();
	const Rect& last = geo.allRowRects.back();
	if (ux < first.x || ux > first.x + first.w || uy < first.y || uy > last.y + last.h) {
		return false;
	}
	g_wheel.fetch_add(-notches * 3);
	return true;
}

auto OnWheel(int notches, int x, int y, int clientW, int clientH) noexcept -> bool {
	return Wheel(notches, x, y, clientW, clientH, false);
}

auto SideWheel(int notches, int x, int y, int clientW, int clientH) noexcept -> bool {
	return Wheel(notches, x, y, clientW, clientH, true);
}

auto __cdecl OnUiMessage(const D2RL::PluginContext*, const D2RL::SharedEvents::UiMessageEvent* event, void*) noexcept -> D2RL::SharedEvents::UiMessageAction {
	if (event != nullptr && event->target != nullptr && event->command != nullptr && g_bound.load() && !g_isPad && (!g_plain || g_sideOn.load()) &&
	    std::strcmp(event->target, "CharacterStatsPanelMessage") == 0 && std::strcmp(event->command, "ToggleAdvancedStats") == 0) {
		g_arrow.store(true);
		return D2RL::SharedEvents::UiMessageAction::Consume;
	}
	return D2RL::SharedEvents::UiMessageAction::Continue;
}

}  // namespace

auto InstallSheetHost(const D2RL::PluginContext* context, const statbook::Book* book, const char* selfPath, bool padTriggers, SheetHostServices services,
                      char* report, size_t reportSize) noexcept -> bool {
	g_context = context;
	g_book = book;
	g_sv = services;
	g_padTriggers = padTriggers;
	g_tabs.pages = static_cast<int>(book->pages.size());
	const D2RL::SharedEventService* events = nullptr;
	if (context->QueryService(&g_threads) != D2RL::ServiceQueryResult::Success || !D2RL::HasThreadServiceField(g_threads, D2RL::ThreadServiceRequiredSize) ||
	    context->QueryService(&events) != D2RL::ServiceQueryResult::Success || !D2RL::HasSharedEventServiceField(events, D2RL::SharedEventServiceRequiredSize) ||
	    context->QueryService(&g_widgets) != D2RL::ServiceQueryResult::Success || !D2RL::HasWidgetServiceField(g_widgets, D2RL::WidgetServiceRequiredSize) ||
	    context->QueryService(&g_panels) != D2RL::ServiceQueryResult::Success || !D2RL::HasPanelServiceField(g_panels, D2RL::PanelServiceRequiredSize) ||
	    !panel_shared::Init(context)) {
		std::snprintf(report, reportSize, "host off: a loader service is missing");
		return false;
	}
	g_client.panelName = PanelName;
	std::string json;
	if (panel_shared::ReadModFile(context, selfPath, L"data\\hd\\global\\ui\\panel\\statbook\\statbook-layout.json", 256 * 1024, &json) == panel_shared::FileResult::Ok) {
		g_pc = ParseGeometry(json, "pc");
		g_pad = ParseGeometry(json, "pad");
		g_side = ParseGeometry(json, "side");
		g_legacy = ParseGeometry(json, "legacy");
		g_legacySide = ParseGeometry(json, "legacyside");
		// the side panel (tabs = "side"): its layout is the mod's (statbook_layout.py writes it beside statbook-layout.json)
		const char* side = "no sidepanelhd.json";
		if (g_side.ok && panel_shared::ReadModFile(context, selfPath, L"data\\hd\\global\\ui\\panel\\statbook\\sidepanelhd.json", 4 * 1024 * 1024, &g_sideJson) ==
		                     panel_shared::FileResult::Ok) {
			D2RL::Panels::PanelRegistration reg{};
			reg.structSize = D2RL::Panels::PanelRegistrationSize;
			reg.flags = D2RL::Panels::PanelFlags::None;
			reg.localId = SideLocalId;
			// its classic layout (statbook_legacy.py), for the mod's legacy sheet: registered first, the panel then has both
			if (g_legacySide.ok && panel_shared::ReadModFile(context, selfPath, L"data\\hd\\global\\ui\\panel\\statbook\\sidepanel.json", 4 * 1024 * 1024,
			                                                 &g_sideClassicJson) == panel_shared::FileResult::Ok) {
				g_sideLegacyReady = panel_shared::RegisterLayout(context, SideLocalId, g_sideClassicJson.c_str(), g_sideClassicJson.size());
			}
			g_sideReady = panel_shared::RegisterLayout(context, (std::string(SideLocalId) + "hd").c_str(), g_sideJson.c_str(), g_sideJson.size()) &&
			              g_panels->registerPanel(context, &reg, &g_sidePanel) == D2RL::Panels::Result::Success;
			side = g_sideReady ? "side panel ok" : "side panel NOT registered";
		}
		std::snprintf(g_geometryFrom, sizeof(g_geometryFrom), "statbook-layout.json: pc %s (%zu tabs), pad %s, legacy %s; %s%s", g_pc.ok ? "ok" : "BAD",
		              g_pc.tabs.size(), g_pad.ok ? "ok" : "BAD", g_legacy.ok ? "ok" : "none", side, g_sideLegacyReady ? " (+ legacy)" : "");
	} else {
		// no mod sheet layout: plain D2R, the plugin's own panels: over the sheet, and the side panel
		g_plain = true;
		for (const char* part : statbook_plain::LayoutHd) {
			g_plainHd += part;
		}
		for (const char* part : statbook_plain::SideLayoutHd) {
			g_sideJson += part;
		}
		for (const char* part : statbook_plain::Geometry) {
			g_plainGeometry += part;
		}
		for (const char* part : statbook_plain::LayoutLegacy) {
			g_plainLegacy += part;
		}
		for (const char* part : statbook_plain::SideLayoutLegacy) {
			g_sideLegacyJson += part;
		}
		for (const char* part : statbook_plain::GeometryLegacy) {
			g_plainLegacyGeometry += part;
		}
		// the Stat Book's own sprites when the install has them (as the mod's art: the MPQ folder's data), else D2R's stock ones
		std::unordered_map<std::string, bool> have;
		auto installed = [&](const char* file) {
			const auto it = have.find(file);
			if (it != have.end()) {
				return it->second;
			}
			std::wstring rel = L"data\\hd\\global\\ui\\panel\\statbook\\";
			for (const char* c = file; *c != '\0'; ++c) {
				rel += static_cast<wchar_t>(*c);
			}
			std::string unused;  // a 1-byte limit: a sprite that is there answers BadSize without being read
			const panel_shared::FileResult r = panel_shared::ReadModFile(context, selfPath, rel.c_str(), 1, &unused);
			return have[file] = r == panel_shared::FileResult::Ok || r == panel_shared::FileResult::BadSize;
		};
		int swapped = 0, unmatched = 0;
		for (const auto& row : statbook_plain::Fallback) {
			if (installed(row[0])) {
				continue;
			}
			std::string* text = g_plainHd.find(row[1]) != std::string::npos ? &g_plainHd : &g_sideJson;
			if (const size_t at = text->find(row[1]); at != std::string::npos) {
				text->replace(at, std::strlen(row[1]), row[2]);
				++swapped;
			} else {
				++unmatched;
			}
		}
		g_pc = ParseGeometry(g_plainGeometry, "pc");
		g_side = ParseGeometry(g_plainGeometry, "side");
		// legacy graphics: the classic layouts, registered first (the panel then has both) when the install has all their art
		// (data/global/ui/panel/statbook/*.dc6); else legacy keeps D2R's own sheet
		int legacyArt = 0;
		for (const char* file : statbook_plain::LegacyArt) {
			std::wstring rel = L"data\\global\\ui\\panel\\statbook\\";
			for (const char* c = file; *c != '\0'; ++c) {
				rel += static_cast<wchar_t>(*c);
			}
			std::string unused;
			const panel_shared::FileResult r = panel_shared::ReadModFile(context, selfPath, rel.c_str(), 1, &unused);
			legacyArt += r == panel_shared::FileResult::Ok || r == panel_shared::FileResult::BadSize ? 1 : 0;
		}
		const int legacyArtWanted = static_cast<int>(sizeof(statbook_plain::LegacyArt) / sizeof(statbook_plain::LegacyArt[0]));
		if (legacyArt == legacyArtWanted) {
			g_legacy = ParseGeometry(g_plainLegacyGeometry, "legacy");
			g_legacySide = ParseGeometry(g_plainLegacyGeometry, "legacyside");
			g_plainLegacyReady = g_legacy.ok && panel_shared::RegisterLayout(context, statbook_plain::PanelLocalId, g_plainLegacy.c_str(), g_plainLegacy.size());
			g_legacy.ok = g_plainLegacyReady;
		}
		// The HD layout (<localId>hd.json; the classic one is <localId>.json). Its name must not start with the click panel's name (statbook/StatBook): with statbook/StatBookPlain
		// the loader never opened it (each open "failed" with the resource found)
		const bool layouts = panel_shared::RegisterLayout(context, (std::string(statbook_plain::PanelLocalId) + "hd").c_str(), g_plainHd.c_str(), g_plainHd.size());
		D2RL::Panels::PanelRegistration panel{};
		panel.structSize = D2RL::Panels::PanelRegistrationSize;
		panel.flags = D2RL::Panels::PanelFlags::None;
		panel.localId = statbook_plain::PanelLocalId;
		const bool registered = layouts && g_panels->registerPanel(context, &panel, &g_plainPanel) == D2RL::Panels::Result::Success;
		if (!registered || statbook_plain::TabCount != g_tabs.Count()) {
			std::snprintf(report, reportSize, "host off: plain D2R panel %s", !registered ? "not registered" : "has another tab count than the book");
			return false;
		}
		D2RL::Panels::PanelRegistration reg{};
		reg.structSize = D2RL::Panels::PanelRegistrationSize;
		reg.flags = D2RL::Panels::PanelFlags::None;
		reg.localId = statbook_plain::SideLocalId;
		if (g_plainLegacyReady && g_legacySide.ok) {
			g_sideLegacyReady = panel_shared::RegisterLayout(context, statbook_plain::SideLocalId, g_sideLegacyJson.c_str(), g_sideLegacyJson.size());
		}
		g_sideReady = g_side.ok && panel_shared::RegisterLayout(context, (std::string(statbook_plain::SideLocalId) + "hd").c_str(), g_sideJson.c_str(), g_sideJson.size()) &&
		              g_panels->registerPanel(context, &reg, &g_sidePanel) == D2RL::Panels::Result::Success;
		std::snprintf(g_geometryFrom, sizeof(g_geometryFrom), "plain D2R: own panel %s (pc %s, %zu tabs, tab art %s, cell art %s); side panel %s (side art %s, toggle art %s); %d stock swaps%s; legacy %s%s (%d of %d DC6)",
		              statbook_plain::PanelName, g_pc.ok ? "ok" : "BAD", g_pc.tabs.size(), installed("tab.sprite") ? "own" : "D2R's stash tab", installed("halfcell.sprite") && installed("sidehalfcell.sprite") ? "own" : "none",
		              g_sideReady ? "ok" : "NOT registered", installed("sidebody.sprite") && installed("sidetab.sprite") ? "own" : "D2R's stock",
		              installed("tabstoggleside.sprite") ? "own" : "D2R's level-up button", swapped, unmatched != 0 ? ", SOME NOT FOUND" : "",
		              g_plainLegacyReady ? "ok" : "off", g_sideLegacyReady ? " (+ side)" : "", legacyArt, legacyArtWanted);
		g_client.panelName = statbook_plain::PanelName;
		g_sheet.panelName = PanelName;
	}
	g_client.inputName = "SbSearchInput";
	g_client.buttonPrefix = "statbook/StatBook";
	g_client.buttonCount = 1;
	g_client.onPress = &OnPress;
	g_client.inputBox = &InputBox;
	g_client.onWheel = &OnWheel;
	const bool name = panel_shared::RegisterPanelName(context, "StatBook");
	panel_shared::AddClient(&g_client);
	if (g_sideReady) {  // the side panel's search box and wheel (its buttons come through g_client's StatBook name)
		g_sideClient.panelName = SideName;
		g_sideClient.inputName = "SbSearchInput";
		g_sideClient.inputBox = &SideInputBox;
		g_sideClient.onWheel = &SideWheel;
		panel_shared::AddClient(&g_sideClient);
	}
	D2RL::SharedEvents::UiMessageListener listener{};
	listener.structSize = D2RL::SharedEvents::UiMessageListenerSize;
	listener.callback = &OnUiMessage;
	D2RL::SharedEvents::ListenerHandle handle = 0;
	const bool listening = events->registerUiMessageListener(context, &listener, &handle) == D2RL::SharedEvents::Result::Success;
	HANDLE t = CreateThread(nullptr, 0, TimerThread, nullptr, 0, nullptr);
	if (t == nullptr) {
		std::snprintf(report, reportSize, "host off: no timer thread");
		return false;
	}
	CloseHandle(t);
	std::snprintf(report, reportSize, "host on: %d tabs, %s; button name %s, arrow listener %s, typing %s", g_tabs.Count(), g_geometryFrom,
	              name ? "statbook/StatBook" : "NOT registered", listening ? "on" : "off", panel_shared::TypingOk() ? "on" : "off (bytes differ)");
	return true;
}

void SheetHostStatus(char* out, size_t outSize) noexcept {
	std::snprintf(out, outSize,
	              "bound %d (%s), tab %d of %d, query \"%s\"; %s, sheet open %d; ticks %ld, opens %ld, tab changes %ld, clicks %ld (missed %ld), arrows %ld, typed reads %ld, "
	              "box clicked %d focus %d; names missing %ld, handles %zu (fails %ld), visibility sets %ld (fails %ld), D2R re-shown %ld, texts %ld (fails %ld), stat lines %ld (D2R's fails %ld), "
	              "faults %ld; + buttons %s (sets %ld, fails %ld); all rows %zu; plain panel %s (opens %ld, fails %ld); tabs %s (side %s, panel %s, opens %ld, fails %ld, toggles %ld)",
	              g_bound.load() ? 1 : 0, g_isPad ? "gamepad" : g_legacyNow.load() ? "legacy" : "PC", g_tabNow.load(), g_tabs.Count(), g_query.c_str(), g_calib, g_wasOpen ? 1 : 0, g_ticks.load(), g_opens.load(),
	              g_tabChanges.load(), g_clicks.load(), g_clickMisses.load(), g_arrows.load(), g_typedReads.load(), g_client.boxClicked.load() ? 1 : 0,
	              g_client.boxFocus.load() ? 1 : 0, g_missing.load(), g_handles.size(), g_handleFails.load(), g_visSets.load(), g_visFails.load(), g_reshown.load(), g_client.textsSet.load(), g_client.textFails.load(),
	              g_statLines.load(), g_statLineFails.load(), g_faults.load(), g_plusOn == 1 ? "on" : g_plusOn == 0 ? "off" : "unset",
	              g_plusSets.load(), g_plusFails.load(), RowCount(g_all), g_plain ? (g_plainOpen ? "open" : g_plainPadSheet ? "closed (gamepad sheet: D2R's own)" : "closed") : "no", g_plainOpens.load(),
	              g_plainFails.load(), g_sideWanted.load() ? "side" : "top", g_sideOn.load() ? "showing" : "off", !g_sideReady ? "none" : g_sideOpen ? "open" : "closed",
	              g_sideOpens.load(), g_sideFails.load(), g_toggles.load());
}

void SheetHostSetSide(bool side) noexcept {
	g_sideWanted.store(side);
}

auto SheetHostSide() noexcept -> bool {
	return g_sideWanted.load();
}

auto SheetHostSideReady() noexcept -> bool {
	return g_sideReady;
}

auto SheetHostBound() noexcept -> bool {
	return g_bound.load();
}

void SheetHostSelect(int tab) noexcept {
	g_wantTab.store(tab);
}

void SheetHostStep(int by) noexcept {
	g_stepBy.fetch_add(by);
}

void SheetHostFind(const char* text) noexcept {
	const std::lock_guard<std::mutex> lock(g_requests);
	g_findText = text != nullptr ? text : "";
	g_findSet.store(true);
}

void SheetHostHold(const char* name, int on) noexcept {
	const std::lock_guard<std::mutex> lock(g_requests);
	g_holdQueue.emplace_back(name != nullptr ? name : "", on);
}

auto SheetHostTab() noexcept -> int {
	return g_tabNow.load();
}

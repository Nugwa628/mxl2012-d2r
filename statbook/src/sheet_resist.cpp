// Magic and Physical Resistance on D2R's character sheet (part sheetres; rules in sheet_resist_logic.h; docs/hd-ui.md "Magic and
// Physical Resistance on the character sheet").
//
// D2R's sheet (CharacterStatsPanel) fills only the widgets it knows by name (FireText, ColdText, ...); a layout cannot bind a text box
// to a stat. The mod's sheet layouts (PC HD, legacy, gamepad; tools/sheet_resists.py) add a literal title and three value boxes per row
// (one per colour: white, gold at the cap, red below 0). A timer thread queues a UI-thread tick every 100 ms; the tick finds the
// sheet by its layout name, reads stats 36 / 37 / 38 of the client's own player through GetStat (the client's copy, as the sheet's
// own rows read theirs) and sets the boxes with D2R's text setter (panel_shared::SetLine). A sheet without the boxes (D2R's own
// layout) is counted and left alone. Nothing of D2R's code is patched.
#include "sheet_resist.h"

#include "panel_shared.h"
#include "sheet_resist_logic.h"

#include <D2RLPlugin/threads.h>

#include <windows.h>

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <string>

namespace {

using namespace sheet_resist;

// game functions (image 0x6ab3782c; the plugin's image check guards all of them; the same as devmenu.cpp)
constexpr uint64_t RvaLocalId = 0x8b2d0;       // () -> the client's own player id
constexpr uint64_t RvaClientPlayer = 0x9a480;  // (id) -> the client's player unit
constexpr uint64_t RvaGetStat = 0x2f5020;      // (unit, stat, layer)
constexpr DWORD TickMs = 100;

using LocalIdFn = uint32_t (*)();
using ClientPlayerFn = void* (*)(uint32_t);
using GetStatFn = int32_t (*)(void*, int32_t, int32_t);

const D2RL::PluginContext* g_context = nullptr;
const D2RL::ThreadService* g_threads = nullptr;
uint64_t g_base = 0;
std::atomic<bool> g_tickQueued{false};
panel_shared::Client g_sheet;  // only for NativePanel / SetLine (not added as a client: no buttons, no text input)
std::atomic<long> g_ticks{0}, g_shown{0}, g_noRows{0}, g_faults{0};
std::atomic<int> g_lastMagic{0}, g_lastPhysical{0}, g_lastRawMagic{0}, g_lastRawMax{0}, g_lastRawPhysical{0};

template <class F>
auto Fn(uint64_t rva) noexcept -> F {
	return reinterpret_cast<F>(g_base + rva);
}

struct Shown {
	std::string normal, capped, negative;
};
Shown g_magicShown, g_physicalShown;

void SetRow(void* panel, const Names& n, const Row& r, Shown& shown, bool percent) {
	char value[16];
	Text(r, value, sizeof(value), percent);
	const char* box = BoxFor(n, r.tone);
	panel_shared::SetLine(g_sheet, panel, n.normal, shown.normal, box == n.normal ? value : "", true);
	panel_shared::SetLine(g_sheet, panel, n.capped, shown.capped, box == n.capped ? value : "", true);
	panel_shared::SetLine(g_sheet, panel, n.negative, shown.negative, box == n.negative ? value : "", true);
}

void TickInner() {
	g_ticks.fetch_add(1, std::memory_order_relaxed);
	void* player = Fn<ClientPlayerFn>(RvaClientPlayer)(Fn<LocalIdFn>(RvaLocalId)());
	if (player == nullptr) {
		return;
	}
	void* panel = panel_shared::NativePanel(g_sheet);
	if (panel == nullptr) {
		return;
	}
	if (panel_shared::NativeChild(panel, MagicNames.normal) == nullptr) {
		g_noRows.fetch_add(1, std::memory_order_relaxed);  // D2R's own sheet layout: nothing to fill
		return;
	}
	const auto stat = Fn<GetStatFn>(RvaGetStat);
	const int rawPhysical = stat(player, StatDamageResist, 0);
	const int rawMagic = stat(player, StatMagicResist, 0);
	const int rawMax = stat(player, StatMaxMagicResist, 0);
	const Row magic = Magic(rawMagic, rawMax);
	const Row physical = Physical(rawPhysical);
	const bool percent = panel_shared::NativeChild(panel, LegacyMarker) == nullptr;  // the legacy sheet: "50", as its own rows
	SetRow(panel, MagicNames, magic, g_magicShown, percent);
	SetRow(panel, PhysicalNames, physical, g_physicalShown, percent);
	g_lastMagic.store(magic.value);
	g_lastPhysical.store(physical.value);
	g_lastRawMagic.store(rawMagic);
	g_lastRawMax.store(rawMax);
	g_lastRawPhysical.store(rawPhysical);
	g_shown.fetch_add(1, std::memory_order_relaxed);
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

}  // namespace

auto InstallSheetResist(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	g_context = context;
	g_base = context->exeBase;
	if (context->QueryService(&g_threads) != D2RL::ServiceQueryResult::Success || !D2RL::HasThreadServiceField(g_threads, D2RL::ThreadServiceRequiredSize) ||
	    !panel_shared::Init(context)) {
		std::snprintf(report, reportSize, "sheetres off: a loader service is missing");
		return false;
	}
	g_sheet.panelName = PanelName;
	HANDLE t = CreateThread(nullptr, 0, TimerThread, nullptr, 0, nullptr);
	if (t == nullptr) {
		std::snprintf(report, reportSize, "sheetres off: no timer thread");
		return false;
	}
	CloseHandle(t);
	std::snprintf(report, reportSize, "sheetres on: the character sheet's Magic / Physical Resistance rows (stats %d / %d, max %d; caps %d / 75 + max, at most %d)",
	              StatMagicResist, StatDamageResist, StatMaxMagicResist, PhysicalCeiling, HardCeiling);
	return true;
}

void SheetResistStatus(char* out, size_t outSize) noexcept {
	std::snprintf(out, outSize, "ticks %ld, sheets filled %ld, sheets without the rows %ld, texts %ld, text fails %ld, faults %ld; last magic %d%% (stat %d, max %d), "
	              "physical %d%% (stat %d)",
	              g_ticks.load(), g_shown.load(), g_noRows.load(), g_sheet.textsSet.load(), g_sheet.textFails.load(), g_faults.load(), g_lastMagic.load(),
	              g_lastRawMagic.load(), g_lastRawMax.load(), g_lastPhysical.load(), g_lastRawPhysical.load());
}

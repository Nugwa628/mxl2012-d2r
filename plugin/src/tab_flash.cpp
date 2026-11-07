// The stash tab that flashes after a Ctrl-click deposit is the tab the item went to, MEDIAN and ORBS too (docs/bugs.md #550;
// off word tabflash).
//
// tab_flash_logic.h has D2R's flash: it knows the five tabs and takes the tab from the page kind of the item's slot, so the
// MEDIAN and ORBS items (slots of the Runes page, as medtab builds them) flashed RUNES. The part hooks the kind lookup 0x15ef70
// (kind 4 / 5 for those codes while medtab's tabs are live), maps kinds 1-5 to tabs 2-6 in the flash, gives its "none" value
// and highlight loop 7 tabs, and moves the flash's shown-tab test into the hook of 0x23bb50 (the real tab, not the getter
// medtab caps at Runes). With D2R's layout or medtab's off word nothing changes: the kinds stay 1-3 and the real tab is 0-4.
#include "tab_flash.h"

#include "median_tabs.h"
#include "tab_flash_logic.h"

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

using namespace tab_flash;

using KindFn = uint8_t (*)(uint32_t classId) noexcept;
using FlashFn = void (*)(uint32_t kind) noexcept;
using PanelFn = void* (*)(uint32_t id) noexcept;
using IdFn = uint32_t (*)() noexcept;
using UnitFn = void* (*)(uint32_t id) noexcept;
using FlagFn = uint8_t (*)(void* unit) noexcept;
using RecordFn = const uint8_t* (*)(uint32_t dataFlag, int32_t classId) noexcept;

constexpr uint64_t LocalPlayerIdRva = 0x8b2d0;  // () -> the local player's unit id
constexpr uint64_t ClientUnitRva = 0x9a480;     // (id) -> the client's player unit (0x15fa54 reads it the same way)
constexpr uint64_t UnitDataFlagRva = 0x34a0e0;  // (unit) -> data-table flag byte
constexpr uint64_t ItemRecordRva = 0x314110;    // (dataFlag, class id) -> items record
constexpr size_t ItemCode = 0x80;

KindFn g_kind = nullptr;
FlashFn g_flash = nullptr;
PanelFn g_panel = nullptr;
uint64_t g_base = 0;
std::atomic<uint32_t> g_flashes{0}, g_shown{0}, g_median{0}, g_orbs{0};
std::atomic<int> g_lastTab{-1};

auto CodeOf(uint32_t classId) noexcept -> uint32_t {
	void* player = reinterpret_cast<UnitFn>(g_base + ClientUnitRva)(reinterpret_cast<IdFn>(g_base + LocalPlayerIdRva)());
	if (player == nullptr) {
		return 0;
	}
	const uint8_t flag = reinterpret_cast<FlagFn>(g_base + UnitDataFlagRva)(player);
	const uint8_t* rec = reinterpret_cast<RecordFn>(g_base + ItemRecordRva)(flag, static_cast<int32_t>(classId));
	uint32_t code = 0;
	if (rec != nullptr) {
		std::memcpy(&code, rec + ItemCode, sizeof(code));
	}
	return code;
}

uint8_t KindHook(uint32_t classId) noexcept {
	const uint8_t d2r = g_kind(classId);
	if (d2r != KindRunes || !MedianTabsLive()) {
		return d2r;
	}
	const uint8_t k = Kind(d2r, CodeOf(classId), true);
	if (k == KindMedian) {
		g_median.fetch_add(1);
	} else if (k == KindOrbs) {
		g_orbs.fetch_add(1);
	}
	return k;
}

void FlashHook(uint32_t kind) noexcept {
	void* panel = g_panel(BankPanelId);
	const int real = panel != nullptr ? MedianTabsRealTab(panel) : -1;
	if (!Flash(kind & 0xff, real)) {
		if (TabOfKind(kind & 0xff) >= 0) {
			g_shown.fetch_add(1);
		}
		return;
	}
	g_lastTab.store(TabOfKind(kind & 0xff));
	g_flashes.fetch_add(1);
	g_flash(kind);
}

}  // namespace

auto InstallTabFlash(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	g_base = context->exeBase;
	const auto* image = reinterpret_cast<const uint8_t*>(g_base);
	bool same = std::memcmp(image + KindRva, KindEntry, sizeof(KindEntry)) == 0 && std::memcmp(image + FlashRva, FlashEntry, sizeof(FlashEntry)) == 0 &&
	            std::memcmp(image + SwitchRva, Switch, sizeof(Switch)) == 0 && std::memcmp(image + ShownTestRva, ShownTest, sizeof(ShownTest)) == 0;
	for (const Imm& s : NoFlashSites) {
		same = same && std::memcmp(image + s.rva, s.code, s.size) == 0;
	}
	if (!same) {
		std::snprintf(report, reportSize, "tabflash off: bytes differ at 0x15ef70 / 0x23bb50 / 0x23bbb0 / 0x23bbd2 / the flash's tab count, left as D2R");
		return false;
	}
	g_panel = reinterpret_cast<PanelFn>(g_base + PanelByIdRva);
	// the flash hook first (it tests the real tab as D2R tests its own), then the 7-tab flash, then the kinds that use tabs 5 / 6
	bool ok = context->InstallInlineHook(FlashRva, FlashEntry, sizeof(FlashEntry), reinterpret_cast<void*>(&FlashHook), reinterpret_cast<void**>(&g_flash));
	for (const Imm& s : NoFlashSites) {
		uint8_t patched[8];
		std::memcpy(patched, s.code, s.size);
		patched[s.size - 1] = NoFlashNew;
		ok = ok && context->PatchBytes(s.rva, s.code, s.size, patched, s.size);
	}
	uint8_t nops[sizeof(ShownTest)];
	std::memset(nops, 0x90, sizeof(nops));
	ok = ok && context->PatchBytes(SwitchRva, Switch, sizeof(Switch), SwitchNew, sizeof(SwitchNew)) &&
	     context->PatchBytes(ShownTestRva, ShownTest, sizeof(ShownTest), nops, sizeof(nops)) &&
	     context->InstallInlineHook(KindRva, KindEntry, sizeof(KindEntry), reinterpret_cast<void*>(&KindHook), reinterpret_cast<void**>(&g_kind));
	std::snprintf(report, reportSize, "tabflash %s: a Ctrl-click deposit flashes the item's own tab, MEDIAN / ORBS too (kind 0x15ef70, flash 0x23bb50, "
	              "7 tabs)", ok ? "on" : "FAILED");
	return ok;
}

void TabFlashStatus(char* out, size_t outSize) noexcept {
	std::snprintf(out, outSize, "flashes %u (last tab %d), on the shown tab %u; MEDIAN kinds %u, ORBS kinds %u", g_flashes.load(), g_lastTab.load(),
	              g_shown.load(), g_median.load(), g_orbs.load());
}

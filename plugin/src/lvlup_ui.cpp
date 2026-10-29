// The classic HUD's level-up + buttons (docs/bugs.md #488, docs/plugin-plan.md section 24; off word lvlupui).
//
// In legacy graphics a level-up left the StatUp / SkillUp buttons grey and their clicks dead until G was pressed twice: D2R
// updates only enabled widgets, and a LevelUpButtonWidget disables itself when there are no points, so in the classic HUD
// nothing ever ran its Update again (lvlup_ui_logic.h). LevelUpButtonWidget's Draw slot (vtable 0x1fd9ef8, only this class
// uses the vtable) is replaced by a wrapper: in legacy graphics a disabled button runs its own Update (0x14d1090) before it is
// drawn, which is what an enabled button gets from D2R every frame. HD and enabled buttons go to D2R's Draw as they are.
#include "lvlup_ui.h"

#include "lvlup_ui_logic.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

using WidgetFn = void (*)(void*);
using HdModeFn = bool (*)();

WidgetFn g_draw = nullptr;
WidgetFn g_update = nullptr;
HdModeFn g_hdMode = nullptr;
volatile LONG g_updates = 0;
volatile LONG g_draws = 0;

void DrawHook(void* widget) {
	InterlockedIncrement(&g_draws);
	if (widget != nullptr && lvlup_ui::NeedsUpdate(g_hdMode(), static_cast<const uint8_t*>(widget)[lvlup_ui::DisabledOffset])) {
		InterlockedIncrement(&g_updates);
		g_update(widget);
	}
	g_draw(widget);
}

}  // namespace

auto InstallLevelUpUi(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	using namespace lvlup_ui;
	const uint64_t base = context->exeBase;
	const auto* b = reinterpret_cast<const uint8_t*>(base);
	const uint64_t update = *reinterpret_cast<const uint64_t*>(base + UpdateSlotRva);
	const uint64_t draw = *reinterpret_cast<const uint64_t*>(base + DrawSlotRva);
	const bool same = update == base + UpdateRva && draw == base + DrawRva &&
	                  std::memcmp(b + UpdateRva, UpdateEntry, sizeof(UpdateEntry)) == 0 &&
	                  std::memcmp(b + DrawRva, DrawEntry, sizeof(DrawEntry)) == 0 &&
	                  std::memcmp(b + DisableRva + DisableStoreAt, DisableStore, sizeof(DisableStore)) == 0 &&
	                  std::memcmp(b + HdModeRva, HdModeCode, sizeof(HdModeCode)) == 0;
	if (!same) {
		std::snprintf(report, reportSize, "lvlupui off: bytes differ at 0x1fd9ef0 / 0x14d1090 / 0x14d01a0 / 0x86eec9 / 0x846210, left as D2R");
		return false;
	}
	g_update = reinterpret_cast<WidgetFn>(update);
	g_draw = reinterpret_cast<WidgetFn>(draw);
	g_hdMode = reinterpret_cast<HdModeFn>(base + HdModeRva);
	if (!context->PatchWriteU64(DrawSlotRva, &draw, sizeof(draw), reinterpret_cast<uint64_t>(&DrawHook))) {
		std::snprintf(report, reportSize, "lvlupui off: the Draw slot 0x1fd9ef8 write was refused");
		return false;
	}
	std::snprintf(report, reportSize,
	              "lvlupui on: legacy level-up buttons update while grey (LevelUpButtonWidget Draw slot 0x1fd9ef8 -> Update 0x14d1090 first)");
	return true;
}

void LevelUpUiCounts(long* updates, long* draws) noexcept {
	*updates = g_updates;
	*draws = g_draws;
}

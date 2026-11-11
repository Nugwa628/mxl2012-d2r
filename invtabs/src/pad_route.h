#pragma once
// invtabs: the controller (gamepad) tab of the charm inventory. docs/invtabs-pad.md.
//
// D2R's gamepad menu (Start: Quest Log, Character, Inventory, ..., Options; RT / LT or the tab strip switch tabs) gets one entry
// after Inventory, "Charm Inventory": our panel invtabs/Pad<N> on the left (summary area on top, the tab's grid below), D2R's
// player inventory on the right, as with the stash or the Cube. D-pad right from the grid's last column crosses into the
// inventory, left from the inventory's left edge crosses back; A / X / Y / RS on the grid are D2R's own grid controls.
//
// What the core (invtabs.cpp) calls, and when:
//
//   1. invtabs::pad::Register(Context, PanelApi, ResourceApi, Page, options, hooks, &PadHandles)
//        at plugin load, after the custom page is registered (Page) and after its own tab panels; only when the page is
//        ours (not when CharmInv holds it). options: the charm tab's size from invtabs.toml ([tabs.charms] columns / rows,
//        default 10 x 6) and its slot (0: marker 7400, the same area as invtabs/Tab0). hooks.registerSprite: the core's
//        RegisterSprite (HD + lowend) for the panel art; hooks.log: its Log.
//        Ok: the menu shows the tab. RouteTaken: another plugin holds D2RLoader's only controller route (CharmInv); the
//        panel is withdrawn again and the gamepad has no charm tab (keyboard / mouse unaffected).
//   2. invtabs::pad::Unregister(Context, PanelApi, ResourceApi, &PadHandles)
//        at plugin unload, before the core withdraws its own panels and the page.
//
// The core's grid wrappers must treat the Pad grid as tab N's area: it carries the same marker (chronicleFlourishOffset
// {7400 + N, 7400}) but cellCount = the tab's size (not 16 x 16), so D2R's pad navigation stops at the tab's edges. Cell
// (0, 0) of this grid is the area's top-left cell of the page.

#include <D2RLPlugin/api.h>

#include <cstdint>

#include "pad_layout.h"

namespace invtabs::pad {

using LogFn            = void (*)(bool warn, const char* text) noexcept;
using RegisterSpriteFn = bool (*)(const char* name, int width, int height, const std::uint8_t* rgba) noexcept;

struct Options {
	int         cols      = 10;
	int         rows      = 6;
	int         slot      = 0;                          // the core's tab slot: panel invtabs/Pad<slot>, marker 7400 + slot
	const char* labelKey  = "@invtabs:PadRouteLabel";   // the menu tab's label (full reference, D2RLoader LOCALIZATION.md)
	const char* labelText = "Charm Inventory";          // enUS text registered for labelKey; null: the core ships the string
	const char* summary   = nullptr;                    // the summary widgets for the summary area (LayoutJson), or none
};

struct Hooks {
	LogFn            log            = nullptr;
	RegisterSpriteFn registerSprite = nullptr; // null: no art registered (the layout still names BackgroundName)
};

struct Handles {
	D2RL::Panels::RegistrationHandle    panel   = D2RL::Panels::InvalidHandle;
	D2RL::Panels::ControllerRouteHandle route   = D2RL::Panels::InvalidControllerRouteHandle;
	D2RL::Resources::RegistrationHandle layout  = D2RL::Resources::InvalidHandle;
	D2RL::Resources::RegistrationHandle strings = D2RL::Resources::InvalidHandle;
};

enum class Status : std::uint32_t {
	Ok            = 0,
	BadOptions    = 1, // size or slot out of range, or no label key
	NoService     = 2, // panel service without controller routes, or no resource service
	LayoutRefused = 3, // the layout resource was not registered
	PanelRefused  = 4, // registerPanel or bindPlayerPageGrid failed
	RouteTaken    = 5, // registerControllerRoute: Conflict (another plugin's route) or another refusal
};

Status Register(const D2RL::PluginContext* context, const D2RL::PanelService* panels, const D2RL::ResourceService* resources,
                D2RL::Inventory::PageRegistrationHandle page, const Options& options, const Hooks& hooks, Handles* out) noexcept;

void Unregister(const D2RL::PluginContext* context, const D2RL::PanelService* panels, const D2RL::ResourceService* resources, Handles* handles) noexcept;

// The strings file for labelKey / labelText (JSON array, D2RLoader LOCALIZATION.md); exposed for the test.
std::string StringsJson(const char* labelKey, const char* labelText);

} // namespace invtabs::pad

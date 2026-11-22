// The health bar and damage number keys (overlay_keys.cpp, overlay_keys_logic.h; docs/bundled-plugins.md "Keys for the
// health bars and damage numbers"). Off word: overlaykeys.
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Two Controls actions in category "D2R-XL 2012", with no default key: "Enemy Health Bars Mode" (mxl_health_bars_mode)
// cycles the bundled Enemy Health Bars through five modes, "Floating Damage Numbers" (mxl_damage_numbers) turns the bundled
// Floating Damage's numbers on and off. Each plugin applies the setting at once and saves it in its own TOML (our patches:
// Enemy Health Bars 0005, Floating Damage 0006). Each press shows a yellow line in the message log, except while the client
// talks to an NPC. Client side only, no hook. True when on.
auto InstallOverlayKeys(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;

// Test harness (UI thread): the counters, the plugins' state and the last line.
void OverlayKeysStatus(char* out, size_t size) noexcept;
// Test harness (UI thread): what a press of the key does, at once (which: 0 health bars, 1 damage numbers). False when off.
auto OverlayKeysPress(int which) noexcept -> bool;

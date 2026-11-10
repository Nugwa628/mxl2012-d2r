// The in-game developer menu (devmenu.cpp, devmenu_logic.h, docs/dev-menu.md; off word devmenu): Ctrl+F12 opens a native panel with item
// spawning, area travel, a level raise, waypoint unlocks and the advanced quests action. Single player only: it fails closed in any
// joined or TCP-hosted game.
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// `selfPath` is this DLL's path (UTF-8): the catalog file is read from the mod folder relative to it. True when the part is on.
auto InstallDevMenu(const D2RL::PluginContext* context, const char* selfPath, char* report, size_t reportSize) noexcept -> bool;

// One line of counters and state for the `mxl` console line and the harness.
void DevMenuStatus(char* out, size_t size) noexcept;

// The socket read-back of spawned items (harness line devmenu sockets ...): failures and the last item's native flag word.
void DevMenuSockets(char* out, size_t size) noexcept;

// Test harness: presses a button by name ("tab1", "row0", "raise", ...), sets the input box text, or opens and closes the panel.
// Returns false when the part is off. `verb` is one of open, close, press, input.
auto DevMenuHarness(const char* verb, const char* argument) noexcept -> bool;

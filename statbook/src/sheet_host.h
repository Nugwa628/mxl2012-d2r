// The Stat Book's host on D2R's character sheet (sheet_host.cpp; widget contract: docs/statbook-layout.md).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>
#include <cstdint>

#include "book_logic.h"

struct SheetHostServices {
	void* (*player)() noexcept = nullptr;                                       // the client's own player, null outside a game
	int32_t (*value)(void* player, uint16_t id, bool classParam) noexcept = nullptr;  // a stat as the sheet reads it (and Chance to Block)
	bool (*padTriggers)() noexcept = nullptr;  // the tab buttons now: LT / RT, else LB / RB (Controller QOL may load later)
	void (*tabsChanged)(bool side) noexcept = nullptr;  // the book's toggle switched top / side tabs (statbook.toml is written back)
};

// Starts the host: the "StatBook" button name, the UI listener (tab and row clicks, the Advanced Stats arrow), the search box
// client of panel_shared and a 50 ms UI-thread tick. `book` must stay valid. `padTriggers`: the gamepad glyphs LT / RT, else LB / RB
// (until services.padTriggers answers).
auto InstallSheetHost(const D2RL::PluginContext* context, const statbook::Book* book, const char* selfPath, bool padTriggers, SheetHostServices services,
                      char* report, size_t reportSize) noexcept -> bool;
void SheetHostStatus(char* out, size_t outSize) noexcept;
// The served sheet has the Stat Book's widgets (StatBookMarker) and the host fills them.
auto SheetHostBound() noexcept -> bool;
// Queued for the next tick (any thread): a tab, a step through the tabs, the All Stats query (as if typed), one widget's
// visibility held (`on` 0 / 1; -1 lets it go: the console's `statbook vis`, to see what hiding a group does).
void SheetHostSelect(int tab) noexcept;
void SheetHostStep(int by) noexcept;
void SheetHostFind(const char* text) noexcept;
void SheetHostHold(const char* name, int on) noexcept;
auto SheetHostTab() noexcept -> int;
// Top (folder tabs on the sheet) or side tabs (the book as the panel statbook/SbSidePanel beside the sheet; the mod's HD PC sheet
// only: plain D2R and the gamepad sheet keep the top tabs). Takes effect on the next tick, with the sheet open or closed.
void SheetHostSetSide(bool side) noexcept;
auto SheetHostSide() noexcept -> bool;
// The side panel is registered (the mod's sidepanelhd.json was found): the side tabs can be shown.
auto SheetHostSideReady() noexcept -> bool;

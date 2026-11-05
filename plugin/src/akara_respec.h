// Akara's unlimited respec up to level 100 (akara_respec.cpp, akara_respec_logic.h; off word akararespec).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Hooks D2R's respec packet handler (server, 0x4b2530) and Akara's menu opener and builder (client, 0x1141d0 / 0x1147a0): a
// character of level 1-100 gets "Reset Skills and Stats" every time it talks to Akara and the respec every time it asks, and its
// quest bits stay as they were. Above level 100 everything is D2R's. Returns the number of the three hooks installed.
auto InstallAkaraRespec(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int;

// Since load: respecs the part ran, packets left to D2R, Akara menus shown with the line by the part (opener and builder calls),
// Akara menus built while the client had no quest record, and the local player's level at the last Akara menu (-1: none yet).
void AkaraRespecCounts(long* respecs, long* toD2r, long* menus, long* noRecord, long* lastLevel) noexcept;

// Menu hook calls and the menu NPC class the last builder call saw (the global and the unit's own).
void AkaraRespecTrace(char* out, size_t size) noexcept;

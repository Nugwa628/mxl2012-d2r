// Client skill functions of Median XL 2012 that D2R no longer has (client_skills.cpp).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

constexpr int CltDoWallSlot = 113;  // skills.txt cltdofunc of Rock Shock / ParasiteSkill after tools/idmap.py (1.13c: 22)

// Writes the client do slot(s); the report gets one "cltdofunc <slot> <name>" entry each. Returns the number installed.
auto InstallClientSkills(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int;
// Wraps D2R's client curse (cltdofunc 30) and client start 18 in place: a row without a client missile skips them instead of
// asserting (bug #6), and guards D2R's area aura applier against a radius below 1 (bug #31). Returns the number installed (3).
auto InstallClientNoMissile(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int;
// Calls of the two wrappers that skipped D2R's function (no client missile) since load.
auto ClientNoMissileSkips() noexcept -> long;
// Calls of the area aura applier skipped for a radius below 1 (bug #31) since load.
auto AreaAuraSkips() noexcept -> long;
// Calls of CltDoWall since load (the `mxl2012` line and `h state`).
auto ClientWallCalls() noexcept -> long;

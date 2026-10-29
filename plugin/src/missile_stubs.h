// Empty missile function slots (missile_stubs.cpp, docs/plugin-plan.md section 5, item D).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Fills every empty slot of the missile client do and server hit tables (below their bounds) with a function that does
// nothing. Must run after every part that writes a real function into those tables. False when the tables were not as
// expected (nothing written then) or a write failed.
auto InstallMissileStubs(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
// Missile rows that ran into a stub since load (client do, server hit).
void MissileStubHits(long* clientDo, long* serverHit) noexcept;

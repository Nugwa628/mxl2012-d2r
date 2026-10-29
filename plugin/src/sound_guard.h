// Guard of the client's sound record lookups: a sound id outside the loaded sounds.txt is skipped instead of crashing in the
// record lookup 0xd8c70 (docs/crash-audit.md C17; sound_guard.cpp, sound_guard_logic.h). Off word `soundguard`.
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Hooks the unit sound wrapper 0x107dd0 and the five record readers, and registers the sounds table check after each table
// load. True when all six hooks went in.
auto InstallSoundGuard(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;

// "sounds.txt <rows> rows (D2R-XL 2012 <ModSoundRows>), <n> bad sound ids skipped (last id <id> in 0x<rva> from +0x<caller>)"
// for `mxl2012`.
void SoundGuardStatus(char* out, size_t outSize) noexcept;

// Part spiritsound (bug #502): hooks the client play 0x1a0780 so the spirit summons' HD Ancients death sound is not played.
auto InstallSpiritSound(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
// Plays of ancient_death_hd skipped so far.
auto SpiritSoundSkips() noexcept -> long;

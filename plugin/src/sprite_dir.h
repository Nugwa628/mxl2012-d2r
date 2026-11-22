// Sprite-card monsters turn (sprite_dir.cpp, lane hdtools-monster).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Hooks D2R's state transition (0xf61ae0), unit mode call (0x773f30) and unit layer update (0x77a3b0): a card unit's
// state machine (one under sprite_dir_logic.h Marker) plays the clip bound for the unit's facing; every other state
// machine is untouched.
// `verbose` logs each transition and turn of a card unit (a few hundred lines at most). `tickOnly` (a test switch) turns
// card units only after the once-a-frame layer update, as for a card with no other monster in the game. The report gets one entry.
// Returns the number of hooks installed (3, or 0 when the game's functions read differently).
auto InstallSpriteDir(const D2RL::PluginContext* context, bool verbose, bool tickOnly, char* report, size_t reportSize) noexcept -> int;
// Since load: card transitions given a facing's key, card transitions without a known unit, turns applied, turns not
// applied, card units watched now.
void SpriteDirCounts(long* keyed, long* unkeyed, long* turns, long* skipped, long* watched) noexcept;
// Turns applied after the layer update and after a monster's mode call.
void SpriteDirTurns(long* afterLayer, long* afterMode) noexcept;

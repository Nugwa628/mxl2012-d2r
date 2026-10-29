// Pet-warp spread (pet_spread.cpp, bug #493).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Hooks D2R's two ways of bringing pets to their owner (the owner's move: 0x500a40 / 0x501df0; the pet warp: 0x596d40): a totem
// (pettype `totemic`) left on its owner's sub-tile is moved to a free spot of a ring round the owner (pet_spread_logic.h). The report gets one entry. Returns
// the number of the two installed.
auto InstallPetSpread(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int;
// Since load: owner moves that set pets on the owner, single pet warps, pets of either left on the owner's spot, the totems among
// them spread, the other pets left to D2R; the pet class of the last stacked pet (-1 none).
void PetSpreadCounts(long* gathers, long* warps, long* stacked, long* spread, long* kept, long* lastClass) noexcept;

// The Barbarian spirits' owner warp (spirit_warp.cpp, bug #534).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Adds a server-frame check (server_frame.cpp, 0x406550): once a second a live Guardian / Defender / Protector Spirit farther than
// 20 sub-tiles from its player owner is warped to it by D2R's pet warp, unless it is fighting within 40 (spirit_warp_logic.h).
// Hooks the think of AIs Vampire (0x5b7590) and PinHead (0x5b2b10) to tell whether a spirit is fighting. The report gets one
// entry. Returns the number of the three hooks on.
auto InstallSpiritWarp(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int;
// Since load: spirit checks, those farther than 20, those left fighting (within 40), warps done, warps that did
// not move the spirit; sub-tiles from the owner before and after the last warp and the class of the last spirit warped (-1 none).
void SpiritWarpCounts(long* checks, long* beyond, long* held, long* warps, long* failed, long* lastFrom, long* lastTo, long* lastClass) noexcept;
// Since load: think calls of a spirit and those that saw it fighting; the last check's sub-tiles from the owner and verdict
// (0 stay, 1 left fighting, 2 warp; -1 none).
void SpiritWarpLast(long* thinks, long* fightNotes, long* checkDist, long* checkVerdict) noexcept;

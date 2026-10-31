// The Ancient Tunnels' void in HD (void_floor.cpp, void_floor_logic.h; lane tunnelfloor). Off word: void65 (on by default).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Makes D2R's ground-plane loop skip level 65 as well as 74 (0x6b4b80 -> the pad 0x6b4a22 -> a stub). The report gets one
// entry. Returns true when the patch went in; on any byte difference nothing is written.
auto InstallVoidFloor(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;

// The hover text of the RotW stash's advanced slots (stash_tip.cpp, bug #551, lane orbtab).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Takes over the item tooltip builder's thunk slot (0x3e2af58) with a pass-through that clears the stash slot's short flag
// (its call only, return address 0x2ce71b). The report gets one entry. On any byte difference nothing is written.
auto InstallStashTip(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
// Stash slot tooltips built, other callers passed through and the last slot call's short flag as D2R passed it.
void StashTipStatus(char* out, size_t outSize) noexcept;

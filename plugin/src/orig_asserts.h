// Guards of D2R asserts that 1.14d does not have (orig_asserts.cpp, bugs #74 #181, lane fixes4).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Patches assert block `index` of orig_asserts_logic.h (Blocks[index], off word Blocks[index].word) into the jump D2R takes
// after it. The report gets one entry. Returns 1 when the block was patched, else 0.
auto InstallOrigAssertGuard(const D2RL::PluginContext* context, size_t index, char* report, size_t reportSize) noexcept -> int;

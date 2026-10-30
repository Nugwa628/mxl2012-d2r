// The save format check and the cancelled-save watch (save_mode.cpp, bug #512). Off word `savemode`.
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Checks the mod's d2rloader.toml for D2RLoader's extended save format (puts it back and says so on screen when it is not
// there) and starts the thread that shows a red line for each save D2RLoader cancels. No game address: runs on any build.
// `selfPath` is this DLL, `gameDir` the folder of the game exe. True when the watch thread runs.
auto InstallSaveMode(const D2RL::PluginContext* context, const char* selfPath, const char* gameDir, char* report, size_t reportSize) noexcept
    -> bool;
// Cancelled saves seen since load.
auto SaveModeFailures() noexcept -> int;
// Ends the watch thread (plugin unload).
void StopSaveMode() noexcept;

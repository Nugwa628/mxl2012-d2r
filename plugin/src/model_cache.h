// The larger HD model cache (model_cache.cpp, model_cache_logic.h; lane hdscene2). Off word: modelcache (on by default).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Starts D2R's ModelAsset cache at 8250 entries instead of 2750 (the asset manager's constructor, 0xdfb5b9 and 0xdfb61d). The
// report gets one entry. Returns true when the patch went in; on any byte difference nothing is written.
auto InstallModelCache(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;

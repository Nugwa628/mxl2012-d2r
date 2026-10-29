// Wrong game build (build_guard.cpp, decision in build_guard_logic.h).
#pragma once

#include <D2RLPlugin/api.h>

// Draws `text` at the top of the screen for the whole session; false when D2RLoader has no overlay service.
auto ShowWrongBuildNotice(const D2RL::PluginContext* context, const char* text) noexcept -> bool;
// The same line for any other notice (the environment warning, docs/bugs.md #53); a later call replaces the text.
auto ShowNotice(const D2RL::PluginContext* context, const char* text) noexcept -> bool;
// Registers the notice line's draw callback with no text yet. Called at plugin load: a registration from the later worker thread
// fails, so a notice found there (the sounds table, docs/bugs.md #46) only swaps the text.
auto RegisterNotice(const D2RL::PluginContext* context) noexcept -> bool;
// True while a notice is drawn (a later, lesser one leaves it).
auto NoticeShown() noexcept -> bool;

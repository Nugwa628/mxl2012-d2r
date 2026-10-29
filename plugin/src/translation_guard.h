// Guard for a crash inside D2R's own UnitTranslationLayer event handler (docs/crash-audit.md C14; translation_guard.cpp,
// translation_guard_logic.h). Off word `transguard`.
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Hooks the handler of event type 0x10 of the client's unit translation layer (0x775fc0) and skips an event whose payload is not
// readable memory.
auto InstallTranslationGuard(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;

// Events seen by the hook and events skipped so far (`mxl2012`).
void TranslationGuardStats(unsigned* seen, unsigned* skipped) noexcept;

// Calls the hook with an event whose payload word is 0x80000003F0 (the value of a known crash report) and says whether it
// was skipped (for a harness verb; D2R's handler is not called).
auto TranslationGuardProbe() noexcept -> bool;

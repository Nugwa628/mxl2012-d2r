#pragma once
#include <D2RLPlugin/api.h>
// Best-effort synchronous pre-menu cleanup. A skipped pair is never offered as
// converted: the loader retains its own per-character integrity/provider
// checks.
auto RetireStashPage(const D2RL::PluginContext *, const char *selfPath) noexcept
    -> bool;
void RetireStashFolder(const D2RL::PluginContext *,
                       const wchar_t *folder) noexcept;

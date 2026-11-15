// Stash tabs that need Reign of the Warlock stay closed on an account without it (rotw_warn.cpp, bug #590).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Part rotwwarn: finds D2R's RotW entitlement check and the message log's chat handler by signature. The report gets one entry.
// False when the entitlement check is not found (then nothing is ever blocked).
auto InstallRotwWarn(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
// D2R's answer: does this account own Reign of the Warlock (true when the check was not found).
auto RotwWarnOwned() noexcept -> bool;
// The stash is about to show tab `to` (0 Personal ... 6 ORBS): true when it needs RotW and the account does not own it. Then the
// warning line went to the message log (at most one every 2 s) and the caller keeps the tab closed. UI thread.
auto RotwWarnBlocks(int to) noexcept -> bool;
// Items stay out of the RotW pages: the part runs, its gate is on and the account does not own RotW (the dev switch included).
// The part's own hooks refuse Ctrl-click and gamepad deposits then; the inventory's Send to stash button asks it (bug #591).
auto RotwWarnStoreBlocked() noexcept -> bool;
// UI thread: the banner "Send to stash needs Reign of the Warlock." (no message log line: send_stash writes its own).
void RotwWarnSendRefused() noexcept;
void RotwWarnStatus(char* out, size_t outSize) noexcept;

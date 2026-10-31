// The RotW stash pages in classic graphics (rotw_stash.cpp, bug #516, lane rotwgate).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Part rotwstash: the stash's init asks the plugin instead of the HD check whether to wire its five pages, and the classic
// item picture skips an item without a draw record (rotw_stash_logic.h). The report gets one entry. Returns true when both
// were installed; on any byte difference nothing is written.
auto InstallRotwStash(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;

struct RotwStashCounts {
	long inits;        // stash inits that asked (any graphics)
	long classicWired; // of them: classic, pages wired
	long classicLeft;  // of them: classic, left as D2R (HD only)
	long skipped;      // item pictures skipped (no draw record)
	int gameType;      // client game byte +0x5c now (-1: no game)
	bool hd;           // graphics now
	const char* mode;
};
void RotwStashState(RotwStashCounts* out) noexcept;

// "Send storable/stackable items to stash" (send_stash.cpp, send_stash_logic.h; lane sendstash). Off word: sendstash.
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// The inventory panel's button (tools/send_stash.py): sends every backpack item that has a slot on a Reign of the Warlock stash
// page into that slot with D2R's own deposit packet, stash open or closed, anywhere; prints one summary line. True when on.
auto InstallSendStash(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;

// Counters since load and the button shown last ("show=button ... sent=14 full=3 ...").
void SendStashStatus(char* out, size_t size) noexcept;
// The last summary line ("" before the first run).
auto SendStashLastLine() noexcept -> const char*;
// Test harness: what a click of the button does (false: the part is off or a run is going).
auto SendStashPress() noexcept -> bool;

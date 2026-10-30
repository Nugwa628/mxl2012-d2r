// Baal's laugh in the chat at most once every 30 s (vo_chat.cpp, bug #508). Off word `vochat`.
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Hooks D2R's voice subtitle 0x1a0da0: the "Baal says: ..." chat line of the voice file baallaugh1 is left out when the last one
// was printed less than 30 s ago; the sound itself is not touched. True when the hook went in.
auto InstallVoChat(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
// Since load: Baal laugh lines printed and left out.
void VoChatCounts(long* printed, long* dropped) noexcept;

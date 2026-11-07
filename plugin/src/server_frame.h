// The per-game server frame hook (server_frame.cpp), shared by the parts that need it: D2RLoader takes one hook per address.
#pragma once

#include <D2RLPlugin/api.h>

namespace d2r {
struct Game;
}

using ServerFrameCallback = void (*)(d2r::Game* game) noexcept;

// Hooks `0x406550(Game*)` (docs/d2r-addresses.md "The server game frame") the first time; later calls only answer whether the
// hook is on. True when it is.
auto InstallServerFrame(const D2RL::PluginContext* context) noexcept -> bool;
// Runs `callback` after every server frame of every game, on the game thread, in the order added. At most 8; false when full.
auto AddServerFrameCallback(ServerFrameCallback callback) noexcept -> bool;

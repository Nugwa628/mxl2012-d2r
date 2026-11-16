// Move Only's start function (move_only.cpp; unit test plugin/tests/move_only_test.cpp). No Windows headers, no game calls.
//
// skills.txt srvstfunc picks a function of D2R's server start table (0x238e710, 91 slots; D2R fills 0-70) that runs when a
// skill is cast, before its do function; returning 0 stops the cast: no mana, no do function, no hit. Move Only (the mod's
// own skill, tools/move_only.py) names slot 71, and the function there refuses every cast. A click on the ground is a walk
// already (the row is TargetableOnly); a click on a monster walks into reach and then stops here, so the character never
// attacks. Ported from our Sigma port's start functions, where Move Only's start never starts either.
#pragma once

#include <cstdint>

namespace move_only {

inline constexpr int StartSlot = 71;   // skills.txt srvstfunc of Move Only (tools/move_only.py START_SLOT)
inline constexpr int StartSlots = 91;  // entries in D2R's server start table

// Whether `slot` can take the function: inside the table and still empty (a non-zero entry is a function of D2R's own).
constexpr auto SlotFree(int slot, uint64_t entry) noexcept -> bool {
	return slot > 0 && slot < StartSlots && entry == 0;
}

// The start's answer: never start (0 stops the cast).
constexpr auto Start() noexcept -> int64_t {
	return 0;
}

}  // namespace move_only

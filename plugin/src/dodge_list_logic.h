// Pure part of the dodge / avoid / evade list guard (dodge_list.cpp; unit test plugin/tests/dodge_list_test.cpp).
// No Windows headers, no game calls.
#pragma once

#include <cstdint>

namespace dodge_list {

// D2R's damage code (D2Game SUnitDmg.cpp, function 0x44ad9a) picks state 65 / 66 / 68 (dodge / avoid / evade) from the hit's
// result flags and asks for the defender's stat list of that state (0x2f5940 at 0x44b148) to read the passive skill in it (stat
// 350): in vanilla only the Amazon's Dodge / Avoid / Evade passives give the chance, through those states. Median XL 2012 gives
// passive_dodge / passive_avoid / passive_evade (338-340) as plain stats (items, states such as Black Mass or Ring of Light),
// so the list is missing: D2R logs "BC_ASSERT: hList" (call 0x449c40 at 0x44b15b) and then leaves the function at 0x44b27d (bug
// #53). The guard turns the assert's first instruction into a jump to 0x44b27d: the same path without the log line.
inline constexpr uint64_t RvaAssertBlock = 0x44b152;  // lea rcx,[rsp+0x40] / mov [rsp+0x40],al / call 0x449c40 / ...
inline constexpr uint64_t RvaLeave = 0x44b27d;        // where D2R goes after the assert (function epilogue)
// The block as D2R has it: the 5 bytes the jump replaces (D2RLoader's patch check compares exactly the patched size), then the
// rest up to and with the call to the assert reporter, which the plugin compares itself before writing.
inline constexpr uint8_t Expected[] = {0x48, 0x8d, 0x4c, 0x24, 0x40, 0x88, 0x44, 0x24, 0x40, 0xe8, 0xe0, 0xea, 0xff, 0xff};
inline constexpr uint32_t PatchSize = 5;

// rel32 of a 5-byte jmp at `from` to `to`.
constexpr auto Rel32(uint64_t from, uint64_t to) noexcept -> int32_t {
	return static_cast<int32_t>(static_cast<int64_t>(to) - static_cast<int64_t>(from + 5));
}

// The 5 bytes written at RvaAssertBlock: jmp RvaLeave.
struct Jump {
	uint8_t bytes[5];
};
constexpr auto JumpBytes() noexcept -> Jump {
	const auto rel = static_cast<uint32_t>(Rel32(RvaAssertBlock, RvaLeave));
	return Jump{{0xe9, static_cast<uint8_t>(rel), static_cast<uint8_t>(rel >> 8), static_cast<uint8_t>(rel >> 16), static_cast<uint8_t>(rel >> 24)}};
}

}  // namespace dodge_list

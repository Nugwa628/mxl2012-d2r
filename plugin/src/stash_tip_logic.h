// Pure part of the advanced stash slot tooltip (stash_tip.cpp; unit test plugin/tests/stash_tip_test.cpp). No Windows
// headers, no game calls.
#pragma once

#include <cstddef>
#include <cstdint>

namespace stash_tip {

// D2R's advanced stash slot (AdvancedStashSlotWidget, vtable slot 0x2ce4d0, tooltip part 0x2ce648..0x2ce8fe) builds its hover
// text with the item tooltip builder every item widget calls, through the D2RLoader thunk 0x3e2b826 (jmp [rip-0x8d4], slot
// 0x3e2af58, D2RLoader's BuildItemTooltipWithStatRanges, which calls D2R's builder with the same arguments):
//   (out string, viewer, viewer, item, int [widget+0x5c0], bool 6th, bool 7th, ptr 8th, rect*)
// The backpack's grid (0x2c8b64) passes the 7th as its widget byte +0x633, the belt (0x2290f0) and the other callers 0; the
// stash slot alone hard-codes 1 (0x2ce703: mov [rsp+0x30], r14b with r14d = 1).
inline constexpr uint64_t ThunkRva = 0x3e2b826;
inline constexpr uint8_t Thunk[] = {0xff, 0x25, 0x2c, 0xf7, 0xff, 0xff};
inline constexpr uint64_t SlotRva = ThunkRva + sizeof(Thunk) - 0x8d4;  // 0x3e2af58
inline constexpr uint64_t CallRva = 0x2ce716;
inline constexpr uint64_t ReturnRva = CallRva + 5;  // 0x2ce71b

// Compared (read only) before the slot is touched: 0x2ce6e1..0x2ce71b, the argument set-up and the call (rel32 into the thunk).
inline constexpr uint64_t SiteRva = 0x2ce6e1;
inline constexpr uint8_t Site[] = {
	0x48, 0x8d, 0x4c, 0x24, 0x50, 0x88, 0x5c, 0x24, 0x58, 0x48, 0x89, 0x4c, 0x24, 0x40, 0x4c, 0x8b, 0xce, 0x8b, 0x8f, 0xc0,
	0x05, 0x00, 0x00, 0x4c, 0x8b, 0xc0, 0x48, 0x89, 0x5c, 0x24, 0x38, 0x48, 0x8b, 0xd0, 0x44, 0x88, 0x74, 0x24, 0x30, 0x44,
	0x88, 0x74, 0x24, 0x28, 0x89, 0x4c, 0x24, 0x20, 0x48, 0x8d, 0x4c, 0x24, 0x70, 0xe8, 0x0b, 0xd1, 0xb5, 0x03,
};
inline constexpr size_t SiteSize = sizeof(Site);
inline constexpr size_t CallInSite = CallRva - SiteRva;

// Target of an e8 rel32 at `rva` whose displacement is `disp`.
constexpr auto CallTarget(uint64_t rva, int32_t disp) noexcept -> uint64_t {
	return rva + 5 + static_cast<uint64_t>(static_cast<int64_t>(disp));
}

// The 7th is D2R's "short" flag: 1 builds the name line alone (bug #551, the orbs showed "Mystic Orb" and the move hints only),
// 0 the whole description as the backpack shows it (effect text, stats, requirements). Seen in game (lane orbtab): with the 7th
// set to 0 the slot's text equals the backpack's; clearing the 6th instead adds "Socket info unavailable in item link" and
// leaves the text short, the 5th changes nothing. Only the 7th's low byte is cleared; the 5th / 6th stay as D2R passes them.
struct Args {
	uint64_t fifth, sixth, seventh;
};

constexpr auto Apply(Args a) noexcept -> Args {
	a.seventh &= ~uint64_t{0xff};
	return a;
}

}  // namespace stash_tip

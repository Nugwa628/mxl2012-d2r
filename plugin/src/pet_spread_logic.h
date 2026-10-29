// Pure rule of the pet-warp spread (pet_spread.cpp; unit test plugin/tests/pet_spread_test.cpp). No Windows headers, no game calls.
#pragma once

#include <cstdint>

namespace pet_spread {

// D2R brings warp pets to their owner in two ways, and both can leave a pet on the owner's own sub-tile: the owner's move
// (`0x491ca0` -> `0x500a40`: every pet of a pettype with the warp bit set exactly on the owner's new x / y, e.g. after Bend the
// Shadows or Teleport) and the pet warp (`0x596d40`, D2Game AiUtil.cpp: a random spot near the owner first, then the owner's
// position through the free-spot search, whose mask 0x1c09 has no unit bit). Pets that walk step off at their next move;
// immobile ones (Median's totems: pettype `totemic` has `warp` 1) stay stacked for good (bug #493). A pet within one sub-tile
// of its owner is moved to the first free spot of this list instead (offsets from the owner in sub-tiles): a ring of 8 at 3
// sub-tiles, then rings of 16 at 5 and 7.
struct Offset {
	int8_t dx, dy;
};
inline constexpr Offset Ring[] = {
    {3, 0},  {0, 3},  {-3, 0}, {0, -3}, {3, 3},  {-3, 3}, {-3, -3}, {3, -3},                                    // 8 at 3
    {5, 0},  {0, 5},  {-5, 0}, {0, -5}, {5, 5},  {-5, 5}, {-5, -5}, {5, -5},                                    // 16 at 5
    {5, 2},  {2, 5},  {-2, 5}, {-5, 2}, {-5, -2}, {-2, -5}, {2, -5}, {5, -2},
    {7, 0},  {0, 7},  {-7, 0}, {0, -7}, {7, 7},  {-7, 7}, {-7, -7}, {7, -7},                                    // 16 at 7
    {7, 3},  {3, 7},  {-3, 7}, {-7, 3}, {-7, -3}, {-3, -7}, {3, -7}, {7, -3},
};
inline constexpr int RingSize = static_cast<int>(sizeof(Ring) / sizeof(Ring[0]));

// The collision bits a ring spot must be free of, as D2's collision flags: 0x0001 block walk, 0x0008 block leap, 0x0400 object,
// 0x0800 door, 0x1000 unit related (the warp's own mask 0x1c09), plus 0x0080 player, 0x0100 monster and 0x2000 pet, so a pet
// placed by an earlier warp of the same cast (and the owner) keeps its spot.
inline constexpr int32_t SpotMask = 0x1c09 | 0x0080 | 0x0100 | 0x2000;

// True when the warp left the pet on its owner's spot (within one sub-tile), i.e. the spread should move it.
constexpr auto OnOwner(int32_t petX, int32_t petY, int32_t ownerX, int32_t ownerY) noexcept -> bool {
	const int32_t dx = petX - ownerX, dy = petY - ownerY;
	return dx >= -1 && dx <= 1 && dy >= -1 && dy <= 1;
}

// True when a move to (wantX, wantY) took: the pet stands within one sub-tile of it (the move's free-spot search may shift it).
constexpr auto Landed(int32_t x, int32_t y, int32_t wantX, int32_t wantY) noexcept -> bool {
	return OnOwner(x, y, wantX, wantY);
}

// A spot of the same gather is taken when a pet already placed there stands within 2 sub-tiles (Chebyshev): D2R's collision test
// does not see a pet placed a moment ago (seen in game: four totems 1 sub-tile apart), so the part keeps its own list.
struct Spot {
	int32_t x, y;
};
constexpr auto Taken(int32_t x, int32_t y, const Spot* spots, int count) noexcept -> bool {
	for (int i = 0; i < count; ++i) {
		const int32_t dx = x - spots[i].x, dy = y - spots[i].y;
		if (dx >= -2 && dx <= 2 && dy >= -2 && dy <= 2) {
			return true;
		}
	}
	return false;
}

}  // namespace pet_spread

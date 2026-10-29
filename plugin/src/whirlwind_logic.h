// Whirlwind's hit rate as in 1.13c (whirlwind.cpp; unit test plugin/tests/whirlwind_test.cpp). Bug #281.
// No Windows headers, no game calls.
//
// Median XL 2012 runs 1.13c's Whirlwind function (srvdofunc 76) on four skills: Whirlwind (Barbarian), Spin To Win, Danse
// Macabre, Harvest. D2R 2.4 reworked the hit rate of that function (do 0x568f40): it waits `0x56ac00(unit, weapon)` frames
// between hits, the weapon's attack animation length at D2R's speed
//   frames * 256 / (clamp(stat 68 + 120 * IAS / (120 + IAS), 15, max) * animSpeed / 100)            (10 without a weapon),
// so a spin hits about half as often as before. 1.13c (D2Game 0x6fce1470, D2Common 10564; read from its 1.13
// decompile) takes the same animation length at its own speed, 100 + stat 68 + IAS (stat 93,
// no diminishing returns, no cap), and turns it into a delay through a table:
//   < 12 frames -> a hit every 4, < 15 -> 6, < 18 -> 8, < 20 -> 10, < 23 -> 12, < 26 -> 14, else 16 (no weapon: 10).
// The hook rescales D2R's length to 1.13c's speed and applies the table.
#pragma once

#include <cstdint>

namespace whirlwind {

inline constexpr int32_t SpeedMin = 15;      // D2R's floor (0x34ab50)
inline constexpr int32_t NoWeaponDelay = 10;  // both games: a hit every 10 frames without a weapon

// 1.13c's frames -> delay table.
constexpr auto ClassicDelay(int32_t frames) noexcept -> int32_t {
	return frames < 12 ? 4 : frames < 15 ? 6 : frames < 18 ? 8 : frames < 20 ? 10 : frames < 23 ? 12 : frames < 26 ? 14 : 16;
}

// D2R's animation speed term: stat 68 plus IAS with diminishing returns, clamped to [15, speedMax].
constexpr auto D2RSpeed(int32_t rate, int32_t ias, int32_t speedMax) noexcept -> int32_t {
	const int32_t s = rate + (ias != 0 && ias != -120 ? ias * 120 / (ias + 120) : 0);
	return s < SpeedMin ? SpeedMin : (s > speedMax ? speedMax : s);
}

// 1.13c's: 100 + stat 68 + IAS. 1.13c adds the 100 itself; D2R's units carry a base of 100 in stat 68, so the base is taken
// once either way (to be confirmed on real units by logging the first spins' values).
constexpr auto ClassicSpeed(int32_t rate, int32_t ias) noexcept -> int32_t {
	return (rate >= 100 ? rate : rate + 100) + ias;
}

// The delay a spin waits between hits: D2R's `d2rFrames` (what 0x56ac00 returned) rescaled from D2R's speed to 1.13c's,
// then 1.13c's table. A non-positive classic speed keeps D2R's frame count for the table.
constexpr auto HitDelay(int32_t d2rFrames, int32_t rate, int32_t ias, int32_t speedMax, bool haveWeapon) noexcept -> int32_t {
	if (!haveWeapon) {
		return NoWeaponDelay;
	}
	const int32_t d2rSpeed = D2RSpeed(rate, ias, speedMax);
	const int32_t classic = ClassicSpeed(rate, ias);
	const int32_t frames = classic > 0 ? static_cast<int32_t>(static_cast<int64_t>(d2rFrames) * d2rSpeed / classic) : d2rFrames;
	return ClassicDelay(frames);
}

}  // namespace whirlwind

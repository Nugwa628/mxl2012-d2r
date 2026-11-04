// Pure rule of the Barbarian spirits' owner warp (spirit_warp.cpp; unit test plugin/tests/spirit_warp_test.cpp). No Windows
// headers, no game calls.
#pragma once

#include <cstdint>

namespace spirit_warp {

// Owner ruling (2026-11-04, bug #534): Guardian, Defender and Protector Spirit teleport to their owner when they are more than
// about 20 away. Median gives them hostile AIs (Guardian: Vampire 28, Defender / Protector: PinHead 39) with no owner follow, so
// D2R's pet warp only brings them back from far off and after a fight they stood 32-91 sub-tiles away. The part checks them once a
// second on the server frame and warps them with D2R's own pet warp (0x596d40). The two AIs' think only says whether a spirit is
// fighting: D2R does not run the think of an idle spirit (no target), so the think alone never sees a spirit left behind.
//
// The spirits are told apart by their owner's pet lists: pettype rows 30 / 31 / 32 of the build's pettype.txt (guardianspet,
// defenderspet, protectorspet; D2R's demon and binddemon rows 20-21 shift Median's 28-30 by two, as `totemic` 32 -> 34). Daystar,
// Sinner and every hostile Vampire / PinHead are left alone.
inline constexpr int32_t SpiritPetTypes[] = {30, 31, 32};

// Distances are in sub-tiles (the unit x / y D2R keeps, as the harness's `state` prints them). A spirit farther than WarpBeyond
// from its owner is warped, unless it is fighting and still within HardBeyond: then it keeps fighting there and is warped once
// that fight ends or the owner runs farther off.
inline constexpr int32_t WarpBeyond = 20;
inline constexpr int32_t HardBeyond = 40;

constexpr auto DistanceSq(int32_t ax, int32_t ay, int32_t bx, int32_t by) noexcept -> int64_t {
	const int64_t dx = static_cast<int64_t>(ax) - bx, dy = static_cast<int64_t>(ay) - by;
	return dx * dx + dy * dy;
}

// Fighting: the spirit has a live target (tick +0x10; not in mode DT 0 / DD 12) that is in reach (tick +0x24) or within
// HardBeyond of the owner, so a spirit on its way to a monster near its owner is not warped back before it gets there. A killed
// target stays in the tick as a corpse (seen in game: spirits held next to a dead zombie), so it does not count.
inline constexpr int32_t ModeDeath = 0;
inline constexpr int32_t ModeDead = 12;
constexpr auto Alive(int32_t mode) noexcept -> bool {
	return mode != ModeDeath && mode != ModeDead;
}
constexpr auto Fighting(bool liveTarget, bool targetInReach, int64_t targetOwnerSq) noexcept -> bool {
	return liveTarget && (targetInReach || targetOwnerSq <= static_cast<int64_t>(HardBeyond) * HardBeyond);
}

enum class Verdict { Stay, Held, Warp };
// Stay: within WarpBeyond; Held: farther, but fighting within HardBeyond; Warp: bring it to the owner.
constexpr auto Decide(int64_t distanceSq, bool fighting) noexcept -> Verdict {
	if (distanceSq <= static_cast<int64_t>(WarpBeyond) * WarpBeyond) {
		return Verdict::Stay;
	}
	if (fighting && distanceSq <= static_cast<int64_t>(HardBeyond) * HardBeyond) {
		return Verdict::Held;
	}
	return Verdict::Warp;
}

// The frame check runs once every CheckEveryFrames server frames (25 Hz: once a second).
inline constexpr uint32_t CheckEveryFrames = 25;
constexpr auto FrameDue(uint32_t frame) noexcept -> bool {
	return frame % CheckEveryFrames == 0;
}

// The think notes the last time it saw each spirit fighting; the frame check takes a note younger than FightFreshMs as fighting
// (the AIs think every 15 frames, 0.6 s, at Median's aidel, and an idle spirit's think does not run, so its note goes stale). Up
// to SlotCount spirits are kept by unit id; a new one takes the oldest slot.
inline constexpr uint64_t FightFreshMs = 1500;
inline constexpr int SlotCount = 16;
struct Slot {
	uint32_t unitId;
	uint64_t lastMs;  // 0: free
};
// The think saw the spirit fighting (`fighting`) or not at `nowMs`.
inline void Note(Slot* slots, uint32_t unitId, bool fighting, uint64_t nowMs) noexcept {
	int oldest = 0;
	for (int i = 0; i < SlotCount; ++i) {
		if (slots[i].lastMs != 0 && slots[i].unitId == unitId) {
			slots[i].lastMs = fighting ? (nowMs != 0 ? nowMs : 1) : 0;
			return;
		}
		if (slots[i].lastMs < slots[oldest].lastMs) {
			oldest = i;
		}
	}
	if (fighting) {
		slots[oldest] = {unitId, nowMs != 0 ? nowMs : 1};
	}
}
// True when the spirit's last note says fighting and is younger than FightFreshMs.
inline auto FightingRecently(const Slot* slots, uint32_t unitId, uint64_t nowMs) noexcept -> bool {
	for (int i = 0; i < SlotCount; ++i) {
		if (slots[i].lastMs != 0 && slots[i].unitId == unitId) {
			return nowMs - slots[i].lastMs <= FightFreshMs;
		}
	}
	return false;
}

}  // namespace spirit_warp

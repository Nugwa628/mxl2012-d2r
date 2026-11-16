// Pure part of the aimed Laughing Ghost (lob_aim.cpp; unit test plugin/tests/lob_aim_test.cpp).
// No Windows headers, no game calls.
#pragma once

#include <cstdint>
#include <cstdlib>

namespace lob_aim {

// Median XL 2012's Laughing Ghost (skills.txt `lob` empty) makes laughingghostemerge (Range 12, Vel 24, no CollideType,
// AlwaysExplode): it always flies 12 frames and explodes there, wherever the player clicked. That is 1.13c's behaviour too
// (Median's own skills.bin / missiles.bin). The port's skills row sets `lob` 1 (tools/txt_migrate.py lob_skills), as D2R's
// Fire Trauma and Median's Thunderstone: the server makes the missile with D2R's lob path (flags 0x400 | 0x20), whose
// create (server 0x5371a0, 0x537959) sets the missile's frames to the distance to the target point over its speed, and the
// client's (0x1b7760, 0x1b819e) sets the same and arcs it (0x100). Neither caps that at the missile's Range, so a far click
// would throw the ghost across the screen. The hooks move a target point past the Range back along the line to where
// the missile reaches in Range frames; a click inside it is left as it is.
inline constexpr int32_t Skill = 453;  // skills.txt Laughing Ghost (the port's id, tools/idmap.py)
inline constexpr uint32_t FlagOriginXY = 0x1;     // params x / y are the start (else the origin unit's position)
inline constexpr uint32_t FlagRelTarget = 0x2;    // target x / y are added to the start
inline constexpr uint32_t FlagOwnVelocity = 0x4;  // params +0x38 is the speed (<< 8 unless FlagRawVelocity)
inline constexpr uint32_t FlagRawVelocity = 0x10;
inline constexpr uint32_t FlagAbsTarget = 0x20;   // target x / y as they are
inline constexpr uint32_t FlagLob = 0x400;        // frames from the distance (D2R's lob path)

inline constexpr uint64_t RvaRangeCalc = 0x3b4a90;  // (dataFlag, missile or null, owner, record +0xbc, missile id, level) -> frames
inline constexpr int RecRangeCalc = 0xbc;
inline constexpr int RecVel = 0xc0;     // uint8 Vel
inline constexpr int RecVelLev = 0xc1;  // uint8 VelLev

// MissileParams entry of the server create: PUSH RBP / PUSH RDI / PUSH R14 / LEA RBP,[RSP-0x40] / SUB RSP,0x140
inline constexpr uint64_t RvaServer = 0x5371a0;
inline constexpr uint8_t ServerEntry[] = {0x40, 0x55, 0x57, 0x41, 0x56, 0x48, 0x8d, 0x6c, 0x24, 0xc0, 0x48, 0x81, 0xec, 0x40, 0x01, 0x00, 0x00};
// Client create: MOV [RSP+0x10],EDX / PUSH RBP / PUSH RDI / PUSH R13 / PUSH R15 / LEA RBP,[RSP-0x3f] / SUB RSP,0x88
inline constexpr uint64_t RvaClient = 0x1b7760;
inline constexpr uint8_t ClientEntry[] = {0x89, 0x54, 0x24, 0x10, 0x55, 0x57, 0x41, 0x55, 0x41, 0x57, 0x48, 0x8d, 0x6c, 0x24, 0xc1,
                                          0x48, 0x81, 0xec, 0x88, 0x00, 0x00, 0x00};

// The speed the server create uses (0x537488-0x537540): params +0x38 with flag 4, else (Vel + VelLev * level / 8) << 8;
// then 75 %. The slow-missiles stat check between them is left out (it only changes the speed, not where the point is).
constexpr auto Velocity(uint32_t flags, int32_t own, int32_t vel, int32_t velLev, int32_t level) noexcept -> int32_t {
	int32_t v = 0;
	if ((flags & FlagOwnVelocity) != 0) {
		v = (flags & FlagRawVelocity) != 0 ? own : own << 8;
	} else {
		v = (vel + (velLev * level) / 8) << 8;
	}
	return v * 75 / 100;
}

// D2R's unit-to-point distance (0x325370): the longer axis plus half the shorter.
constexpr auto Distance(int32_t dx, int32_t dy) noexcept -> int32_t {
	const int32_t ax = dx < 0 ? -dx : dx;
	const int32_t ay = dy < 0 ? -dy : dy;
	const int32_t hi = ax > ay ? ax : ay;
	const int32_t lo = ax > ay ? ay : ax;
	return (2 * hi + lo) / 2;
}

// The frames the lob branch gives a missile for a distance (0x53796c-0x5379ab: 0 counts as 1; dist << 16 over v << 4).
constexpr auto Frames(int32_t distance, int32_t velocity) noexcept -> uint32_t {
	const uint32_t d = static_cast<uint32_t>(distance == 0 ? 1 : distance) << 16;
	const uint32_t v = static_cast<uint32_t>(velocity) << 4;
	return v == 0 ? 0 : d / v;
}

// Moves (tx, ty) towards (ox, oy) until the missile's frames are no more than `range`. True when it moved.
inline auto ClampTarget(int32_t ox, int32_t oy, int32_t* tx, int32_t* ty, int32_t velocity, int32_t range) noexcept -> bool {
	if (velocity <= 0 || range <= 0) {
		return false;
	}
	int32_t dx = *tx - ox, dy = *ty - oy;
	const int32_t dist = Distance(dx, dy);
	if (Frames(dist, velocity) <= static_cast<uint32_t>(range)) {
		return false;
	}
	// the farthest distance still at `range` frames, then the same line shortened to it
	const int64_t reach = ((static_cast<int64_t>(range) + 1) * (static_cast<int64_t>(velocity) << 4) - 1) >> 16;
	dx = static_cast<int32_t>(static_cast<int64_t>(dx) * reach / dist);
	dy = static_cast<int32_t>(static_cast<int64_t>(dy) * reach / dist);
	while ((dx != 0 || dy != 0) && Frames(Distance(dx, dy), velocity) > static_cast<uint32_t>(range)) {
		if (std::abs(dx) >= std::abs(dy)) {
			dx += dx > 0 ? -1 : 1;
		} else {
			dy += dy > 0 ? -1 : 1;
		}
	}
	*tx = ox + dx;
	*ty = oy + dy;
	return true;
}

}  // namespace lob_aim

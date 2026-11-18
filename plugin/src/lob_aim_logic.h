// Pure part of the aimed lob skills (lob_aim.cpp; unit test plugin/tests/lob_aim_test.cpp).
// No Windows headers, no game calls.
#pragma once

#include <cstdint>

namespace lob_aim {

// skills.txt `lob` 1 (tools/txt_migrate.py lob_skills) makes these skills' missiles on D2R's lob path: the create (server
// 0x5371a0, 0x537959; client 0x1b7760, 0x1b819e) sets the frames to the distance to the target point over the speed, not the
// missile's Range. The target point is where the game put the cursor in the world, in its own HD or legacy view, so the
// farthest click is the edge of the screen at any resolution. No numeric cap: a fixed radius would cut a wide view short.
inline constexpr int32_t SkillLaughingGhost = 453;  // the port's skill ids (tools/idmap.py)
inline constexpr int32_t SkillRisingDawn = 512;
constexpr auto IsAimedSkill(int32_t skill) noexcept -> bool {
	return skill == SkillLaughingGhost || skill == SkillRisingDawn;
}
inline constexpr uint32_t FlagOriginXY = 0x1;     // params x / y are the start (else the origin unit's position)
inline constexpr uint32_t FlagRelTarget = 0x2;    // target x / y are added to the start
inline constexpr uint32_t FlagOwnVelocity = 0x4;  // params +0x38 is the speed (<< 8 unless FlagRawVelocity)
inline constexpr uint32_t FlagRawVelocity = 0x10;
inline constexpr uint32_t FlagAbsTarget = 0x20;   // target x / y as they are
inline constexpr uint32_t FlagLob = 0x400;        // frames from the distance (D2R's lob path)

inline constexpr int RecVel = 0xc0;     // uint8 Vel
inline constexpr int RecVelLev = 0xc1;  // uint8 VelLev

// The target point in world sub-tiles (relative ones added to the start); false when the params name no point.
constexpr auto ResolvePoint(uint32_t flags, int32_t ox, int32_t oy, int32_t* tx, int32_t* ty) noexcept -> bool {
	if ((flags & FlagRelTarget) != 0) {
		*tx += ox;
		*ty += oy;
		return true;
	}
	return (flags & FlagAbsTarget) != 0;
}

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

}  // namespace lob_aim

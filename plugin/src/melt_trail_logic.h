// Pure part of the state-22 melt trail (melt_trail.cpp; unit test plugin/tests/melt_trail_test.cpp).
// No Windows headers, no game calls.
#pragma once

#include <cstddef>
#include <cstdint>

namespace melt_trail {

// D2R keeps a client and a server function for vanilla state 22 (spiderlay): client 0x221650 (called by the client walk-mode
// step 0xf9aba after its state test 0xf9aca), server 0x578680 (called by the server walk-mode step 0x445d20 after its test
// 0x445d54). Both take the unit's state-22 stat list and read stat 350 / 351 (modifierlist_skill / level) as the skill and
// level, the skill's cltmissilea (record +0x140) / srvmissile (+0x68) as the missile, and make that missile one step (step table) off the
// unit. 1.14d's functions (Game.exe client 0x4e2d40, server 0x5ce4f0, called from the same place: 0x4807c0 / 0x5a8490) read no
// list: they always make missile 143 with the level of the unit's own skill 173. Median XL 2012 keeps its `raptured` state
// (Rapture, NTRAP) on id 22, as 1.13c ran it, and its list names no skill, so D2R's functions leave and the trail 1.13c drew
// behind raptured units (Median's row 143 `spidergoolay`: IceBreakSmallMelt, no damage) is missing (docs/bugs.md #52).
// The hooks run D2R's function unchanged when the list names a skill; otherwise they make 1.14d's missile.
inline constexpr int32_t State = 22;
inline constexpr int32_t Missile = 143;    // missiles.txt spidergoolay (1.13c id; Median's row keeps it, tools/idmap.py)
inline constexpr int32_t Skill = 173;      // skills.txt SpiderLay (id kept); its level on the unit is the missile's level
inline constexpr int32_t Sound = 0x726;    // sounds.txt 1830 spider_web_1, played by both games' client functions
inline constexpr int32_t StatSkill = 350;  // modifierlist_skill: D2R's choice between its own trail and 1.14d's
inline constexpr int32_t StatSeed = 202;   // D2R's trail seed in the state list (no 1.14d counterpart, kept as D2R does it)
inline constexpr uint32_t ClientFlags = 0x25;  // both games
inline constexpr uint32_t ServerFlags = 0x21;  // both games
inline constexpr int32_t Velocity = 3;         // params +0x38 (1.14d +0x28)
inline constexpr int32_t ClientSkill = 0;      // 1.14d's client passes no skill (+0x2c unset); the server passes 173
inline constexpr int32_t ServerSkill = Skill;

inline constexpr uint64_t RvaClient = 0x221650;
inline constexpr uint64_t RvaServer = 0x578680;
// MOV [RSP+0x10],RBX / MOV [RSP+0x18],RSI / MOV [RSP+0x20],RDI
inline constexpr uint8_t ClientEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x10, 0x48, 0x89, 0x74, 0x24, 0x18, 0x48, 0x89, 0x7c, 0x24, 0x20};
// MOV [RSP+0x18],RBX / PUSH RBP / PUSH RSI / PUSH RDI / PUSH R12 / PUSH R13 / PUSH R14 / PUSH R15
inline constexpr uint8_t ServerEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x18, 0x55, 0x56, 0x57, 0x41, 0x54, 0x41, 0x55, 0x41, 0x56, 0x41, 0x57};

// Both games' functions turn the path's direction (D2R 0x341930 -> 0x3aeb30, 1.14d 0x648810 -> 0x63e7a0) into an index 0-7
// and look up the step direction here (the same 8 bytes on the stack of all four functions), whose x / y offsets
// (D2R 0x3aeb40, 1.14d 0x63e7e0) give the step.
inline constexpr uint8_t StepTable[8] = {0x0a, 0x08, 0x16, 0x14, 0x12, 0x10, 0x0e, 0x0c};

// D2R's own trail runs when its list names a skill in range (its first check); every other list gets 1.14d's fixed one.
constexpr auto FixedTrail(int32_t listSkill, int32_t skillCount) noexcept -> bool {
	return listSkill <= 0 || listSkill >= skillCount;
}

// The step direction of an index; false for one past the table (D2R reads no further; the hook makes nothing then).
constexpr auto StepDirection(uint32_t index, uint8_t* direction) noexcept -> bool {
	if (index >= sizeof(StepTable)) {
		return false;
	}
	*direction = StepTable[index];
	return true;
}

// Where the missile starts and where it heads, from the unit's position and the step (dx, dy): one step on, then two more.
// The same in both games (D2R: x += dx; target x + 2 dx. 1.14d: edi += dx; lea [edi + dx * 2]).
struct Spot {
	int32_t x, y, targetX, targetY;
};
constexpr auto SpotFrom(int32_t ux, int32_t uy, int32_t dx, int32_t dy) noexcept -> Spot {
	return Spot{ux + dx, uy + dy, ux + dx + dx * 2, uy + dy + dy * 2};
}

}  // namespace melt_trail

// Pure part of the 1.13c stun length for Leap Attack and Cherub Strike (stun_len.cpp; unit test plugin/tests/stun_len_test.cpp).
// No Windows headers, no game calls.
#pragma once

#include <cstdint>
#include <initializer_list>

namespace stun_len {

// missiles.txt pSrvDmgFunc 7 (stun) with dParam1 0 takes the length from the missile's skill (Median's note "stun len (0 =
// skill)"). 1.13c / 1.14d (Game.exe 0x5ad3e0 -> 0x4e6ca0): Param1 + Param2 * (lvl - 1) of the missile's own skill and level.
// D2R 93847 (0x453e30): the skill's calc4 when the missile has an owner. tools/txt_migrate.py stun_calc4 puts `ln12` there,
// except on skills whose server function reads calc4 as "% Damage Dealt as Elemental"; these are the ones left, so the hook
// writes the 1.13c length after D2R's function for them only (docs/bugs.md #580).
inline constexpr int32_t SkillLeapAttack = 143;     // srvdofunc 78, missile leapattack (the port's ids, tools/idmap.py)
inline constexpr int32_t SkillCherubStrike = 665;   // srvdofunc 11, deathrockcenter ... deathrockbolt
inline constexpr int32_t SkillLevel90Cherub = 1001; // srvdofunc 11, the same missiles
constexpr auto IsParamStunSkill(int32_t skill) noexcept -> bool {
	return skill == SkillLeapAttack || skill == SkillCherubStrike || skill == SkillLevel90Cherub;
}

// 1.14d 0x4e6cc4: 0 for a level of 0 or less, else Param1 + (lvl - 1) * Param2.
constexpr auto StunLength(int32_t param1, int32_t param2, int32_t level) noexcept -> int32_t {
	return level <= 0 ? 0 : param1 + (level - 1) * param2;
}

// The length applies only when the missile names none of its own (dParam1 > 0 wins, as in both games).
constexpr auto TakesSkillLength(int32_t dParam1) noexcept -> bool {
	return dParam1 <= 0;
}

// The log key of a function-7 hit (stun_len.cpp logs each combination once): never 0, which marks a free slot.
constexpr auto NoteKey(int32_t missile, int32_t skill, int32_t level, int32_t before, int32_t after) noexcept -> uint64_t {
	uint64_t h = 1469598103934665603ULL;
	for (const int32_t v : {missile, skill, level, before, after}) {
		h = (h ^ static_cast<uint32_t>(v)) * 1099511628211ULL;
	}
	return h == 0 ? 1 : h;
}

// Server damage function 7 entry: MOV [RSP+0x20],RBX / PUSH RBP / PUSH RSI / PUSH R15 / SUB RSP,0x30 / MOV RBP,R9
// (game, missile, target, damage): table 0x2391270 entry 7.
inline constexpr uint64_t RvaSrvDmgStun = 0x453e30;
inline constexpr uint8_t Entry[] = {0x48, 0x89, 0x5c, 0x24, 0x20, 0x55, 0x56, 0x41, 0x57, 0x48, 0x83, 0xec, 0x30, 0x49, 0x8b, 0xe9};

inline constexpr int MisDParam1 = 0x9c;    // missiles.txt record: int32 dParam1 (0x453eba)
inline constexpr int SkParam1 = 0x1b8;     // skills.txt record: int32 Param1, Param2 after it (0x453f2d / 0x453f34)
inline constexpr int SkParam2 = 0x1bc;
inline constexpr int UnitData = 0x10;      // missile unit -> missile data (0x3bc48e)
inline constexpr int MisDataSkill = 0x0c;  // int16 skill (0x3bc4b2)
inline constexpr int MisDataLevel = 0x0e;  // int16 level (0x3bb4d2)
inline constexpr int DmgStunLength = 0x12c;  // damage block: the stun length function 7 writes (0x453f44)

}  // namespace stun_len

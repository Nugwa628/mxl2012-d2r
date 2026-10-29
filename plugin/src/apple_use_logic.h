// Pure rule of the Apple's item spell (apple_use.cpp; unit test plugin/tests/apple_use_test.cpp). No Windows headers, no game calls.
#pragma once

#include <cstdint>

namespace apple_use {

// misc.txt pSpell 10 means two things (bug #499). In 1.13c (1.14d Game.exe 0x5bf170, item-spell table 0x741794) it casts skill
// 47 on the user, level 1: on the user's target unit when there is one, else at the user's x / y; it has no check function, so the
// item can always be used. Median XL 2012 rewrote skills row 47 as `Apple Healing Spell` (srvdofunc 18, aurastate `mega_apple`,
// 15000 frames, hpregen plus four class synergy stats) and gives pSpell 10 to its Apple (`dog`). D2R's pSpell 10 is its Book of
// Skill (`ass `, +1 skill point, refused with "I can't" until Radament's book flag is set). The part keeps D2R's code for `ass `
// and runs 1.13c's for every other pSpell 10 item.
inline constexpr int32_t AppleSkill = 47;  // skills.txt `Apple Healing Spell`: a 1.13c row, so its id is kept by the id map
inline constexpr int32_t AppleLevel = 1;   // 1.14d passes level 1
inline constexpr int32_t CastFlag = 0;     // 1.14d passes 0 to both casts

// D2R's item spells (D2Game SkillItem.cpp): pSpell n -> descriptor 0x236fe30 + 12 n = {check index, use index, flag}; pSpell 10 is
// {7, 10, 0}. Check table 0x1d3ea30 (11 entries; slot 7 = 0x5806f0, only reached through it), use table 0x1d3ea90 (16 entries;
// slot 10 = 0x580750). Both are (game, user, item) -> bool.
inline constexpr int CheckSlot = 7;
inline constexpr int UseSlot = 10;

// Item codes are 4 bytes, little-endian, space padded ("ass " = 0x20737361).
inline constexpr uint32_t BookCode = 0x20737361u;

// True when the item takes 1.13c's spell (skill 47) instead of D2R's Book of Skill. An unknown code (0: no record) stays D2R's.
constexpr auto RunsApple(uint32_t code) noexcept -> bool {
	return code != 0 && code != BookCode;
}

}  // namespace apple_use

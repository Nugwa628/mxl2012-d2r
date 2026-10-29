// Pure rule of the skill-remove guard (skill_remove.cpp; unit test plugin/tests/skill_remove_test.cpp).
// No Windows headers, no game calls.
#pragma once

namespace skill_remove {

// D2R's skill remove (D2Common Skills.cpp, 0x3402d0: unit, skill id, flag) is reached when a skill's level is set to 0 (set-skill-level
// 0x33efb0). It asserts "ptSkill" (Skills.cpp:904) when the unit's skill list (unit +0x100) has no first skill, and asserts too
// when the unit has no list at all; both times it then returns having removed nothing. Median XL 2012 gets there through its
// summons: Batstrike's bats (familiarbats), Summon Rampagor's and Summon Lamia's pets own no skill in monstats, and the summon
// do 119 gives them their `sumskill`s at the caster's level in them, 0 for a caster without them, i.e. a remove (bug #15). 1.13c
// found no skill to remove and returned. The guard returns the same without the asserts; a unit with skills, and a null unit
// (a real fault), take D2R's path.
constexpr auto SkipsRemove(bool haveUnit, bool haveList, bool haveFirstSkill) noexcept -> bool {
	return haveUnit && (!haveList || !haveFirstSkill);
}

}  // namespace skill_remove

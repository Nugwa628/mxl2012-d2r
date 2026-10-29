// Pure rule of the item-event skill guard (item_effect.cpp; unit test plugin/tests/item_effect_test.cpp).
// No Windows headers, no game calls.
#pragma once

#include <cstdint>

namespace item_effect {

// D2R's item-event skill resolver (D2Game SkillItemEffect.cpp, 0x589930) is asked for the skill an item property fires on an
// event (att-skill, kill-skill, hit-skill, gethit-skill, levelup-skill, death-skill; the chance-to-cast items). For a skill
// whose skills.txt row has no ItemEffect (record +0x20a == 0) it logs "BC_ASSERT: ptSkill->nItemEffect != 0"
// (SkillItemEffect.cpp:136) and then returns 0, i.e. casts nothing. Median XL 2012 has such properties on 8 uniques / set items
// / recipes / suffixes (bug #40; 1.13c ran nothing for them either, the tooltip line stays). The guard returns the same 0
// without the assert, so a skill id of 0 (D2R's own 0 result), an unknown skill or a skill with an ItemEffect take D2R's path.
constexpr auto SkipsEventSkill(int32_t skillId, bool haveRecord, uint32_t itemEffect) noexcept -> bool {
	return skillId > 0 && haveRecord && itemEffect == 0;
}

}  // namespace item_effect

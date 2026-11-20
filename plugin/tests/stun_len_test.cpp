// Standalone test of the Leap Attack / Cherub Strike stun length's pure part (stun_len_logic.h; not part of the plugin DLL).
#include "../src/stun_len_logic.h"

#include <cstdio>

namespace {
int failures = 0;
void Check(bool ok, const char* what) {
	if (!ok) {
		++failures;
		std::printf("FAIL: %s\n", what);
	}
}
}  // namespace

int main() {
	using namespace stun_len;
	Check(IsParamStunSkill(143) && IsParamStunSkill(665) && IsParamStunSkill(1001), "Leap Attack, Cherub Strike, Level 90 Cherub");
	Check(!IsParamStunSkill(346) && !IsParamStunSkill(443) && !IsParamStunSkill(444), "Blink, Bear Claw, Stampede: calc4 carries theirs");
	Check(!IsParamStunSkill(407) && !IsParamStunSkill(0) && !IsParamStunSkill(-1), "Korlic's Leap Attack, none");

	// Cherub Strike: Param1 10, Param2 5; Leap Attack: Param1 4, Param2 30 (Median's skills.txt)
	Check(StunLength(10, 5, 1) == 10 && StunLength(10, 5, 3) == 20, "Cherub Strike 10 / 20 frames at levels 1 / 3");
	Check(StunLength(4, 30, 1) == 4 && StunLength(4, 30, 2) == 34, "Leap Attack 4 / 34 frames at levels 1 / 2");
	Check(StunLength(15, 5, 22) == 120, "Blink's formula at level 22: 120 frames (the wiki's 4.8 s)");
	Check(StunLength(10, 5, 0) == 0 && StunLength(10, 5, -1) == 0, "level 0 or less: no stun (1.14d 0x4e6cc6)");

	Check(TakesSkillLength(0) && TakesSkillLength(-5), "dParam1 0: from the skill");
	Check(!TakesSkillLength(25), "dParam1 25: the missile's own");

	Check(NoteKey(1, 2, 3, 4, 5) == NoteKey(1, 2, 3, 4, 5) && NoteKey(1, 2, 3, 4, 5) != NoteKey(1, 2, 3, 4, 6), "log key per combination");
	Check(NoteKey(0, 0, 0, 0, 0) != 0 && NoteKey(-1, -1, 0, 0, 0) != 0, "key never 0 (a free slot)");
	Check(sizeof(Entry) == 16 && Entry[0] == 0x48 && Entry[15] == 0xe9, "entry bytes up to MOV RBP,R9");
	Check(SkParam2 == SkParam1 + 4 && DmgStunLength == 0x12c, "offsets");

	if (failures == 0) {
		std::printf("stun_len: all checks passed\n");
	}
	return failures == 0 ? 0 : 1;
}

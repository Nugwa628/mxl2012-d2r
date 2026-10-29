// Standalone test of the sound guard's pure part (sound_guard_logic.h; not part of the plugin DLL).
#include "../src/sound_guard_logic.h"

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
	using namespace sound_guard;
	// ids outside the table are skipped (crash-audit C17: id -1 from an unresolved Median name)
	Check(Skips(-1, ModSoundRows), "id -1");
	Check(Skips(-2147483647 - 1, ModSoundRows), "the lowest int");
	Check(Skips(ModSoundRows, ModSoundRows), "the row count itself");
	Check(!Skips(0, ModSoundRows), "row 0");
	Check(!Skips(ModSoundRows - 1, ModSoundRows), "the last row");
	Check(Skips(0, 0), "any id with no table");
	// a Median-only row (past D2R's) is skipped in D2R's own table, kept in ours
	Check(Skips(D2RSoundRows, D2RSoundRows) && !Skips(D2RSoundRows, ModSoundRows), "the first Median-only row");

	// answers for a skipped id: 0, or the id itself for the variant pickers
	Check(FieldAnswer() == 0, "field readers answer 0");
	Check(PickAnswer(-1) == 0xffffffffu && PickAnswer(5) == 5, "pickers answer the id (32 bits)");

	// table check: not loaded, D2R's own (the snapshot start), ours (either bank)
	Check(CheckTable(0) == Table::NotLoaded && CheckTable(-1) == Table::NotLoaded, "no rows: not loaded");
	Check(CheckTable(D2RSoundRows) == Table::Short, "D2R's 11913 rows: short");
	Check(CheckTable(ModSoundRows) == Table::Ours && CheckTable(ModSoundRowsBase) == Table::Ours, "both banks are ours");
	Check(CheckTable(MinModRows - 1) == Table::Short, "one row short");
	Check(CheckTable(ModSoundRows + 100) == Table::Ours, "more rows (a later data build) is ours");
	Check(D2RSoundRows < MinModRows && MinModRows <= ModSoundRows, "row counts ordered");

	// entry bytes: lengths the hooks copy, opcodes as listed
	Check(sizeof(PlayingSoundEntry) == 15 && PlayingSoundEntry[10] == 0x57, "0x107dd0: 15 bytes, push rdi");
	Check(sizeof(FieldC7Entry) == 8 && FieldC7Entry[7] == 0xd9 && sizeof(FieldB0Entry) == 8, "0xd8c70 / 0xd9180: 8 bytes, mov ebx,ecx");
	Check(sizeof(PathEntry) == 8 && sizeof(PickEntry) == 12 && sizeof(VariantEntry) == 11, "reader entry sizes");
	const uint8_t* const entries[] = {PlayingSoundEntry, FieldC7Entry, FieldB0Entry, PathEntry, PickEntry, VariantEntry};
	for (const uint8_t* e : entries) {
		Check(e[0] == 0x40 || e[0] == 0x48, "entry starts with a REX prefix");
	}
	Check(RvaFieldC7 == 0xd8c70 && RvaPlayingSound == 0x107dd0 && RvaSoundCount == 0x3b20c0, "rvas of the guard");

	// part spiritsound (#502): only ancient_death_hd, only for monsters 1085-1087
	Check(SkipsSpiritDeath(AncientDeathHd, UnitMonster, 1085) && SkipsSpiritDeath(AncientDeathHd, UnitMonster, 1087), "guardians / protectors");
	Check(SkipsSpiritDeath(AncientDeathHd, UnitMonster, 1086), "defenders");
	Check(!SkipsSpiritDeath(AncientDeathHd, UnitMonster, 1088), "crusaders (no summon skill, not drawn as an Ancient here)");
	Check(!SkipsSpiritDeath(AncientDeathHd, UnitMonster, 540) && !SkipsSpiritDeath(AncientDeathHd, UnitMonster, 541), "the real Ancients keep it");
	Check(!SkipsSpiritDeath(AncientDeathHd, 0, 1085) && !SkipsSpiritDeath(AncientDeathHd, 3, 1085), "players / missiles with the same class");
	Check(!SkipsSpiritDeath(AncientDeathHd + 1, UnitMonster, 1085) && !SkipsSpiritDeath(-1, UnitMonster, 1085), "other sounds of a spirit");
	Check(!Skips(AncientDeathHd, D2RSoundRows), "ancient_death_hd is a D2R row");
	Check(RvaClientPlay == 0x1a0780 && sizeof(ClientPlayEntry) == 13 && ClientPlayEntry[0] == 0x40 && ClientPlayEntry[12] == 0xd1,
	      "0x1a0780: 13 bytes, lea rbp,[rsp-0x2f]");

	if (failures == 0) {
		std::printf("sound guard tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}

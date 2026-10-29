// Standalone test of the patch bytes of the guards for D2R-only asserts (orig_asserts_logic.h; not part of the plugin DLL).
#include "../src/orig_asserts_logic.h"

#include <cstdio>
#include <cstring>

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
	using namespace orig_asserts;
	Check(BlockCount == 3, "three blocks: animseq, monequip, aurastate");
	for (size_t i = 0; i < BlockCount; ++i) {
		const Block& b = Blocks[i];
		char what[96];
		std::snprintf(what, sizeof(what), "%s: block shape lea ... call / test al,al / je / int3", b.word);
		Check(TestAt(b) != 0, what);
		std::snprintf(what, sizeof(what), "%s: the jump goes where D2R's je goes after the assert", b.word);
		Check(ContinueOf(b) == b.next, what);
		std::snprintf(what, sizeof(what), "%s: the call in the block is its assert reporter", b.word);
		Check(ReporterOf(b) == b.reporter, what);
		std::snprintf(what, sizeof(what), "%s: the patch is inside the compared bytes", b.word);
		Check(PatchSize < b.size, what);
		const Jump j = JumpBytes(b);
		std::snprintf(what, sizeof(what), "%s: jmp rel32 lands on next", b.word);
		const int32_t rel = Le32(&j.bytes[1]);
		Check(j.bytes[0] == 0xe9 && static_cast<uint64_t>(static_cast<int64_t>(b.rva + 5) + rel) == b.next, what);
		for (size_t k = 0; k < i; ++k) {
			std::snprintf(what, sizeof(what), "%s: own off word and address", b.word);
			Check(std::strcmp(Blocks[k].word, b.word) != 0 && Blocks[k].rva != b.rva, what);
		}
	}
	// the addresses read from the dump (docs/bugs.md #74 #181): reporters of Units.cpp:2835, SkillAss.cpp:2364, SkillSor.cpp:424
	Check(Blocks[0].rva == 0x34d935 && Blocks[0].next == 0x34d948 && Blocks[0].reporter == 0x346000, "animseq 0x34d935 -> 0x34d948");
	Check(Blocks[1].rva == 0x56d38b && Blocks[1].next == 0x56d47d && Blocks[1].reporter == 0x56bf20, "monequip 0x56d38b -> 0x56d47d");
	Check(Blocks[2].rva == 0x553ef4 && Blocks[2].next == 0x553f0e && Blocks[2].reporter == 0x551300, "aurastate 0x553ef4 -> 0x553f0e");
	const Jump j0 = JumpBytes(Blocks[0]);
	Check(j0.bytes[1] == 0x0e && j0.bytes[2] == 0 && j0.bytes[3] == 0 && j0.bytes[4] == 0, "animseq jmp bytes e9 0e 00 00 00");
	Check(Rel32(0x1000, 0x1000) == -5, "rel32 to itself");

	if (failures == 0) {
		std::printf("orig asserts tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}

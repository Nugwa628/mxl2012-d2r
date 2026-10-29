// Standalone test of the durability update patch (dur_sync_logic.h; not part of the plugin DLL). Lane dursync, bug #433.
#include "../src/dur_sync_logic.h"

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
	using namespace dur_sync;
	Check(PatchInExpected == 0x20 && PatchInExpected + PatchSize <= ExpectedSize, "the patched store lies inside the compared block");
	bool oldInCheck = true;
	for (size_t i = 0; i < PatchSize; ++i) {
		oldInCheck = oldInCheck && Expected[PatchInExpected + i] == Old[i];
	}
	Check(oldInCheck, "Old is the compared block at 0x441c4b");
	Check(Expected[XorInExpected] == 0x33 && Expected[XorInExpected + 1] == 0xf6, "xor esi,esi before the store: rsi is 0");
	Check(XorInExpected + 2 + 3 == PatchInExpected, "only mov rcx,rbp between the xor and the store (rsi untouched)");
	int diff = 0;
	for (size_t i = 0; i < PatchSize; ++i) {
		diff += New[i] != Old[i];
	}
	Check(diff == 1 && Old[0] == 0x66 && New[0] == 0x48, "only the prefix changes: 0x66 (16-bit) -> REX.W (64-bit)");
	Check(New[1] == 0x89 && New[2] == 0x74 && New[3] == 0x24 && New[4] == 0x28, "same opcode / ModRM / SIB / disp8: [rsp+0x28], rsi");
	Check(Rel32Target(Expected, 0x0d, ExpectedRva) == 0x2f7940, "the block's call is the stat set 0x2f7940");
	Check(Rel32Target(Expected, ExpectedSize - 5, ExpectedRva) == SendRva, "the block ends in the jump to the shared send 0x441e62");
	Check(Rel32Target(Send, sizeof(Send) - 5, SendRva) == SenderRva, "the shared send calls 0x47a190");
	Check(Send[2] == StatDurability, "the send is for stat 0x48 (durability)");
	Check(Expected[11] == 0x51 && Expected[12] == StatDurability, "the set is stat 0x48 too (lea edx,[r9+0x48])");

	// the slot the sender sees (the garbage seen in game, run checks-20261029-111824-s3)
	const unsigned long long seen = 0x140380000ULL;
	Check(SlotAfter(seen, 0, false) == seen, "D2R: the upper bytes keep the stack's garbage");
	Check((SlotAfter(seen, 0, false) & 0xffff) == 0, "and the 16 bits D2R's own sender reads are 0");
	Check(SlotAfter(seen, 0, true) == 0, "patched: the whole slot is 0");
	Check(SlotAfter(0xffffffffffffffffULL, 0, true) == 0, "whatever the stack held");
	std::printf(failures == 0 ? "dur sync tests: all passed\n" : "dur sync tests: %d failures\n", failures);
	return failures == 0 ? 0 : 1;
}

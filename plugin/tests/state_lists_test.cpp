// Standalone test of the blaze / spider-lay state list guard's patch bytes (state_lists_logic.h; not part of the plugin DLL).
#include "../src/state_lists_logic.h"

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
	using namespace state_lists;
	Check(BlockCount == 12, "three asserts in each of the four functions");
	// the assert reporters the blocks call (one per assert line in D2R's dump)
	constexpr uint64_t reporters[BlockCount] = {0x21eb70, 0x21eae0, 0x21ed20, 0x2213c0, 0x220fd0, 0x221150,
	                                            0x551150, 0x550f40, 0x551120, 0x5783e0, 0x5782f0, 0x5781a0};
	for (size_t i = 0; i < BlockCount; ++i) {
		const Block& b = Blocks[i];
		Check(WellFormed(b), b.what);
		Check(ReporterOf(b) == reporters[i], "the call in the expected bytes is the assert reporter");
		const Jump j = JumpBytes(b);
		const auto rel = static_cast<int32_t>(j.bytes[1] | (j.bytes[2] << 8) | (j.bytes[3] << 16) | (static_cast<uint32_t>(j.bytes[4]) << 24));
		Check(j.bytes[0] == 0xe9 && b.rva + 5 + rel == b.next, "jmp lands after the int3");
		Check(PatchSize < b.size, "the patch check covers the 5 bytes written, the block is longer");
		for (size_t k = 0; k < i; ++k) {
			Check(Blocks[k].rva + Blocks[k].size <= b.rva || b.rva + b.size <= Blocks[k].rva, "blocks do not overlap");
		}
	}
	// spot values: server 22 skill assert 0x578759 jumps 15 bytes on (e9 0a 00 00 00)
	constexpr Jump s = JumpBytes(Blocks[9]);
	Check(s.bytes[0] == 0xe9 && s.bytes[1] == 0x0a && s.bytes[2] == 0 && s.bytes[3] == 0 && s.bytes[4] == 0, "jmp bytes e9 0a 00 00 00");
	Check(Rel32(0x1000, 0x1000) == -5, "rel32 to itself");

	if (failures == 0) {
		std::printf("state list tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}

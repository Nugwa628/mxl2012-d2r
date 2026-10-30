// Standalone test of the reassign guard's pure part (reassign_guard_logic.h; not part of the plugin DLL).
#include "../src/reassign_guard_logic.h"

#include <cstdint>
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
	using namespace reassign_guard;
	Check(RvaHandler == 0x12ab40 && sizeof(HandlerEntry) == 15 && HandlerEntry[0] == 0x40 && HandlerEntry[14] == 0x0a, "handler rva and entry bytes");
	Check(RvaLocalPlayerId == 0x8b2d0 && RvaPlayerById == 0x9a480, "the handler's own calls");

	// 15 01 | id 0x12345678 | x 0x2044 (8260) | y 0x1d71 (7537) | flags 2: a monster (the mercenary) sent into Underground Passage
	const uint8_t pkt[PacketSize] = {0x15, 0x01, 0x78, 0x56, 0x34, 0x12, 0x44, 0x20, 0x71, 0x1d, 0x02};
	const Reassign r = Parse(pkt);
	Check(r.unitType == 1 && r.id == 0x12345678u && r.x == 8260 && r.y == 7537 && r.flags == 2, "packet fields");

	Check(Decide(false) == Verdict::Leave, "another unit without a room: left so");
	Check(Decide(true) == Verdict::End, "the local player without a room: D2R's end");

	// D2R's je 0x12aec0 at 0x12addb; the new one goes to the pad 0x12aee4 (rel 0x103)
	Check(RvaNoRoomBranch + 6 + NoRoomBranch[2] == RvaFail && NoRoomBranch[3] == 0, "D2R's branch goes to the fail block");
	const Branch b = BranchBytes();
	const uint8_t want[6] = {0x0f, 0x84, 0x03, 0x01, 0x00, 0x00};
	Check(std::memcmp(b.bytes, want, 6) == 0, "branch to the pad");
	Check(RvaPad + sizeof(Pad) == 0x12aef0 && RvaPad > RvaFail, "pad between the fail block and the next function");

	const AbsJump j = AbsJumpBytes(0x1122334455667788ull);
	const uint8_t wantJ[12] = {0x48, 0xb8, 0x88, 0x77, 0x66, 0x55, 0x44, 0x33, 0x22, 0x11, 0xff, 0xe0};
	Check(std::memcmp(j.bytes, wantJ, 12) == 0 && sizeof(j.bytes) == sizeof(Pad), "absolute jump fills the pad");

	const Stub s = StubBytes(0x1111111111111111ull, 0x2222222222222222ull, 0x3333333333333333ull);
	const uint8_t head[9] = {0x48, 0x89, 0xf9, 0x48, 0x83, 0xec, 0x20, 0x48, 0xb8};
	Check(std::memcmp(s.bytes, head, 9) == 0, "stub: mov rcx,rdi / sub rsp,0x20 / movabs rax");
	Check(s.bytes[17] == 0xff && s.bytes[18] == 0xd0 && s.bytes[19] == 0x48 && s.bytes[22] == 0x20, "stub: call rax / add rsp,0x20");
	Check(s.bytes[23] == 0x84 && s.bytes[24] == 0xc0 && s.bytes[25] == 0x74 && s.bytes[26] == 12, "stub: test al,al / je over the leave jump");
	Check(s.bytes[27] == 0x48 && s.bytes[29] == 0x22 && s.bytes[37] == 0xff && s.bytes[38] == 0xe0, "stub: jump to leave");
	Check(27 + s.bytes[26] == 39 && s.bytes[39] == 0x48 && s.bytes[41] == 0x33 && s.bytes[49] == 0xff && s.bytes[50] == 0xe0, "stub: jump to fail");
	Check(s.bytes[9] == 0x11 && s.bytes[16] == 0x11, "stub: the callback address");

	if (failures == 0) {
		std::printf("reassign_guard: all checks passed\n");
	}
	return failures == 0 ? 0 : 1;
}

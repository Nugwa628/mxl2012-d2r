// Standalone test of the Ancient Tunnels void patch (void_floor_logic.h; not part of the plugin DLL). Lane tunnelfloor.
#include "../src/void_floor_logic.h"

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

auto Rel32At(const uint8_t* b, size_t off, uint64_t base, size_t len) -> uint64_t {
	int32_t rel = 0;
	std::memcpy(&rel, b + off + len - 4, 4);
	return base + off + len + static_cast<int64_t>(rel);
}

auto Abs(const uint8_t* b) -> uint64_t {
	uint64_t v = 0;
	std::memcpy(&v, b + 6, 8);
	return v;
}
}  // namespace

int main() {
	using namespace void_floor;
	// D2R's bytes: the compare is level 74, the branch goes to the next-room step, the load before it fetches the level
	Check(Site[6] == 74 && Site[2] == 0xf8 && Site[3] == 0x01, "the site compares [rax+0x1f8] with 74");
	Check(Rel32At(Site, 7, SiteRva, 6) == NextRoomRva, "the site's je goes to 0x6b4e19");
	Check(Rel32At(NextRoom, 7, NextRoomRva, 6) == LoopRva, "0x6b4e19 loops back to 0x6b4b76");
	Check(LoadRva + sizeof(Load) == SiteRva && SiteRva + sizeof(Site) == PlaneRva, "load, site and plane path are adjacent");
	Check(PadRva + sizeof(Pad) == 0x6b4a30, "the pad ends where the function starts");

	// the rule
	Check(D2RSkips(74) && !D2RSkips(65), "D2R: only 74 skips the plane");
	Check(Skips(74) && Skips(65) && !Skips(1) && !Skips(64) && !Skips(66) && !Skips(0), "patched: 74 and 65, nothing else");

	// the site: a jmp to the pad, the rest nops
	const SiteBytes site = SitePatch();
	Check(site.bytes[0] == 0xe9 && Rel32At(site.bytes, 0, SiteRva, 5) == PadRva, "the site jumps to the pad");
	bool nops = true;
	for (size_t i = 5; i < sizeof(site.bytes); ++i) {
		nops = nops && site.bytes[i] == 0x90;
	}
	Check(nops, "the site's tail is nops");
	Check(sizeof(AbsJump) == sizeof(Pad), "the absolute jump fills the pad exactly");

	// the stub
	const uint64_t base = 0x140000000ULL;
	const Stub s = StubBytes(base + PlaneRva, base + NextRoomRva);
	Check(Abs(s.bytes + SkipCount * CompareSize) == base + PlaneRva, "no match: on to the plane at 0x6b4b8d");
	Check(Abs(s.bytes + SkipCount * CompareSize + sizeof(AbsJump)) == base + NextRoomRva, "a match: to the next room");
	Check(s.bytes[SkipCount * CompareSize] == 0xff && s.bytes[SkipCount * CompareSize + 1] == 0x25, "jmp qword ptr [rip] (no register)");
	for (int lv = 0; lv < 128; ++lv) {
		Check(StubSkips(s, lv) == Skips(lv), "the stub skips exactly the listed levels");
	}
	for (size_t i = 0; i < SkipCount; ++i) {
		Check(std::memcmp(s.bytes + i * CompareSize, Site, 6) == 0, "each compare is D2R's own instruction with another level");
		Check(SkipLevels[i] > 0 && SkipLevels[i] < 128, "the level fits the imm8");
	}
	if (failures == 0) {
		std::printf("void_floor: all checks passed\n");
	}
	return failures == 0 ? 0 : 1;
}

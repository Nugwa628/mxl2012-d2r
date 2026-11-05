// Standalone test of Akara's unlimited respec rule (akara_respec_logic.h; not part of the plugin DLL).
#include "../src/akara_respec_logic.h"

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
	using namespace akara_respec;
	Check(!Unlimited(0), "no level (no unit): D2R's rule");
	Check(Unlimited(1) && Unlimited(99) && Unlimited(100), "levels 1-100: unlimited");
	Check(!Unlimited(101) && !Unlimited(120), "above 100: the Den of Evil's one respec per difficulty");
	constexpr uint32_t Npc = 7;
	Check(DecideServer(5, Npc, 1, true) == Server::Respec, "level 1 at Akara: respec without the Den");
	Check(DecideServer(5, Npc, 100, true) == Server::Respec, "level 100 at Akara: respec");
	Check(DecideServer(5, Npc, 101, true) == Server::D2R, "level 101: D2R's handler (quest 41 bit 1)");
	Check(DecideServer(5, Npc, 50, false) == Server::D2R, "an NPC without the respec byte, or out of range: D2R's handler");
	Check(DecideServer(5, 0xffffffffu, 50, true) == Server::D2R, "unit id -1 (D2R's no-NPC respec): D2R's handler");
	Check(DecideServer(6, Npc, 50, true) == Server::D2R && DecideServer(4, Npc, 50, true) == Server::D2R, "a packet of another size: D2R's");
	Check(FakeClient(AkaraClass, 1) && FakeClient(AkaraClass, 100), "Akara's menu shows the line up to 100");
	Check(!FakeClient(AkaraClass, 101), "above 100 the client's own bits decide");
	Check(!FakeClient(154, 50) && !FakeClient(-1, 50), "other NPCs (Charsi 154, none): real bits");
	Check(HideLine(AkaraClass, 101, false) && HideLine(AkaraClass, 150, false), "above 100, no respec waiting: the line is hidden");
	Check(!HideLine(AkaraClass, 101, true), "above 100 with the Den's respec waiting: D2R's line");
	Check(!HideLine(AkaraClass, 100, false) && !HideLine(AkaraClass, 1, false), "1-100: never hidden (the part shows it)");
	Check(!HideLine(154, 120, false) && !HideLine(-1, 120, false), "other NPCs: untouched");
	constexpr Bits s = Shown();
	Check(s.denDone && s.ready && !s.used, "shown: Den done (opener's service line), respec waiting and not used (builder)");
	Check(RespecQuest == 41 && RespecReadyBit == 1 && RespecUsedBit == 0 && DenQuest == 1 && DenDoneBit == 0,
	      "D2R 93847 bits: 0x5d9ae0 sets 41/0 and clears 41/1; service entry {0x94, 1, 0, 1}");
	if (failures == 0) {
		std::printf("akara respec tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}

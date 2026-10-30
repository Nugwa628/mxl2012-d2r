// Standalone test of vochat's pure part (vo_chat_logic.h; not part of the plugin DLL).
#include "../src/vo_chat_logic.h"

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
	using namespace vo_chat;
	// the key from a sounds.txt path, as 0x1a0210 builds it
	Check(PathKeyIs("Monster\\baal\\baallaugh1.flac", LimitedKey), "Baal's laugh path");
	Check(PathKeyIs("monster/baal/BaalLaugh1.wav", LimitedKey), "slashes and case");
	Check(PathKeyIs("baallaugh1", LimitedKey), "no folder, no extension");
	Check(PathKeyIs("Monster\\baal\\baallaugh1_hd.flac", LimitedKey), "a trailing _hd is dropped");
	Check(PathKeyIs("a.b\\baallaugh1.flac", LimitedKey), "a dot in a folder name");
	Check(!PathKeyIs("Monster\\baal\\baallaugh2.flac", LimitedKey), "the second laugh is another key");
	Check(!PathKeyIs("Monster\\baal\\baallaugh10.flac", LimitedKey), "a longer name");
	Check(!PathKeyIs("Monster\\baal\\baallaugh.flac", LimitedKey), "a shorter name");
	Check(!PathKeyIs("Monster\\soldier\\sol_overhere.flac", LimitedKey), "the soldiers' lines are not Baal's key");
	Check(!PathKeyIs("Monster\\baal\\.flac", LimitedKey) && !PathKeyIs("", LimitedKey) && !PathKeyIs(nullptr, LimitedKey), "no file name");
	Check(!PathKeyIs("Monster\\baal\\", LimitedKey), "a folder only");

	// the 30 s cooldown (ms of GetTickCount64)
	Check(CooldownMs == 30000, "30 s");
	Check(LineAllowed(5000, 0), "the first line goes out");
	Check(!LineAllowed(5001, 5000) && !LineAllowed(5000, 5000), "a second line at once is left out");
	Check(!LineAllowed(5000 + CooldownMs - 1, 5000), "29.999 s later: left out");
	Check(LineAllowed(5000 + CooldownMs, 5000), "30 s later: printed");
	Check(LineAllowed(5000 + 10 * CooldownMs, 5000), "much later: printed");
	Check(LineAllowed(4000, 5000), "a clock that went back: printed");

	// a run: casts every 4 s for 70 s print at 0, 32 and 64 s
	uint64_t last = 0;
	int printed = 0;
	uint64_t at[3] = {};
	for (uint64_t t = 1000; t <= 71000; t += 4000) {
		if (LineAllowed(t, last)) {
			last = t;
			if (printed < 3) {
				at[printed] = t;
			}
			++printed;
		}
	}
	Check(printed == 3 && at[0] == 1000 && at[1] == 33000 && at[2] == 65000, "casts every 4 s: lines at 1, 33, 65 s");

	// the soldiers' lines: their own keys and 5 s each
	Check(LimitedIndex("Monster\\baal\\baallaugh1.flac") == 0, "Baal's laugh is entry 0 (30 s)");
	Check(LimitedIndex("Monster\\soldier\\sol_overhere.flac") == 1 && LimitedIndex("sol_helpus_hd.flac") == 2, "soldier keys");
	Check(LimitedIndex("Monster\\soldier\\sol_overhere2.flac") == -1 && LimitedIndex("Monster\\baal\\baallaugh2.flac") == -1
	          && LimitedIndex(nullptr) == -1, "other lines are not limited");
	Check(LimitedLines[1].cooldownMs == 5000 && LimitedLines[2].cooldownMs == 5000, "soldiers: 5 s");
	Check(!LineAllowed(5000 + 4999, 5000, SoldierCooldownMs) && LineAllowed(5000 + 5000, 5000, SoldierCooldownMs),
	      "soldiers: 4.999 s left out, 5 s printed");

	// hook site
	Check(RvaVoSubtitle == 0x1a0da0 && RvaSoundRecord == 0xd96a0 && RecordPath == 0x32, "rvas and the path offset");
	Check(sizeof(VoSubtitleEntry) == 19 && VoSubtitleEntry[0] == 0x4c && VoSubtitleEntry[3] == 0x55 && VoSubtitleEntry[12] == 0x48,
	      "0x1a0da0: 19 bytes, mov r11,rsp / push rbp / ... / sub rsp,0x1e8");

	if (failures == 0) {
		std::printf("vochat_tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}

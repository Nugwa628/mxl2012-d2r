// Standalone test of the RotW stash pages in classic graphics (rotw_stash_logic.h; not part of the plugin DLL).
#include "../src/rotw_stash_logic.h"

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
	using namespace rotw_stash;
	// the compared bytes
	int32_t rel = 0;
	std::memcpy(&rel, HdCheckCall + 1, sizeof(rel));
	Check(HdCheckCall[0] == 0xe8 && Rel32Call(HdCheckCallRva, HdModeRva) == rel, "0x23b204 calls the HD check 0x846210");
	Check(HdModeCode[15] == 0xb9 && HdModeCode[sizeof(HdModeCode) - 1] == 0xc3, "0x846210 returns the panel manager's +0xb9");
	int32_t rip = 0;
	std::memcpy(&rip, RotwGameCode + 3, sizeof(rip));
	Check(RotwGameRva + 7 + rip == ClientGameRva, "0x8d3e0 loads the client game 0x2a236e0");
	Check(RotwGameCode[12] == 0x80 && RotwGameCode[13] == 0x78 && RotwGameCode[14] == GameTypeOffset && RotwGameCode[15] == GameTypeRotw,
	      "and compares its byte +0x5c with 3");
	Check(PadRva + sizeof(Pad) <= 0x2388b0 && sizeof(Pad) == sizeof(AbsJump::bytes), "the absolute jump fits the pad before 0x2388b0");
	Check(Pad[0] == 0xcc && Pad[sizeof(Pad) - 1] == 0xcc, "the pad is int3");
	Check(sizeof(ItemPictureEntry) == 16 && ItemPictureEntry[9] == 0x55, "the picture entry: two stores, push rbp ...");
	const AbsJump j = AbsJumpBytes(0x1122334455667788ull);
	Check(j.bytes[0] == 0x48 && j.bytes[1] == 0xb8 && j.bytes[2] == 0x88 && j.bytes[9] == 0x11 && j.bytes[10] == 0xff && j.bytes[11] == 0xe0,
	      "movabs rax / jmp rax");

	// the decision
	const Mode modes[] = {Mode::Rotw, Mode::Always, Mode::Never};
	for (Mode m : modes) {
		Check(WirePages(true, false, m) && WirePages(true, true, m), "HD: D2R's yes in every mode");
	}
	Check(WirePages(false, false, Mode::Always) && WirePages(false, true, Mode::Always), "default: classic wired in every game, as HD");
	Check(WirePages(false, true, Mode::Rotw), "dev rotw, RotW game: wired");
	Check(!WirePages(false, false, Mode::Rotw), "dev rotw, LoD game: left as D2R");
	Check(!WirePages(false, true, Mode::Never) && !WirePages(false, false, Mode::Never), "dev never: D2R's HD-only rule");
	Check(ParseMode("rotw") == Mode::Rotw && ParseMode("ROTW") == Mode::Rotw && ParseMode("never") == Mode::Never, "test values");
	Check(ParseMode(nullptr) == Mode::Always && ParseMode("") == Mode::Always && ParseMode("rot") == Mode::Always &&
	          ParseMode("rotwx") == Mode::Always && ParseMode("always") == Mode::Always,
	      "anything else: the default");

	// the picture guard
	int item = 0, draw = 0;
	Check(SkipPicture(&item, nullptr), "an item without a draw record is skipped");
	Check(!SkipPicture(&item, &draw), "with one it is drawn");
	Check(!SkipPicture(nullptr, nullptr), "a null item goes to D2R as before");

	if (failures == 0) {
		std::printf("rotwstash_tests: all passed\n");
		return 0;
	}
	return 1;
}

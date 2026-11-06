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

	// the empty slots' dimming
	std::memcpy(&rel, SlotPlaceholderDraw + 1, sizeof(rel));
	Check(SlotPlaceholderDraw[0] == 0xe8 && Rel32Call(SlotPlaceholderDrawCall, ItemDrawRva) == rel, "0x2ce636 calls 0x15bb80");
	Check(sizeof(ItemDrawEntry) == 19 && sizeof(CelDrawEntry) == 18, "whole instructions at both entries");
	const DrawAlpha slot{0.2f, 1}, full{1.0f, 1}, unused{0.2f, 0};
	Check(DimDraw(false, &slot), "classic, the slot's 0.2: dimmed");
	Check(!DimDraw(true, &slot), "HD tints by itself");
	Check(!DimDraw(false, &full) && !DimDraw(false, &unused) && !DimDraw(false, nullptr), "alpha 1, an unused alpha, none: as D2R");
	Check(CelMode(CelModeNormal, true) == CelModeDim && CelMode(CelModeNormal, false) == CelModeNormal, "mode 5 turns translucent while dimmed");
	Check(CelMode(1, true) == 1 && CelMode(3, true, 2) == 3 && CelMode(5, true, 2) == 2, "other modes stay; the dev mode is used");

	// the cube window's small items
	std::memcpy(&rip, SpriteScaleCode + 2, sizeof(rip));
	Check(SpriteScaleRva + 6 + rip == SpriteScaleValueRva && SpriteScaleCode[6] == 0xc3, "0x6bbac0 returns the dword 0x341d248");
	std::memcpy(&rip, SpriteScaleOnCode + 3, sizeof(rip));
	Check(SpriteScaleOnRva + 7 + rip == SpriteScaleOnRefRva && SpriteScaleOnCode[sizeof(SpriteScaleOnCode) - 1] == 0xc3,
	      "0x6bbad0 reads through 0x32f0868 and ends with its ret");
	Check(sizeof(SpriteScaleCode) >= sizeof(AbsJump::bytes) && sizeof(SpriteScaleOnCode) >= sizeof(AbsJump::bytes),
	      "the absolute jump fits both");
	Check(SmallDraw(false, 0.2759f) && !SmallDraw(true, 0.2759f), "classic with a scale below 1: small; HD draws it itself");
	Check(!SmallDraw(false, 1.0f) && !SmallDraw(false, 0.0f) && !SmallDraw(false, 1.5f), "scale 1, none, larger: as D2R");
	Check(SpriteScale(0, false, 0.2759f) == 71 && SpriteScale(512, true, 0.5f) == 256 && SpriteScale(512, false, 0.5f) == 128,
	      "256ths: D2R's own scale only when it is on");
	Check(SpriteScale(256, true, 0.001f) == 1, "never 0");
	Check(SmallPlace(100, 100, 0.25f) == 100 && SmallPlace(158, 100, 0.25f) == 115 && SmallPlace(90, 100, 0.25f) == 97,
	      "places move toward the origin");

	if (failures == 0) {
		std::printf("rotwstash_tests: all passed\n");
		return 0;
	}
	return 1;
}

// The RotW stash pages in classic graphics (docs/bugs.md #516, docs/plugin-plan.md section 29; off word rotwstash).
//
// D2R wires the stash's Gems / Materials / Runes pages only in HD: its BankPanel init (0x23b1b0) sets up the page table after
// the HD check 0x846210 (rotw_stash_logic.h). The classic RotW stash layout of tools/rotw_stash_legacy.py therefore crashed
// D2R on G with the stash open (lane rotwstash: +0x23E6A5, the tab update through the empty table; +0x154AF2, the classic item
// picture of an AdvancedStashSlotWidget on a page nobody hid). This part:
//   - the init's `call 0x846210` (0x23b204) goes through the int3 pad 0x2388a2 to WireDecision: HD answers D2R's yes, and so
//     does classic, in every game. The panel then runs as in HD: D2R's own RotW rule keeps the Gems / Materials / Runes tabs
//     closed in a game without RotW (slot 1, lane rotwgate: only Personal / Shared, G back and forth without a crash); in a RotW
//     game it should open them as in HD (not testable here: no slot account owns RotW). With D2R's own classic layout nothing changes (no basicstash_container: the init leaves right
//     after the check). Without the wiring (D2R's rule, dev `never` / `rotw` in a
//     game without RotW) the classic RotW layout crashed on G (+0x23E6A5), as lane rotwstash saw;
//   - the classic item picture 0x154ac0 returns at once for an item without its draw record (+0x78) instead of reading
//     null + 0x440 (lane rotwstash's +0x154AF2; not reached once the pages are wired, kept as a guard).
// The game type (client game byte +0x5c, 3 = RotW) is read for `mxl2012` and the dev mode `rotw`.
// Dev builds: MXL_ROTWSTASH_TEST=rotw wires the pages in classic only in a RotW game, =never keeps D2R's HD-only rule.
#include "rotw_stash.h"

#include "rotw_stash_logic.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

using namespace rotw_stash;

using BoolFn = bool (*)() noexcept;
using PictureFn = void (*)(void* item, uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e) noexcept;

BoolFn g_hd = nullptr;
BoolFn g_rotwGame = nullptr;
PictureFn g_picture = nullptr;
uint64_t g_base = 0;
Mode g_mode = Mode::Always;
volatile LONG g_inits = 0, g_wired = 0, g_left = 0, g_skipped = 0;

bool WireDecision() noexcept {
	const bool hd = g_hd();
	InterlockedIncrement(&g_inits);
	const bool wire = WirePages(hd, g_rotwGame(), g_mode);
	if (!hd) {
		InterlockedIncrement(wire ? &g_wired : &g_left);
	}
	return wire;
}

void PictureGuard(void* item, uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e) noexcept {
	if (item != nullptr && SkipPicture(item, *reinterpret_cast<void* const*>(static_cast<uint8_t*>(item) + ItemDrawDataOffset))) {
		InterlockedIncrement(&g_skipped);
		return;
	}
	g_picture(item, a, b, c, d, e);
}

}  // namespace

auto InstallRotwStash(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	g_base = context->exeBase;
	const auto* image = reinterpret_cast<const uint8_t*>(g_base);
#ifndef MXL_RELEASE
	char env[16] = "";
	if (GetEnvironmentVariableA("MXL_ROTWSTASH_TEST", env, sizeof(env)) > 0) {
		g_mode = ParseMode(env);
	}
#endif
	const bool same = std::memcmp(image + HdCheckCallRva, HdCheckCall, sizeof(HdCheckCall)) == 0 &&
	                  std::memcmp(image + HdModeRva, HdModeCode, sizeof(HdModeCode)) == 0 &&
	                  std::memcmp(image + RotwGameRva, RotwGameCode, sizeof(RotwGameCode)) == 0 &&
	                  std::memcmp(image + PadRva, Pad, sizeof(Pad)) == 0 &&
	                  std::memcmp(image + ItemPictureRva, ItemPictureEntry, sizeof(ItemPictureEntry)) == 0;
	if (!same) {
		std::snprintf(report, reportSize, "rotwstash off: bytes differ at 0x23b204 / 0x846210 / 0x8d3e0 / 0x2388a2 / 0x154ac0, left as D2R");
		return false;
	}
	g_hd = reinterpret_cast<BoolFn>(g_base + HdModeRva);
	g_rotwGame = reinterpret_cast<BoolFn>(g_base + RotwGameRva);
	// the picture guard first (harmless alone), then the pad, then the call that makes the decision live
	bool ok = context->InstallInlineHook(ItemPictureRva, ItemPictureEntry, sizeof(ItemPictureEntry), reinterpret_cast<void*>(&PictureGuard),
	                                     reinterpret_cast<void**>(&g_picture));
	if (ok) {
		const AbsJump pad = AbsJumpBytes(reinterpret_cast<uint64_t>(&WireDecision));
		ok = context->PatchBytes(PadRva, Pad, sizeof(Pad), pad.bytes, sizeof(pad.bytes)) &&
		     context->PatchCallRel32(HdCheckCallRva, HdCheckCall, sizeof(HdCheckCall), PadRva);
	}
	std::snprintf(report, reportSize, "rotwstash %s: the stash wires its RotW pages in classic graphics in %s (init 0x23b1b0, HD check "
	              "0x23b204); classic item pictures without a draw record skipped (0x154ac0)", ok ? "on" : "FAILED", ModeName(g_mode));
	return ok;
}

void RotwStashState(RotwStashCounts* out) noexcept {
	out->inits = g_inits;
	out->classicWired = g_wired;
	out->classicLeft = g_left;
	out->skipped = g_skipped;
	out->mode = ModeName(g_mode);
	out->hd = g_hd != nullptr && g_hd();
	out->gameType = -1;
	if (g_base != 0) {
		const auto* game = *reinterpret_cast<const uint8_t* const volatile*>(g_base + ClientGameRva);
		if (game != nullptr) {
			out->gameType = game[GameTypeOffset];
		}
	}
}

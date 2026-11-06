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
//     null + 0x440 (lane rotwstash's +0x154AF2; not reached once the pages are wired, kept as a guard);
//   - an empty slot's placeholder icon is dimmed in classic as in HD: 0x15bb80 (the item draw with an alpha) notes a classic
//     draw with alpha < 1, and 0x656020 (the classic cel draw) draws mode 5 translucent while it holds (lane cubewindow);
//   - a classic item draw with a scale below 1 (the stash cube window's 10 x 8 grid, lane legacycube) draws small: 0x15bb80
//     notes the scale and the item's top left, 0x656020 moves its places toward that corner, and D2R's sprite scale getters
//     0x6bbac0 / 0x6bbad0 (whole functions replaced by jumps to SpriteScaleHook / SpriteScaleOnHook) answer that scale.
// The game type (client game byte +0x5c, 3 = RotW) is read for `mxl2012` and the dev mode `rotw`.
// Dev builds: MXL_ROTWSTASH_TEST=rotw wires the pages in classic only in a RotW game, =never keeps D2R's HD-only rule;
// MXL_ROTWSTASH_DIM=<mode> draws the empty slots with another classic draw mode (0-8) instead of CelModeDim.
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
using ItemDrawFn = uint64_t (*)(void* item, uint64_t pos, float scale, DrawAlpha* alpha) noexcept;
using CelDrawFn = uint64_t (*)(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t mode, uint64_t f, uint64_t g, uint64_t h) noexcept;

BoolFn g_hd = nullptr;
BoolFn g_rotwGame = nullptr;
PictureFn g_picture = nullptr;
ItemDrawFn g_itemDraw = nullptr;
CelDrawFn g_celDraw = nullptr;
struct Small {
	float scale;
	int32_t x, y;  // the item's top left
};
thread_local Small t_small{0.0f, 0, 0};
bool g_smallOn = false;
volatile LONG g_small = 0;
uint32_t g_dimMode = CelModeDim;
thread_local bool t_dim = false;
volatile LONG g_dimmed = 0;
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

uint64_t ItemDrawHook(void* item, uint64_t pos, float scale, DrawAlpha* alpha) noexcept {
	const bool hd = g_hd();
	const bool dim = DimDraw(hd, alpha);
	const bool was = t_dim;
	const Small wasSmall = t_small;
	t_dim = dim;
	if (g_smallOn && SmallDraw(hd, scale)) {
		t_small = {scale, static_cast<int32_t>(pos), static_cast<int32_t>(pos >> 32)};
		InterlockedIncrement(&g_small);
	}
	const uint64_t r = g_itemDraw(item, pos, scale, alpha);
	t_dim = was;
	t_small = wasSmall;
	return r;
}

// 0x6bbad0 and 0x6bbac0 as D2R has them, and their answers inside a small draw
uint32_t OwnScaleOn() noexcept {
	const auto* on = *reinterpret_cast<const uint32_t* const volatile*>(g_base + SpriteScaleOnRefRva);
	return on[1] != 0 ? on[0] : 0;
}

uint32_t SpriteScaleOnHook() noexcept {
	const uint32_t own = OwnScaleOn();
	return t_small.scale > 0.0f && own == 0 ? 1 : own;
}

uint32_t SpriteScaleHook() noexcept {
	const uint32_t own = *reinterpret_cast<const volatile uint32_t*>(g_base + SpriteScaleValueRva);
	return t_small.scale > 0.0f ? SpriteScale(own, OwnScaleOn() != 0, t_small.scale) : own;
}

// 0x656020's own arguments are four registers and stack dwords (the mode the first of them); eight are passed on
uint64_t CelDrawHook(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t mode, uint64_t f, uint64_t g, uint64_t h) noexcept {
	if (t_dim) {
		const uint32_t m = CelMode(static_cast<uint32_t>(mode), true, g_dimMode);
		if (m != static_cast<uint32_t>(mode)) {
			InterlockedIncrement(&g_dimmed);
			mode = (mode & 0xffffffff00000000ull) | m;
		}
	}
	if (t_small.scale > 0.0f) {
		b = (b & 0xffffffff00000000ull) | static_cast<uint32_t>(SmallPlace(static_cast<int32_t>(b), t_small.x, t_small.scale));
		c = (c & 0xffffffff00000000ull) | static_cast<uint32_t>(SmallPlace(static_cast<int32_t>(c), t_small.y, t_small.scale));
	}
	return g_celDraw(a, b, c, d, mode, f, g, h);
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
	if (GetEnvironmentVariableA("MXL_ROTWSTASH_DIM", env, sizeof(env)) > 0 && env[0] >= '0' && env[0] <= '8' && env[1] == '\0') {
		g_dimMode = static_cast<uint32_t>(env[0] - '0');
	}
#endif
	const bool same = std::memcmp(image + HdCheckCallRva, HdCheckCall, sizeof(HdCheckCall)) == 0 &&
	                  std::memcmp(image + HdModeRva, HdModeCode, sizeof(HdModeCode)) == 0 &&
	                  std::memcmp(image + RotwGameRva, RotwGameCode, sizeof(RotwGameCode)) == 0 &&
	                  std::memcmp(image + PadRva, Pad, sizeof(Pad)) == 0 &&
	                  std::memcmp(image + ItemPictureRva, ItemPictureEntry, sizeof(ItemPictureEntry)) == 0;
	const bool dimSame = std::memcmp(image + ItemDrawRva, ItemDrawEntry, sizeof(ItemDrawEntry)) == 0 &&
	                     std::memcmp(image + CelDrawRva, CelDrawEntry, sizeof(CelDrawEntry)) == 0 &&
	                     std::memcmp(image + SlotPlaceholderDrawCall, SlotPlaceholderDraw, sizeof(SlotPlaceholderDraw)) == 0;
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
	// the empty slots' dimming: the cel draw first (inert while nothing is noted), then the item draw that notes
	bool dim = ok && dimSame &&
	           context->InstallInlineHook(CelDrawRva, CelDrawEntry, sizeof(CelDrawEntry), reinterpret_cast<void*>(&CelDrawHook),
	                                      reinterpret_cast<void**>(&g_celDraw));
	// the small items: both getters replaced while nothing is noted yet (they answer as D2R's), then the item draw notes
	const bool smallSame = std::memcmp(image + SpriteScaleRva, SpriteScaleCode, sizeof(SpriteScaleCode)) == 0 &&
	                       std::memcmp(image + SpriteScaleOnRva, SpriteScaleOnCode, sizeof(SpriteScaleOnCode)) == 0;
	if (dim && smallSame) {
		const AbsJump on = AbsJumpBytes(reinterpret_cast<uint64_t>(&SpriteScaleOnHook));
		const AbsJump value = AbsJumpBytes(reinterpret_cast<uint64_t>(&SpriteScaleHook));
		g_smallOn = context->PatchBytes(SpriteScaleOnRva, SpriteScaleOnCode, sizeof(on.bytes), on.bytes, sizeof(on.bytes)) &&
		            context->PatchBytes(SpriteScaleRva, SpriteScaleCode, sizeof(value.bytes), value.bytes, sizeof(value.bytes));
	}
	dim = dim && context->InstallInlineHook(ItemDrawRva, ItemDrawEntry, sizeof(ItemDrawEntry), reinterpret_cast<void*>(&ItemDrawHook),
	                                        reinterpret_cast<void**>(&g_itemDraw));
	std::snprintf(report, reportSize, "rotwstash %s: the stash wires its RotW pages in classic graphics in %s (init 0x23b1b0, HD check "
	              "0x23b204); classic item pictures without a draw record skipped (0x154ac0); empty slots dimmed in classic %s "
	              "(0x15bb80 / 0x656020, mode %u); small items in classic %s (0x6bbac0 / 0x6bbad0)",
	              ok ? "on" : "FAILED", ModeName(g_mode), dim ? "on" : dimSame ? "FAILED" : "off (bytes differ)", g_dimMode,
	              dim && g_smallOn ? "on" : !smallSame ? "off (bytes differ)" : "FAILED");
	return ok;
}

void RotwStashState(RotwStashCounts* out) noexcept {
	out->inits = g_inits;
	out->classicWired = g_wired;
	out->classicLeft = g_left;
	out->skipped = g_skipped;
	out->dimmed = g_dimmed;
	out->shrunk = g_small;
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

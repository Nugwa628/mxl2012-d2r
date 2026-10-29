// The Apple's item spell (docs/bugs.md #499, docs/plugin-plan.md section 25, off word appleuse).
//
// Median XL 2012's Apple (`dog`, misc pSpell 10) runs 1.13c's item spell 10: cast skill 47 (`Apple Healing Spell`: 10 minutes of
// life regeneration and four class synergy stats) on the user, level 1. D2R's pSpell 10 is its Book of Skill, whose check refuses
// the Apple ("I can't", the Apple stays). D2R reaches pSpell 10's check and use only through two table slots (apple_use_logic.h);
// the part puts its own functions there and calls D2R's for the Book (`ass `):
//  - check (slot 7, D2R `0x5806f0`): any other item passes, as in 1.14d (its entry 10 has no check);
//  - use (slot 10, D2R `0x580750`): any other item casts skill 47 with D2R's item-event casts, the same two branches as 1.14d
//    `0x5bf170`: on the user's target unit (`0x48fe20`) with `0x5896e0` (1.14d `0x5fdca0`), else at the user's position with
//    `0x589820` (1.14d `0x5fdd60`). It returns 1, so D2R's use path (`0x581680`) uses the item up as it does the Book.
#include "apple_use.h"

#include "apple_use_logic.h"
#include "d2r.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>

namespace {

using d2r::At;
using d2r::Game;
using d2r::Unit;

constexpr uint64_t CheckTable = 0x1d3ea30;    // item-spell checks, 11 entries
constexpr uint64_t UseTable = 0x1d3ea90;      // item-spell uses, 16 entries
constexpr uint64_t RvaBookCheck = 0x5806f0;   // slot 7: Radament's book flag (quest 9 bit 5) set, else "I can't"
constexpr uint64_t RvaBookUse = 0x580750;     // slot 10: +1 skill point (stat 5), the flag, the sound
constexpr uint64_t RvaUnitClass = 0x349860;   // (unit, file, line) -> class id
constexpr uint64_t RvaItemRecord = 0x314110;  // (dataFlag, class id) -> items record (+0x80 code)
constexpr uint64_t RvaTarget = 0x48fe20;      // (game, unit) -> the unit's target unit, null for none or itself
constexpr uint64_t RvaCastOnUnit = 0x5896e0;  // (unit, skill, level, target, flag) -> non-zero when cast; item-event cast
constexpr uint64_t RvaCastAt = 0x589820;      // (unit, skill, level, x, y, flag) -> non-zero when cast
constexpr uint64_t RvaUnitX = 0x34b8f0;       // (unit): the two position words 0x583b30 passes to 0x589820, in that order
constexpr uint64_t RvaUnitY = 0x34b940;
constexpr int ItemCode = 0x80;

using ItemSpellFn = bool (*)(Game* game, Unit* user, Unit* item);
using UnitClassFn = int32_t (*)(Unit*, const char*, int32_t);
using ItemRecordFn = const uint8_t* (*)(uint32_t, int32_t);
using TargetFn = Unit* (*)(Game*, Unit*);
using CastOnUnitFn = int32_t (*)(Unit*, int32_t, int32_t, Unit*, int32_t);
using CastAtFn = int32_t (*)(Unit*, int32_t, int32_t, int32_t, int32_t, int32_t);
using UnitWordFn = int32_t (*)(Unit*);

uint64_t g_base = 0;
ItemSpellFn g_bookCheck = nullptr;
ItemSpellFn g_bookUse = nullptr;
volatile LONG g_casts = 0;
volatile LONG g_refused = 0;
volatile LONG g_books = 0;

template <typename F>
auto Fn(uint64_t rva) noexcept -> F {
	return reinterpret_cast<F>(g_base + rva);
}

auto CodeOf(Game* game, Unit* item) noexcept -> uint32_t {
	if (game == nullptr || item == nullptr || At<int32_t>(item, d2r::UnitType) != 4) {
		return 0;
	}
	const uint8_t* rec = Fn<ItemRecordFn>(RvaItemRecord)(d2r::DataFlag(game), Fn<UnitClassFn>(RvaUnitClass)(item, "apple_use", __LINE__));
	return rec != nullptr ? At<uint32_t>(rec, ItemCode) : 0U;
}

auto CheckHook(Game* game, Unit* user, Unit* item) noexcept -> bool {
	if (user != nullptr && apple_use::RunsApple(CodeOf(game, item))) {
		return true;
	}
	return g_bookCheck(game, user, item);
}

auto UseHook(Game* game, Unit* user, Unit* item) noexcept -> bool {
	if (user == nullptr || !apple_use::RunsApple(CodeOf(game, item))) {
		InterlockedIncrement(&g_books);
		return g_bookUse(game, user, item);
	}
	int32_t cast = 0;
	if (Unit* target = Fn<TargetFn>(RvaTarget)(game, user)) {
		cast = Fn<CastOnUnitFn>(RvaCastOnUnit)(user, apple_use::AppleSkill, apple_use::AppleLevel, target, apple_use::CastFlag);
	} else {
		const int32_t x = Fn<UnitWordFn>(RvaUnitX)(user);
		const int32_t y = Fn<UnitWordFn>(RvaUnitY)(user);
		cast = Fn<CastAtFn>(RvaCastAt)(user, apple_use::AppleSkill, apple_use::AppleLevel, x, y, apple_use::CastFlag);
	}
	InterlockedIncrement(cast != 0 ? &g_casts : &g_refused);
	return true;  // used up either way, as 1.14d's caller did; a false answer would only add D2R's SkillItem.cpp verify line
}

}  // namespace

auto InstallAppleUse(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int {
	g_base = context->exeBase;
	g_bookCheck = reinterpret_cast<ItemSpellFn>(g_base + RvaBookCheck);
	g_bookUse = reinterpret_cast<ItemSpellFn>(g_base + RvaBookUse);
	struct Slot {
		uint64_t at, d2r;
		ItemSpellFn replacement;
	};
	const Slot slots[] = {{CheckTable + apple_use::CheckSlot * 8, RvaBookCheck, &CheckHook},
	                      {UseTable + apple_use::UseSlot * 8, RvaBookUse, &UseHook}};
	bool ok[2] = {};
	for (int i = 0; i < 2; ++i) {
		const uint64_t have = *reinterpret_cast<const volatile uint64_t*>(g_base + slots[i].at);
		// Only when the slot still holds D2R's own function (the expected old value of the write).
		ok[i] = have == g_base + slots[i].d2r &&
		        context->PatchWriteU64(slots[i].at, &have, sizeof(have), reinterpret_cast<uint64_t>(slots[i].replacement));
	}
	std::snprintf(report, reportSize, "pSpell 10 items other than the Book of Skill cast skill %d (Apple Healing Spell) as 1.13c (check slot 7%s, use slot 10%s)",
	              apple_use::AppleSkill, ok[0] ? "" : " FAILED", ok[1] ? "" : " FAILED");
	return (ok[0] ? 1 : 0) + (ok[1] ? 1 : 0);
}

void AppleUseCounts(long* casts, long* refused, long* books) noexcept {
	*casts = g_casts;
	*refused = g_refused;
	*books = g_books;
}

// Carry1 duplicates: more copies of one carry1 unique may be carried, one copy gives its bonus (off word charmdup;
// docs/d2r-addresses.md section 22c, docs/bundled-plugins.md "CharmInv").
//
// Median XL 2012's carry1 uniques (unique charms, relics, quest charms) give their bonus once per character. D2R refuses the second
// copy of one of them in its carry test (0x473960: the build gives each carry1 row its own number, txt_migrate.py carry_numbers),
// so a player could not pick up a second copy to trade. With the part:
//  - carry test 0x473960 (item, uniques, uniquesEnd, bases, basesEnd) gets an empty unique range: the carry1 comparison is left
//    out, the base half (items record +0x13a) is kept;
//  - requirement check 0x36bc50 (item, unit, equipping, &str, &dex, &lvl, x; hooked by mercequip, this part adds a veto to that hook,
//    or hooks it itself when mercequip is off) answers false for a carry1 unique stored in the
//    backpack or the charm area of the custom page (page 6) of `unit` that is not the active copy of its unique, and for one on
//    page 6 outside the charm area (charm_dup_logic.h): D2R then treats it as an item whose requirements are not met. The charm
//    area is the whole page with CharmInv, invtabs' charm tab when invtabs.dll exports InvTabsCharmTab (docs/invtabs.md). The
//    server's refresh 0x470ca0 merges a stored charm's stats only when this passes (0x475760), and the client grid draws such
//    an item red;
//  - refresh 0x470ca0 (game, player, x): first, a copy whose stats are merged but that is no longer the active one has its stat
//    list detached from the player (0x2f8290; in the game neither the equipped-item sequence NOEQUIP + 0x475020 nor 0x2f81a0
//    with bType 0 removed them); then D2R's refresh merges the active copy. The client's refresh 0x1c9610 (unit), which runs
//    after the item packets and keeps the client's copy of the stats (the character sheet), gets the same step. D2R calls the refresh after every place / move / pickup, identify, level-up, load.
// Nothing is written into the items: no flag, no stat, no position.
#include "charm_dup.h"

#include "charm_dup_logic.h"
#include "d2r.h"
#include "merc_equip.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

using d2r::At;
using d2r::Game;
using d2r::Unit;

constexpr uint64_t RvaCompareSlot = 0x3e2abb0; // slot of thunk 0x3e2b556 (ff 25): the carry1 record comparison, D2RCore's
constexpr uint64_t RvaCompareThunk = 0x3e2b556;
constexpr uint64_t RvaCarryUnique = 0x473960;  // (item, u16* uniques, u16* uniquesEnd, entry* bases, entry* basesEnd) -> refuse
constexpr uint64_t RvaRequirements = 0x36bc50; // (item, unit, equipping, int* str, int* dex, int* lvl) -> BOOL
constexpr uint64_t RvaRefresh = 0x470ca0;      // (game, player, x): re-merges the stats of usable items
constexpr uint64_t RvaClientRefresh = 0x1c9610; // (unit): the client's copy of it (D2Client Item.cpp), after item packets
constexpr uint64_t RvaInventory = 0x34a360;    // (unit, file, line) -> inventory
constexpr uint64_t RvaInvFirst = 0x388c10;     // (inventory) -> first item
constexpr uint64_t RvaInvNext = 0x38aba0;      // (item) -> next item
constexpr uint64_t RvaItemData = 0x34a500;     // (item) -> item data: +0 quality, +0x18 flags, +0x34 unique index
constexpr uint64_t RvaItemLocation = 0x382d20; // (int32 location[4], item): unit id, page, packed x | y << 16
constexpr uint64_t RvaItemPage = 0x36cfe0;     // (item) -> page byte
constexpr uint64_t RvaUnitDataFlag = 0x34a0e0; // (unit) -> data flag byte
constexpr uint64_t RvaUniqueRecord = 0x194320; // (dataFlag, unique index) -> uniqueitems record (+0x30 carry1)
constexpr uint64_t RvaMergedList = 0x2f8120;   // (item, int* out) -> non-null while the item's stats are merged
constexpr uint64_t RvaDetach = 0x2f8290;       // (target, item): takes the item's stat list out of the target

constexpr int UnitId = 0x08, UnitMode = 0x0c;
constexpr int ItemDataQuality = 0x00, ItemDataIndex = 0x34;
constexpr int UniqueCarry1 = 0x30;
constexpr int32_t QualityUnique = 7;
constexpr size_t MaxCopies = 128;

// Entry bytes checked before hooking (D2R 3.3 build 93847).
constexpr uint8_t CarryEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x08, 0x48, 0x89, 0x6c, 0x24, 0x10, 0x48, 0x89, 0x74, 0x24, 0x18};
constexpr uint8_t ReqEntry[] = {0x4c, 0x89, 0x4c, 0x24, 0x20, 0x44, 0x89, 0x44, 0x24, 0x18, 0x55, 0x56, 0x57, 0x48, 0x83, 0xec, 0x60};
constexpr uint8_t RefreshEntry[] = {0x44, 0x89, 0x44, 0x24, 0x18, 0x57, 0x41, 0x57, 0x48, 0x81, 0xec, 0x88, 0x00, 0x00, 0x00};
constexpr uint8_t ClientRefreshEntry[] = {0x40, 0x53, 0x48, 0x83, 0xec, 0x70};  // push rbx; sub rsp, 0x70 (next: rip-relative)

using CarryFn = bool (*)(Unit*, uint16_t*, uint16_t*, void*, void*);
using CompareFn = bool (*)(const uint8_t*, const uint8_t*);
using ReqFn = uint64_t (*)(Unit*, Unit*, int32_t, int32_t*, int32_t*, int32_t*, int32_t);
using RefreshFn = void (*)(Game*, Unit*, int32_t);
using ClientRefreshFn = void (*)(Unit*);
using InventoryFn = void* (*)(Unit*, const char*, int32_t);
using InvFirstFn = Unit* (*)(void*);
using InvNextFn = Unit* (*)(Unit*);
using ItemDataFn = uint8_t* (*)(Unit*);
using ItemLocationFn = int32_t* (*)(int32_t*, Unit*);
using ItemByteFn = uint8_t (*)(Unit*);
using RecordFn = const uint8_t* (*)(uint32_t, int32_t);
using MergedFn = void* (*)(Unit*, int32_t*);
using DetachFn = void (*)(Unit*, Unit*);

uint64_t g_base = 0;
CarryFn g_carry = nullptr;
CompareFn g_compare = nullptr;
volatile LONG g_compares = 0;     // carry1 comparisons answered "not the same"
ReqFn g_req = nullptr;
RefreshFn g_refresh = nullptr;
ClientRefreshFn g_clientRefresh = nullptr;
volatile LONG g_carryPassed = 0;   // carry tests that ran without the unique half
volatile LONG g_carryRefused = 0;  // of those, refused all the same (the base half, items record +0x13a)
volatile LONG g_inactive = 0;      // requirement checks answered "not met" for an inactive copy
volatile LONG g_disabled = 0;      // merged copies taken out by the refresh

template <typename F>
auto Fn(uint64_t rva) noexcept -> F {
	return reinterpret_cast<F>(g_base + rva);
}

// The carry1 unique index of a stored item on a counting page, or -1.
auto Carry1Index(Unit* item) noexcept -> int32_t {
	if (item == nullptr || At<int32_t>(item, d2r::UnitType) != 4 || At<int32_t>(item, UnitMode) != 0) {
		return -1;
	}
	const uint8_t* data = Fn<ItemDataFn>(RvaItemData)(item);
	if (data == nullptr || At<int32_t>(data, ItemDataQuality) != QualityUnique) {
		return -1;
	}
	if (!charm_dup::CountingPage(Fn<ItemByteFn>(RvaItemPage)(item))) {
		return -1;
	}
	const int32_t index = At<int32_t>(data, ItemDataIndex);
	if (index < 0) {
		return -1;
	}
	const uint8_t* rec = Fn<RecordFn>(RvaUniqueRecord)(Fn<ItemByteFn>(RvaUnitDataFlag)(item), index);
	return rec != nullptr && charm_dup::IsCarry1(At<int32_t>(rec, UniqueCarry1)) ? index : -1;
}

auto CopyOf(Unit* item, int32_t index) noexcept -> charm_dup::Copy {
	int32_t loc[8] = {};
	Fn<ItemLocationFn>(RvaItemLocation)(loc, item);
	return {At<uint32_t>(item, UnitId), index, static_cast<int32_t>(Fn<ItemByteFn>(RvaItemPage)(item)), loc[2] & 0xffff,
	        (loc[2] >> 16) & 0xffff};
}

// invtabs (docs/invtabs.md) owns the custom page at 16 x 16 and exports its charm tab's rectangle; looked up when the game first
// asks (every plugin is loaded by then) and kept: absent (CharmInv) = the whole custom page is charm inventory.
using CharmTabFn = int(__cdecl*)(int*, int*, int*, int*);

auto CharmTab() noexcept -> CharmTabFn {
	static const CharmTabFn fn = []() noexcept -> CharmTabFn {
		HMODULE invtabs = GetModuleHandleW(L"invtabs.dll");
		return invtabs != nullptr ? reinterpret_cast<CharmTabFn>(GetProcAddress(invtabs, "InvTabsCharmTab")) : nullptr;
	}();
	return fn;
}

auto CharmAreaNow() noexcept -> charm_dup::CharmArea {
	const CharmTabFn fn = CharmTab();
	if (fn == nullptr) {
		return {};
	}
	int x = 0, y = 0, w = 0, h = 0;
	const int found = fn(&x, &y, &w, &h);
	return charm_dup::TabArea(found, x, y, w, h);
}

auto PlaceOf(const charm_dup::Copy& copy, const charm_dup::CharmArea& area) noexcept -> charm_dup::Place {
	return charm_dup::PlaceOf(copy.page, copy.x, copy.y, area);
}

// True when `item` is in `owner`'s inventory list.
auto Carries(Unit* owner, Unit* item) noexcept -> bool {
	void* inv = Fn<InventoryFn>(RvaInventory)(owner, "charm_dup", __LINE__);
	int guard = 0;
	for (Unit* it = inv != nullptr ? Fn<InvFirstFn>(RvaInvFirst)(inv) : nullptr; it != nullptr && guard++ < 4000; it = Fn<InvNextFn>(RvaInvNext)(it)) {
		if (it == item) {
			return true;
		}
	}
	return false;
}

// The copies of `index` that `owner` carries in the backpack or the charm area; `items[i]` is the unit of `copies[i]`.
auto Collect(Unit* owner, int32_t index, const charm_dup::CharmArea& area, charm_dup::Copy* copies, Unit** items) noexcept -> size_t {
	void* inv = Fn<InventoryFn>(RvaInventory)(owner, "charm_dup", __LINE__);
	size_t n = 0;
	int guard = 0;
	for (Unit* it = inv != nullptr ? Fn<InvFirstFn>(RvaInvFirst)(inv) : nullptr; it != nullptr && guard++ < 4000 && n < MaxCopies;
	     it = Fn<InvNextFn>(RvaInvNext)(it)) {
		if (Carry1Index(it) == index) {
			const charm_dup::Copy copy = CopyOf(it, index);
			if (PlaceOf(copy, area) == charm_dup::Place::Charm) {
				copies[n] = copy;
				items[n] = it;
				++n;
			}
		}
	}
	return n;
}

// True when `item` is a carry1 copy in `owner`'s backpack or charm area that is not the active copy of its unique, or a carry1
// copy on the custom page outside the charm area (another invtabs tab: not charm inventory, never gives its bonus).
auto IsInactiveCopy(Unit* item, Unit* owner) noexcept -> bool {
	if (owner == nullptr || At<int32_t>(owner, d2r::UnitType) != 0) {
		return false;
	}
	const int32_t index = Carry1Index(item);
	if (index < 0) {
		return false;
	}
	const charm_dup::CharmArea area = CharmAreaNow();
	const charm_dup::Place place = PlaceOf(CopyOf(item, index), area);
	if (place != charm_dup::Place::Charm) {
		return place == charm_dup::Place::OutsideTab && Carries(owner, item);
	}
	charm_dup::Copy copies[MaxCopies];
	Unit* items[MaxCopies];
	const size_t n = Collect(owner, index, area, copies, items);
	if (n < 2) {
		return false;
	}
	const int active = charm_dup::PickActive(copies, n);
	bool mine = false;
	for (size_t i = 0; i < n; ++i) {
		mine = mine || items[i] == item;
	}
	return mine && active >= 0 && items[active] != item;
}

// The carry1 comparison (0x473960's unique half, D2RCore's custom page placement, the cube executor 0x5277f2): two carry1
// records never count as "the same", so a copy is never refused for another copy.
auto CompareHook(const uint8_t* a, const uint8_t* b) noexcept -> bool {
	if (a != nullptr && charm_dup::IsCarry1(At<int32_t>(a, UniqueCarry1))) {
		InterlockedIncrement(&g_compares);
		return false;
	}
	return g_compare(a, b);
}

// The slot written directly (VirtualProtect), for a loader that refuses the data write (as stash_tip.cpp).
auto WriteSlot(uint64_t* slot, uint64_t value) noexcept -> bool {
	DWORD old = 0;
	if (!VirtualProtect(slot, sizeof(uint64_t), PAGE_READWRITE, &old)) {
		return false;
	}
	*slot = value;
	VirtualProtect(slot, sizeof(uint64_t), old, &old);
	return true;
}

auto CarryHook(Unit* item, uint16_t* uniques, uint16_t* uniquesEnd, void* bases, void* basesEnd) noexcept -> bool {
	(void)uniquesEnd;
	InterlockedIncrement(&g_carryPassed);
	const bool refuse = g_carry(item, uniques, uniques, bases, basesEnd);
	if (refuse) {
		InterlockedIncrement(&g_carryRefused);
	}
	return refuse;
}

// "Not met" for an inactive copy (asked after D2R said "met").
auto Refuses(void* item, void* unit, int32_t equipping) noexcept -> bool {
	if (equipping == 0 && IsInactiveCopy(static_cast<Unit*>(item), static_cast<Unit*>(unit))) {
		InterlockedIncrement(&g_inactive);
		return true;
	}
	return false;
}

// Own hook, only when mercequip's hook on the same entry is not in.
auto ReqHook(Unit* item, Unit* unit, int32_t equipping, int32_t* str, int32_t* dex, int32_t* lvl, int32_t a7) noexcept -> uint64_t {
	const uint64_t ok = g_req(item, unit, equipping, str, dex, lvl, a7);
	return (ok & 0xff) != 0 && Refuses(item, unit, equipping) ? 0 : ok;
}

// Detaches the stat list of every copy of `player` that is merged but no longer the active one (as the level-up re-merge
// 0x46f220 detaches each item before merging it again); the charm loop of the refresh that follows merges the active copy.
void DetachInactive(Unit* player) noexcept {
	if (player == nullptr || At<int32_t>(player, d2r::UnitType) != 0) {
		return;
	}
	void* inv = Fn<InventoryFn>(RvaInventory)(player, "charm_dup", __LINE__);
	int guard = 0;
	for (Unit* it = inv != nullptr ? Fn<InvFirstFn>(RvaInvFirst)(inv) : nullptr; it != nullptr && guard++ < 4000;) {
		Unit* next = Fn<InvNextFn>(RvaInvNext)(it);
		if (Carry1Index(it) >= 0 && Fn<MergedFn>(RvaMergedList)(it, nullptr) != nullptr && IsInactiveCopy(it, player)) {
			Fn<DetachFn>(RvaDetach)(player, it);
			InterlockedIncrement(&g_disabled);
		}
		it = next;
	}
}

void RefreshHook(Game* game, Unit* player, int32_t x) noexcept {
	if (game != nullptr) {
		DetachInactive(player);
	}
	g_refresh(game, player, x);
}

// The client keeps its own copy of the item stats (the character sheet draws from it): the same step before its refresh.
void ClientRefreshHook(Unit* unit) noexcept {
	DetachInactive(unit);
	g_clientRefresh(unit);
}

}  // namespace

auto InstallCharmDup(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int {
	g_base = context->exeBase;
	constexpr uint8_t Thunk[] = {0xff, 0x25};
	const auto* base = reinterpret_cast<const uint8_t*>(context->exeBase);
	auto* slot = reinterpret_cast<uint64_t*>(context->exeBase + RvaCompareSlot);
	const uint64_t current = std::memcmp(base + RvaCompareThunk, Thunk, sizeof(Thunk)) == 0 ? *slot : 0;
	bool compare = false;
	if (current != 0) {
		g_compare = reinterpret_cast<CompareFn>(current);
		const auto hook = reinterpret_cast<uint64_t>(&CompareHook);
		compare = context->PatchWriteU64(RvaCompareSlot, &current, sizeof(current), hook) || WriteSlot(slot, hook);
	}
	const bool carry = context->InstallInlineHook(RvaCarryUnique, CarryEntry, sizeof(CarryEntry), reinterpret_cast<void*>(&CarryHook),
	                                              reinterpret_cast<void**>(&g_carry));
	// mercequip hooks 0x36bc50 first (D2RLoader takes one hook per entry): ride on it when it is in
	const bool viaMerc = MercEquipAddRequirementFilter(&Refuses);
	const bool req = viaMerc || context->InstallInlineHook(RvaRequirements, ReqEntry, sizeof(ReqEntry), reinterpret_cast<void*>(&ReqHook),
	                                                       reinterpret_cast<void**>(&g_req));
	const bool refresh = context->InstallInlineHook(RvaRefresh, RefreshEntry, sizeof(RefreshEntry), reinterpret_cast<void*>(&RefreshHook),
	                                                reinterpret_cast<void**>(&g_refresh));
	const bool client = context->InstallInlineHook(RvaClientRefresh, ClientRefreshEntry, sizeof(ClientRefreshEntry),
	                                               reinterpret_cast<void*>(&ClientRefreshHook), reinterpret_cast<void**>(&g_clientRefresh));
	std::snprintf(report, reportSize,
	              "carry1 duplicates carried, one copy active (charm page or tab first, then top-left): compare slot 0x3e2abb0%s, carry test 0x473960%s, requirements 0x36bc50%s%s, refresh 0x470ca0%s, client refresh 0x1c9610%s",
	              compare ? "" : " FAILED", carry ? "" : " FAILED", viaMerc ? " (through mercequip's hook)" : "", req ? "" : " FAILED", refresh ? "" : " FAILED",
	              client ? "" : " FAILED");
	return (compare ? 1 : 0) + (carry ? 1 : 0) + (req ? 1 : 0) + (refresh ? 1 : 0) + (client ? 1 : 0);
}

void CharmDupArea(char* text, size_t size) noexcept {
	const charm_dup::CharmArea area = CharmAreaNow();
	if (area.wholePage) {
		std::snprintf(text, size, "the whole custom page (%s)", CharmTab() != nullptr ? "invtabs has no charm tab" : "no invtabs");
	} else {
		std::snprintf(text, size, "invtabs charm tab %dx%d at %d,%d", area.w, area.h, area.x, area.y);
	}
}

void CharmDupCounts(long* carryPassed, long* inactive, long* disabled, long* carryRefused) noexcept {
	*carryPassed = g_carryPassed + g_compares;
	*carryRefused = g_carryRefused;
	*inactive = g_inactive;
	*disabled = g_disabled;
}

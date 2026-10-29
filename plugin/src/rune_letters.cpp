// The rune letters of a runeword's tooltip (docs/bugs.md #334, docs/plugin-plan.md section 19; off word runeletter).
//
// D2R looks the gems record's `letter` cell up as a key of its own string namespace and, under D2RLoader, draws "Missing
// string" when there is none: Median XL 2012's Great Runes r34-r56 (Sha .. Shaad) have no key there and the 5-character cell
// cannot hold a `mxl2012:` one, and No / On / Xar are other D2R keys ("NO", "ON", "Ornate Plate"). 1.14d draws the cell
// itself (rune_letters_logic.h has the reading). The key lookup D2R calls through the thunk 0x3e2b736 is replaced in its
// import slot by a pass-through that changes the answer only for the letter line's call (return address 0x2c29df): there a
// cell that is not D2R's r01L..r33L, or whose lookup has no text, reads as the cell. Every other lookup goes to D2R as it is.
#include "rune_letters.h"

#include "rune_letters_logic.h"

#include <windows.h>
#include <intrin.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

struct StrView {  // the lookup's argument: rcx -> {text, length} (every caller of the thunk sets only rcx)
	const char* ptr;
	size_t len;
};
using LookupFn = const char* (*)(const StrView*);

LookupFn g_original = nullptr;
uintptr_t g_letterReturn = 0;
volatile LONG g_drawn = 0;
volatile LONG g_kept = 0;
thread_local char t_cell[rune_letters::CellMax];
constexpr char MissingKey[] = "strMissingString";

const char* LookupHook(const StrView* key) {
	const char* text = g_original(key);
	if (reinterpret_cast<uintptr_t>(_ReturnAddress()) != g_letterReturn || key == nullptr) {
		return text;
	}
	const size_t len = key->len < rune_letters::CellMax ? key->len : rune_letters::CellMax - 1;
	const char* missing = nullptr;
	if (rune_letters::IsD2RLetterKey(key->ptr, len)) {
		const StrView missingKey{MissingKey, sizeof(MissingKey) - 1};
		missing = g_original(&missingKey);
	}
	if (!rune_letters::UseCell(key->ptr, len, text, missing)) {
		InterlockedIncrement(&g_kept);
		return text;
	}
	rune_letters::CopyCell(t_cell, sizeof(t_cell), key->ptr, len);
	InterlockedIncrement(&g_drawn);
	return t_cell;
}

// The slot written directly (VirtualProtect), for a loader that refuses the data write.
auto WriteSlot(uint64_t* slot, uint64_t value) noexcept -> bool {
	DWORD old = 0;
	if (!VirtualProtect(slot, sizeof(uint64_t), PAGE_READWRITE, &old)) {
		return false;
	}
	*slot = value;
	VirtualProtect(slot, sizeof(uint64_t), old, &old);
	return true;
}

}  // namespace

auto InstallRuneLetters(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	using namespace rune_letters;
	const auto* base = reinterpret_cast<const uint8_t*>(context->exeBase);
	const bool same = std::memcmp(base + ThunkRva, Thunk, sizeof(Thunk)) == 0 && std::memcmp(base + SiteRva, Site, SiteSize) == 0;
	auto* slot = reinterpret_cast<uint64_t*>(context->exeBase + SlotRva);
	const uint64_t current = same ? *slot : 0;
	const char* how = "";
	bool ok = false;
	if (same && current != 0) {
		g_original = reinterpret_cast<LookupFn>(current);
		g_letterReturn = static_cast<uintptr_t>(context->exeBase + ReturnRva);
		const auto hook = reinterpret_cast<uint64_t>(&LookupHook);
		if (context->PatchWriteU64(SlotRva, &current, sizeof(current), hook)) {
			ok = true;
			how = "loader patch";
		} else if (WriteSlot(slot, hook)) {
			ok = true;
			how = "slot written";
		}
	}
	if (ok) {
		std::snprintf(report, reportSize, "on: rune letters without a D2R key drawn from the gems cell, as 1.14d (lookup 0x3e2b736 at 0x2c29da, %s)", how);
	} else {
		std::snprintf(report, reportSize, "off: %s", !same ? "bytes differ at 0x2c29ae / 0x3e2b736, left as D2R" : (current == 0 ? "lookup slot empty" : "slot write refused"));
	}
	return ok;
}

void RuneLetterCounts(long* drawn, long* kept) noexcept {
	*drawn = g_drawn;
	*kept = g_kept;
}

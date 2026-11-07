// The hover text of the RotW stash's advanced slots (docs/bugs.md #551; off word stashtip).
//
// stash_tip_logic.h has the call: the slot asks the item tooltip builder for the short text (7th argument 1), the name alone. The
// thunk 0x3e2b826's import slot is replaced by a pass-through that clears that flag for the stash slot's call only (return
// address 0x2ce71b), so the slot shows the backpack's whole description. Every other tooltip goes to D2RLoader / D2R as it is.
#include "stash_tip.h"

#include "stash_tip_logic.h"

#include <windows.h>
#include <intrin.h>

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

using BuildFn = void* (*)(void* out, void* viewer, void* owner, void* item, uint64_t fifth, uint64_t sixth, uint64_t seventh, void* eighth,
                          void* rect);

BuildFn g_original = nullptr;
uintptr_t g_slotReturn = 0;
std::atomic<long> g_built{0}, g_passed{0};
std::atomic<uint64_t> g_seventh{0};

void* BuildHook(void* out, void* viewer, void* owner, void* item, uint64_t fifth, uint64_t sixth, uint64_t seventh, void* eighth, void* rect) {
	if (reinterpret_cast<uintptr_t>(_ReturnAddress()) != g_slotReturn) {
		g_passed.fetch_add(1, std::memory_order_relaxed);
		return g_original(out, viewer, owner, item, fifth, sixth, seventh, eighth, rect);
	}
	g_seventh.store(seventh & 0xff, std::memory_order_relaxed);
	const stash_tip::Args a = stash_tip::Apply({fifth, sixth, seventh});
	g_built.fetch_add(1, std::memory_order_relaxed);
	return g_original(out, viewer, owner, item, a.fifth, a.sixth, a.seventh, eighth, rect);
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

auto InstallStashTip(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	using namespace stash_tip;
	const auto* base = reinterpret_cast<const uint8_t*>(context->exeBase);
	const bool same = std::memcmp(base + ThunkRva, Thunk, sizeof(Thunk)) == 0 && std::memcmp(base + SiteRva, Site, SiteSize) == 0;
	auto* slot = reinterpret_cast<uint64_t*>(context->exeBase + SlotRva);
	const uint64_t current = same ? *slot : 0;
	const char* how = "";
	bool ok = false;
	if (same && current != 0) {
		g_original = reinterpret_cast<BuildFn>(current);
		g_slotReturn = static_cast<uintptr_t>(context->exeBase + ReturnRva);
		const auto hook = reinterpret_cast<uint64_t>(&BuildHook);
		if (context->PatchWriteU64(SlotRva, &current, sizeof(current), hook)) {
			ok = true;
			how = "loader patch";
		} else if (WriteSlot(slot, hook)) {
			ok = true;
			how = "slot written";
		}
	}
	if (ok) {
		std::snprintf(report, reportSize, "stashtip on: advanced stash slots build the item's whole tooltip (builder 0x3e2b826 at 0x2ce716, %s)", how);
	} else {
		std::snprintf(report, reportSize, "stashtip off: %s", !same ? "bytes differ at 0x2ce6e1 / 0x3e2b826, left as D2R" : (current == 0 ? "builder slot empty" : "slot write refused"));
	}
	return ok;
}

void StashTipStatus(char* out, size_t outSize) noexcept {
	std::snprintf(out, outSize, "slot tooltips %ld, other tooltips passed %ld; last slot call's short flag %llu (built as 0)", g_built.load(),
	              g_passed.load(), static_cast<unsigned long long>(g_seventh.load()));
}

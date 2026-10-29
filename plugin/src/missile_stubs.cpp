// Empty missile function slots (docs/plugin-plan.md section 5, item D).
//
// D2R's client missile tick (0x1ba040) calls table[record +0x28] (0x2358430) for every missile whose pCltDoFunc is below
// the bound at 0x2358a60 (91), with no check for an empty slot; slot 0 and 78-90 are empty, so a missile row with an empty
// pCltDoFunc (= 0) crashes the client with a call through a null pointer. Median XL 2012 has two such rows (stuckarrow,
// footprint). The server hit dispatcher (0x464ac0, table 0x2391030, bound 71 at 0x2391404) does the same for 0 < index <
// bound (61-70 empty); 2012's values stop at 59, but a later remap into a free slot must not leave a gap.
//
// Every empty slot below the bound of both tables gets a function that does nothing and logs the first missile row it
// was called for (an InstallMissileHits clientDoStubs part, as-is); no missile hit functions, phalanx or revive wrap comes over (docs/plugin-plan.md section 11).
#include "missile_stubs.h"

#include "d2r.h"
#include "missile_stubs_logic.h"

#include <windows.h>

#include <array>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <utility>

namespace {

using d2r::At;
using d2r::Game;
using d2r::Unit;

using CltDoFn = int64_t (*)(Unit* missile, float);
using SrvHitFn = int64_t (*)(Game* game, Unit* missile, Unit* target);

const D2RL::PluginContext* g_logContext = nullptr;
std::atomic<uint32_t> g_cltDoSeen[(8192 + 31) / 32];
std::atomic<uint32_t> g_srvHitSeen[(8192 + 31) / 32];
volatile LONG g_cltDoHits = 0;
volatile LONG g_srvHitHits = 0;

// First call per missile row and table is logged.
void NoteEmptySlot(std::atomic<uint32_t>* seen, const char* table, int slot, Unit* missile) noexcept {
	const uint32_t row = missile != nullptr ? At<uint32_t>(missile, d2r::UnitClass) : 0;
	if (row >= 8192) {
		return;
	}
	const uint32_t bit = 1u << (row & 31);
	if ((seen[row >> 5].fetch_or(bit, std::memory_order_relaxed) & bit) == 0 && g_logContext != nullptr) {
		char line[128];
		std::snprintf(line, sizeof(line), "mxl2012-core: missile row %u has %s slot %d, which D2R leaves empty: skipped", row, table, slot);
		g_logContext->LogInfo(line);
	}
}

template <int N>
auto CltDoEmpty(Unit* missile, float) noexcept -> int64_t {
	InterlockedIncrement(&g_cltDoHits);
	NoteEmptySlot(g_cltDoSeen, "client do", N, missile);
	return 0;
}

template <int... N>
constexpr auto CltDoEmptyTable(std::integer_sequence<int, N...>) noexcept {
	return std::array<CltDoFn, sizeof...(N)>{&CltDoEmpty<N>...};
}
const auto g_cltDoEmpty = CltDoEmptyTable(std::make_integer_sequence<int, missile_stubs::CltDoMaxSlots>{});

template <int N>
auto SrvHitEmpty(Game*, Unit* missile, Unit*) noexcept -> int64_t {
	InterlockedIncrement(&g_srvHitHits);
	NoteEmptySlot(g_srvHitSeen, "server hit", N, missile);
	return 0;
}

template <int... N>
constexpr auto SrvHitEmptyTable(std::integer_sequence<int, N...>) noexcept {
	return std::array<SrvHitFn, sizeof...(N)>{&SrvHitEmpty<N>...};
}
const auto g_srvHitEmpty = SrvHitEmptyTable(std::make_integer_sequence<int, missile_stubs::SrvHitMaxSlots>{});

}  // namespace

auto InstallMissileStubs(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	g_logContext = context;
	const uint64_t base = context->exeBase;
	static constexpr uint8_t Empty[8] = {};
	const int32_t cltBound = *reinterpret_cast<const volatile int32_t*>(base + d2r::MissileCltDoBound);
	const int32_t srvBound = *reinterpret_cast<const volatile int32_t*>(base + d2r::SrvHitBound);
	int cltSlots[missile_stubs::CltDoMaxSlots];
	int srvSlots[missile_stubs::SrvHitMaxSlots];
	const int nClt = missile_stubs::EmptySlots(reinterpret_cast<const uint64_t*>(base + d2r::MissileCltDoTable), cltBound, 0,
	                                           missile_stubs::CltDoMaxSlots, cltSlots, missile_stubs::CltDoMaxSlots);
	// Server hit 0 means "no hit function" and is never called.
	const int nSrv = missile_stubs::EmptySlots(reinterpret_cast<const uint64_t*>(base + d2r::SrvHitTable), srvBound, 1,
	                                           missile_stubs::SrvHitMaxSlots, srvSlots, missile_stubs::SrvHitMaxSlots);
	int stubbed = 0, srvStubbed = 0, failed = 0;
	for (int i = 0; i < nClt; ++i) {
		const uint64_t rva = d2r::MissileCltDoTable + static_cast<uint64_t>(cltSlots[i]) * 8;
		++(context->PatchWriteU64(rva, Empty, sizeof(Empty), reinterpret_cast<uint64_t>(g_cltDoEmpty[static_cast<size_t>(cltSlots[i])])) ? stubbed : failed);
	}
	for (int i = 0; i < nSrv; ++i) {
		const uint64_t rva = d2r::SrvHitTable + static_cast<uint64_t>(srvSlots[i]) * 8;
		++(context->PatchWriteU64(rva, Empty, sizeof(Empty), reinterpret_cast<uint64_t>(g_srvHitEmpty[static_cast<size_t>(srvSlots[i])])) ? srvStubbed : failed);
	}
	const bool ok = nClt >= 0 && nSrv >= 0 && failed == 0;
	std::snprintf(report, reportSize, "empty slots skipped: missile client do %d of %d, server hit %d of %d%s", stubbed,
	              static_cast<int>(cltBound), srvStubbed, static_cast<int>(srvBound),
	              ok ? "" : (nClt < 0 || nSrv < 0 ? " FAILED (table bound not as expected, nothing written)" : " FAILED (a slot write)"));
	return ok;
}

void MissileStubHits(long* clientDo, long* serverHit) noexcept {
	*clientDo = g_cltDoHits;
	*serverHit = g_srvHitHits;
}

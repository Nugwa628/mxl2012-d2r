// The larger HD model cache (lane hdscene2; on by default, off word `modelcache`).
//
// D2R's ModelAsset cache holds 2750 models, then asserts (Fog AssetCache.h:187) and grows by half. Median's maps draw their
// classic wall tiles as one small model per tile where D2R has no full-height wall piece (tools/walls_sprite.py), so a long
// session over several of those maps can pass 2750. The patch makes the asset manager's constructor start the cache (its
// capacity and its entry pool) at 8250, and the ModelAssetCache init at renderer start keep that capacity
// (model_cache_logic.h has the instructions). Every byte it touches, and the ones round it, are compared first.
#include "model_cache.h"

#include "model_cache_logic.h"

#include <cstdint>
#include <cstdio>
#include <cstring>

auto InstallModelCache(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	using namespace model_cache;
	const auto* image = reinterpret_cast<const uint8_t*>(context->exeBase);
	const bool same = std::memcmp(image + CapacityRva, CapacitySite, sizeof(CapacitySite)) == 0 &&
	                  std::memcmp(image + ReserveRva, ReserveSite, sizeof(ReserveSite)) == 0 &&
	                  std::memcmp(image + PoolRva, PoolCall, sizeof(PoolCall)) == 0 &&
	                  std::memcmp(image + InitRva, InitSite, sizeof(InitSite)) == 0 &&
	                  std::memcmp(image + InitCallRva, InitCall, sizeof(InitCall)) == 0;
	uint64_t manager = 0;
	std::memcpy(&manager, image + SingletonRva, sizeof(manager));
	bool ok = false;
	if (same) {
		const CapacityBytes capacity = CapacityPatch();
		const ReserveBytes reserve = ReservePatch();
		const InitBytes init = InitPatch();
		ok = context->PatchBytes(ReserveRva, ReserveSite, sizeof(ReserveSite), reserve.bytes, sizeof(reserve.bytes)) &&
		     context->PatchBytes(CapacityRva, CapacitySite, sizeof(CapacitySite), capacity.bytes, sizeof(capacity.bytes)) &&
		     context->PatchBytes(InitRva, InitSite, sizeof(InitSite), init.bytes, sizeof(init.bytes));
	}
	std::snprintf(report, reportSize, "modelcache: HD model cache starts at %u models, D2R %u (0xdfb5b9, 0xdfb61d, 0xf75cc1)%s%s",
	              static_cast<unsigned>(Capacity), static_cast<unsigned>(D2RCapacity),
	              ok ? "" : (same ? " FAILED (patch refused)" : " FAILED (bytes differ, left as D2R)"),
	              manager != 0 ? "; the asset manager was already built, so this session keeps D2R's size" : "");
	return ok && manager == 0;
}

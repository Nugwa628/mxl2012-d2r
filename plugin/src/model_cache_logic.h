// Pure part of the larger HD model cache (model_cache.cpp; unit test plugin/tests/model_cache_test.cpp). Lane hdscene2,
// docs/maps-hd.md "Model cache". No Windows headers, no game calls.
//
// D2R keeps every HD model it has loaded in the render asset manager's ModelAsset cache (Fog AssetCache<ModelAsset, 2750>,
// tools/cache_probe.py: asset manager + 0x26648). When a load finds it full, D2R raises `BC_ASSERT: 0` (Fog AssetCache.h:187,
// "The size of the asset cache has been exceeded!"), grows the capacity by half and goes on (0x68a516: capacity * 1.5 into
// +0x70, the buckets rehashed, then 0x122fee0 reserves the cache's entry pool at +0x78 for the new capacity). Median's wall
// sprites add one model per classic tile a map draws that way, so a session that visits several such maps would reach 2750.
//
// The asset manager is built once, on the first call of its getter 0xe21140 (constructor 0xdf9d40, singleton at 0x34f6480).
// Its constructor sets the ModelAsset cache's capacity and reserves its pool with the same constant:
//   0xdfb5b9  mov qword ptr [rsi+0x266b8], 0xabe     ; cache + 0x70: capacity 2750
//   0xdfb61d  mov edx, 0xabe                         ; the pool reserve's count
//   0xdfb622  lea rcx, [rsi+0x266c0]                 ; cache + 0x78: the pool
//   0xdfb629  call 0x122fee0                         ; reserve
// When the renderer starts (0xe21850), the ModelAssetCache init 0xf75c60 (it reads data/hd/model_lod_desc.bin) runs on the
// same cache and sets its capacity again, before the first model is loaded:
//   0xe218bf  lea rcx, [r15+0x26648]                 ; the ModelAsset cache
//   0xe218cd  call 0xf75c60
//   0xf75cc1  mov qword ptr [rsi+0x70], 0xabe        ; capacity 2750 (the buckets are then sized from it, 0xf768c0)
// The patch writes Capacity into all three immediates, past where D2R's own growth gets after two overflows, so the cache
// never needs to grow (and assert) in a session; the pool is reserved for it once. Every byte is compared first; the patch
// only matters while the singleton is not built yet (at plugin load it is not: the getter runs when the renderer starts).
// Seen in game (lane hdscene2): with only the constructor's two sites patched the live capacity read 2750 (the init's store).
#pragma once

#include <cstddef>
#include <cstdint>

namespace model_cache {

inline constexpr uint32_t D2RCapacity = 2750;
inline constexpr uint32_t Capacity = 3 * D2RCapacity;   // 8250

inline constexpr uint64_t CapacityRva = 0xdfb5b9;
inline constexpr uint8_t CapacitySite[11] = {0x48, 0xc7, 0x86, 0xb8, 0x66, 0x02, 0x00, 0xbe, 0x0a, 0x00, 0x00};
inline constexpr size_t CapacityImm = 7;     // the imm32 inside CapacitySite
inline constexpr uint64_t ReserveRva = 0xdfb61d;
inline constexpr uint8_t ReserveSite[5] = {0xba, 0xbe, 0x0a, 0x00, 0x00};
inline constexpr size_t ReserveImm = 1;
// Compared before writing (read only): the pool's lea and the reserve call right after the count.
inline constexpr uint64_t PoolRva = 0xdfb622;
inline constexpr uint8_t PoolCall[12] = {0x48, 0x8d, 0x8e, 0xc0, 0x66, 0x02, 0x00,  // lea rcx, [rsi+0x266c0]
                                         0xe8, 0xb2, 0x48, 0x43, 0x00};             // call 0x122fee0
inline constexpr uint64_t ReserveFnRva = 0x122fee0;
inline constexpr uint64_t InitRva = 0xf75cc1;
inline constexpr uint8_t InitSite[8] = {0x48, 0xc7, 0x46, 0x70, 0xbe, 0x0a, 0x00, 0x00};   // mov qword ptr [rsi+0x70], 2750
inline constexpr size_t InitImm = 4;
inline constexpr uint64_t InitFnRva = 0xf75c60;
// Compared before writing (read only): the renderer start passes the ModelAsset cache to the init.
inline constexpr uint64_t InitCallRva = 0xe218bf;
inline constexpr uint8_t InitCall[19] = {0x49, 0x8d, 0x8f, 0x48, 0x66, 0x02, 0x00,         // lea rcx, [r15+0x26648]
                                         0x48, 0x8d, 0x15, 0x23, 0x45, 0xfd, 0x00,         // lea rdx, "ModelAssets"
                                         0xe8, 0x8e, 0x43, 0x15, 0x00};                    // call 0xf75c60
inline constexpr uint64_t SingletonRva = 0x34f6480;   // the asset manager, 0 until its getter first runs
inline constexpr uint32_t CacheFieldOffset = 0x266b8;  // asset manager -> ModelAsset cache capacity (cache + 0x70)

constexpr auto Le32(const uint8_t* b) noexcept -> uint32_t {
	return static_cast<uint32_t>(b[0]) | static_cast<uint32_t>(b[1]) << 8 | static_cast<uint32_t>(b[2]) << 16 |
	       static_cast<uint32_t>(b[3]) << 24;
}

struct CapacityBytes {
	uint8_t bytes[sizeof(CapacitySite)];
};
struct ReserveBytes {
	uint8_t bytes[sizeof(ReserveSite)];
};
struct InitBytes {
	uint8_t bytes[sizeof(InitSite)];
};

constexpr void PutLe32(uint8_t* b, uint32_t v) noexcept {
	b[0] = static_cast<uint8_t>(v);
	b[1] = static_cast<uint8_t>(v >> 8);
	b[2] = static_cast<uint8_t>(v >> 16);
	b[3] = static_cast<uint8_t>(v >> 24);
}

// The constructor's two instructions with `capacity` in place of 2750.
constexpr auto CapacityPatch(uint32_t capacity = Capacity) noexcept -> CapacityBytes {
	CapacityBytes out{};
	for (size_t i = 0; i < sizeof(CapacitySite); ++i) {
		out.bytes[i] = CapacitySite[i];
	}
	PutLe32(out.bytes + CapacityImm, capacity);
	return out;
}
constexpr auto ReservePatch(uint32_t capacity = Capacity) noexcept -> ReserveBytes {
	ReserveBytes out{};
	for (size_t i = 0; i < sizeof(ReserveSite); ++i) {
		out.bytes[i] = ReserveSite[i];
	}
	PutLe32(out.bytes + ReserveImm, capacity);
	return out;
}

constexpr auto InitPatch(uint32_t capacity = Capacity) noexcept -> InitBytes {
	InitBytes out{};
	for (size_t i = 0; i < sizeof(InitSite); ++i) {
		out.bytes[i] = InitSite[i];
	}
	PutLe32(out.bytes + InitImm, capacity);
	return out;
}

// D2R's growth from a capacity once it is full: capacity + capacity / 2.
constexpr auto Grown(uint64_t capacity) noexcept -> uint64_t {
	return capacity + (capacity >> 1);
}

}  // namespace model_cache

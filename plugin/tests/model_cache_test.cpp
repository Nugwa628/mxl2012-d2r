// Standalone test of the larger HD model cache patch (model_cache_logic.h; not part of the plugin DLL). Lane hdscene2.
#include "../src/model_cache_logic.h"

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
	using namespace model_cache;
	// D2R's bytes: the capacity store into the cache + 0x70 (0x26648 + 0x70 = 0x266b8) and the reserve count, both 2750
	Check(CapacitySite[0] == 0x48 && CapacitySite[1] == 0xc7 && CapacitySite[2] == 0x86, "mov qword ptr [rsi+disp32], imm32");
	Check(Le32(CapacitySite + 3) == CacheFieldOffset && CacheFieldOffset == 0x26648 + 0x70, "the store goes to the ModelAsset cache's capacity");
	Check(Le32(CapacitySite + CapacityImm) == D2RCapacity && D2RCapacity == 0xabe, "D2R's capacity is 2750");
	Check(ReserveSite[0] == 0xba && Le32(ReserveSite + ReserveImm) == D2RCapacity, "mov edx, 2750");
	Check(ReserveRva + sizeof(ReserveSite) == PoolRva, "the reserve count is right before the pool's lea");
	Check(Le32(PoolCall + 3) == 0x266c0 && 0x266c0 == 0x26648 + 0x78, "the pool is the cache + 0x78, as in D2R's growth");
	const int32_t rel = static_cast<int32_t>(Le32(PoolCall + 8));
	Check(PoolCall[7] == 0xe8 && PoolRva + 7 + 5 + static_cast<int64_t>(rel) == ReserveFnRva, "the call goes to the reserve 0x122fee0");
	Check(CapacityRva < ReserveRva, "the capacity is stored before the pool is reserved");
	// the renderer start's init of the same cache stores the capacity again
	Check(InitSite[0] == 0x48 && InitSite[1] == 0xc7 && InitSite[2] == 0x46 && InitSite[3] == 0x70, "mov qword ptr [rsi+0x70], imm32");
	Check(Le32(InitSite + InitImm) == D2RCapacity, "the init's capacity is 2750");
	Check(Le32(InitCall + 3) == 0x26648 && CacheFieldOffset == Le32(InitCall + 3) + 0x70, "the init gets the ModelAsset cache");
	const int32_t initRel = static_cast<int32_t>(Le32(InitCall + 15));
	Check(InitCall[14] == 0xe8 && InitCallRva + 14 + 5 + static_cast<int64_t>(initRel) == InitFnRva, "the call goes to the init 0xf75c60");
	Check(InitFnRva < InitRva && InitRva < InitFnRva + 0x80, "the store is inside the init, before its rehash");

	// the patch: only the immediates change
	const CapacityBytes c = CapacityPatch();
	const ReserveBytes r = ReservePatch();
	const InitBytes i = InitPatch();
	Check(Le32(c.bytes + CapacityImm) == Capacity && Le32(r.bytes + ReserveImm) == Capacity && Le32(i.bytes + InitImm) == Capacity,
	      "the three immediates carry the new capacity");
	Check(std::memcmp(c.bytes, CapacitySite, CapacityImm) == 0 && std::memcmp(r.bytes, ReserveSite, ReserveImm) == 0 &&
	          std::memcmp(i.bytes, InitSite, InitImm) == 0,
	      "the opcodes and the field stay");
	Check(std::memcmp(InitPatch(D2RCapacity).bytes, InitSite, sizeof(InitSite)) == 0, "the init with D2R's capacity is D2R's bytes");
	Check(Le32(CapacityPatch(D2RCapacity).bytes + CapacityImm) == D2RCapacity &&
	          std::memcmp(CapacityPatch(D2RCapacity).bytes, CapacitySite, sizeof(CapacitySite)) == 0 &&
	          std::memcmp(ReservePatch(D2RCapacity).bytes, ReserveSite, sizeof(ReserveSite)) == 0,
	      "D2R's capacity gives D2R's bytes back");

	// the size: three times D2R's, more than D2R's own growth after two overflows, and positive as an imm32
	Check(Capacity == 8250 && Capacity >= Grown(Grown(D2RCapacity)), "8250 is past two of D2R's growths (2750 -> 4125 -> 6187)");
	Check(Capacity < 0x80000000u, "the imm32 stays positive (sign-extended to 64 bits by the store)");

	if (failures == 0) {
		std::printf("model_cache: all tests passed\n");
	}
	return failures == 0 ? 0 : 1;
}

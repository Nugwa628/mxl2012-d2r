// Pure part of the empty missile slot stubs (missile_stubs.cpp; unit test plugin/tests/missile_stubs_test.cpp).
#pragma once

#include <cstdint>

namespace missile_stubs {

constexpr int CltDoMaxSlots = 96;   // stubs compiled in for the missile client do table (D2R's bound: 91)
constexpr int SrvHitMaxSlots = 80;  // ... and for the server hit table (D2R's bound: 71)

// Which slots get a stub: every empty entry (0) from `first` to below the bound. A bound that is <= 0 or above the
// compiled-in stubs means the table is not the expected one: nothing is written. Returns the count written to `out`.
inline auto EmptySlots(const uint64_t* table, int32_t bound, int first, int maxSlots, int* out, int outSize) noexcept -> int {
	if (table == nullptr || bound <= 0 || bound > maxSlots) {
		return -1;
	}
	int n = 0;
	for (int slot = first; slot < bound && n < outSize; ++slot) {
		if (table[slot] == 0) {
			out[n++] = slot;
		}
	}
	return n;
}

}  // namespace missile_stubs

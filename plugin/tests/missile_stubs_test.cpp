// Standalone test of the empty missile slot selection (missile_stubs_logic.h; not part of the plugin DLL).
#include "../src/missile_stubs_logic.h"

#include <cstdint>
#include <cstdio>

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
	using missile_stubs::EmptySlots;
	// D2R's missile client do table: slot 0 and 78-90 empty, bound 91.
	uint64_t clt[96] = {};
	for (int i = 1; i <= 77; ++i) {
		clt[i] = 0x140000000ULL + static_cast<uint64_t>(i) * 16;
	}
	int out[96];
	int n = EmptySlots(clt, 91, 0, missile_stubs::CltDoMaxSlots, out, 96);
	Check(n == 14, "client do: slot 0 and 78-90 = 14 slots");
	Check(n > 0 && out[0] == 0 && out[1] == 78 && out[n - 1] == 90, "client do: the slots themselves");

	// Server hit table: 1-60 filled, 61-70 empty, bound 71; slot 0 is never called and never stubbed.
	uint64_t srv[80] = {};
	for (int i = 1; i <= 60; ++i) {
		srv[i] = 0x140000000ULL + static_cast<uint64_t>(i);
	}
	n = EmptySlots(srv, 71, 1, missile_stubs::SrvHitMaxSlots, out, 80);
	Check(n == 10 && out[0] == 61 && out[9] == 70, "server hit: 61-70");

	// A slot a real function took first (CltDoWall-style order rule) is left alone.
	srv[65] = 0x1234;
	n = EmptySlots(srv, 71, 1, missile_stubs::SrvHitMaxSlots, out, 80);
	Check(n == 9, "server hit: a filled free slot is not stubbed");

	// Not the expected table: nothing.
	Check(EmptySlots(clt, 0, 0, missile_stubs::CltDoMaxSlots, out, 96) == -1, "bound 0");
	Check(EmptySlots(clt, 97, 0, missile_stubs::CltDoMaxSlots, out, 96) == -1, "bound above the compiled-in stubs");
	Check(EmptySlots(nullptr, 91, 0, missile_stubs::CltDoMaxSlots, out, 96) == -1, "no table");
	// Output limited to its size.
	Check(EmptySlots(clt, 91, 0, missile_stubs::CltDoMaxSlots, out, 3) == 3, "output size");

	if (failures == 0) {
		std::printf("missile stubs tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}

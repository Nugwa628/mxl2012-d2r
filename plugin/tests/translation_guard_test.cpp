// Standalone test of the translation guard's pure part (translation_guard_logic.h; not part of the plugin DLL).
#include "../src/translation_guard_logic.h"

#include <cstdint>
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

// A fake address space: one readable region [lo, hi).
struct Space {
	uint64_t lo, hi;
	auto operator()(uint64_t p, uint64_t n) const -> bool {
		return translation_guard::InRegion(lo, hi - lo, p, n);
	}
};
}  // namespace

int main() {
	using namespace translation_guard;
	Check(RvaHandler == 0x775fc0 && sizeof(HandlerEntry) == 16 && HandlerEntry[0] == 0x4c, "handler rva and entry bytes");
	Check(PayloadField == 0x70 && InnerByte == 0x870, "the handler's reads");

	// region test
	Check(InRegion(0x1000, 0x1000, 0x1000, 8), "start of the region");
	Check(InRegion(0x1000, 0x1000, 0x1ff8, 8), "last 8 bytes");
	Check(!InRegion(0x1000, 0x1000, 0x1ffc, 8), "crosses the end");
	Check(!InRegion(0x1000, 0x1000, 0xff8, 8), "before the region");
	Check(!InRegion(0x1000, 0x10, 0x1000, 0x20), "longer than the region");
	Check(!InRegion(0x1000, 0x1000, ~0ull - 3, 8), "no wrap at the top");

	// page protections: PAGE_READONLY 0x02, PAGE_READWRITE 0x04, PAGE_NOACCESS 0x01, PAGE_GUARD 0x100
	Check(ReadableProtect(true, 0x02) && ReadableProtect(true, 0x04) && ReadableProtect(true, 0x20), "readable pages");
	Check(!ReadableProtect(true, 0x01) && !ReadableProtect(true, 0x104) && !ReadableProtect(false, 0x04) && !ReadableProtect(true, 0),
	      "no access, guard, reserved / free");

	// events over real memory: a readable payload whose +0x70 points into the same block
	alignas(16) static uint8_t mem[0x1000] = {};
	const uint64_t base = reinterpret_cast<uint64_t>(mem);
	const Space space{base, base + sizeof(mem)};
	auto load = [](uint64_t p) -> uint64_t {
		uint64_t v;
		std::memcpy(&v, reinterpret_cast<const void*>(p), sizeof(v));
		return v;
	};
	uint8_t* payload = mem;          // payload at the start
	uint8_t* event = mem + 0x900;    // the event word: pointer to the payload
	const uint64_t payloadAddr = reinterpret_cast<uint64_t>(payload);
	std::memcpy(event, &payloadAddr, 8);
	uint64_t pw = 0, iw = 0;

	// +0x70 null: handed on (the handler copes with a null inner)
	Check(EventSound(event, space, load, &pw, &iw) && pw == payloadAddr && iw == 0, "null inner pointer is passed");
	// +0x70 -> mem+0x10: +0x870 is inside the block
	const uint64_t inner = base + 0x10;
	std::memcpy(payload + PayloadField, &inner, 8);
	Check(EventSound(event, space, load, &pw, &iw) && iw == inner, "readable inner and +0x870");
	// +0x70 -> mem+0x800: +0x870 lies past the block
	const uint64_t late = base + 0x800;
	std::memcpy(payload + PayloadField, &late, 8);
	Check(!EventSound(event, space, load, &pw, &iw), "inner +0x870 not readable");
	// the known crash word: a count and a capacity, not a pointer
	std::memcpy(payload + PayloadField, &CrashPayloadWord, 8);
	Check(!EventSound(event, space, load, &pw, &iw) && iw == CrashPayloadWord, "0x80000003F0 is skipped and reported");
	// a freed payload: the event points outside the readable block
	const uint64_t gone = base + 0x10000;
	std::memcpy(event, &gone, 8);
	Check(!EventSound(event, space, load, &pw, &iw) && pw == gone, "unreadable payload");
	// a null payload and a null event
	const uint64_t zero = 0;
	std::memcpy(event, &zero, 8);
	Check(!EventSound(event, space, load, &pw, &iw), "null payload");
	Check(!EventSound(nullptr, space, load, &pw, &iw), "null event");

	if (failures == 0) {
		std::printf("translation guard tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}

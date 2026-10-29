// Pure part of the translation guard (translation_guard.cpp; unit test plugin/tests/translation_guard_test.cpp). No Windows
// headers, no game calls: the memory test is passed in.
#pragma once

#include <cstddef>
#include <cstdint>

namespace translation_guard {

// Handler of event type 0x10 of the client's UnitTranslationLayer loop (0x77a3b0 -> 0x775fc0(layer, event)), build 93847.
inline constexpr uint64_t RvaHandler = 0x775fc0;
// mov r11,rsp / push rbp / push rbx / push rsi / push rdi / lea rbp,[r11-0xe08] / the first 2 bytes of sub rsp,0xee8 (16 bytes
// compared; no rip-relative)
inline constexpr uint8_t HandlerEntry[] = {0x4c, 0x8b, 0xdc, 0x55, 0x53, 0x56, 0x57, 0x49, 0x8d, 0xab, 0xf8, 0xf1, 0xff, 0xff, 0x48, 0x81};
inline constexpr size_t PayloadField = 0x70;  // the handler reads RBX = [*event + 0x70]
inline constexpr size_t InnerByte = 0x870;    // then the byte [RBX + 0x870]
inline constexpr uint64_t CrashPayloadWord = 0x80000003F0ULL;  // RBX of a known crash report (a count and a capacity)

// True when [p, p + n) lies inside a region [base, base + size) (VirtualQuery's answer for p).
constexpr auto InRegion(uint64_t base, uint64_t size, uint64_t p, uint64_t n) noexcept -> bool {
	return p >= base && n <= size && p - base <= size - n;
}

// True when a page of state `committed` and protection `protect` (VirtualQuery) can be read: committed, not
// PAGE_NOACCESS (0x01), not PAGE_GUARD (0x100).
constexpr auto ReadableProtect(bool committed, uint32_t protect) noexcept -> bool {
	return committed && protect != 0 && (protect & (0x01u | 0x100u)) == 0;
}

// True when the event can be handed to D2R's handler. `readable(p, n)` says whether n bytes at p can be read; `load(p)` reads
// the pointer at p. `payloadWord` / `innerWord` get what was read (the log line).
template <typename Readable, typename Load>
auto EventSound(const void* event, Readable readable, Load load, uint64_t* payloadWord, uint64_t* innerWord) noexcept -> bool {
	if (event == nullptr || !readable(reinterpret_cast<uint64_t>(event), sizeof(void*))) {
		return false;
	}
	const uint64_t payload = load(reinterpret_cast<uint64_t>(event));
	*payloadWord = payload;
	if (payload == 0 || !readable(payload + PayloadField, sizeof(void*))) {
		return false;
	}
	const uint64_t inner = load(payload + PayloadField);
	*innerWord = inner;
	return inner == 0 || (readable(inner, sizeof(void*)) && readable(inner + InnerByte, 1));
}

}  // namespace translation_guard

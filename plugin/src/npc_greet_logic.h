// Pure part of the first-meeting greeting fix (npc_greet.cpp, Vendor Stock Refresh's first-trade issue, lane bugs128; unit test
// plugin/tests/npc_greet_test.cpp). No Windows headers, no game calls.
#pragma once

#include <cstddef>
#include <cstdint>

namespace npc_greet {

// D2R's client NPC interaction state, global 0x2a486a4: 0 none, 1 the NPC menu, 2 a vendor panel (Trade 0x112f30 and Gamble
// 0x112c80 both store 2), 2..5 the states whose end closes the vendor panel (panel 0xb, end function 0x10b310).
inline constexpr uint64_t StateRva = 0x2a486a4;

// 0x10da20: the "NPC speech finished" callback (registered with 0x197bd0 by `lea rcx, [rip-0x135]` at 0x10db4e). With no
// more speech queued it stores state 1 (`mov dword ptr [rip+disp], 1` at 0x10dc73) and calls the NPC menu opener 0x1141d0
// (`call` at 0x10dcb7). The opener closes every panel first (0xc8240): a trade the player picked from the menu while the
// greeting was still playing is closed, and the vendor panel's end (0x10b310) sends the server the interaction's cancel, so
// the vendor walks off. D2R shows the NPC menu during the greeting; 1.13c showed it only after, so this never happened there.
inline constexpr uint64_t SpeechDoneRva = 0x10da20;
inline constexpr uint8_t SpeechDoneEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x10, 0x48, 0x89, 0x6c, 0x24, 0x18, 0x56, 0x48, 0x83, 0xec, 0x40};
inline constexpr uint64_t MenuOpenRva = 0x1141d0;
inline constexpr uint8_t MenuOpenEntry[] = {0x40, 0x55, 0x57, 0x41, 0x55, 0x41, 0x57, 0x48, 0x8b, 0xec, 0x48, 0x83, 0xec, 0x48};
inline constexpr uint64_t MenuStateStoreRva = 0x10dc73;
inline constexpr uint8_t MenuStateStore[] = {0xc7, 0x05, 0x27, 0xaa, 0x93, 0x02, 0x01, 0x00, 0x00, 0x00};
inline constexpr uint64_t MenuCallRva = 0x10dcb7;
inline constexpr uint8_t MenuCall[] = {0xe8, 0x14, 0x65, 0x00, 0x00};
inline constexpr uint64_t RegisterRva = 0x10db4e;
inline constexpr uint8_t Register[] = {0x48, 0x8d, 0x0d, 0xcb, 0xfe, 0xff, 0xff};

// The vendor panel stays: the greeting ended while a vendor panel (states 2..5) was open.
constexpr auto KeepsPanel(int32_t stateBefore) noexcept -> bool {
	return stateBefore >= 2 && stateBefore <= 5;
}

// rip-relative target of an instruction of `size` bytes at `at` with displacement `disp`.
constexpr auto RipTarget(uint64_t at, size_t size, int32_t disp) noexcept -> uint64_t {
	return at + size + static_cast<uint64_t>(static_cast<int64_t>(disp));
}

}  // namespace npc_greet

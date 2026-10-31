// Pure part of the RotW stash pages in classic mode (rotw_stash.cpp, bug #516, lane rotwgate; unit test
// plugin/tests/rotw_stash_test.cpp). No Windows headers, no game calls.
#pragma once

#include <cstddef>
#include <cstdint>

namespace rotw_stash {

// D2R's BankPanel (D2Client, the stash) after its layout is read, 0x23b1b0(panel): only when `0x846210()` (HD graphics, the
// panel manager's byte +0xb9) says yes AND the layout has a `basicstash_container`, it sets the panel's byte +0x2a8 (the five
// pages are in use) and fills its page table +0x278 (5 widget pointers: basicstash_container twice, advancedstash_gems,
// _materials, _runes) and +0x2a0 (advancedstash_horadriccube). Its tab update (0x23e630) shows / hides those pages; with
// +0x2a8 clear it walks the first two entries only. So in classic graphics D2R never wires the RotW pages, whatever the
// layout says: a classic layout with `basicstash_container` leaves the table empty and the tab update calls through a null
// entry (D2R.exe+0x23E6A5, lane rotwstash), and the pages' AdvancedStashSlotWidgets are never hidden.
inline constexpr uint64_t PanelInitRva = 0x23b1b0;
inline constexpr uint64_t HdCheckCallRva = 0x23b204;  // call 0x846210 / test al,al / je 0x23b6d7
inline constexpr uint8_t HdCheckCall[] = {0xe8, 0x07, 0xb0, 0x60, 0x00};
inline constexpr uint64_t HdModeRva = 0x846210;
inline constexpr uint8_t HdModeCode[] = {0x48, 0x8b, 0x05, 0x59, 0x9f, 0xbf, 0x02, 0x48, 0x85, 0xc0, 0x74, 0x08,
                                         0x0f, 0xb6, 0x80, 0xb9, 0x00, 0x00, 0x00, 0xc3};
// The 14 int3 bytes between 0x2388a2 and the next function (0x2388b0): the call goes there, to an absolute jump into the
// plugin's decision (the call has pushed its return 0x23b209; rax is the result register, free).
inline constexpr uint64_t PadRva = 0x2388a2;
inline constexpr uint8_t Pad[12] = {0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc};

// The game type: the client game (global 0x2a236e0) byte +0x5c, 1 classic, 2 Lord of Destruction, 3 Reign of the Warlock
// (the values of D2RLoader's DataTables::Bank). 0x8d3e0 is D2R's own "RotW game" test (false without a game).
inline constexpr uint64_t RotwGameRva = 0x8d3e0;
inline constexpr uint8_t RotwGameCode[] = {0x48, 0x8b, 0x05, 0xf9, 0x62, 0x99, 0x02, 0x48, 0x85, 0xc0, 0x74, 0x09,
                                           0x80, 0x78, 0x5c, 0x03, 0x75, 0x03, 0xb0, 0x01, 0xc3, 0x32, 0xc0, 0xc3};
inline constexpr uint64_t ClientGameRva = 0x2a236e0;
inline constexpr size_t GameTypeOffset = 0x5c;
inline constexpr uint8_t GameTypeRotw = 3;

// The classic item picture 0x154ac0(item, ...): `[item+0x78]` is read through without a check (0x9a600 returns it), then
// `[that+0x440]` (D2R.exe+0x154AF2, null + 0x440: an AdvancedStashSlotWidget in classic). The guard returns at once for an
// item without that record, as the function itself does when +0x440 is null (0x154e18). Callers do not use the result.
inline constexpr uint64_t ItemPictureRva = 0x154ac0;
inline constexpr uint8_t ItemPictureEntry[] = {0x44, 0x89, 0x44, 0x24, 0x18, 0x89, 0x54, 0x24, 0x10, 0x55, 0x53, 0x56, 0x41, 0x54, 0x41, 0x56};
inline constexpr size_t ItemDrawDataOffset = 0x78;

// When the stash wires its pages in classic graphics.
enum class Mode {
	Always,  // every game, as D2R does in HD (the default): D2R's own RotW rule then keeps the RotW tabs closed without RotW
	Rotw,    // only in a RotW game (dev test MXL_ROTWSTASH_TEST=rotw)
	Never,   // D2R's own rule, HD only (dev test MXL_ROTWSTASH_TEST=never: the classic RotW layout crashes on G, +0x23E6A5)
};

// What the init's HD check answers. HD stays D2R's yes; classic answers by the mode.
constexpr auto WirePages(bool hd, bool rotwGame, Mode mode) noexcept -> bool {
	if (hd) {
		return true;
	}
	return mode == Mode::Always || (mode == Mode::Rotw && rotwGame);
}

// MXL_ROTWSTASH_TEST value -> mode (anything else: the default).
constexpr auto ParseMode(const char* s) noexcept -> Mode {
	auto eq = [](const char* a, const char* b) {
		for (; *a != '\0' && *b != '\0'; ++a, ++b) {
			const char x = (*a >= 'A' && *a <= 'Z') ? static_cast<char>(*a + 32) : *a;
			if (x != *b) {
				return false;
			}
		}
		return *a == '\0' && *b == '\0';
	};
	if (s == nullptr) {
		return Mode::Always;
	}
	return eq(s, "rotw") ? Mode::Rotw : eq(s, "never") ? Mode::Never : Mode::Always;
}

constexpr auto ModeName(Mode m) noexcept -> const char* {
	return m == Mode::Rotw ? "RotW games only" : m == Mode::Never ? "no game (HD only)" : "every game";
}

// The guard skips an item picture without its draw record.
constexpr auto SkipPicture(const void* item, const void* drawData) noexcept -> bool {
	return item != nullptr && drawData == nullptr;
}

struct AbsJump {
	uint8_t bytes[12];
};

// movabs rax, to / jmp rax
constexpr auto AbsJumpBytes(uint64_t to) noexcept -> AbsJump {
	AbsJump j{{0x48, 0xb8, 0, 0, 0, 0, 0, 0, 0, 0, 0xff, 0xe0}};
	for (int i = 0; i < 8; ++i) {
		j.bytes[2 + i] = static_cast<uint8_t>(to >> (8 * i));
	}
	return j;
}

// rel32 of a 5-byte call at `from` to `to`.
constexpr auto Rel32Call(uint64_t from, uint64_t to) noexcept -> int32_t {
	return static_cast<int32_t>(static_cast<int64_t>(to) - static_cast<int64_t>(from + 5));
}

}  // namespace rotw_stash

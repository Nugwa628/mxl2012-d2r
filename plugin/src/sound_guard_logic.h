// Pure part of the sound guard (sound_guard.cpp; unit test plugin/tests/sound_guard_test.cpp). No Windows headers, no game calls.
#pragma once

#include <cstdint>

namespace sound_guard {

// Data rows of our built sounds.txt (work/mod/data/global/excel, header and blank lines left out): the expansion bank, the one
// the game loads (the loaded count matches that bank), and base/. D2R 93847's own table
// has 11913. tools/tests/test_sound_rows.py compares both constants to the built tables; change them with the data.
inline constexpr int ModSoundRows = 12119;
inline constexpr int ModSoundRowsBase = 12101;
inline constexpr int D2RSoundRows = 11913;
// Fewer rows than this: not our table (D2RLoader's snapshot start loaded D2R's own, crash-audit C17).
inline constexpr int MinModRows = ModSoundRows < ModSoundRowsBase ? ModSoundRows : ModSoundRowsBase;

// Client functions of build 93847.
inline constexpr uint64_t RvaPlayingSound = 0x107dd0;  // (unit, sound id) -> the unit's playing sound with this id, or null
inline constexpr uint64_t RvaSoundCount = 0x3b20c0;    // () -> sounds.txt row count
inline constexpr uint64_t RvaNeutralCallRet = 0x107cd4;  // return address of the Neutral sound call in 0x1079e0 (dev test switch)
// The record readers: each checks the id against the row count but then goes on with a null record.
inline constexpr uint64_t RvaFieldC7 = 0xd8c70;  // (id) -> record +0xc7 (after the +0xbb redirect); 0 for an empty table
inline constexpr uint64_t RvaFieldB0 = 0xd9180;  // (id) -> record +0xb0 & a mask; 0 for an empty table
inline constexpr uint64_t RvaPath = 0xd9030;     // (id, buffer, size): the sound's file path into buffer
inline constexpr uint64_t RvaPick = 0xd9e60;     // (id, ?, ?) -> the sound id to play; the id itself for an empty table
inline constexpr uint64_t RvaVariant = 0xda360;  // (id, mode) -> the sound id to play (group variant); the id itself

// Entry bytes (whole instructions, no rip-relative), from the dump of build 93847.
// mov [rsp+8],rbx / mov [rsp+0x10],rsi / push rdi / sub rsp,0x20
inline constexpr uint8_t PlayingSoundEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x08, 0x48, 0x89, 0x74, 0x24, 0x10, 0x57, 0x48, 0x83, 0xec, 0x20};
// push rbx / sub rsp,0x20 / mov ebx,ecx
inline constexpr uint8_t FieldC7Entry[] = {0x40, 0x53, 0x48, 0x83, 0xec, 0x20, 0x8b, 0xd9};
inline constexpr uint8_t FieldB0Entry[] = {0x40, 0x53, 0x48, 0x83, 0xec, 0x20, 0x8b, 0xd9};
// push rbx / push rbp / push rdi / sub rsp,0x20
inline constexpr uint8_t PathEntry[] = {0x40, 0x53, 0x55, 0x57, 0x48, 0x83, 0xec, 0x20};
// push rbp / push rbx / push r12 / push r13 / lea rbp,[rsp-8]
inline constexpr uint8_t PickEntry[] = {0x40, 0x55, 0x53, 0x41, 0x54, 0x41, 0x55, 0x48, 0x8d, 0x6c, 0x24, 0xf8};
// push rbx / push rbp / push rsi / push rdi / push r13 / sub rsp,0x20
inline constexpr uint8_t VariantEntry[] = {0x40, 0x53, 0x55, 0x56, 0x57, 0x41, 0x55, 0x48, 0x83, 0xec, 0x20};

// True when `id` is not a row of a table of `rows` rows: the guard skips it.
constexpr auto Skips(int id, int rows) noexcept -> bool {
	return id < 0 || id >= rows;
}

// What a record reader returns for a skipped id: its answer for an empty table.
constexpr auto FieldAnswer() noexcept -> uint64_t {
	return 0;
}
constexpr auto PickAnswer(int id) noexcept -> uint64_t {
	return static_cast<uint32_t>(id);
}

enum class Table { NotLoaded, Ours, Short };

// The sounds table after a table load: not loaded yet (no rows), ours, or short (D2RLoader's snapshot start: D2R's own rows).
constexpr auto CheckTable(int rows) noexcept -> Table {
	return rows <= 0 ? Table::NotLoaded : (rows >= MinModRows ? Table::Ours : Table::Short);
}

}  // namespace sound_guard

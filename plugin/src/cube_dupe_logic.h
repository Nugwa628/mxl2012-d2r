// Pure part of the cube's second `useitem` output (cube_dupe.cpp; unit test plugin/tests/cube_dupe_test.cpp). Bug #350.
// No Windows headers, no game calls.
//
// Median XL 2012's 24 dupe rows (cubemain 8397-8420: item + Arcane Crystal + Oil of Duplication, op 18 `item_hasbeenduped`
// == 0) name `useitem` in output a and output b, with the same mods in both. 1.14d (Game.exe, read for 1.13c, which Median 2012
// ran without code patches) gives two items:
//   - the matcher 0x565010 records input 1's item in all three output entries of the search context (0x5656ee..0x565816,
//     input 1 only: `test ebx, ebx / jne` at 0x56533f) when output a is `useitem` / `usetype`;
//   - the executor 0x565ab0 runs each output slot (0x54 bytes from record +0x4c, type byte +8): type 0xfe takes the entry's item
//     and makes a NEW item from it with 0x55a2a0 (the item duplicate: serialise to a 0x400 buffer, read back, flags 0x80000 on,
//     0x2000 off; 0x565e8c), then applies the slot's mods to that copy. Two `useitem` slots = two copies of input 1; the inputs
//     are used up afterwards.
// D2R's executor 0x5269c0 keeps the input item itself for type 0xfe (0x527104: the item's id is taken out of the list of
// inputs to consume, no copy); output b finds the id gone (0x527170 -> 0x52788f) and makes nothing. So the hook copies the
// first output (output a after its mods: the same item 1.13c's second copy is, as both slots carry the same mods) once per
// further `useitem` slot, with D2R's own duplicate 0x43d660 (the same function as 1.14d's 0x55a2a0: same buffer size, same
// flags, same 0x8000000 on the source), and puts the copy in the cube as the executor puts its outputs.
#pragma once

#include <cstdint>

namespace cube_dupe {

inline constexpr int RecordSize = 0x16c;    // D2R cubemain record (0x3e3f60 stride)
inline constexpr int SlotBase = 0x5a;       // output slot i at record + 0x5a + 0x5b * i (parser 0x3e5e60, executor 0x526b5b)
inline constexpr int SlotSize = 0x5b;
inline constexpr int SlotSpecial = 0x0d;    // the special byte (executor 0x527104: movzx eax, byte [r15 + 0x67])
inline constexpr uint8_t UseItem = 0xfe;    // `useitem` (D2R's parser; 1.13c's type byte has the same value)
inline constexpr int Slots = 3;

inline constexpr uint32_t ItemFlagIdentified = 0x10;   // set by the executor on each placed output (0x527e52)
inline constexpr uint32_t ItemFlagDupeSource = 0x8000000;  // set on the source by 0x43d660 / 0x55a2a0 (1.13c's source is used up)

inline constexpr auto SpecialOf(const uint8_t* record, int slot) noexcept -> uint8_t {
	return record[SlotBase + SlotSize * slot + SlotSpecial];
}

// Copies 1.13c makes beyond the one D2R gives: the `useitem` slots after the first, when output a is `useitem` (D2R returns
// output a's item, the copy's source). 0 for every other recipe.
inline constexpr auto ExtraCopies(const uint8_t* record) noexcept -> int {
	if (record == nullptr || SpecialOf(record, 0) != UseItem) {
		return 0;
	}
	int n = 0;
	for (int slot = 1; slot < Slots; ++slot) {
		n += SpecialOf(record, slot) == UseItem ? 1 : 0;
	}
	return n;
}

// Where the copy goes: the cube (page 3) as the executor places outputs (0x34a410 kind 3), else the backpack (page 0, kind 0).
struct Page {
	int32_t page;
	int32_t kind;
};
inline constexpr Page Pages[] = {{3, 3}, {0, 0}};

}  // namespace cube_dupe

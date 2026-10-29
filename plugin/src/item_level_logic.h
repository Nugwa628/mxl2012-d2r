// Pure part of the item level patch (item_level.cpp; unit test plugin/tests/item_level_test.cpp). No Windows headers, no
// game calls.
#pragma once

#include <cstddef>
#include <cstdint>

namespace item_level {

// D2Common's item serializer (0x37d140, called by 0x37ffd0 for the item and again for each socketed child) writes the item
// level (item data +0x38) into a 7-bit field, but first clamps it to 1..99:
//   0x37d733  mov ecx,[rax+0x38] / cmp ecx,1 / jge 0x37d744 / mov dword [rax+0x38],1 / jmp 0x37d6c7
//   0x37d744  cmp ecx,0x63 / jl 0x37d6c7          ; below 99: 0x37d6c7 reads the level again and writes it (0x37d754)
//   0x37d74d  mov eax,0x63 / jmp 0x37d768          ; 99 and up: 99
//   0x37d768  test eax,eax / mov edx,r12d / cmovne edx,eax / cmp edx,r15d / jb +3 / mov edx,r15d   ; r15d = 0x7f (0x37d67d)
//   0x37d778  mov rdi,[rsp+0x28] / mov r8d,7 / mov rcx,rdi / call 0xa1b710                       ; write 7 bits
// so an item made at level 100-127 comes back at 99 (bug #251). The reader (0x378860: 7 bits at 0x378c76, `< 1 -> 1`,
// stored at 0x378d05) has no upper clamp. Median XL 2012's monsters go to level 120, and its cube rerolls / upgrades read
// the item level. The patch raises the clamp to the field's own maximum, 127: both immediates 0x63 -> 0x7f. Levels 1-126
// take D2R's own "below the clamp" path, 127 and up are written as 127, and the 0x7f cap right behind (0x37d770) stays.
inline constexpr uint64_t PatchRva = 0x37d744;
inline constexpr uint32_t PatchSize = 14;
inline constexpr uint8_t Old[PatchSize] = {0x83, 0xf9, 0x63, 0x0f, 0x8c, 0x7a, 0xff, 0xff, 0xff, 0xb8, 0x63, 0x00, 0x00, 0x00};
inline constexpr size_t ImmCmp = 2;  // the cmp's imm8
inline constexpr size_t ImmMov = 10; // the mov's imm32 low byte

// Compared (read only) before writing: the whole clamp from the level read to the 7-bit write's call, and the 0x7f in r15d.
inline constexpr uint64_t ExpectedRva = 0x37d733;
inline constexpr uint8_t Expected[] = {
	0x8b, 0x48, 0x38, 0x83, 0xf9, 0x01, 0x7d, 0x09, 0xc7, 0x40, 0x38, 0x01, 0x00, 0x00, 0x00, 0xeb, 0x83,  // read, < 1 -> 1
	0x83, 0xf9, 0x63, 0x0f, 0x8c, 0x7a, 0xff, 0xff, 0xff, 0xb8, 0x63, 0x00, 0x00, 0x00, 0xeb, 0x14,        // the 99 clamp
	0x8b, 0x40, 0x38, 0x83, 0xf8, 0x01, 0x7d, 0x0c, 0xc7, 0x41, 0x38, 0x01, 0x00, 0x00, 0x00, 0xb8, 0x01, 0x00, 0x00, 0x00,
	0x85, 0xc0, 0x41, 0x8b, 0xd4, 0x0f, 0x45, 0xd0, 0x41, 0x3b, 0xd7, 0x72, 0x03, 0x41, 0x8b, 0xd7,  // cap at r15d
	0x48, 0x8b, 0x7c, 0x24, 0x28, 0x41, 0xb8, 0x07, 0x00, 0x00, 0x00, 0x48, 0x8b, 0xcf, 0xe8,        // 7 bits, call
};
inline constexpr size_t ExpectedSize = sizeof(Expected);
inline constexpr size_t PatchInExpected = PatchRva - ExpectedRva;  // 0x11
inline constexpr size_t BitsInExpected = 0x4c;                  // the `7` of mov r8d,7
inline constexpr uint64_t MaskRva = 0x37d67d;                // mov r15d,0x7f
inline constexpr uint8_t Mask[] = {0x41, 0xbf, 0x7f, 0x00, 0x00, 0x00};

inline constexpr int32_t FieldBits = 7;
inline constexpr int32_t FieldMax = (1 << FieldBits) - 1;  // 127
inline constexpr int32_t D2RClamp = 99;

struct Bytes {
	uint8_t b[PatchSize];
};
// The clamp instructions with `cap` in both immediates (D2RClamp gives Old back).
constexpr auto PatchBytes(int32_t cap) noexcept -> Bytes {
	Bytes r{};
	for (size_t i = 0; i < PatchSize; ++i) {
		r.b[i] = Old[i];
	}
	r.b[ImmCmp] = static_cast<uint8_t>(cap);
	r.b[ImmMov] = static_cast<uint8_t>(cap);
	return r;
}

// What the serializer writes for item level `level` with clamp `cap` (D2RClamp unpatched, FieldMax patched).
constexpr auto Written(int32_t level, int32_t cap) noexcept -> int32_t {
	int32_t v = level < 1 ? 1 : level;
	if (v >= cap) {
		v = cap;
	}
	return static_cast<uint32_t>(v) < static_cast<uint32_t>(FieldMax) ? v : FieldMax;
}

// What the reader (0x378860) makes of the field.
constexpr auto Read(uint32_t bits) noexcept -> int32_t {
	const auto v = static_cast<int32_t>(bits & static_cast<uint32_t>(FieldMax));
	return v < 1 ? 1 : v;
}

}  // namespace item_level

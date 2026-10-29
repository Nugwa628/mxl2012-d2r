// Pure part of the rune letter fallback (rune_letters.cpp; unit test plugin/tests/rune_letters_test.cpp). No Windows
// headers, no game calls.
#pragma once

#include <cstddef>
#include <cstdint>

namespace rune_letters {

// The runeword tooltip's letter line (D2Client InventoryTooltips.cpp, chunk 0x2c2909..0x2c2a4e) walks the socketed runes and
// appends one letter per rune:
//   0x2c297b  call 0x313ce0                        ; (data flag, gem index) -> gems record (0xc0 bytes)
//   0x2c29ae  add rbx,0x20 / [rsp+0x30] = {rbx, strlen}   ; the record's 5-character `letter` cell as a string_view
//   0x2c29da  call 0x3e2b736                       ; key lookup (jmp [rip] into D2RLoader's string table) -> text
//   0x2c29df  ... rax = lookup of "strMissingString" (0x2c29f5)
//   0x2c29fa  cmp rdi,rax / jne 0x2c2a18           ; same pointer: copy the raw cell (0x1227840, 6 bytes) instead
//   0x2c2a1b  append the text (0x12276a0, 0x400)
// D2R draws the raw cell when the lookup fails, as 1.14d does (0x486670 draws the cell itself). Under D2RLoader the failed
// lookup and the lookup of strMissingString are not the same pointer, so a cell without a key in D2R's namespace reads
// "Missing string" (bug #334: Median's Great Runes r34-r56, `Sha` .. `Shaad`), and a cell that is another D2R key reads
// that key's text (`No` -> "NO", `On` -> "ON", `Xar` -> D2R's item key `xar`, "Ornate Plate"). The build points r01-r33 at
// D2R's own r01L..r33L (data/string_gaps.tsv). The fallback answers the letter lookup at this one call site (return
// address 0x2c29df): a cell that is not a D2R rune letter key, or whose lookup has no text, reads as the cell itself.
inline constexpr uint64_t ThunkRva = 0x3e2b736;  // jmp qword [rip-0x924] -> slot 0x3e2ae18
inline constexpr uint8_t Thunk[] = {0xff, 0x25, 0xdc, 0xf6, 0xff, 0xff};
inline constexpr uint64_t SlotRva = ThunkRva + sizeof(Thunk) - 0x924;  // 0x3e2ae18
inline constexpr uint64_t CallRva = 0x2c29da;
inline constexpr uint64_t ReturnRva = CallRva + 5;  // 0x2c29df

// Compared (read only) before the slot is touched: 0x2c29ae..0x2c2a28, from the cell's string_view to the append. The two
// calls into the thunk are rel32 inside the image, so the block names the same targets in every load.
inline constexpr uint64_t SiteRva = 0x2c29ae;
inline constexpr uint8_t Site[] = {
	0x48, 0x83, 0xc3, 0x20, 0x48, 0x89, 0x5c, 0x24, 0x30, 0x80, 0x3b, 0x00, 0x74, 0x12, 0x48, 0xc7, 0xc0, 0xff, 0xff, 0xff,
	0xff, 0x48, 0xff, 0xc0, 0x80, 0x3c, 0x03, 0x00, 0x75, 0xf7, 0xeb, 0x02, 0x33, 0xc0, 0x48, 0x8d, 0x4c, 0x24, 0x30, 0x48,
	0x89, 0x44, 0x24, 0x38, 0xe8, 0x57, 0x8d, 0xb6, 0x03, 0x48, 0x8d, 0x4c, 0x24, 0x20, 0x4c, 0x89, 0x64, 0x24, 0x20, 0x48,
	0x8b, 0xf8, 0x48, 0xc7, 0x44, 0x24, 0x28, 0x10, 0x00, 0x00, 0x00, 0xe8, 0x3c, 0x8d, 0xb6, 0x03, 0x48, 0x3b, 0xf8, 0x75,
	0x19, 0x4c, 0x8b, 0xc3, 0x48, 0x8d, 0x4c, 0x24, 0x40, 0xba, 0x06, 0x00, 0x00, 0x00, 0xe8, 0x2f, 0x4e, 0xf6, 0x00, 0x4c,
	0x8d, 0x44, 0x24, 0x40, 0xeb, 0x03, 0x4c, 0x8b, 0xc7, 0xba, 0x00, 0x04, 0x00, 0x00, 0x48, 0x8b, 0xcd, 0xe8, 0x78, 0x4c,
	0xf6, 0x00,
};
inline constexpr size_t SiteSize = sizeof(Site);
inline constexpr size_t LetterCallInSite = CallRva - SiteRva;  // 0x2c: e8 of the letter lookup
inline constexpr size_t MissingCallInSite = 0x47;              // e8 of the strMissingString lookup (0x2c29f5)

// Target of an e8 rel32 at `rva` whose displacement is `disp`.
constexpr auto CallTarget(uint64_t rva, int32_t disp) noexcept -> uint64_t {
	return rva + 5 + static_cast<uint64_t>(static_cast<int64_t>(disp));
}

constexpr auto Lower(char c) noexcept -> char {
	return c >= 'A' && c <= 'Z' ? static_cast<char>(c - 'A' + 'a') : c;
}

// D2R's own rune letter keys r01L .. r33L (any case, as the loader's lookup and text_audit RUNE_LETTER_KEY take them).
constexpr auto IsD2RLetterKey(const char* cell, size_t len) noexcept -> bool {
	if (cell == nullptr || len != 4 || Lower(cell[0]) != 'r' || Lower(cell[3]) != 'l') {
		return false;
	}
	if (cell[1] < '0' || cell[1] > '9' || cell[2] < '0' || cell[2] > '9') {
		return false;
	}
	const int n = (cell[1] - '0') * 10 + (cell[2] - '0');
	return n >= 1 && n <= 33;
}

constexpr auto SameText(const char* a, const char* b) noexcept -> bool {
	if (a == nullptr || b == nullptr) {
		return false;
	}
	size_t i = 0;
	for (; a[i] != '\0' && b[i] != '\0'; ++i) {
		if (a[i] != b[i]) {
			return false;
		}
	}
	return a[i] == b[i];
}

inline constexpr char MissingText[] = "Missing string";  // what D2RLoader answers for a key it has no string for

// The lookup has no text: null, empty, "Missing string", or the text of strMissingString (`missing`, may be null).
constexpr auto IsMissing(const char* text, const char* missing) noexcept -> bool {
	return text == nullptr || text[0] == '\0' || SameText(text, MissingText) || SameText(text, missing);
}

// True when the letter line must show the cell itself instead of the lookup's `text`.
constexpr auto UseCell(const char* cell, size_t len, const char* text, const char* missing) noexcept -> bool {
	if (cell == nullptr || len == 0) {
		return false;  // nothing to draw: D2R's own path
	}
	return !IsD2RLetterKey(cell, len) || IsMissing(text, missing);
}

// The cell as a terminated string (cut at `size - 1`, and at a 0 byte inside `len`).
constexpr void CopyCell(char* out, size_t size, const char* cell, size_t len) noexcept {
	if (out == nullptr || size == 0) {
		return;
	}
	size_t i = 0;
	for (; cell != nullptr && i < len && i + 1 < size && cell[i] != '\0'; ++i) {
		out[i] = cell[i];
	}
	out[i] = '\0';
}

inline constexpr size_t CellMax = 16;  // the record's field holds 5 characters and a 0; a longer view is cut

}  // namespace rune_letters

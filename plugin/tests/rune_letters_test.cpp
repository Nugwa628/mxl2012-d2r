// Standalone test of the rune letter fallback (rune_letters_logic.h; not part of the plugin DLL).
#include "../src/rune_letters_logic.h"

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
auto Disp(size_t at) -> int32_t {
	int32_t d = 0;
	std::memcpy(&d, rune_letters::Site + at + 1, sizeof(d));
	return d;
}
}  // namespace

int main() {
	using namespace rune_letters;
	// the compared block
	Check(SlotRva == 0x3e2ae18, "thunk 0x3e2b736 jumps through 0x3e2ae18");
	Check(ReturnRva == 0x2c29df, "the letter lookup returns to 0x2c29df");
	Check(SiteSize == 0x7a, "block 0x2c29ae..0x2c2a28");
	Check(Site[0] == 0x48 && Site[1] == 0x83 && Site[2] == 0xc3 && Site[3] == 0x20, "add rbx,0x20: the letter cell at record +0x20");
	Check(Site[LetterCallInSite] == 0xe8 && CallTarget(CallRva, Disp(LetterCallInSite)) == ThunkRva, "the letter lookup calls the thunk");
	Check(Site[MissingCallInSite] == 0xe8 && CallTarget(SiteRva + MissingCallInSite, Disp(MissingCallInSite)) == ThunkRva,
	      "the strMissingString lookup calls the same thunk");
	Check(Site[MissingCallInSite - 4] == 0x10, "strMissingString's length 0x10");
	Check(Site[0x4c] == 0x48 && Site[0x4d] == 0x3b && Site[0x4e] == 0xf8 && Site[0x4f] == 0x75, "cmp rdi,rax / jne: D2R's pointer test");
	Check(Site[SiteSize - 5] == 0xe8, "the block ends at the append's call");

	// D2R's keys
	Check(IsD2RLetterKey("r01L", 4) && IsD2RLetterKey("r33L", 4) && IsD2RLetterKey("R10l", 4), "r01L..r33L, any case");
	Check(!IsD2RLetterKey("r34L", 4) && !IsD2RLetterKey("r00L", 4) && !IsD2RLetterKey("r51L", 4), "r00L and past Zod are not D2R's");
	Check(!IsD2RLetterKey("El", 2) && !IsD2RLetterKey("Taha", 4) && !IsD2RLetterKey("r01", 3) && !IsD2RLetterKey("r1aL", 4) &&
	          !IsD2RLetterKey(nullptr, 4),
	      "literal names are not keys");

	const char* missing = "Missing string";
	// runes 1-33: the data fix, D2R's text stays
	Check(!UseCell("r01L", 4, "El", missing), "El (r01L) keeps D2R's text");
	Check(!UseCell("r33L", 4, "Zod", missing), "Zod (r33L) keeps D2R's text");
	Check(UseCell("r01L", 4, "Missing string", missing) && UseCell("r01L", 4, nullptr, nullptr) && UseCell("r01L", 4, "", nullptr),
	      "a D2R key without a text falls back to the cell");
	Check(UseCell("r02L", 4, "Fehlender Text", "Fehlender Text"), "the text of strMissingString counts as missing");
	// bug #334
	Check(UseCell("Taha", 4, "Missing string", missing) && UseCell("Shaad", 5, "Missing string", missing) && UseCell("Sha", 3, "Missing string", missing),
	      "Great Runes draw the cell");
	Check(UseCell("Xar", 3, "Ornate Plate", missing) && UseCell("No", 2, "NO", missing) && UseCell("On", 2, "ON", missing),
	      "a literal name that is another D2R key draws the cell");
	Check(!UseCell("", 0, "Missing string", missing) && !UseCell(nullptr, 3, "x", missing), "an empty cell stays D2R's");

	char out[CellMax];
	CopyCell(out, sizeof(out), "Shaad", 5);
	Check(std::strcmp(out, "Shaad") == 0, "the cell copied");
	CopyCell(out, sizeof(out), "Ta\0ha", 5);
	Check(std::strcmp(out, "Ta") == 0, "cut at a 0 byte");
	CopyCell(out, 3, "Taha", 4);
	Check(std::strcmp(out, "Ta") == 0, "cut at the buffer");
	CopyCell(out, sizeof(out), nullptr, 4);
	Check(out[0] == '\0', "no cell: empty");
	Check(SameText("NO", "NO") && !SameText("NO", "No") && !SameText(nullptr, "x") && !SameText("Missing", "Missing string"),
	      "SameText");

	if (failures == 0) {
		std::printf("rune_letters: all tests passed\n");
	}
	return failures == 0 ? 0 : 1;
}

// Standalone test of D2R's Chance to Block replica (block_rate_logic.h; not part of the plugin DLL). Lane sbresearch.
#include "../src/block_rate_logic.h"

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

auto Hex(char c) -> int {
	return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
}

// The signature's fixed bytes before its first "??" must be the entry bytes.
auto SignatureStartsWithEntry() -> bool {
	const char* s = block_rate::GetBlockRateSignature;
	size_t i = 0;
	while (*s != '\0' && i < sizeof(block_rate::GetBlockRateEntry)) {
		if (s[0] == '?') {
			return false;
		}
		const int hi = Hex(s[0]), lo = Hex(s[1]);
		if (hi < 0 || lo < 0 || static_cast<uint8_t>(hi * 16 + lo) != block_rate::GetBlockRateEntry[i]) {
			return false;
		}
		++i;
		s += 2;
		while (*s == ' ') {
			++s;
		}
	}
	return i == sizeof(block_rate::GetBlockRateEntry);
}

auto Player(int toBlock, int blockFactor, int dex, int level) -> block_rate::Inputs {
	block_rate::Inputs in;
	in.hasShield = true;
	in.toBlock = toBlock;
	in.blockFactor = blockFactor;
	in.dexterity = dex;
	in.level = level;
	return in;
}
}  // namespace

int main() {
	using namespace block_rate;

	Check(SignatureStartsWithEntry(), "the signature starts with the entry bytes");
	Check(FormulaRva > GetBlockRateRva && FormulaRva < GetBlockRateRva + 0x230, "the formula lies inside the function");
	Check(FormulaBytes[0] == 0x8d && FormulaBytes[1] == 0x43 && FormulaBytes[2] == 0xf1, "lea eax, [rbx - 15]: dexterity - 15");

	// no shield: nothing, whatever the stats
	Inputs bare = Player(60, 3, 300, 50);
	bare.hasShield = false;
	Check(Rate(bare) == 0, "no shield: 0");

	// expansion formula, vanilla numbers: Paladin (30) with a 30% shield (toblock 30), 140 dexterity, level 80
	// (30 + 30) * 125 / 160 = 46 (46.875 truncated)
	Check(Rate(Player(30, 30, 140, 80)) == 46, "vanilla Paladin 60 * 125 / 160 = 46");
	// the cap: a high-dexterity low-level Amazon
	Check(Rate(Player(50, 25, 200, 20)) == 75, "capped at 75");
	Check(Rate(Player(75, 0, 2015, 1)) == 75, "75 stays 75");
	// level 0 and 1 both divide by 2
	Check(Rate(Player(10, 0, 25, 0)) == Rate(Player(10, 0, 25, 1)), "level below 2 counts as 1");
	Check(Rate(Player(10, 0, 25, 1)) == 50, "10 * 10 / 2 = 50");
	// dexterity 15 gives 0, below 15 a negative rate (idiv truncates towards 0, no floor)
	Check(Rate(Player(40, 3, 15, 30)) == 0, "dexterity 15: 0");
	Check(Rate(Player(40, 3, 10, 30)) == -3, "dexterity 10: -215 / 60 = -3 (truncated towards 0)");
	Check(Shown(Rate(Player(40, 3, 10, 30))) == 0, "a negative rate shows as 0");
	Check(Shown(0) == 0 && Shown(1) == 1 && Shown(75) == 75, "Shown keeps 1..75");

	// Median XL 2012: BlockFactor 0-3; a Barbarian (0) with a 50% block shield, 250 dexterity, level 100:
	// 50 * 235 / 200 = 58
	Check(Rate(Player(50, MedianBlockFactor[4], 250, 100)) == 58, "Median Barbarian 50 * 235 / 200 = 58");
	// Median Amazon (3), 30 toblock, 100 dexterity, level 60: 33 * 85 / 120 = 23
	Check(Rate(Player(30, MedianBlockFactor[0], 100, 60)) == 23, "Median Amazon 33 * 85 / 120 = 23");
	Check(MedianBlockFactor[3] == 1 && MedianBlockFactor[5] == 2 && MedianBlockFactor[6] == 3, "Median Paladin 1, Druid 2, Assassin 3");
	Check(VanillaBlockFactor[3] == 30 && VanillaBlockFactor[0] == 25 && VanillaBlockFactor[1] == 20, "vanilla 25 / 20 / 30");

	// classic: no dexterity / level scaling, still capped
	Inputs classic = Player(30, 30, 140, 80);
	classic.expansion = false;
	Check(Rate(classic) == 60, "classic: toblock + BlockFactor");
	classic.toBlock = 70;
	Check(Rate(classic) == 75, "classic: capped");

	// the server's roll while running
	Check(RateWhileRunning(75) == 25 && RateWhileRunning(46) == 15 && RateWhileRunning(2) == 0, "running: rate / 3");

	// overflow guard: the largest real inputs stay inside int32 (toblock and dexterity are far below 46340)
	Check(Rate(Player(1000, 3, 30000, 1)) == 75, "large inputs cap without overflow");

	if (failures == 0) {
		std::printf("block_rate: all checks passed\n");
	}
	return failures == 0 ? 0 : 1;
}

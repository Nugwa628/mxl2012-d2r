// D2R's Chance to Block (the value the server rolls a block against and the sheet's own defense tooltip shows), for a plugin
// that shows it (the Stat Book's Defense page). Pure part, no Windows headers, no game calls; unit test plugin/tests/block_rate_test.cpp.
//
// The game function (image 0x6ab3782c, D2R 3.3 build 93847): Units::GetBlockRate, RVA 0x347da0, Windows x64 calling convention
//     int32_t GetBlockRate(Unit* unit /* rcx */, int32_t expansion /* edx */);
// the same function as 1.14d Game.exe 0x622720 (redivivus: D2Common::Units::Units::GetBlockRate(pUnit, bExpansion), __stdcall).
// Callers in D2R: the server's block roll 0x44b930 (expansion = game +0x106 != 1; while the defender runs, not walks, the roll
// uses rate / 3; then rand % 100 < rate blocks) and the sheet's defense tooltip 0x1514ca0 (char.cpp: the client's own player
// from 0x8b2d0 / 0x9a480, expansion = !0x8d3b0(), which is 1 when the client's game is classic). A plugin on the UI thread may
// call it the way that tooltip does, with the client's player; or replicate it with Rate() below from the same client stats.
//
// For a player the function returns
//     no shield (0x385be0(inventory, 0) == 0)          0
//     classic                                          toblock + BlockFactor
//     expansion                                        (toblock + BlockFactor) * (dexterity - 15) / (2 * max(level, 1))
// then at most 75. toblock is stat 20 (the shield's own block and every "+% Increased Chance of Blocking" are this stat),
// dexterity stat 2, level stat 12, each read by GetStat 0x2f5020(unit, stat, 0); BlockFactor is charstats.txt's byte at record
// +0x45 (0xfcfc0(unit +0x1bd, class)). The division is idiv (truncates towards 0) and there is no floor: a dexterity below 15
// gives a negative rate, which blocks nothing (the roll needs rate >= 1). Monsters: toblock alone when the monster has a shield
// or monstats NoShldBlock, else 0 (D2R adds a few more monster checks; not replicated here).
//
// Median XL 2012 changes no code here (docs/median-rules-audit.md CH8): its charstats BlockFactor is 0-3 instead of
// vanilla's 20-30, the cap stays 75.
#pragma once

#include <cstddef>
#include <cstdint>

namespace block_rate {

inline constexpr uint64_t GetBlockRateRva = 0x347da0;
// The function's first 20 bytes: push rbp / push rdi / push r15 / sub rsp,0x30 / xor ebp,ebp / mov r15d,edx / mov rdi,rcx /
// test rcx,rcx. Unique in the dumped image's .text (also as a signature: the unwildcarded pattern matches once, at 0x347da0).
inline constexpr uint8_t GetBlockRateEntry[] = {0x40, 0x55, 0x57, 0x41, 0x57, 0x48, 0x83, 0xec, 0x30, 0x33,
                                                0xed, 0x44, 0x8b, 0xfa, 0x48, 0x8b, 0xf9, 0x48, 0x85, 0xc9};
// The same as a drawcap-style signature for a build where the RVA moved ("??" any byte): the entry, then jne +0x18 /
// lea rcx,[rsp+0x50] / call (assert) / test al,al / je / int3.
inline constexpr const char* GetBlockRateSignature =
    "40 55 57 41 57 48 83 ec 30 33 ed 44 8b fa 48 8b f9 48 85 c9 75 18 48 8d 4c 24 50 e8 ?? ?? ?? ?? 84 c0 0f 84 ?? ?? ?? ?? cc";
// The expansion formula itself (lea eax,[rbx-0xf] / imul eax,ebp / add ecx,ecx / cdq / idiv ecx / mov ebp,eax), at 0x347fa9:
// a second unique pattern, to confirm a match in another build.
inline constexpr uint8_t FormulaBytes[] = {0x8d, 0x43, 0xf1, 0x0f, 0xaf, 0xc5, 0x03, 0xc9, 0x99, 0xf7, 0xf9, 0x8b, 0xe8};
inline constexpr uint64_t FormulaRva = 0x347fa9;

// The client's "classic game" query the tooltip uses: () -> 1 when classic. Expansion for GetBlockRate is its negation.
inline constexpr uint64_t ClientIsClassicRva = 0x8d3b0;

inline constexpr int StatToBlock = 20;
inline constexpr int StatDexterity = 2;
inline constexpr int StatLevel = 12;
inline constexpr int CharStatsBlockFactor = 0x45;  // byte in D2R's charstats record
inline constexpr int Cap = 75;
inline constexpr int DexterityBase = 15;
inline constexpr int RunningDivisor = 3;  // the server's roll while the defender runs (any moving mode but walk)

using GetBlockRateFn = int32_t (*)(void* unit, int32_t expansion);

struct Inputs {
	bool hasShield = false;
	int32_t toBlock = 0;      // stat 20, all layers summed as GetStat(unit, 20, 0) returns it
	int32_t blockFactor = 0;  // charstats BlockFactor of the class
	int32_t dexterity = 0;    // stat 2
	int32_t level = 1;        // stat 12
	bool expansion = true;
};

// GetBlockRate for a player, step for step.
constexpr auto Rate(const Inputs& in) noexcept -> int32_t {
	if (!in.hasShield) {
		return 0;
	}
	int32_t rate = in.toBlock + in.blockFactor;
	if (in.expansion) {
		const int32_t level = in.level > 1 ? in.level : 1;
		rate = (in.dexterity - DexterityBase) * rate / (2 * level);
	}
	return rate < Cap ? rate : Cap;
}

// The rate the server's roll uses while the defender runs (moving and not walking): GetBlockRate's value / 3 (idiv).
constexpr auto RateWhileRunning(int32_t rate) noexcept -> int32_t {
	return rate / RunningDivisor;
}

// What a sheet row should show: the rate, 0 for "cannot block" (no shield, or a rate below 1, which never blocks).
constexpr auto Shown(int32_t rate) noexcept -> int32_t {
	return rate < 1 ? 0 : rate;
}

// Median XL 2012's charstats BlockFactor by class id (0 Amazon .. 6 Assassin; work/named/charstats.txt), vanilla's next to it.
inline constexpr int32_t MedianBlockFactor[7] = {3, 3, 0, 1, 0, 2, 3};
inline constexpr int32_t VanillaBlockFactor[7] = {25, 20, 20, 30, 25, 20, 25};

}  // namespace block_rate

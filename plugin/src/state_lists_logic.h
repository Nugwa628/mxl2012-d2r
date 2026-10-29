// Pure part of the blaze / spider-lay state list guard (state_lists.cpp; unit test plugin/tests/state_lists_test.cpp).
// No Windows headers, no game calls.
#pragma once

#include <cstddef>
#include <cstdint>

namespace state_lists {

// D2R keeps four functions for vanilla states 13 (blaze) and 22 (spiderlay): a client and a server one each, run for every
// unit that holds the state (client 0xf9aac / 0xf9aca, server 0x445d38 / 0x445d54 test the state, then call them). Each takes
// the unit's stat list of that state (0x2f5940), reads stat 350 / 351 (modifierlist_skill / level) as the skill and level and
// the skill's missile, and makes the trail missile. Median XL 2012 keeps its own states on those ids, as 1.13c ran them
// (shellshock 13: Force Shout; raptured 22: Rapture, NTRAP; docs/id-mapping.md "States D2R's code names by number"), and their
// lists carry no usable skill, so D2R logs an assert (bugs #50 #52) and leaves. 1.14d's functions (Game.exe 0x4e3ab0 /
// 0x5c9d90 for 13; for 22 1.14d makes the fixed missile 143 with skill 173, see docs/unported.md) take the same exits without
// a word. The guard turns the first instruction of each of the three range asserts per function into a jump to the
// instruction after it (the `je` target that skips the assert's int3), so D2R's flow is unchanged and only the log goes.
// The fourth assert of each function (unit not null, 0x85830) stays.
struct Block {
	uint64_t rva;       // the assert's `lea rcx,[rsp+X]`
	uint64_t next;      // the instruction after its int3 (where D2R goes on, assert or not)
	uint8_t bytes[20];  // the whole block as D2R has it, up to and with the int3 (compared before writing)
	uint8_t size;
	const char* what;
};

// clang-format off
inline constexpr Block Blocks[] = {
	// client 13 (blaze, D2Client SkillsSor.cpp): skill out of range, level <= 0, missile out of range
	{0x21ee84, 0x21ee98, {0x48,0x8d,0x4c,0x24,0x20,0xc6,0x44,0x24,0x20,0x00,0xe8,0xdd,0xfc,0xff,0xff,0x84,0xc0,0x74,0x01,0xcc}, 20, "client 13 skill"},
	{0x21eeb8, 0x21eecc, {0x48,0x8d,0x4c,0x24,0x20,0xc6,0x44,0x24,0x20,0x00,0xe8,0x19,0xfc,0xff,0xff,0x84,0xc0,0x74,0x01,0xcc}, 20, "client 13 level"},
	{0x21ef13, 0x21ef27, {0x48,0x8d,0x4c,0x24,0x20,0xc6,0x44,0x24,0x20,0x00,0xe8,0xfe,0xfd,0xff,0xff,0x84,0xc0,0x74,0x01,0xcc}, 20, "client 13 missile"},
	// client 22 (spiderlay, D2Client SkillsMon.cpp)
	{0x221715, 0x221724, {0x48,0x8d,0x4c,0x24,0x30,0xe8,0xa1,0xfc,0xff,0xff,0x84,0xc0,0x74,0x01,0xcc}, 15, "client 22 skill"},
	{0x221744, 0x221753, {0x48,0x8d,0x4c,0x24,0x30,0xe8,0x82,0xf8,0xff,0xff,0x84,0xc0,0x74,0x01,0xcc}, 15, "client 22 level"},
	{0x22178f, 0x22179e, {0x48,0x8d,0x4c,0x24,0x30,0xe8,0xb7,0xf9,0xff,0xff,0x84,0xc0,0x74,0x01,0xcc}, 15, "client 22 missile"},
	// server 13 (0x551450)
	{0x551548, 0x551557, {0x48,0x8d,0x4c,0x24,0x20,0xe8,0xfe,0xfb,0xff,0xff,0x84,0xc0,0x74,0x01,0xcc}, 15, "server 13 skill"},
	{0x55157a, 0x551589, {0x48,0x8d,0x4c,0x24,0x20,0xe8,0xbc,0xf9,0xff,0xff,0x84,0xc0,0x74,0x01,0xcc}, 15, "server 13 level"},
	{0x5515c5, 0x5515d4, {0x48,0x8d,0x4c,0x24,0x20,0xe8,0x51,0xfb,0xff,0xff,0x84,0xc0,0x74,0x01,0xcc}, 15, "server 13 missile"},
	// server 22 (0x578680)
	{0x578759, 0x578768, {0x48,0x8d,0x4c,0x24,0x20,0xe8,0x7d,0xfc,0xff,0xff,0x84,0xc0,0x74,0x01,0xcc}, 15, "server 22 skill"},
	{0x57878c, 0x57879b, {0x48,0x8d,0x4c,0x24,0x20,0xe8,0x5a,0xfb,0xff,0xff,0x84,0xc0,0x74,0x01,0xcc}, 15, "server 22 level"},
	{0x5787e1, 0x5787f0, {0x48,0x8d,0x4c,0x24,0x20,0xe8,0xb5,0xf9,0xff,0xff,0x84,0xc0,0x74,0x01,0xcc}, 15, "server 22 missile"},
};
// clang-format on
inline constexpr size_t BlockCount = sizeof(Blocks) / sizeof(Blocks[0]);
inline constexpr uint32_t PatchSize = 5;

// rel32 of a 5-byte jmp at `from` to `to`.
constexpr auto Rel32(uint64_t from, uint64_t to) noexcept -> int32_t {
	return static_cast<int32_t>(static_cast<int64_t>(to) - static_cast<int64_t>(from + 5));
}

struct Jump {
	uint8_t bytes[5];
};
constexpr auto JumpBytes(const Block& b) noexcept -> Jump {
	const auto rel = static_cast<uint32_t>(Rel32(b.rva, b.next));
	return Jump{{0xe9, static_cast<uint8_t>(rel), static_cast<uint8_t>(rel >> 8), static_cast<uint8_t>(rel >> 16), static_cast<uint8_t>(rel >> 24)}};
}

// The block's shape: lea rcx,[rsp+X] ... call rel32 / test al,al / je +1 / int3, and `next` right after the int3.
constexpr auto WellFormed(const Block& b) noexcept -> bool {
	const size_t n = b.size;
	return n >= 15 && n <= sizeof(b.bytes) && b.bytes[0] == 0x48 && b.bytes[1] == 0x8d && b.bytes[2] == 0x4c && b.bytes[3] == 0x24 &&
	       b.bytes[n - 10] == 0xe8 && b.bytes[n - 5] == 0x84 && b.bytes[n - 4] == 0xc0 && b.bytes[n - 3] == 0x74 && b.bytes[n - 2] == 0x01 &&
	       b.bytes[n - 1] == 0xcc && b.next == b.rva + n;
}

// Target of the block's call to its assert reporter.
constexpr auto ReporterOf(const Block& b) noexcept -> uint64_t {
	const size_t c = b.size - 10;
	const auto rel = static_cast<int32_t>(static_cast<uint32_t>(b.bytes[c + 1]) | (static_cast<uint32_t>(b.bytes[c + 2]) << 8) |
	                                      (static_cast<uint32_t>(b.bytes[c + 3]) << 16) | (static_cast<uint32_t>(b.bytes[c + 4]) << 24));
	return static_cast<uint64_t>(static_cast<int64_t>(b.rva + c + 5) + rel);
}

}  // namespace state_lists

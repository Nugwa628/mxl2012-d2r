// Pure part of the guards for D2R asserts that 1.14d does not have (orig_asserts.cpp; unit test
// plugin/tests/orig_asserts_test.cpp). No Windows headers, no game calls.
#pragma once

#include <cstddef>
#include <cstdint>

namespace orig_asserts {

// Three places where Median XL 2012's data takes a path that D2R and 1.14d (Game.exe, the stand-in for 1.13c, read statically)
// both take, but where D2R logs an assert first and 1.14d says nothing. After each assert D2R goes on exactly as 1.14d does,
// so the guard turns the assert block's first instruction into a jump to where D2R goes after it: only the log line goes.
//
//  animseq   (bug #74, haunt_vasily / haunt_amazon): a monster skill mode that names no MonMode code (Median's Sk1mode `TH`,
//            a player mode) is read as mode 14 (sequence) with sequence -1 by both loaders (1.14d 0x651150, D2R the same
//            result). When the unit enters mode 14, D2Common's "set the animation sequence" (D2R 0x34d900, 1.14d 0x621260) finds
//            no sequence record: 1.14d stores 0 and returns, D2R stores 0, logs `ptUnit->hAnimSequence` (Units.cpp:2835) and
//            returns. The unit then runs mode 14 on the default animdata record (2048 frames, speed 256, no event frame) in both
//            games: it fires nothing and stands until the mode ends (about 82 s) or a hit / death ends it.
//  monequip  (bug #74, flyingscimitar): Median's monequip row for flyingscimitar keeps vanilla's column order under Median's
//            header, so loc1 reads `6`, not a body location; both loaders store -1. The equipment code (D2R 0x56d200, 1.14d
//            0x5d6b60) counts the row's valid locations: 0, so 1.14d goes to the next row (`test ecx,ecx / jle`), D2R logs
//            `count > 0` (SkillAss.cpp:2364) and goes to the same next row. No scimitar is equipped in either game.
//  aurastate (bug #181, goatpriest2 and Median's other Pain Spirit casters): srvdofunc 18 (timed self buff) with a blank
//            aurastate. 1.14d's function (0x5c9480) returns 0 at once when the state is < 0; D2R's (0x553e60) logs
//            `ptSkill->wAuraState >= 0 && ...` (SkillSor.cpp:424) and then returns 0 at the same check. Nothing is applied.
struct Block {
	uint64_t rva;       // the assert's `lea rcx,[rsp+X]`
	uint64_t next;      // where D2R goes after the assert (the target of the block's `je`)
	uint8_t bytes[32];  // the block as D2R has it, from the lea up to and with the int3 (compared before writing)
	uint8_t size;
	uint64_t reporter;  // the assert reporter the block calls (its descriptor names the file, line and message above)
	const char* word;   // off word
	const char* what;
};

// clang-format off
inline constexpr Block Blocks[] = {
	// 0x34d935: lea rcx,[rsp+0x30] / mov [rsp+0x30],al / call 0x346000 / test al,al / je +1 / int3 ; next: cmp qword [rbx+0x40],0
	{0x34d935, 0x34d948, {0x48,0x8d,0x4c,0x24,0x30,0x88,0x44,0x24,0x30,0xe8,0xbd,0x86,0xff,0xff,0x84,0xc0,0x74,0x01,0xcc}, 19,
	 0x346000, "animseq", "mode 14 without a sequence (hAnimSequence)"},
	// 0x56d38b: lea rcx,[rsp+0x32] / mov byte [rsp+0x32],0 / call 0x56bf20 / test al,al / je 0x56d47d / int3 ; next: the next row
	{0x56d38b, 0x56d47d, {0x48,0x8d,0x4c,0x24,0x32,0xc6,0x44,0x24,0x32,0x00,0xe8,0x86,0xeb,0xff,0xff,0x84,0xc0,0x0f,0x84,0xdb,0x00,0x00,0x00,0xcc}, 24,
	 0x56bf20, "monequip", "monequip row without a body location (count > 0)"},
	// 0x553ef4: lea rcx,[rsp+0xb0] / mov byte [rsp+0xb0],0 / call 0x551300 / test al,al / je +1 / int3 ; next: the state < 0 exit test
	{0x553ef4, 0x553f0e, {0x48,0x8d,0x8c,0x24,0xb0,0x00,0x00,0x00,0xc6,0x84,0x24,0xb0,0x00,0x00,0x00,0x00,0xe8,0xf7,0xd3,0xff,0xff,0x84,0xc0,0x74,0x01,0xcc}, 26,
	 0x551300, "aurastate", "timed buff without an aurastate (wAuraState)"},
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

constexpr auto Le32(const uint8_t* p) noexcept -> int32_t {
	return static_cast<int32_t>(static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) | (static_cast<uint32_t>(p[2]) << 16) |
	                            (static_cast<uint32_t>(p[3]) << 24));
}

// Offset of the block's `test al,al` (84 c0) right after its call, or 0 when the shape is not lea ... call / test / je / int3.
constexpr auto TestAt(const Block& b) noexcept -> size_t {
	const size_t n = b.size;
	if (n < 15 || n > sizeof(b.bytes) || b.bytes[0] != 0x48 || b.bytes[1] != 0x8d || b.bytes[n - 1] != 0xcc) {
		return 0;
	}
	if (b.bytes[n - 5] == 0x84 && b.bytes[n - 4] == 0xc0 && b.bytes[n - 3] == 0x74 && b.bytes[n - 2] == 0x01) {
		return n - 5;  // je +1 over the int3
	}
	if (b.bytes[n - 9] == 0x84 && b.bytes[n - 8] == 0xc0 && b.bytes[n - 7] == 0x0f && b.bytes[n - 6] == 0x84) {
		return n - 9;  // je rel32
	}
	return 0;
}

// Target of the block's call to its assert reporter (the call right before the test).
constexpr auto ReporterOf(const Block& b) noexcept -> uint64_t {
	const size_t t = TestAt(b);
	if (t < 5 || b.bytes[t - 5] != 0xe8) {
		return 0;
	}
	return static_cast<uint64_t>(static_cast<int64_t>(b.rva + t) + Le32(&b.bytes[t - 4]));
}

// Where the block's `je` goes when the reporter returns 0 (the normal case: no debugger), i.e. where D2R goes on.
constexpr auto ContinueOf(const Block& b) noexcept -> uint64_t {
	const size_t t = TestAt(b);
	if (t == 0) {
		return 0;
	}
	if (b.bytes[t + 2] == 0x74) {
		return b.rva + t + 4 + static_cast<int8_t>(b.bytes[t + 3]);
	}
	return static_cast<uint64_t>(static_cast<int64_t>(b.rva + t + 8) + Le32(&b.bytes[t + 4]));
}

}  // namespace orig_asserts

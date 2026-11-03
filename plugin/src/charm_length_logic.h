// Pure part of the 1.13c conversion length (charm_length.cpp, bug #527; unit test plugin/tests/charm_length_test.cpp). No
// Windows headers, no game calls.
#pragma once

#include <cstddef>
#include <cstdint>

namespace charm_length {

// Skill server do 51 (Mind Blast's conversion; Median's charms and Batstrike's third charge through srvprgfunc3).
// 1.13c (1.14d Skills_SrvDoFunc_051_MindBlast 0x5d76e0, SKILLASS_ApplyConversionToUnit 0x5d7430) converts for
// Param3 + rand(Param4) frames and never reads calc2. D2R's 0x570780 evaluates calc2 instead (0x57090f / 0x57091b: the calc
// evaluator 0x3b5160 on record +0x194) and passes it to 0x5727e0 as the base length (args +0xc; + rand(args +0x10, record
// +0x1c4 Param4)). Batstrike's calc2 is `ulvl`, because function 119 (its second charge, the bats) reads calc2 as their level
// in 1.13c too: on D2R its charm lasted ulvl frames. The calc2 call goes through the int3 pad before 0x570780 to Length(),
// which returns Param3 as 1.13c does; nothing else reads that call.
inline constexpr uint64_t ConvertRva = 0x570780;
inline constexpr uint64_t CalcEvalRva = 0x3b5160;                      // (game byte +0x106, unit, calc, skill, level) -> value
inline constexpr uint64_t LengthCallRva = 0x57091b;                    // mov r8d,[r14+0x194] / mov [rsp+0x20],r15d / call
inline constexpr uint8_t LengthCall[] = {0xe8, 0x40, 0x48, 0xe4, 0xff};  // call 0x3b5160
inline constexpr uint64_t LengthLoadRva = 0x57090f;
inline constexpr uint8_t LengthLoad[] = {0x45, 0x8b, 0x86, 0x94, 0x01, 0x00, 0x00, 0x44, 0x89, 0x7c, 0x24, 0x20};
inline constexpr uint64_t SkillRecordRva = 0x97790;                    // (game byte +0x106, skill) -> skills record or null
inline constexpr size_t Calc2Offset = 0x194;
inline constexpr size_t Param4Offset = 0x1c4;                          // read by 0x570937 as the random part
inline constexpr size_t Param3Offset = Param4Offset - 4;              // Param1-8 are one int array
// The 14 int3 bytes between 0x570772 and 0x570780: the call goes there, to an absolute jump into Length() (the call has
// pushed its return 0x570920; rax is free, the call's result register).
inline constexpr uint64_t PadRva = 0x570772;
inline constexpr uint8_t Pad[12] = {0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc};

// The base length 0x5727e0 gets, in frames: Param3 (no record: 0, as an empty calc gives).
constexpr auto ClassicLength(bool haveRecord, int32_t param3) noexcept -> int32_t {
	return haveRecord ? param3 : 0;
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

}  // namespace charm_length

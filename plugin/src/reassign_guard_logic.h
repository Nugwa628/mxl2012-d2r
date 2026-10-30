// Pure part of the reassign guard (reassign_guard.cpp; unit test plugin/tests/reassign_guard_test.cpp). No Windows headers,
// no game calls.
#pragma once

#include <cstddef>
#include <cstdint>
#include <initializer_list>

namespace reassign_guard {

// The client's handler of server command 0x15 (unit reassign: the server puts a unit on x, y), build 93847: entry 0x15 of the
// client command table (0x22bbe38). It looks the unit up (0x9a5d0), moves it there (0x9bf00, which takes the unit out of its
// old room and puts it into the client room at x, y), and when the unit then has no room (0x34b440 at 0x12add3) it asserts
// "Could not get act!" (D2Client SCmd.cpp:1254, the block at 0x12aec0) and ends the process (0x12e5278(-1) -> 0x12557f0, image
// +0x1255802). 1.14d's handler (Game.exe 0x45d160, line 0x538) ends the game the same way. (Line 1237 of the same file, the
// same text, is command 0x04's check of the player's own room at 0x129ab1; not this guard's.)
inline constexpr uint64_t RvaHandler = 0x12ab40;
// push rsi / push rdi / push r14 / push r15 / sub rsp,0x68 / movzx esi,byte [rcx+0xa] (15 bytes compared; no rip-relative)
inline constexpr uint8_t HandlerEntry[] = {0x40, 0x56, 0x57, 0x41, 0x56, 0x41, 0x57, 0x48, 0x83, 0xec, 0x68, 0x0f, 0xb6, 0x71, 0x0a};
inline constexpr uint64_t RvaLocalPlayerId = 0x8b2d0;  // () -> the local player's unit id
inline constexpr uint64_t RvaPlayerById = 0x9a480;    // (id) -> the player unit
inline constexpr size_t PacketSize = 11;              // 15 type u8, unit type u8, id u32, x u16, y u16, flags u8

// The branch to the end: `je 0x12aec0` after the room check (test rax,rax at 0x12add8). rdi holds the unit there.
inline constexpr uint64_t RvaNoRoomBranch = 0x12addb;
inline constexpr uint8_t NoRoomBranch[] = {0x0f, 0x84, 0xdf, 0x00, 0x00, 0x00};
inline constexpr uint64_t RvaFail = 0x12aec0;   // lea rcx,[rsp+0x90] / mov byte [rsp+0x90],0 / call 0x131120 (assert) / ... exit
inline constexpr uint64_t RvaLeave = 0x12ae7e;  // the handler's own way out (restores r12, rbx; epilogue)
// The 12 int3 bytes between the handler's end (0x12aee4) and the next function (0x12aef0): the branch goes there, to an
// absolute jump into the stub (rax is free: it held the null room).
inline constexpr uint64_t RvaPad = 0x12aee4;
inline constexpr uint8_t Pad[12] = {0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc};

struct Reassign {
	uint8_t unitType;
	uint32_t id;
	uint16_t x, y;
	uint8_t flags;
};

inline auto Parse(const uint8_t* p) noexcept -> Reassign {
	Reassign r{};
	r.unitType = p[1];
	r.id = static_cast<uint32_t>(p[2]) | static_cast<uint32_t>(p[3]) << 8 | static_cast<uint32_t>(p[4]) << 16 | static_cast<uint32_t>(p[5]) << 24;
	r.x = static_cast<uint16_t>(p[6] | p[7] << 8);
	r.y = static_cast<uint16_t>(p[8] | p[9] << 8);
	r.flags = p[10];
	return r;
}

enum class Verdict { Leave, End };

// Where D2R would end the game: a unit other than the local player is left without a room (the handler returns; the client
// learns the unit again when the server sends it into a room the client has). The local player without a room: D2R's own end.
constexpr auto Decide(bool localPlayer) noexcept -> Verdict {
	return localPlayer ? Verdict::End : Verdict::Leave;
}

// rel32 of a 6-byte jcc at `from` to `to`.
constexpr auto Rel32Jcc(uint64_t from, uint64_t to) noexcept -> int32_t {
	return static_cast<int32_t>(static_cast<int64_t>(to) - static_cast<int64_t>(from + 6));
}

struct Branch {
	uint8_t bytes[6];
};

// `je RvaPad` written over the branch at RvaNoRoomBranch.
constexpr auto BranchBytes() noexcept -> Branch {
	const auto rel = static_cast<uint32_t>(Rel32Jcc(RvaNoRoomBranch, RvaPad));
	return Branch{{0x0f, 0x84, static_cast<uint8_t>(rel), static_cast<uint8_t>(rel >> 8), static_cast<uint8_t>(rel >> 16),
	               static_cast<uint8_t>(rel >> 24)}};
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

inline constexpr size_t StubSize = 51;
struct Stub {
	uint8_t bytes[StubSize];
};

// The stub (executable memory of the plugin): calls `bool onNoRoom(unit)` with the unit (rdi) under 32 bytes of shadow space
// (rsp is 16-aligned in the handler's body; no volatile register is live on either way on), then jumps to `leave` when it
// answers true, else to `fail` (D2R's block, unchanged).
//   mov rcx,rdi / sub rsp,0x20 / movabs rax,onNoRoom / call rax / add rsp,0x20 / test al,al / je +12 /
//   movabs rax,leave / jmp rax / movabs rax,fail / jmp rax
constexpr auto StubBytes(uint64_t onNoRoom, uint64_t leave, uint64_t fail) noexcept -> Stub {
	Stub s{};
	size_t n = 0;
	auto put = [&](std::initializer_list<uint8_t> b) {
		for (uint8_t v : b) {
			s.bytes[n++] = v;
		}
	};
	auto put64 = [&](uint64_t v) {
		for (int i = 0; i < 8; ++i) {
			s.bytes[n++] = static_cast<uint8_t>(v >> (8 * i));
		}
	};
	put({0x48, 0x89, 0xf9});
	put({0x48, 0x83, 0xec, 0x20});
	put({0x48, 0xb8});
	put64(onNoRoom);
	put({0xff, 0xd0});
	put({0x48, 0x83, 0xc4, 0x20});
	put({0x84, 0xc0});
	put({0x74, 0x0c});
	put({0x48, 0xb8});
	put64(leave);
	put({0xff, 0xe0});
	put({0x48, 0xb8});
	put64(fail);
	put({0xff, 0xe0});
	return s;
}

}  // namespace reassign_guard

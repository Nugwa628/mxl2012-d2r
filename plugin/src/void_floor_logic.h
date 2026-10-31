// Pure part of the Ancient Tunnels void patch (void_floor.cpp; unit test plugin/tests/void_floor_test.cpp). Lane tunnelfloor,
// docs/maps-hd.md item 12, docs/d2r-addresses.md section 25. No Windows headers, no game calls.
//
// D2R's HD client places its ground plane `data/hd/env/model/global/terrain/outdoor_lod0.model` under every room in the
// per-room loop of 0x6b4a30 (0x6b4b76-0x6b4e20); the plane carries the floor tiles' HD look, so it also covers the black void
// round Median's Ancient Tunnels platform (level 65, belial.ds1). Only level 74 (the Arcane Sanctuary) is skipped:
//   0x6b4b79  mov rax, qword ptr [r14+0x90]        ; the room's level (r14 = room)
//   0x6b4b80  cmp dword ptr [rax+0x1f8], 0x4a      ; level id 74
//   0x6b4b87  je 0x6b4e19                          ; next room (add rsi,0x10 / cmp rsi,r13 / jne 0x6b4b76)
//   0x6b4b8d  cmp byte ptr [rsi+8], 0              ; the plane's own checks go on here
// The patch skips the plane for every level of SkipLevels (74 as before, and 65). The compare and its branch (13 bytes) become
// a jump to the 14 int3 bytes before the function (0x6b4a22-0x6b4a2f, the gap after the previous function), which hold an
// absolute `jmp [rip]` into the stub. The stub compares the level id with each entry and jumps on (absolute `jmp [rip]`, no
// register touched) to the next room or to 0x6b4b8d. Flags are not live at either target (0x6b4b8d and 0x6b4e19 both start
// with an instruction that sets them), and rax is the level pointer as before.
// Room activation (0x6a1958, docs/d2r-addresses.md section 25) places the same plane only for room type 1 (+0x74 == 1, test at
// 0x6a1f44); belial's rooms all come from its one preset (type 2, split by the game into 40x40-sub-tile rooms), and the memory test of lane voidengine (byte 0x6b4b86 = 0x41, run
// checks-20261031-183526-s1) showed the void with only this loop changed, so that path is left as D2R's.
#pragma once

#include <cstddef>
#include <cstdint>

namespace void_floor {

inline constexpr uint64_t SiteRva = 0x6b4b80;
inline constexpr uint8_t Site[13] = {0x83, 0xb8, 0xf8, 0x01, 0x00, 0x00, 0x4a,  // cmp dword ptr [rax+0x1f8], 0x4a
                                     0x0f, 0x84, 0x8c, 0x02, 0x00, 0x00};       // je 0x6b4e19
// Compared before writing (read only): the load of the level before the site, and the loop step at the branch target.
inline constexpr uint64_t LoadRva = 0x6b4b79;
inline constexpr uint8_t Load[7] = {0x49, 0x8b, 0x86, 0x90, 0x00, 0x00, 0x00};  // mov rax, qword ptr [r14+0x90]
inline constexpr uint64_t NextRoomRva = 0x6b4e19;
inline constexpr uint8_t NextRoom[] = {0x48, 0x83, 0xc6, 0x10, 0x49, 0x3b, 0xf5, 0x0f, 0x85, 0x50, 0xfd, 0xff, 0xff};  // add rsi,0x10 / cmp rsi,r13 / jne 0x6b4b76
inline constexpr uint64_t PlaneRva = 0x6b4b8d;   // after the branch: cmp byte ptr [rsi+8], 0
inline constexpr uint64_t LoopRva = 0x6b4b76;
inline constexpr uint64_t PadRva = 0x6b4a22;
inline constexpr uint8_t Pad[14] = {0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc};
inline constexpr uint32_t LevelIdOffset = 0x1f8;

// Levels without the ground plane: D2R's own 74 (the Arcane Sanctuary), and Median's 65 (the Ancient Tunnels, belial.ds1).
inline constexpr int32_t SkipLevels[] = {74, 65};
inline constexpr size_t SkipCount = sizeof(SkipLevels) / sizeof(SkipLevels[0]);

// D2R's rule and the patched one, for a level id.
constexpr auto D2RSkips(int32_t level) noexcept -> bool {
	return level == 74;
}
constexpr auto Skips(int32_t level) noexcept -> bool {
	for (size_t i = 0; i < SkipCount; ++i) {
		if (SkipLevels[i] == level) {
			return true;
		}
	}
	return false;
}

// rel32 of a 5-byte jmp at `from` to `to`.
constexpr auto Rel32(uint64_t from, uint64_t to) noexcept -> int32_t {
	return static_cast<int32_t>(static_cast<int64_t>(to) - static_cast<int64_t>(from + 5));
}

struct SiteBytes {
	uint8_t bytes[sizeof(Site)];
};

// jmp PadRva, then nop to the end of the 13 bytes (never reached).
constexpr auto SitePatch() noexcept -> SiteBytes {
	SiteBytes s{};
	const auto rel = static_cast<uint32_t>(Rel32(SiteRva, PadRva));
	s.bytes[0] = 0xe9;
	for (int i = 0; i < 4; ++i) {
		s.bytes[1 + i] = static_cast<uint8_t>(rel >> (8 * i));
	}
	for (size_t i = 5; i < sizeof(s.bytes); ++i) {
		s.bytes[i] = 0x90;
	}
	return s;
}

struct AbsJump {
	uint8_t bytes[14];
};

// jmp qword ptr [rip+0] / dq to (no register used).
constexpr auto AbsJumpBytes(uint64_t to) noexcept -> AbsJump {
	AbsJump j{{0xff, 0x25, 0, 0, 0, 0}};
	for (int i = 0; i < 8; ++i) {
		j.bytes[6 + i] = static_cast<uint8_t>(to >> (8 * i));
	}
	return j;
}

inline constexpr size_t CompareSize = 9;   // cmp dword ptr [rax+0x1f8], imm8 (7) / je rel8 (2)
inline constexpr size_t StubSize = SkipCount * CompareSize + 2 * sizeof(AbsJump);
struct Stub {
	uint8_t bytes[StubSize];
};

// The stub: per level `cmp dword ptr [rax+0x1f8], level / je skip`, then `jmp [rip] plane`, skip: `jmp [rip] nextRoom`.
// Level ids must fit a signed imm8 (0..127).
constexpr auto StubBytes(uint64_t plane, uint64_t nextRoom) noexcept -> Stub {
	Stub s{};
	size_t n = 0;
	const size_t skip = SkipCount * CompareSize + sizeof(AbsJump);
	for (size_t i = 0; i < SkipCount; ++i) {
		const uint8_t cmp[7] = {0x83, 0xb8, static_cast<uint8_t>(LevelIdOffset), static_cast<uint8_t>(LevelIdOffset >> 8), 0x00, 0x00,
		                        static_cast<uint8_t>(SkipLevels[i])};
		for (uint8_t b : cmp) {
			s.bytes[n++] = b;
		}
		s.bytes[n++] = 0x74;
		s.bytes[n] = static_cast<uint8_t>(skip - (n + 1));
		++n;
	}
	for (uint8_t b : AbsJumpBytes(plane).bytes) {
		s.bytes[n++] = b;
	}
	for (uint8_t b : AbsJumpBytes(nextRoom).bytes) {
		s.bytes[n++] = b;
	}
	return s;
}

// What the stub does for a level id (an interpreter of StubBytes' compares, for the test): true = to nextRoom.
constexpr auto StubSkips(const Stub& s, int32_t level) noexcept -> bool {
	size_t pc = 0;
	while (pc < SkipCount * CompareSize) {
		const bool eq = static_cast<int32_t>(static_cast<int8_t>(s.bytes[pc + 6])) == level;
		pc += 7;
		const size_t target = pc + 2 + s.bytes[pc + 1];
		pc += 2;
		if (eq) {
			return target == SkipCount * CompareSize + sizeof(AbsJump);
		}
	}
	return false;
}

}  // namespace void_floor

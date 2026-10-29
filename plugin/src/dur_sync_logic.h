// Pure part of the durability update patch (dur_sync.cpp; unit test plugin/tests/dur_sync_test.cpp). Lane dursync, bug #433.
// No Windows headers, no game calls.
//
// D2R's wear dispatcher 0x441b10 (game, unit, item) takes one point off a worn item's durability (stat 0x48) in its loss
// branch and sends the new value to the wearer's client with packet 0x3e:
//   0x441c38  call 0x2f7940(item, 0x48, value, 0)        ; set the stat
//   0x441c3d  test rbp,rbp / je 0x441e73                  ; rbp = the wearer's client (0x48fde0)
//   0x441c46  xor esi,esi / mov rcx,rbp
//   0x441c4b  mov word ptr [rsp+0x28],si                  ; 6th argument: the stat's layer, 0 (16 bits)
//   0x441c50  mov dword ptr [rsp+0x20],ebx                ; 5th argument: the value
//   0x441c54  jmp 0x441e62 -> mov r9d,0x48 / mov r8b,1 / mov rdx,rdi / call 0x47a190(client, item, 1, 0x48, value, layer)
// The word store leaves the upper six bytes of the 8-byte argument slot as they were (seen in game: 0x140380000). D2R's own
// sender body reads 16 bits (movzx ebx, word [rsp+0xd8]), but D2RLoader replaces 0x47a190 (a `jmp [rip]` thunk to its own
// code), and that path reads the slot wider: the client never applies the update. Its tooltip keeps the old durability and
// the smith's Repair All reads 0 until the item is moved, which sends the whole item (bug #433). With the slot passed on
// clean (a wrapper that re-stores it) the update lands; passed on as it is, it does not (runs checks-20261029-105438-s3 /
// -111824-s3, docs/testing.md). Every other call of 0x47a190 in the wear dispatcher stores the layer as a dword.
//
// The patch stores the whole slot: `mov qword ptr [rsp+0x28],rsi` (REX.W instead of the 0x66 prefix, same length); rsi is 0
// from the `xor esi,esi` right before it.
#pragma once

#include <cstddef>
#include <cstdint>

namespace dur_sync {

inline constexpr uint64_t PatchRva = 0x441c4b;
inline constexpr uint32_t PatchSize = 5;
inline constexpr uint8_t Old[PatchSize] = {0x66, 0x89, 0x74, 0x24, 0x28};  // mov word ptr [rsp+0x28],si
inline constexpr uint8_t New[PatchSize] = {0x48, 0x89, 0x74, 0x24, 0x28};  // mov qword ptr [rsp+0x28],rsi

// Compared (read only) before writing: the loss branch from its stat set to the jump into the shared send, and that send.
inline constexpr uint64_t ExpectedRva = 0x441c2b;
inline constexpr uint8_t Expected[] = {
	0x45, 0x33, 0xc9, 0x44, 0x8b, 0xc3, 0x48, 0x8b, 0xcf, 0x41, 0x8d, 0x51, 0x48,  // xor r9d,r9d / mov r8d,ebx / mov rcx,rdi / lea edx,[r9+0x48]
	0xe8, 0x03, 0x5d, 0xeb, 0xff,                                                  // call 0x2f7940
	0x48, 0x85, 0xed, 0x0f, 0x84, 0x2d, 0x02, 0x00, 0x00,                          // test rbp,rbp / je 0x441e73
	0x33, 0xf6, 0x48, 0x8b, 0xcd,                                                  // xor esi,esi / mov rcx,rbp
	0x66, 0x89, 0x74, 0x24, 0x28,                                                  // mov word ptr [rsp+0x28],si   <- patched
	0x89, 0x5c, 0x24, 0x20,                                                        // mov dword ptr [rsp+0x20],ebx
	0xe9, 0x09, 0x02, 0x00, 0x00,                                                  // jmp 0x441e62
};
inline constexpr size_t ExpectedSize = sizeof(Expected);
inline constexpr size_t PatchInExpected = PatchRva - ExpectedRva;  // 0x20
inline constexpr size_t XorInExpected = 0x1b;                     // xor esi,esi
inline constexpr uint64_t SendRva = 0x441e62;
inline constexpr uint8_t Send[] = {0x41, 0xb9, 0x48, 0x00, 0x00, 0x00, 0x41, 0xb0, 0x01,  // mov r9d,0x48 / mov r8b,1
                                   0x48, 0x8b, 0xd7, 0xe8, 0x1d, 0x83, 0x03, 0x00};    // mov rdx,rdi / call 0x47a190
inline constexpr uint64_t SenderRva = 0x47a190;

inline constexpr int32_t StatDurability = 0x48;

// The 8-byte layer slot the sender gets after the store: `slot` is what the stack held before (garbage), `rsi` the register.
constexpr auto SlotAfter(uint64_t slot, uint64_t rsi, bool patched) noexcept -> uint64_t {
	return patched ? rsi : (slot & ~0xffffULL) | (rsi & 0xffff);
}

// The rel32 target of the 5-byte call / jmp at `at` (offset `off` into a block starting at `base`).
constexpr auto Rel32Target(const uint8_t* block, size_t off, uint64_t base) noexcept -> uint64_t {
	const int32_t rel = static_cast<int32_t>(static_cast<uint32_t>(block[off + 1]) | static_cast<uint32_t>(block[off + 2]) << 8 |
	                                         static_cast<uint32_t>(block[off + 3]) << 16 | static_cast<uint32_t>(block[off + 4]) << 24);
	return base + off + 5 + static_cast<int64_t>(rel);
}

}  // namespace dur_sync

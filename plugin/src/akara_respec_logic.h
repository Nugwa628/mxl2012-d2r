// Pure rule of Akara's unlimited respec up to level 100 (akara_respec.cpp; unit test plugin/tests/akara_respec_test.cpp). No
// Windows headers, no game calls.
#pragma once

#include <cstdint>

namespace akara_respec {

// Owner, 2026-11-05: a character of level 1 to 100 can use Akara's "Reset Skills and Stats" any number of times, on every
// difficulty, without the Den of Evil reward. Above 100 D2R's rule stays: the one respec per difficulty that the Den gives.
inline constexpr int32_t MaxLevel = 100;

constexpr auto Unlimited(int32_t level) noexcept -> bool {
	return level >= 1 && level <= MaxLevel;
}

// D2R 93847 keeps the respec in two quest records of the difficulty (the save's quest words): quest 41 bit 1 = a respec is
// waiting (set by the Den of Evil), bit 0 = it was used; quest 1 (Den of Evil) bit 0 = the quest is done.
inline constexpr int32_t RespecQuest = 41;
inline constexpr int32_t RespecUsedBit = 0;
inline constexpr int32_t RespecReadyBit = 1;
inline constexpr int32_t DenQuest = 1;
inline constexpr int32_t DenDoneBit = 0;

// Server: packet 0x39 (CCMD_RESPEC, `u8 0x39, u32 npc unit id`), handler 0x4b2530. D2R's handler respecs only when the NPC's
// row of the static NPC table (0x3971a0, 0x1c bytes; Akara's is the only one with `+5` = 1) gates on quest `+0x10 - 1` = 41 bit
// 1, then marks it used (0x5d9ae0: bit 0 set, bit 1 cleared). The part respecs itself for a player of level 1-100 and leaves
// the quest bits alone, so the Den's own respec is still there after level 100.
inline constexpr int32_t PacketSize = 5;
inline constexpr int32_t NpcRange = 0x32;  // 0x53b8f0's distance, as D2R's handler passes it
inline constexpr int RowRespec = 5;        // NPC table row byte: the NPC offers the respec

enum class Server { D2R, Respec };

// `npcOffersRespec`: the NPC was found within range and its row has the respec byte.
constexpr auto DecideServer(int32_t size, uint32_t npcId, int32_t level, bool npcOffersRespec) noexcept -> Server {
	if (size != PacketSize || npcId == 0xffffffffu || !Unlimited(level) || !npcOffersRespec) {
		return Server::D2R;
	}
	return Server::Respec;
}

// Client: the menu opener (0x1141d0) adds the line (string 0x2ba0, handler 0x109200) through its service table entry
// {Akara 0x94, quest 1, bit 0, set}; the menu builder (0x1147a0, which the opener calls, and which rebuilds the menu after a
// sub-page) keeps the line when quest 41 bit 0 is clear and bit 1 set. Both read the client's own copy of the record
// (0x2a48778). For Akara and a local player of level 1-100 the part shows those three bits as "Den done, respec waiting, not
// used" while the two run, and puts the client's real bits back right after.
inline constexpr int32_t AkaraClass = 0x94;

struct Bits {
	bool denDone, ready, used;
};

constexpr auto Shown() noexcept -> Bits {
	return {true, true, false};
}

constexpr auto FakeClient(int32_t npcClass, int32_t level) noexcept -> bool {
	return npcClass == AkaraClass && Unlimited(level);
}

// Builder 0x1147a0 (chunk 0x114c20): the line is dropped when quest 41 bit 0 is set; kept when bit 1 is set, or in Hell
// (0x8af40() == 2) when Den of Evil is done, so D2R shows the line in Hell to a character without a respec, and its server then
// refuses it. Owner, 2026-11-05: above 100 the line shows only while the Den's respec is waiting. For Akara, a local player above
// 100 and no respec waiting, the builder sees bit 0 ("used") set, so its first test drops the line.
constexpr auto HideLine(int32_t npcClass, int32_t level, bool ready) noexcept -> bool {
	return npcClass == AkaraClass && level > MaxLevel && !ready;
}

}  // namespace akara_respec

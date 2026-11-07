// Pure part of "Send storable/stackable items to stash" (send_stash.cpp; unit test plugin/tests/send_stash_test.cpp). No Windows
// headers, no game calls.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace send_stash {

// Client functions of build 93847 (the dump's first bytes; the part checks them before it turns on).
// (op, sub, a, b, c, d, e): the client packet builder of the Reign of the Warlock stash. D2R's Ctrl+click into a Gems / Materials
// / Runes page runs 0x2c73d0 -> 0x15f8b0 -> 0x159a30(item, stash unit), which calls 0xec880(0x63, 0, item id, stash unit id, 0,
// 0, 0): packet 0x63 sub 0 (deposit), 0x19 bytes. Server: 0x4c4af0 -> 0x4f92f0 checks that the stash unit has state 0xd1 and
// belongs to the player, that the page is active and that the item's row has AdvancedStashStackable, and refuses when the slot
// holds more than 0x62 (99 is full) with D2R's "Impossible." (0x491960(player, 0x14, 0)); no town, bank or panel check.
inline constexpr uint64_t RvaSend = 0xec880;
inline constexpr uint8_t SendEntry[] = {0x48, 0x83, 0xec, 0x58, 0x48, 0x8b, 0x05, 0x3d, 0xea, 0x8d, 0x02, 0x48, 0x33, 0xc4, 0x48, 0x89};
inline constexpr uint32_t OpAdvancedStash = 0x63;
inline constexpr uint32_t SubDeposit = 0;
inline constexpr uint64_t RvaLocalId = 0x8b2d0;    // () -> the client's own player id
inline constexpr uint8_t LocalIdEntry[] = {0x8b, 0x05, 0x2e, 0x84, 0x99, 0x02, 0xc3};
inline constexpr uint64_t RvaPlayerById = 0x9a480; // (id) -> the client player unit or null
inline constexpr uint8_t PlayerByIdEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x08, 0x57, 0x48, 0x83, 0xec, 0x20, 0x83, 0xf9, 0x08, 0x0f, 0x83, 0x85};
inline constexpr uint64_t RvaClientUnit = 0x9a5d0; // (id, unit type) -> the client's unit (type 0 player, 4 item)
inline constexpr uint8_t ClientUnitEntry[] = {0x4c, 0x63, 0xca, 0x48, 0x8d, 0x05, 0x36, 0x93, 0x98, 0x02, 0x8b, 0xd1, 0x44, 0x8b, 0xc1, 0x49};
inline constexpr uint64_t RvaInventory = 0x34a360; // (unit, file, line) -> inventory
inline constexpr uint8_t InventoryEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x18, 0x56, 0x48, 0x83, 0xec, 0x20, 0x48, 0x8b, 0xf1, 0x48, 0x85, 0xc9};
inline constexpr uint64_t RvaInvFirst = 0x388c10;  // (inventory) -> first item
inline constexpr uint8_t InvFirstEntry[] = {0x40, 0x53, 0x48, 0x83, 0xec, 0x20, 0x48, 0x8b, 0xd9, 0x48, 0x85, 0xc9, 0x74, 0x2e, 0x81, 0x39};
inline constexpr uint64_t RvaInvNext = 0x38aba0;   // (item) -> next item
inline constexpr uint8_t InvNextEntry[] = {0x40, 0x53, 0x48, 0x83, 0xec, 0x20, 0x48, 0x8b, 0xd9, 0x48, 0x85, 0xc9, 0x75, 0x10, 0x88, 0x4c};
inline constexpr uint64_t RvaUnitClass = 0x349860; // (unit, file, line) -> class id
inline constexpr uint64_t RvaUnitId = 0x34a330;    // (unit, file, line) -> unit id (the same first bytes as 0x349860)
inline constexpr uint8_t UnitFieldEntry[] = {0x48, 0x83, 0xec, 0x28, 0x48, 0x85, 0xc9, 0x75, 0x1d, 0x88, 0x4c, 0x24, 0x30, 0x48, 0x8d, 0x4c};
inline constexpr uint64_t RvaDataFlag = 0x34a0e0;  // (unit) -> data flag byte, as client functions read it (d2r.h)
inline constexpr uint64_t RvaItemRecord = 0x314110; // (dataFlag, class id) -> items record (+0x80 code)
inline constexpr size_t RecordCode = 0x80;
inline constexpr uint64_t RvaItemPage = 0x36cfe0;  // (item) -> page byte (0 backpack, 3 cube, 4 stash)
inline constexpr uint8_t ItemPageEntry[] = {0x40, 0x53, 0x48, 0x83, 0xec, 0x20, 0x48, 0x8b, 0xd9, 0x48, 0x85, 0xc9, 0x74, 0x0a, 0xe8, 0xdd};
inline constexpr uint64_t RvaHasState = 0x3351b0;  // (unit, state) -> non-zero when set
inline constexpr uint8_t HasStateEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x08, 0x48, 0x89, 0x74, 0x24, 0x10, 0x57, 0x48, 0x83, 0xec, 0x20, 0x8b};
// Server: (game, unit type, id) -> unit; (player) -> its client; (client, record) writes chat packet 0x26 (docs/d2r-addresses.md 13).
inline constexpr uint64_t RvaServerUnit = 0x48fe80;
inline constexpr uint64_t RvaClientOf = 0x48fde0;
inline constexpr uint8_t ClientOfEntry[] = {0x40, 0x53, 0x48, 0x83, 0xec, 0x20, 0x48, 0x8b, 0xd9, 0x48, 0x85, 0xc9, 0x74, 0x1e, 0xe8};
// the empty panel that makes the button's message one of a known panel (mxl2012-core/SendStash)
inline constexpr char PanelLocalId[] = "SendStash";
inline constexpr char PanelLayout[] = R"({"type": "Widget", "name": "MxlSendStashPanel", "fields": {"rect": {"x": 0, "y": 0, "width": 1, "height": 1}}})";
inline constexpr uint64_t RvaSendChat = 0x477a30;
inline constexpr uint8_t SendChatEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x18, 0x55, 0x56, 0x57, 0x41, 0x56, 0x41, 0x57, 0x48, 0x81, 0xec};

// Inventory (+0 magic): +0x40 the item on the cursor; +0x68 the list of the player's linked units, one 0x18-byte node each (+0 unit
// id, +0xa kind, +0x10 next), filled by 0x385860 on the server and by the client's packet handler 0x12df10. The Reign of the
// Warlock stash unit ("advanced stash", made at game join by 0x52f8d0) is the player unit (type 0) in that list with state 0xd1.
inline constexpr uint32_t InventoryMagic = 0x1020304;
inline constexpr size_t InventoryCursor = 0x40;
inline constexpr size_t InventoryLinks = 0x68;
inline constexpr size_t LinkUnitId = 0;
inline constexpr size_t LinkNext = 0x10;
inline constexpr unsigned MaxLinks = 16;
inline constexpr int32_t StateAdvancedStash = 0xd1;
inline constexpr uint32_t PageBackpack = 0;
inline constexpr int StackCap = 99;
inline constexpr unsigned MaxItems = 128;           // a 10 x 6 backpack holds at most 60
inline constexpr uint64_t TakenTimeoutMs = 1000;    // an item still in the backpack after this: the server refused it (slot full)

// The joiners' switch (owner, 2026-11-05): on only after a game test shows a joiner's stash keeps the items after leaving and
// rejoining. That needs two game instances, which this PC does not have for the port, so it stays off.
inline constexpr bool JoinersOn = false;

// "r01" -> the record's 4-byte code ("r01 ").
constexpr auto CodeOf(const char* s) noexcept -> uint32_t {
	uint32_t v = 0;
	for (int i = 0; i < 4; ++i) {
		const char c = s[i] == '\0' ? ' ' : s[i];
		v |= static_cast<uint32_t>(static_cast<uint8_t>(c)) << (8 * i);
		if (s[i] == '\0') {
			for (int j = i + 1; j < 4; ++j) {
				v |= static_cast<uint32_t>(' ') << (8 * j);
			}
			break;
		}
	}
	return v;
}

// The code as text without the padding ("r01").
inline void CodeText(uint32_t code, char out[5]) noexcept {
	for (int i = 0; i < 4; ++i) {
		out[i] = static_cast<char>((code >> (8 * i)) & 0xff);
	}
	out[4] = '\0';
	for (int i = 3; i >= 0 && (out[i] == ' ' || out[i] == '\0'); --i) {
		out[i] = '\0';
	}
}

template <size_t N>
auto CodeIndex(uint32_t code, const char (&codes)[N][5]) noexcept -> int {
	for (size_t i = 0; i < N; ++i) {
		if (CodeOf(codes[i]) == code) {
			return static_cast<int>(i);
		}
	}
	return -1;
}

template <size_t N>
auto IsSlotCode(uint32_t code, const char (&codes)[N][5]) noexcept -> bool {
	return CodeIndex(code, codes) >= 0;
}

// Which of the three buttons shows. `hasPlayer`: the client has a local player; `joined`: no server game of this process has that
// player (a joiner of another player's game); `hasStash`: the player has the RotW stash unit.
enum class Show { None, Button, NoSlots, Joined };

constexpr auto Decide(bool hasPlayer, bool joined, bool hasStash, bool joinersOn = JoinersOn) noexcept -> Show {
	if (!hasPlayer) {
		return Show::None;
	}
	if (joined && !joinersOn) {
		return Show::Joined;
	}
	return hasStash ? Show::Button : Show::NoSlots;
}

// The chat line for a click while the button is greyed (bug #554: the greyed button gave no answer at all); null for the others.
constexpr auto RefusalLine(Show show) noexcept -> const char* {
	switch (show) {
	case Show::NoSlots:
		return "Send to stash works in Reign of the Warlock games only (its Gems, Materials, Runes, Median and Orbs stash pages).";
	case Show::Joined:
		return "Send to stash is not available when joined to another player's game.";
	default:
		return nullptr;
	}
}

// Every button but the one that shows is hidden and disabled: D2R hit-tests a hidden widget, so a hidden button on top took the
// clicks and the hover (tooltip) of the greyed one under it (bug #554).
constexpr auto ButtonActive(Show button, Show shown) noexcept -> bool {
	return button == shown;
}

// A backpack item with a slot code; `stack` = what its slot holds now when known (0: not read; the server refuses past 99).
struct Candidate {
	uint32_t id;
	uint32_t code;
	int32_t cls;
	int stack;
};

enum class Verdict : uint8_t { Send, Full };

// In backpack order: an item goes when its slot plus the items already planned for it stay under the cap; the rest of that
// class stays ("stack full"). `items[i].stack` is the slot's count read before the run (the same for every item of a class).
inline void Plan(const Candidate* items, size_t n, Verdict* out) noexcept {
	for (size_t i = 0; i < n; ++i) {
		int planned = 0;
		for (size_t j = 0; j < i; ++j) {
			if (items[j].cls == items[i].cls && out[j] == Verdict::Send) {
				++planned;
			}
		}
		out[i] = items[i].stack + planned < StackCap ? Verdict::Send : Verdict::Full;
	}
}

// One name of the "stack full" list with how many of it stayed.
struct Stayed {
	char name[48];
	int count;
};

// A string-table name without its leading icon: D2R's rune and gem names start with a private-use glyph and ';'
// ("\xee\x81\xbe;El Rune", U+E07E). Returns the text after that marker, else `name` itself.
inline auto PlainName(const char* name) noexcept -> const char* {
	if (static_cast<unsigned char>(name[0]) == 0xee) {
		for (const char* p = name; *p != '\0' && p - name < 8; ++p) {
			if (*p == ';') {
				return p + 1;
			}
		}
	}
	return name;
}

// Adds one stayed item of `name` to `list` (n entries, room for `cap`); returns the new n.
inline auto AddStayed(Stayed* list, size_t n, size_t cap, const char* name) noexcept -> size_t {
	for (size_t i = 0; i < n; ++i) {
		if (std::strcmp(list[i].name, name) == 0) {
			++list[i].count;
			return n;
		}
	}
	if (n >= cap) {
		return n;
	}
	std::snprintf(list[n].name, sizeof(list[n].name), "%s", name);
	list[n].count = 1;
	return n + 1;
}

// The summary line (owner, 2026-11-05): "Sent 14 items. 3 stayed: stack full (El Rune, Chipped Ruby x2)."; " 1 was not taken."
// when the server kept an item; "No storable/stackable items in the backpack." when there was nothing to send. At most 255
// characters (the chat record's text), a long list ends with "...".
inline void Summary(char* out, size_t size, int sent, const Stayed* stayed, size_t nStayed, int notTaken) noexcept {
	if (out == nullptr || size == 0) {
		return;
	}
	int full = 0;
	for (size_t i = 0; i < nStayed; ++i) {
		full += stayed[i].count;
	}
	if (sent == 0 && full == 0 && notTaken == 0) {
		std::snprintf(out, size, "No storable/stackable items in the backpack.");
		return;
	}
	size_t len = 0;
	auto add = [&](const char* fmt, auto... args) {
		if (len < size) {
			const int n = std::snprintf(out + len, size - len, fmt, args...);
			len = n < 0 ? size : len + static_cast<size_t>(n);
		}
	};
	add("Sent %d item%s.", sent, sent == 1 ? "" : "s");
	if (full > 0) {
		add(" %d stayed: stack full (", full);
		for (size_t i = 0; i < nStayed; ++i) {
			const size_t room = size > 8 ? size - 8 : 0;  // keeps space for "...)."
			if (len + std::strlen(stayed[i].name) + 6 > room) {
				add("...");
				break;
			}
			add(stayed[i].count > 1 ? "%s%s x%d" : "%s%s", i == 0 ? "" : ", ", stayed[i].name, stayed[i].count);
		}
		add(").");
	}
	if (notTaken > 0) {
		add(" %d %s not taken.", notTaken, notTaken == 1 ? "was" : "were");
	}
	if (len >= size) {
		out[size - 1] = '\0';
	}
}

// Chat packet 0x26 record (docs/d2r-addresses.md 13): +0 0x26, +1 type (4: a line in the message log), +2 language, +3 speaker
// unit type, +4 speaker id, +8 colour, +9 name flag, +0x0a name[0x3d], +0x47 text[0xff].
inline constexpr size_t ChatRecordSize = 0x147;
inline constexpr size_t ChatText = 0x47, ChatTextSize = 0xff;
inline constexpr uint8_t ChatLogLine = 4;
inline constexpr uint8_t ChatWhite = 0;

inline void BuildChat(uint8_t* record, uint8_t type, uint8_t colour, const char* text) noexcept {
	std::memset(record, 0, ChatRecordSize);
	record[0] = 0x26;
	record[1] = type;
	record[8] = colour;
	std::snprintf(reinterpret_cast<char*>(record + ChatText), ChatTextSize, "%s", text != nullptr ? text : "");
}

}  // namespace send_stash

// The pure rules of part rotwwarn (rotw_warn.cpp; tests in plugin/tests/rotw_warn_test.cpp): byte signatures, which stash tabs
// need Reign of the Warlock, and the warning line.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdio>

namespace rotw_warn {

// ---- signatures ("48 8B ?? 05": hex bytes, ?? any byte) ----
inline constexpr size_t MaxPattern = 128;

struct Pattern {
	uint8_t bytes[MaxPattern]{};
	bool any[MaxPattern]{};
	size_t size = 0;
};

inline auto HexDigit(char c) noexcept -> int {
	if (c >= '0' && c <= '9') {
		return c - '0';
	}
	c = static_cast<char>(c | 0x20);
	return c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
}

// False on a malformed pattern (odd digit, unknown character, too long, empty).
inline auto Parse(const char* text, Pattern& out) noexcept -> bool {
	out = Pattern{};
	for (const char* p = text; p != nullptr && *p != '\0';) {
		if (*p == ' ') {
			++p;
			continue;
		}
		if (out.size == MaxPattern || p[1] == '\0') {
			return false;
		}
		if (p[0] == '?' && p[1] == '?') {
			out.any[out.size++] = true;
		} else {
			const int hi = HexDigit(p[0]);
			const int lo = HexDigit(p[1]);
			if (hi < 0 || lo < 0) {
				return false;
			}
			out.bytes[out.size++] = static_cast<uint8_t>(hi * 16 + lo);
		}
		p += 2;
		if (*p != '\0' && *p != ' ') {
			return false;
		}
	}
	return out.size > 0;
}

inline auto MatchesAt(const uint8_t* data, const Pattern& p) noexcept -> bool {
	for (size_t k = 0; k < p.size; ++k) {
		if (!p.any[k] && data[k] != p.bytes[k]) {
			return false;
		}
	}
	return true;
}

// The offset of the only match of `p` in data[0..size); -1 when there is none or more than one (a signature must be unique).
inline auto FindUnique(const uint8_t* data, size_t size, const Pattern& p) noexcept -> long long {
	if (p.size == 0 || size < p.size) {
		return -1;
	}
	long long found = -1;
	for (size_t at = 0; at + p.size <= size; ++at) {
		if (MatchesAt(data + at, p)) {
			if (found >= 0) {
				return -1;
			}
			found = static_cast<long long>(at);
		}
	}
	return found;
}

// D2R's own "does this account own Reign of the Warlock" (93847: 0xbe200; its callers are the character creation's game version,
// the Warlock class, the RotW panel layouts and the "Missing Required Account Entitlement" message of 0x5ffb10). It asks the
// platform for the entitlement "rotw-dlc" (the movabs at +0x5c is that text) or D2R's own override flag. () -> bool.
inline constexpr char OwnsRotwPattern[] =
    "48 89 5C 24 08 57 48 83 EC 50 48 8B 05 ?? ?? ?? ?? 48 33 C4 48 89 44 24 48 E8 ?? ?? ?? ?? 0F B6 D8 48 C7 44 24 28 00 00 00 00 "
    "48 8D 44 24 38 C6 44 24 38 00 48 89 44 24 20 48 8D 4C 24 20 48 B8 0F 00 00 00 00 00 00 80 BA 08 00 00 00 48 89 44 24 30 E8 ?? "
    "?? ?? ?? 48 8B 4C 24 20 48 B8 72 6F 74 77 2D 64 6C 63";

// The client's handler of chat packet 0x26 (93847: 0x12c190): one line in the message log (map_reveal_logic.h BuildChatPacket).
inline constexpr char ClientChatPattern[] = "48 89 5C 24 10 48 89 74 24 18 57 48 81 EC 90 01 00 00 48 8B 05 ?? ?? ?? ?? 48 33 C4 48 89 84 24 80 01 00 00 0F B6 01 48 8D 71 0A 88 44 24 30";

// ---- the tabs ----
// The stash's tabs (tools/median_tabs.py): 0 Personal, 1 Shared, 2 Gems, 3 Materials, 4 Runes, 5 MEDIAN, 6 ORBS. Tabs 2-6 live in
// the RotW shared stash file and its advanced stash unit, which only an account that owns Reign of the Warlock gets.
inline constexpr int FirstRotwTab = 2;
inline constexpr int LastTab = 6;

constexpr auto NeedsRotw(int tab) noexcept -> bool {
	return tab >= FirstRotwTab && tab <= LastTab;
}

// What a tab change does. `owned`: D2R's entitlement answer; `from`: the tab shown before (a valid tab to go back to).
enum class Verdict { Open, Block };

constexpr auto Decide(int to, bool owned) noexcept -> Verdict {
	return NeedsRotw(to) && !owned ? Verdict::Block : Verdict::Open;
}

// The tab the panel keeps instead of a blocked one: the tab shown before when it needs no RotW, else Personal.
constexpr auto FallbackTab(int from) noexcept -> int {
	return from >= 0 && from <= LastTab && !NeedsRotw(from) ? from : 0;
}

// At most one warning line per `gapMs` (a held trigger or a burst of clicks says it once).
constexpr auto WarnNow(uint64_t now, uint64_t last, uint64_t gapMs) noexcept -> bool {
	return last == 0 || now - last >= gapMs;
}
inline constexpr uint64_t WarnGapMs = 2000;
// The banner: a native panel of the plugin with the line in huge red letters on a dark band across the middle of the screen, open for
// BannerMs after each blocked tab change (every one starts the time again). Priority 9000 puts it over the stash (5) and inventory.
inline constexpr uint64_t BannerMs = 3500;
// Shown at `now` when it ends at `until` (0: none yet).
constexpr auto BannerShown(uint64_t now, uint64_t until) noexcept -> bool {
	return until != 0 && now < until;
}
inline constexpr char BannerLocalId[] = "RotwWarn";
inline constexpr char BannerPanelName[] = "mxl2012-core/RotwWarn";
inline constexpr char BannerLineName[] = "Line";
// HD: the whole width and 340 of the 3840 x 2160 layout space (142 pixels at 1600 x 900), 100 point letters (42 pixels at 900; the
// English line is about 3200 units wide).
inline constexpr char BannerLayoutHd[] = R"({
"type": "Panel", "name": "mxl2012-core/RotwWarn",
"fields": { "rect": { "x": -1920, "y": -170, "width": 3840, "height": 340 }, "anchor": { "x": 0.5, "y": 0.5 }, "priority": 9000 },
"children": [
{ "type": "RectangleWidget", "name": "Band",
  "fields": { "rect": { "x": 0, "y": 0, "width": 3840, "height": 340 }, "color": [ 0.0, 0.0, 0.0, 0.85 ],
              "borderColor": { "r": 200, "g": 40, "b": 30, "a": 255 } } },
{ "type": "TextBoxWidget", "name": "Line",
  "fields": { "rect": { "x": 0, "y": 0, "width": 3840, "height": 340 }, "text": "This stash tab needs Reign of the Warlock.",
              "style": { "fontColor": { "r": 252, "g": 70, "b": 70, "a": 255 }, "pointSize": 100,
                         "alignment": { "h": "center", "v": "center" } } } }
]
})";
// Legacy: 790 x 80 of the 800 x 600 layout space, D2R's 30 point font, the band opaque (legacy draws it lighter than HD).
inline constexpr char BannerLayoutSd[] = R"({
"type": "Panel", "name": "mxl2012-core/RotwWarn",
"fields": { "rect": { "x": -395, "y": -40, "width": 790, "height": 80 }, "anchor": { "x": 0.5, "y": 0.5 }, "priority": 9000 },
"children": [
{ "type": "RectangleWidget", "name": "Band",
  "fields": { "rect": { "x": 0, "y": 0, "width": 790, "height": 80 }, "color": [ 0.0, 0.0, 0.0, 1.0 ],
              "borderColor": { "r": 200, "g": 40, "b": 30, "a": 255 } } },
{ "type": "TextBoxWidget", "name": "Line",
  "fields": { "rect": { "x": 0, "y": 0, "width": 790, "height": 80 }, "text": "This stash tab needs Reign of the Warlock.",
              "fontType": "30pt",
              "style": { "fontColor": { "r": 252, "g": 70, "b": 70, "a": 255 }, "alignment": { "h": "center", "v": "center" } } } }
]
})";

// The line, with D2R's own name of the expansion (string key RotWLong, localized) or the English name.
inline constexpr char RotwFallbackName[] = "Reign of the Warlock";

// What the line is about: a tab change (Tab), an item that would go into a RotW page (Store: Ctrl-click, the gamepad's moves,
// controller-qol's Deposit All), the inventory's Send to stash button (Send).
enum class Line { Tab, Store, Send };

inline void WarningLine(Line kind, char* out, size_t size, const char* expansionName) noexcept {
	const char* name = expansionName != nullptr && expansionName[0] != '\0' ? expansionName : RotwFallbackName;
	const char* fmt = kind == Line::Store ? "That stash tab needs %s." : kind == Line::Send ? "Send to stash needs %s." : "This stash tab needs %s.";
	std::snprintf(out, size, fmt, name);
}

inline void WarningLine(char* out, size_t size, const char* expansionName) noexcept {
	WarningLine(Line::Tab, out, size, expansionName);
}

// ---- items put into the RotW pages without opening them (docs/bugs.md #591) ----
// Every client route into the advanced stash ends in packet 0x63 sub 0 (send_stash_logic.h). Its sender 0xec880 cannot be hooked
// (a rip-relative load at +4), so the guard sits one step before, at the two places all of D2R's routes pass (93847):
//   - 0x15f320(class id) -> bool "the item has a slot on a RotW page" (the page map 0x22be698). The transfer 0x15f8b0 asks it
//     before its own inline deposit (0x15fa95: Ctrl-click and the gamepad's moves through 0x2c73d0 / 0x1f6674 / 0x2a9d68...,
//     controller-qol's Deposit All) and before 0x159a30 (0x15fdb7); a false answer is D2R's own refusal path. Its other
//     callers (0x15a0b0 / 0x15a39b eligibility, 0x2c4e00 the grid) then treat the item as one without a slot.
//   - 0x159a30(item, stash unit): the deposit packet itself (from 0x15f8b0 at 0x15fdc6 and 0x16001c, the latter without asking
//     0x15f320, and from the slot widget 0x2cf953), void.
// Withdrawals (sub 1 / 2 / 3: 0x159b30, 0x1599a0, 0x159ac0) are left alone.
inline constexpr uint64_t RvaHasSlot = 0x15f320;
inline constexpr uint8_t HasSlotEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x08, 0x48, 0x89, 0x74, 0x24, 0x10, 0x48, 0x89, 0x7c, 0x24, 0x18};
inline constexpr uint64_t RvaDeposit = 0x159a30;
inline constexpr uint8_t DepositEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x08, 0x57, 0x48, 0x83, 0xec, 0x40,
                                           0x48, 0x8b, 0xda, 0x41, 0xb8, 0xec, 0x06, 0x00, 0x00};
// The return addresses of the transfer's two questions to 0x15f320: a refusal there is an item the player tried to store, so it
// gets the warning; the other callers ask while drawing or testing and get none.
inline constexpr uint64_t TransferAsks[] = {0x15fa9a, 0x15fdbc};

constexpr auto IsTransferAsk(uint64_t returnRva) noexcept -> bool {
	for (const uint64_t at : TransferAsks) {
		if (at == returnRva) {
			return true;
		}
	}
	return false;
}

// Items stay out of the RotW pages when the part runs (`found`: D2R's check was found), its gate is on and the account does not
// own RotW.
constexpr auto StoreBlocked(bool found, bool gate, bool owned) noexcept -> bool {
	return found && gate && !owned;
}

// D2R's answer is asked again at most every OwnedCacheMs (0x15f320 is asked while the grid draws).
inline constexpr uint64_t OwnedCacheMs = 2000;

// Dev builds: MXL_ROTW_OWNED_TEST=no makes this part's answer "not owned" (D2R itself still sees its own answer), =yes "owned";
// =d2r-no patches D2R's entitlement check itself to "not owned" (every D2R caller too: an account without RotW as far as D2R
// asks this function); anything else leaves D2R's answer.
enum class OwnedTest { Game, No, Yes, D2rNo };

inline auto ParseOwnedTest(const char* text) noexcept -> OwnedTest {
	if (text == nullptr) {
		return OwnedTest::Game;
	}
	if ((text[0] | 0x20) == 'd' && text[1] == '2' && (text[2] | 0x20) == 'r' && text[3] == '-' && ParseOwnedTest(text + 4) == OwnedTest::No) {
		return OwnedTest::D2rNo;
	}
	const char a = static_cast<char>(text[0] | 0x20);
	if (a == 'n' && (text[1] | 0x20) == 'o' && text[2] == '\0') {
		return OwnedTest::No;
	}
	if (a == 'y' && (text[1] | 0x20) == 'e' && (text[2] | 0x20) == 's' && text[3] == '\0') {
		return OwnedTest::Yes;
	}
	return OwnedTest::Game;
}

}  // namespace rotw_warn

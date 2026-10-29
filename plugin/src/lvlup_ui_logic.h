// Pure part of the classic level-up button refresh (lvlup_ui.cpp, bug #488; unit test plugin/tests/lvlup_ui_test.cpp). No
// Windows headers, no game calls.
#pragma once

#include <cstddef>
#include <cstdint>

namespace lvlup_ui {

// D2R's LevelUpButtonWidget (D2Client UI\Widgets\LevelUpButtonWidget.cpp, the HUD's StatUp / SkillUp, 0xd70 bytes, vtable
// 0x1fd9ee0). Its Update (slot 2, 0x14d1090) reads the player's stat 4 (statpts) / 5 (newskills) through 0x14d0dd0, stores the
// lit mask at +0xd5c and enables (0x86efb0) or disables (0x86eec0: byte +0x67a = 1) the button. D2R's widget tree runs
// Update only on enabled widgets, while Draw (slot 3, 0x14d01a0) runs on disabled ones too. HD's HUD (HUDPanelHD) keeps its
// own buttons going; in legacy graphics a button that went grey (no points) is never updated again, so a level-up there
// leaves it grey and its clicks dead until G (a new HUD) or a new game (lane uiplus, harness `lvlbtn`: in legacy 0 Updates
// against 800 Draws over 2 s; one Update by hand lit both and the tree went on updating them).
inline constexpr uint64_t VtableRva = 0x1fd9ee0;
inline constexpr uint64_t UpdateSlotRva = VtableRva + 2 * 8;  // 0x1fd9ef0
inline constexpr uint64_t DrawSlotRva = VtableRva + 3 * 8;    // 0x1fd9ef8
inline constexpr uint64_t UpdateRva = 0x14d1090;
inline constexpr uint64_t DrawRva = 0x14d01a0;
inline constexpr uint8_t UpdateEntry[] = {0x40, 0x55, 0x57, 0x48, 0x8b, 0xec, 0x48, 0x83, 0xec, 0x48, 0x48, 0x89, 0x5c, 0x24, 0x70, 0x48};
inline constexpr uint8_t DrawEntry[] = {0x40, 0x55, 0x53, 0x56, 0x48, 0x8d, 0xac, 0x24, 0x30, 0xfe, 0xff, 0xff, 0x48, 0x81, 0xec, 0xd0};

// 0x86eec0 (the widget's disable): `mov byte ptr [rcx+0x67a], 1` at +9.
inline constexpr uint64_t DisableRva = 0x86eec0;
inline constexpr uint8_t DisableStore[] = {0xc6, 0x81, 0x7a, 0x06, 0x00, 0x00, 0x01};
inline constexpr size_t DisableStoreAt = 9;
inline constexpr size_t DisabledOffset = 0x67a;

// 0x846210: the panel manager's (global 0x3440170) byte +0xb9, 1 in HD and 0 in legacy graphics (seen in game: `lvlbtn`).
inline constexpr uint64_t HdModeRva = 0x846210;
inline constexpr uint8_t HdModeCode[] = {0x48, 0x8b, 0x05, 0x59, 0x9f, 0xbf, 0x02, 0x48, 0x85, 0xc0, 0x74, 0x08,
                                         0x0f, 0xb6, 0x80, 0xb9, 0x00, 0x00, 0x00, 0xc3};

// The Draw wrapper runs the widget's own Update first when this is true: legacy graphics and the button disabled. An enabled
// button is updated by D2R itself; HD is left exactly as D2R runs it.
constexpr auto NeedsUpdate(bool hd, uint8_t disabled) noexcept -> bool {
	return !hd && disabled != 0;
}

// rip-relative target of `mov rax, [rip+disp]` at `at` (7 bytes).
constexpr auto RipTarget(uint64_t at, int32_t disp) noexcept -> uint64_t {
	return at + 7 + static_cast<uint64_t>(static_cast<int64_t>(disp));
}

}  // namespace lvlup_ui

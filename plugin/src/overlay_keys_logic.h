// The pure part of overlay_keys.cpp (unit-tested in plugin/tests/overlay_keys_test.cpp): the Enemy Health Bars mode cycle,
// the chat lines and when a line may be shown.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdio>

namespace overlay_keys {

// Enemy Health Bars' mode bits, as its export Mxl2012EnemyBarsModeV1 returns them (our patch 0005, mode_config.h):
// Valid, enabled, show_full_health, uniques_bosses_only. 0 = the plugin is not loaded.
inline constexpr uint32_t BarsValid = 0x80000000u, BarsEnabled = 1, BarsFull = 2, BarsUniques = 4;

// The five modes in the order a press goes through them (owner, 2026-11-22): Off -> Always, all monsters -> Always,
// uniques/bosses -> When damaged, all monsters -> When damaged, uniques/bosses -> Off. The shipped default is DamagedAll.
// "Uniques/bosses" is Enemy Health Bars' own Rarity::Unique, the monsters with the orange outline: unique, super unique and
// boss monsters (act bosses and Median's ubers, from the MonStats boss flag). Champions (blue outline) do not count.
enum class BarsMode : int { Off = 0, AlwaysAll = 1, AlwaysUniques = 2, DamagedAll = 3, DamagedUniques = 4 };
inline constexpr int BarsModeCount = 5;

inline auto ModeOf(uint32_t bits) noexcept -> BarsMode {
	if ((bits & BarsEnabled) == 0) {
		return BarsMode::Off;
	}
	const bool uniques = (bits & BarsUniques) != 0;
	if ((bits & BarsFull) != 0) {
		return uniques ? BarsMode::AlwaysUniques : BarsMode::AlwaysAll;
	}
	return uniques ? BarsMode::DamagedUniques : BarsMode::DamagedAll;
}

inline auto NextMode(BarsMode m) noexcept -> BarsMode {
	return static_cast<BarsMode>((static_cast<int>(m) + 1) % BarsModeCount);
}

// The bits that set mode m. Off keeps show_full_health and uniques_bosses_only as they were (only enabled goes false).
inline auto BitsOf(BarsMode m, uint32_t old) noexcept -> uint32_t {
	switch (m) {
	case BarsMode::Off:
		return BarsValid | (old & (BarsFull | BarsUniques));
	case BarsMode::AlwaysAll:
		return BarsValid | BarsEnabled | BarsFull;
	case BarsMode::AlwaysUniques:
		return BarsValid | BarsEnabled | BarsFull | BarsUniques;
	case BarsMode::DamagedAll:
		return BarsValid | BarsEnabled;
	case BarsMode::DamagedUniques:
		return BarsValid | BarsEnabled | BarsUniques;
	}
	return BarsValid | BarsEnabled;
}

inline auto ModeText(BarsMode m) noexcept -> const char* {
	switch (m) {
	case BarsMode::Off:
		return "off";
	case BarsMode::AlwaysAll:
		return "always, all monsters";
	case BarsMode::AlwaysUniques:
		return "always, uniques/bosses";
	case BarsMode::DamagedAll:
		return "when damaged, all monsters";
	case BarsMode::DamagedUniques:
		return "when damaged, uniques/bosses";
	}
	return "?";
}

// What the plugin answered: 1 applied and saved, 0 applied but not saved, -1 refused / not running, -2 not loaded.
inline constexpr int ApplySaved = 1, ApplyNotSaved = 0, ApplyRefused = -1, ApplyMissing = -2;

inline auto Suffix(int result) noexcept -> const char* {
	return result == ApplyNotSaved ? " (not saved)" : "";
}

// "Health bars: when damaged, uniques/bosses"
inline void BarsLine(char* out, size_t n, BarsMode m, int result) noexcept {
	if (result == ApplyMissing) {
		std::snprintf(out, n, "Health bars: the Enemy Health Bars plugin is not loaded");
	} else if (result == ApplyRefused) {
		std::snprintf(out, n, "Health bars: the Enemy Health Bars plugin did not take the setting");
	} else {
		std::snprintf(out, n, "Health bars: %s%s", ModeText(m), Suffix(result));
	}
}

// "Floating damage: off". Not running: the plugin is missing, or its master switch ([general] enabled = false) kept its
// hooks out at the start.
inline void DamageLine(char* out, size_t n, bool on, int result) noexcept {
	if (result == ApplyMissing) {
		std::snprintf(out, n, "Floating damage: the Floating Damage plugin is not loaded");
	} else if (result == ApplyRefused) {
		std::snprintf(out, n, "Floating damage: switched off in ruffneckk-floating-damage.toml (enabled = false)");
	} else {
		std::snprintf(out, n, "Floating damage: %s%s", on ? "on" : "off", Suffix(result));
	}
}

// A chat line during an NPC's speech freezes the speech (docs/d2r-addresses.md 13), so no line is shown while the client
// talks to an NPC (0x2a48760 non-zero: speech, menu, trade) or the NPC menu state (0x2a486a4) is set. The setting is changed
// all the same; only the line is skipped.
inline auto LineAllowed(uint32_t npcValid, uint32_t npcMenuState) noexcept -> bool {
	return npcValid == 0 && npcMenuState == 0;
}

}  // namespace overlay_keys

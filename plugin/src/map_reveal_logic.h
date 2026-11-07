// Pity map reveal, pure part (map_reveal.cpp; docs/plugin-plan.md section 34, docs/map-reveal-research.md). Unit-tested in
// tests/map_reveal_test.cpp.
//
// Explored share of a level = tile area of the level's DRLG rooms that have been active at least once / tile area of all its
// rooms. A room becomes active exactly when D2R adds it to the automap, so the share follows what the automap shows. The
// rooms are counted by their place in the level's room list (at most MaxRooms), one bit each.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace map_reveal {

inline constexpr int DefaultThreshold = 70;  // % explored of the current level before the reveal is offered
inline constexpr int ThresholdAlways = 0;    // threshold 0: the reveal works at once
inline constexpr int ThresholdOff = 101;     // threshold 101: never (the part's key does nothing but say so)
inline constexpr int MaxRooms = 4096;        // rooms of one level that are counted (MapSense's walk limit too)
inline constexpr int MaxLevels = 256;        // level ids kept per game (Median XL 2012: 1-137)
inline constexpr int MaxExclude = 32;
// The five towns: always fully drawn, nothing to reveal (levels.txt rows with PreventTownPortal and a town; 136 / 137 are not
// towns).
inline constexpr int Towns[] = {1, 40, 75, 103, 109};

struct Settings {
	int threshold = DefaultThreshold;
	int exclude[MaxExclude] = {};  // level ids with no reveal (besides the towns); empty by default
	int nExclude = 0;
};

inline auto IsTown(int levelId) noexcept -> bool {
	for (const int t : Towns) {
		if (t == levelId) {
			return true;
		}
	}
	return false;
}

inline auto Excluded(int levelId, const Settings& s) noexcept -> bool {
	if (IsTown(levelId)) {
		return true;
	}
	for (int i = 0; i < s.nExclude; ++i) {
		if (s.exclude[i] == levelId) {
			return true;
		}
	}
	return false;
}

inline auto ClampThreshold(long v) noexcept -> int {
	return v < ThresholdAlways ? ThresholdAlways : v > ThresholdOff ? ThresholdOff : static_cast<int>(v);
}

namespace detail {
inline auto SkipSpace(const char* p, const char* end) noexcept -> const char* {
	while (p < end && (*p == ' ' || *p == '\t')) {
		++p;
	}
	return p;
}
// A decimal integer at p (optional sign); false when there is none.
inline auto ReadInt(const char** pp, const char* end, long* out) noexcept -> bool {
	const char* p = *pp;
	bool neg = false;
	if (p < end && (*p == '-' || *p == '+')) {
		neg = *p == '-';
		++p;
	}
	if (p >= end || *p < '0' || *p > '9') {
		return false;
	}
	long v = 0;
	while (p < end && *p >= '0' && *p <= '9') {
		v = v < 100000000 ? v * 10 + (*p - '0') : v;
		++p;
	}
	*out = neg ? -v : v;
	*pp = p;
	return true;
}
}  // namespace detail

// The [mapreveal] table of mxl2012-core.toml (D2RLoader's config of the plugin):
//   threshold = 70        0 = always, 101 = off; clamped to 0-101
//   exclude = [73, 74]    level ids with no reveal (one line)
// Other tables and keys, comments (#) and unreadable values are skipped; what is missing keeps its default. True when the
// table was found.
inline auto ParseSettings(const char* toml, Settings* out) noexcept -> bool {
	*out = Settings{};
	if (toml == nullptr) {
		return false;
	}
	bool found = false, inside = false;
	for (const char* line = toml; *line != '\0';) {
		const char* nl = std::strchr(line, '\n');
		const char* end = nl != nullptr ? nl : line + std::strlen(line);
		const char* hash = static_cast<const char*>(std::memchr(line, '#', static_cast<size_t>(end - line)));
		const char* stop = hash != nullptr ? hash : end;
		const char* p = detail::SkipSpace(line, stop);
		if (p < stop && *p == '[') {
			const char* close = static_cast<const char*>(std::memchr(p, ']', static_cast<size_t>(stop - p)));
			inside = close != nullptr && close - p - 1 == 9 && std::strncmp(p + 1, "mapreveal", 9) == 0;
			found = found || inside;
		} else if (inside) {
			const char* key = p;
			while (p < stop && ((*p >= 'a' && *p <= 'z') || *p == '_')) {
				++p;
			}
			const size_t keyLen = static_cast<size_t>(p - key);
			p = detail::SkipSpace(p, stop);
			if (p < stop && *p == '=') {
				p = detail::SkipSpace(p + 1, stop);
				long v = 0;
				if (keyLen == 9 && std::strncmp(key, "threshold", 9) == 0 && detail::ReadInt(&p, stop, &v)) {
					out->threshold = ClampThreshold(v);
				} else if (keyLen == 7 && std::strncmp(key, "exclude", 7) == 0 && p < stop && *p == '[') {
					out->nExclude = 0;
					for (++p; p < stop && *p != ']';) {
						p = detail::SkipSpace(p, stop);
						if (detail::ReadInt(&p, stop, &v)) {
							if (v > 0 && v < MaxLevels && out->nExclude < MaxExclude) {
								out->exclude[out->nExclude++] = static_cast<int>(v);
							}
						} else if (p < stop && *p != ']') {
							++p;  // a comma or anything else
						}
					}
				}
			}
		}
		line = nl != nullptr ? nl + 1 : end;
	}
	return found;
}

// Whole percent, rounded down (69.9 % is 69): what the player is told.
inline auto Percent(uint64_t seenArea, uint64_t totalArea) noexcept -> int {
	return totalArea == 0 ? 0 : static_cast<int>(seenArea * 100 / totalArea);
}

enum class Gate { Off, Excluded, Below, Ready };

// May the player reveal this level now? The share is compared exactly (seen * 100 >= threshold * total), not after rounding.
inline auto Decide(int threshold, bool excluded, uint64_t seenArea, uint64_t totalArea) noexcept -> Gate {
	if (threshold >= ThresholdOff) {
		return Gate::Off;
	}
	if (excluded) {
		return Gate::Excluded;
	}
	if (threshold <= ThresholdAlways) {
		return Gate::Ready;
	}
	return totalArea > 0 && seenArea * 100 >= static_cast<uint64_t>(threshold) * totalArea ? Gate::Ready : Gate::Below;
}

// What the part keeps per level id in one game.
struct Level {
	uint64_t bits[MaxRooms / 64];  // rooms seen active, by place in the level's room list
	const void* first;             // the level's first room when the bits were started (another one: the level was built again)
	int rooms;                     // rooms in the list at the last walk
	uint64_t totalArea;            // tile area of all rooms / of the rooms seen, at the last walk
	uint64_t seenArea;
	bool announced;  // the "available" line went out (or the level was revealed)
	bool revealed;
};

inline void ResetLevel(Level* l, const void* first) noexcept {
	std::memset(l, 0, sizeof(*l));
	l->first = first;
}

inline void Mark(Level* l, int index) noexcept {
	if (index >= 0 && index < MaxRooms) {
		l->bits[index / 64] |= uint64_t{1} << (index % 64);
	}
}

inline auto Seen(const Level& l, int index) noexcept -> bool {
	return index >= 0 && index < MaxRooms && (l.bits[index / 64] >> (index % 64) & 1) != 0;
}

// True once per level: the first time it is Ready and not revealed yet (threshold 0 is Ready on arrival, so it announces too).
inline auto ShouldAnnounce(Level* l, Gate g) noexcept -> bool {
	if (g != Gate::Ready || l->announced || l->revealed) {
		return false;
	}
	l->announced = true;
	return true;
}

// The bound key as players read it ("L", "Shift+L", "F5"); "" when the action has no key.
inline void KeyName(uint32_t vk, uint32_t modifier, char* out, size_t n) noexcept {
	char key[16];
	if ((vk >= 'A' && vk <= 'Z') || (vk >= '0' && vk <= '9')) {
		std::snprintf(key, sizeof(key), "%c", static_cast<char>(vk));
	} else if (vk >= 0x70 && vk <= 0x87) {
		std::snprintf(key, sizeof(key), "F%u", vk - 0x6f);
	} else if (vk >= 0x60 && vk <= 0x69) {
		std::snprintf(key, sizeof(key), "Num %u", vk - 0x60);
	} else if (vk == 0) {
		key[0] = '\0';
	} else {
		std::snprintf(key, sizeof(key), "key 0x%02X", vk);
	}
	const char* mod = modifier == 1 ? "Shift+" : modifier == 2 ? "Ctrl+" : modifier == 3 ? "Alt+" : "";
	std::snprintf(out, n, "%s%s", key[0] != '\0' ? mod : "", key);
}

// The chat lines (message log, bottom left).
inline void AvailableLine(char* out, size_t n, int percent, const char* key) noexcept {
	if (key != nullptr && key[0] != '\0') {
		std::snprintf(out, n, "Map: %d%% of this level explored. Press %s to reveal the rest.", percent, key);
	} else {
		std::snprintf(out, n, "Map: %d%% of this level explored. The Reveal Level Map key reveals the rest.", percent);
	}
}

inline void RefusedLine(char* out, size_t n, Gate g, int percent, int threshold, bool revealed) noexcept {
	if (g == Gate::Off) {
		std::snprintf(out, n, "Map: the level reveal is off (mxl2012-core.toml).");
	} else if (g == Gate::Excluded) {
		std::snprintf(out, n, "Map: no reveal in this area.");
	} else if (revealed) {
		std::snprintf(out, n, "Map: this level is already revealed.");
	} else {
		std::snprintf(out, n, "Map: %d%% of this level explored (%d%% needed).", percent, threshold);
	}
}

inline void RevealedLine(char* out, size_t n, int percent, int made, int rooms) noexcept {
	if (made == rooms) {
		std::snprintf(out, n, "Map: rest of the level revealed (%d%% explored).", percent);
	} else {
		std::snprintf(out, n, "Map: level revealed in part (%d of %d rooms).", made, rooms);
	}
}

// Client chat packet 0x26 as the client's handler 0x12c190 reads it (docs/d2r-addresses.md 13): +0 0x26, +1 type (4: message
// log line), +2 language, +3 speaker type, +4 speaker id, +8 colour, +9 name flag, +0x0a the name (zero-terminated, here empty),
// then the text (zero-terminated, at most 255 bytes). Returns the bytes written, 0 when it does not fit.
inline constexpr uint8_t ChatLogLine = 4;
inline constexpr uint8_t ColourWhite = 0, ColourYellow = 9;
inline constexpr size_t ChatPacketMax = 0x0b + 0x100;

inline auto BuildChatPacket(uint8_t* out, size_t n, uint8_t colour, const char* text) noexcept -> size_t {
	const size_t len = text != nullptr ? std::strlen(text) : 0;
	const size_t textLen = len > 0xff ? 0xff : len;
	const size_t need = 0x0b + textLen + 1;
	if (out == nullptr || n < need) {
		return 0;
	}
	std::memset(out, 0, need);
	out[0] = 0x26;
	out[1] = ChatLogLine;
	out[8] = colour;
	if (textLen > 0) {
		std::memcpy(out + 0x0b, text, textLen);
	}
	return need;
}

}  // namespace map_reveal

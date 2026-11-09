// Level map reveal, pure part (map_reveal.cpp; docs/plugin-plan.md section 34, docs/map-reveal-research.md). Unit-tested in
// tests/map_reveal_test.cpp.
//
// The key reveals the current level's automap on every press, from the arrival on (owner, bug #559, 2026-11-08: no explored
// share, no threshold). Only the optional exclusion list of mxl2012-core.toml can refuse it. The act towns are revealed by
// themselves on each arrival, no key needed (owner, 2026-11-08); the list does not stop that.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace map_reveal {

inline constexpr int MaxRooms = 4096;  // rooms of one level that are revealed (MapSense's walk limit too)
inline constexpr int MaxLevels = 256;  // level ids (Median XL 2012: 1-137)
inline constexpr int MaxExclude = 32;

struct Settings {
	int exclude[MaxExclude] = {};  // level ids where the key reveals nothing; empty by default
	int nExclude = 0;
	bool oldThreshold = false;     // the file still has the retired `threshold` key (0.1.15 / 0.1.16): read and ignored
};

// The act towns. Median XL 2012 has no others (levels.txt: only these and the boss level 136 have no monsters of their own);
// D2R's town check 0x327850 compares the same five ids.
inline auto IsTown(int levelId) noexcept -> bool {
	return levelId == 1 || levelId == 40 || levelId == 75 || levelId == 103 || levelId == 109;
}

// The automap layer of a town (levels.txt Layer; D2R's current layer +0 reads the same once it has switched), -1 for other levels.
inline auto TownLayer(int levelId) noexcept -> int {
	return levelId == 1 ? 0 : levelId == 40 ? 27 : levelId == 75 ? 57 : levelId == 103 ? 77 : levelId == 109 ? 79 : -1;
}

// The automatic town reveal: fed the player's level (0: none) and D2R's current automap layer (-1: none) by a poll of about
// 250 ms. True once per arrival in a town, after TownSettlePolls polls in a row with the level the same and the layer the
// town's: D2R's automap callback draws into its current layer.
inline constexpr int TownSettlePolls = 3;

struct TownWatch {
	int level = 0;
	int polls = 0;
	bool done = false;
};

inline auto TownArrival(TownWatch* w, int levelId, int layer) noexcept -> bool {
	if (levelId != w->level) {
		*w = TownWatch{levelId, 0, false};
	}
	if (!IsTown(levelId) || w->done) {
		return false;
	}
	if (layer != TownLayer(levelId)) {
		w->polls = 0;
		return false;
	}
	if (++w->polls < TownSettlePolls) {
		return false;
	}
	w->done = true;
	return true;
}

inline auto Excluded(int levelId, const Settings& s) noexcept -> bool {
	for (int i = 0; i < s.nExclude; ++i) {
		if (s.exclude[i] == levelId) {
			return true;
		}
	}
	return false;
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
//   exclude = [73, 74]    level ids with no reveal (one line)
// `threshold = N` of 0.1.15 / 0.1.16 (the explored share the reveal used to need) is read and ignored: only oldThreshold is
// set. Other tables and keys, comments (#) and unreadable values are skipped; what is missing keeps its default. True when the
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
				if (keyLen == 9 && std::strncmp(key, "threshold", 9) == 0) {
					out->oldThreshold = true;
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
inline void RefusedLine(char* out, size_t n) noexcept {
	std::snprintf(out, n, "Map: no reveal in this area.");
}

inline void RevealedLine(char* out, size_t n, int made, int rooms) noexcept {
	if (made == rooms) {
		std::snprintf(out, n, "Map: level revealed.");
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

// Pure part of the clear legacy fonts setting (clear_fonts.cpp; unit test plugin/tests/clear_fonts_test.cpp). Lane fonttoggle,
// docs/legacy-font-research.md "In-game setting". No Windows headers, no game calls.
//
// D2R 93847 loads a classic font (DC6 + TBL) per font id when a text first asks for it, not once at start:
//   0x90e230 SetFont(id): if id is not the current font (0x2672400) and its slot holds no DC6 (slots 0x34b2a30, 0x28 bytes each:
//            DC6 handle, TBL, TBL copy, glyphs, last use), and graphics are classic (0x846210), it builds the path with 0x90eae0,
//            loads the DC6 (0x145f320) and the TBL (0x90f070, which frees the old TBL first). Every 600 s it frees the DC6 of
//            each other font unused for 240 s (0x79d200(handle), slot = 0), the TBL stays until the next load replaces it.
//   0x90eae0 / 0x90f070: "data\local" "\font\" + language ("latin\", 0x34b2c78) + name ("%s%s%s" / "%s%s%s.tbl"), the name
//            read from the pointer table 0x1d84a00 (14 entries, read nowhere else).
//   0x90da90 the text language set-up (called only from 0x902ff0, call at 0x902ff4): language dir, then it loads font 1.
// The part points the six safe ids' table entries at its own name buffers once. The setting swaps the buffer text between
// D2R's name ("font8") and the clear set's ("clear\font8": data/local/font/latin/clear/, staged by tools/legacy_fonts.py), and
// frees those fonts' DC6s as D2R's idle unload does, so their next SetFont loads the other pair; DC6 and TBL of one id always
// come from the same set. Only for the language dir "latin\": the clear set has no other locale, and a missing font file is an
// assert. The call 0x902ff4 goes through the int3 pad 0x903002 to the part, which puts D2R's names back around the language
// set-up and applies the setting again after it. A font that is current when it has to be freed is first swapped for
// fontformal10 with D2R's own SetFont, then selected again.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace clear_fonts {

inline constexpr uint64_t NameTableRva = 0x1d84a00;
inline constexpr int FontIds = 14;
inline constexpr uint64_t CurrentFontRva = 0x2672400;  // int32: the id SetFont last chose
inline constexpr uint64_t SlotsRva = 0x34b2a30;
inline constexpr uint64_t SlotStride = 0x28;            // +0 DC6 handle (0 = not loaded)
inline constexpr uint64_t LanguageRva = 0x34b2c78;      // char[20] "latin\"
inline constexpr uint64_t FreeDc6Rva = 0x79d200;        // (handle): what 0x90e230 / 0x90ca60 call to free a font's DC6 (entry compared)
inline constexpr uint64_t LangInitRva = 0x90da90;
inline constexpr uint64_t LangCallRva = 0x902ff4;
inline constexpr uint8_t LangCall[5] = {0xe8, 0x97, 0xaa, 0x00, 0x00};  // call 0x90da90
inline constexpr uint64_t PadRva = 0x903002;
inline constexpr uint8_t Pad[14] = {0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc};
// Compared before anything is written (read only): the unload loop of 0x90ca60 (DC6 at slot +0 freed by 0x79d200, TBL at +8) and
// SetFont's load test (slot +0 == 0, then the current id is set).
inline constexpr uint64_t UnloadRva = 0x90ca80;
inline constexpr uint8_t Unload[] = {0x48, 0x8b, 0x4b, 0xf8, 0x48, 0x85, 0xc9, 0x74, 0x09, 0xe8, 0x72, 0x07, 0xe9, 0xff,
                                     0x48, 0x89, 0x73, 0xf8, 0x48, 0x8b, 0x0b, 0x48, 0x89, 0x33};
inline constexpr uint64_t SetFontRva = 0x90e230;  // (id): select a font, loading it when needed (classic graphics)
inline constexpr uint8_t SetFontEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x20, 0x56, 0x57, 0x41, 0x54, 0x41, 0x56, 0x41, 0x57, 0x48, 0x81, 0xec};
// A font the part never redirects (fontformal10): selected for a moment so the current font may be freed.
inline constexpr int StandIn = 4;
inline constexpr uint64_t LoadTestRva = 0x90e291;
inline constexpr uint8_t LoadTest[] = {0x48, 0x83, 0x3c, 0x1f, 0x00, 0x44, 0x89, 0x3d, 0x63, 0x41, 0xd6, 0x01, 0x75, 0x36};
inline constexpr uint8_t FreeDc6Bytes[] = {0x48, 0x85, 0xc9, 0x0f, 0x84, 0xb5, 0x01, 0x00, 0x00};

// D2R's 14 font names at their table order (the table's strings, compared before patching).
inline constexpr const char* D2RNames[FontIds] = {"font8",  "font16",       "font30",         "font42",     "fontformal10",
                                                  "fontformal12", "font6", "font24",       "fontformal11", "fontexocet10",
                                                  "fontridiculous", "fontexocet8", "ReallyTheLastSucker", "fontingamechat"};
inline constexpr uint64_t D2RNameRvas[FontIds] = {0x1d84a90, 0x1d84a98, 0x1d84aa0, 0x1d84aa8, 0x1d84ab0, 0x1d84ac0, 0x1d84ad0,
                                                  0x1d84ad8, 0x1d84ae0, 0x1d84af0, 0x1d84b00, 0x1d84b10, 0x1d84b20, 0x1d84b38};
// The redirected ids: font8, font16, font30, font6, fontexocet8, ReallyTheLastSucker. Formal 10/11/12 and chat stay stock
// (the repack's formal11 has line height 0: divide by zero at 0x90dd16); 42, 24, exocet10 and ridiculous have no clear pair.
inline constexpr int Ids[] = {0, 1, 2, 6, 11, 12};
inline constexpr int Count = static_cast<int>(sizeof(Ids) / sizeof(Ids[0]));
inline constexpr const char* Folder = "clear\\";
inline constexpr size_t NameSize = 32;

inline constexpr const char* Section = "fonts";
inline constexpr const char* Key = "legacy_clear_fonts";

// D2R's name or the clear set's for id slot i (0..Count-1) into out (NameSize). The clear name is the folder plus D2R's name.
inline void NameFor(int i, bool clear, char* out) noexcept {
	const char* name = D2RNames[Ids[i]];
	const size_t folder = clear ? std::strlen(Folder) : 0;
	std::memcpy(out, Folder, folder);
	std::memcpy(out + folder, name, std::strlen(name) + 1);
}

// The clear set is only made for the Latin language dir.
inline auto IsLatin(const char* language) noexcept -> bool {
	return language != nullptr && std::strncmp(language, "latin\\", 7) == 0;
}

// A TBL the classic text code can lay out: 12-byte header "Woo!", version 1, 256 glyphs of 14 bytes, and a line height (byte
// 0x0a) that is not 0 (0x90dd16 divides by it; tools/legacy_fonts.py checks the same before the files are staged).
inline auto TblSafe(const uint8_t* tbl, size_t size) noexcept -> bool {
	if (tbl == nullptr || size != 12 + 256 * 14 || std::memcmp(tbl, "Woo!", 4) != 0) {
		return false;
	}
	const uint32_t version = tbl[4] | tbl[5] << 8 | tbl[6] << 16 | static_cast<uint32_t>(tbl[7]) << 24;
	const uint32_t glyphs = tbl[8] | tbl[9] << 8;
	return version == 1 && glyphs == 256 && tbl[10] != 0;
}

namespace detail {

inline auto SkipSpace(const char* p, const char* stop) noexcept -> const char* {
	while (p < stop && (*p == ' ' || *p == '\t' || *p == '\r')) {
		++p;
	}
	return p;
}

// The line's table name if it is a [table] line (without brackets), else null.
inline auto TableName(const char* p, const char* stop, size_t* len) noexcept -> const char* {
	p = SkipSpace(p, stop);
	if (p >= stop || *p != '[') {
		return nullptr;
	}
	const char* close = static_cast<const char*>(std::memchr(p, ']', static_cast<size_t>(stop - p)));
	if (close == nullptr) {
		return nullptr;
	}
	*len = static_cast<size_t>(close - p - 1);
	return p + 1;
}

inline auto IsKey(const char* p, const char* stop, const char** value) noexcept -> bool {
	p = SkipSpace(p, stop);
	const size_t n = std::strlen(Key);
	if (static_cast<size_t>(stop - p) < n || std::strncmp(p, Key, n) != 0) {
		return false;
	}
	p = SkipSpace(p + n, stop);
	if (p >= stop || *p != '=') {
		return false;
	}
	*value = SkipSpace(p + 1, stop);
	return true;
}

}  // namespace detail

// `[fonts] legacy_clear_fonts = true|false` in mxl2012-core.toml. Anything else (missing, unreadable) is off.
inline auto ParseSetting(const char* toml) noexcept -> bool {
	bool inside = false, on = false;
	for (const char* line = toml; line != nullptr && *line != '\0';) {
		const char* nl = std::strchr(line, '\n');
		const char* end = nl != nullptr ? nl : line + std::strlen(line);
		const char* hash = static_cast<const char*>(std::memchr(line, '#', static_cast<size_t>(end - line)));
		const char* stop = hash != nullptr ? hash : end;
		size_t len = 0;
		const char* value = nullptr;
		if (const char* table = detail::TableName(line, stop, &len)) {
			inside = len == std::strlen(Section) && std::strncmp(table, Section, len) == 0;
		} else if (inside && detail::IsKey(line, stop, &value)) {
			on = static_cast<size_t>(stop - value) >= 4 && std::strncmp(value, "true", 4) == 0;
		}
		line = nl != nullptr ? nl + 1 : end;
	}
	return on;
}

// The config text with the setting set to `on`: the value of an existing key is replaced (the rest of its line, a comment too,
// is kept), else the key goes under an existing [fonts] or a new [fonts] table at the end. False when out is too small.
inline auto WithSetting(const char* toml, bool on, char* out, size_t size) noexcept -> bool {
	const char* value = on ? "true" : "false";
	const char* text = toml != nullptr ? toml : "";
	const char* table = nullptr;  // the line after [fonts]
	bool inside = false;
	for (const char* line = text; *line != '\0';) {
		const char* nl = std::strchr(line, '\n');
		const char* end = nl != nullptr ? nl : line + std::strlen(line);
		const char* hash = static_cast<const char*>(std::memchr(line, '#', static_cast<size_t>(end - line)));
		const char* stop = hash != nullptr ? hash : end;
		size_t len = 0;
		const char* old = nullptr;
		if (const char* name = detail::TableName(line, stop, &len)) {
			inside = len == std::strlen(Section) && std::strncmp(name, Section, len) == 0;
			if (inside && table == nullptr) {
				table = nl != nullptr ? nl + 1 : end;
			}
		} else if (inside && detail::IsKey(line, stop, &old)) {
			const char* oldEnd = old;
			while (oldEnd < stop && *oldEnd != ' ' && *oldEnd != '\t' && *oldEnd != '\r') {
				++oldEnd;
			}
			const int n = std::snprintf(out, size, "%.*s%s%s", static_cast<int>(old - text), text, value, oldEnd);
			return n >= 0 && static_cast<size_t>(n) < size;
		}
		line = nl != nullptr ? nl + 1 : end;
	}
	int n = 0;
	if (table != nullptr) {
		n = std::snprintf(out, size, "%.*s%s = %s\n%s", static_cast<int>(table - text), text, Key, value, table);
	} else {
		const size_t len = std::strlen(text);
		const char* sep = len == 0 || text[len - 1] == '\n' ? "" : "\n";
		n = std::snprintf(out, size, "%s%s\n[%s]\n%s = %s\n", text, sep, Section, Key, value);
	}
	return n >= 0 && static_cast<size_t>(n) < size;
}

// Which of the redirected fonts can be freed now: loaded (handle != 0) and not the current font (D2R's own idle unload skips
// the current one too). The current one (font16 between frames) is first handed over: SetFont(StandIn), free, SetFont(it),
// which also loads its new pair at once.
inline auto MayFree(int id, int current, uint64_t handle) noexcept -> bool {
	return handle != 0 && id != current;
}

// rel32 call at `from` to `to` (both RVAs).
struct CallBytes {
	uint8_t bytes[5];
};
constexpr auto CallTo(uint64_t from, uint64_t to) noexcept -> CallBytes {
	const auto rel = static_cast<uint32_t>(static_cast<int64_t>(to) - static_cast<int64_t>(from + 5));
	return {{0xe8, static_cast<uint8_t>(rel), static_cast<uint8_t>(rel >> 8), static_cast<uint8_t>(rel >> 16), static_cast<uint8_t>(rel >> 24)}};
}

// jmp qword ptr [rip+0] / dq to (no register used).
struct AbsJump {
	uint8_t bytes[14];
};
constexpr auto AbsJumpBytes(uint64_t to) noexcept -> AbsJump {
	AbsJump j{{0xff, 0x25, 0, 0, 0, 0}};
	for (int i = 0; i < 8; ++i) {
		j.bytes[6 + i] = static_cast<uint8_t>(to >> (8 * i));
	}
	return j;
}

}  // namespace clear_fonts

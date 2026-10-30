// Pure part of `vochat` (vo_chat.cpp; unit test plugin/tests/vo_chat_test.cpp). No Windows headers, no game calls.
#pragma once

#include <cstdint>

namespace vo_chat {

// Client functions of build 93847.
// (sound id, flag) -> nothing: the subtitle of a voice file. Reads the sound's path (record +0x32), turns its file name into a
// string key (0x1a0210: lower case, no folder, no extension, no trailing "_hd"), and when vo.json has the key (and the flag is
// 0) writes "<speaker> says: <line>" (ui.json DialogSpeakerFormatString) into the chat. One caller: the client play 0x1a0780 at
// 0x1a0bc3, with flag 0, after the sound started and only with subtitles on; the return value is not used.
inline constexpr uint64_t RvaVoSubtitle = 0x1a0da0;
inline constexpr uint64_t RvaSoundRecord = 0xd96a0;  // (id, 0, 0) -> sounds record or null; the subtitle calls it the same way
inline constexpr int RecordPath = 0x32;              // char path[] in the record (0x1a0da0: lea rcx, [rax + 0x32])
inline constexpr int PathMax = 0x9b;                 // 0x1a0210 copies at most this many bytes
// mov r11,rsp / push rbp / push rbx / lea rbp,[r11-0xf8] / sub rsp,0x1e8
inline constexpr uint8_t VoSubtitleEntry[] = {0x4c, 0x8b, 0xdc, 0x55, 0x53, 0x49, 0x8d, 0xab, 0x08, 0xff, 0xff, 0xff,
                                              0x48, 0x81, 0xec, 0xe8, 0x01, 0x00, 0x00};

// Baal's laugh: the vo.json key Median's skills and missiles reach (bugs.md #508). Its line is limited to one per Cooldown.
inline constexpr char LimitedKey[] = "baallaugh1";
inline constexpr uint64_t CooldownMs = 30000;
// The Act 5 soldiers' lines Median gives to summon missiles ("Over here!") and deathcoil ("Help us!"): one per 5 s each
// (owner ruling 2026-10-30).
inline constexpr char SoldierOverHere[] = "sol_overhere";
inline constexpr char SoldierHelpUs[] = "sol_helpus";
inline constexpr uint64_t SoldierCooldownMs = 5000;

struct Limited {
	const char* key;
	uint64_t cooldownMs;
};
inline constexpr Limited LimitedLines[] = {{LimitedKey, CooldownMs}, {SoldierOverHere, SoldierCooldownMs}, {SoldierHelpUs, SoldierCooldownMs}};
inline constexpr int LimitedCount = static_cast<int>(sizeof(LimitedLines) / sizeof(LimitedLines[0]));

// True when `path` (a sounds.txt file path, e.g. "Monster\\baal\\baallaugh1.flac") gives the vo.json key `key` the way 0x1a0210
// builds it: the file name after the last '\\' or '/', up to its last '.', without a trailing "_hd", compared without case.
// Null or empty paths give no key.
constexpr auto PathKeyIs(const char* path, const char* key) noexcept -> bool {
	if (path == nullptr || key == nullptr) {
		return false;
	}
	int len = 0;
	while (len < PathMax && path[len] != '\0') {
		++len;
	}
	int start = 0;
	int end = len;
	for (int i = 0; i < len; ++i) {
		if (path[i] == '\\' || path[i] == '/') {
			start = i + 1;
			end = len;
		} else if (path[i] == '.') {
			end = i;
		}
	}
	const auto lower = [](char c) { return c >= 'A' && c <= 'Z' ? static_cast<char>(c - 'A' + 'a') : c; };
	if (end - start >= 3 && path[end - 3] == '_' && lower(path[end - 2]) == 'h' && lower(path[end - 1]) == 'd') {
		end -= 3;
	}
	int k = 0;
	for (int i = start; i < end; ++i, ++k) {
		if (key[k] == '\0' || lower(path[i]) != key[k]) {
			return false;
		}
	}
	return k > 0 && key[k] == '\0';
}

// The cooldown: a line at `now` (ms) goes to the chat when none went out yet (`last` 0) or the last one is at least
// `cooldownMs` (Baal's CooldownMs unless given) ago. A clock that went back counts as "long ago" (no line is lost for good).
constexpr auto LineAllowed(uint64_t now, uint64_t last, uint64_t cooldownMs = CooldownMs) noexcept -> bool {
	return last == 0 || now < last || now - last >= cooldownMs;
}

// The index in LimitedLines of the key `path` gives, or -1 for a line that is not limited.
constexpr auto LimitedIndex(const char* path) noexcept -> int {
	for (int i = 0; i < LimitedCount; ++i) {
		if (PathKeyIs(path, LimitedLines[i].key)) {
			return i;
		}
	}
	return -1;
}

}  // namespace vo_chat

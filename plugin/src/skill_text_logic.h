// Pure rule of the skill tooltip label fix (skill_text.cpp; unit test plugin/tests/skill_text_test.cpp, bug #396).
// No Windows headers, no game calls.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace skill_text {

// D2R's skill tooltip line renderer (D2Client UI/SkillDesc.cpp, 0x287a50; jump table 0x289f88 on the line type) still builds
// 1.13c's line types 9, 10, 11, 14, 22, 25, 27 and 28 by appending a label it names by id, then the numbers ("%d-%d" written by
// the renderer), then a unit, as 1.13c did. D2R rewrote those labels as printf formats: 1.13c's StrSkill5 "Fire Damage: " reads
// "Fire Damage: %d-%d" in D2R, so the line shows "Fire Damage: %d-%d12-15". No data cell names these labels (the ids are in
// the code), and D2R's own lines that format them must keep D2R's text. The fix cuts the raw label in the text the renderer
// has just appended back to 1.13c's words: the text before its first conversion ("Fire Damage: "), or for StrSkill34 ("Mana
// Cost: %d per second", 1.13c " per second") the text after its last one. A formatted line never holds a raw "%d", so only
// these unformatted labels match.
struct Label {
	uint16_t id;      // D2R string id (= 1.13c's)
	bool keepSuffix;  // keep the text after the last conversion instead of the text before the first
};
inline constexpr Label Labels[] = {
    {4256, false},  // StrSkill4  "Damage: %d-%d"
    {4257, false},  // StrSkill5  "Fire Damage: %d-%d"
    {4258, false},  // StrSkill6  "Cold Damage: %d-%d"
    {4259, false},  // StrSkill7  "Lightning Damage: %d-%d"
    {4260, false},  // StrSkill8  "Poison Damage: %d-%d"
    {4291, false},  // StrSkill39 "Magic Damage: %d-%d"
    {4265, false},  // StrSkill13 "Cold Length: %d seconds"
    {4270, false},  // StrSkill18 "Radius: %d yards"
    {4272, false},  // StrSkill20 "Duration: %d seconds"
    {4286, true},   // StrSkill34 "Mana Cost: %d per second"
};
inline constexpr uint64_t RendererRva = 0x287a50;
inline constexpr uint64_t GetStringRva = 0x3e2b730;  // (uint16 id) -> const char*, the thunk the renderer calls
inline constexpr size_t LineBuffer = 0x800;           // the renderer's output buffer (strcat 0x12276a0 with 0x800)

// Length of the printf conversion that starts at `s` ('%'), 0 when it is none ("%%" is literal text).
inline auto ConversionLength(const char* s) noexcept -> size_t {
	if (s[0] != '%' || s[1] == '%' || s[1] == '\0') {
		return 0;
	}
	size_t n = 1;
	while (s[n] != '\0' && std::strchr("-+ #0123456789.", s[n]) != nullptr) {
		++n;
	}
	return s[n] != '\0' && std::strchr("dis", s[n]) != nullptr ? n + 1 : 0;
}

// The part of `label` to keep: [start, start + length). False when the label has no conversion (nothing to cut).
inline auto KeptPart(const char* label, bool keepSuffix, size_t* start, size_t* length) noexcept -> bool {
	const size_t len = std::strlen(label);
	size_t first = len, lastEnd = 0;
	for (size_t i = 0; i < len; ++i) {
		const size_t c = ConversionLength(label + i);
		if (c != 0) {
			first = first == len ? i : first;
			lastEnd = i + c;
			i += c - 1;
		} else if (label[i] == '%' && label[i + 1] == '%') {
			++i;
		}
	}
	if (first == len) {
		return false;
	}
	*start = keepSuffix ? lastEnd : 0;
	*length = keepSuffix ? len - lastEnd : first;
	return true;
}

// Replaces every occurrence of `label` in the NUL-terminated `text` by its kept part, in place (the text only gets shorter).
// Returns the number replaced.
inline auto CutLabel(char* text, const char* label, bool keepSuffix) noexcept -> int {
	size_t start = 0, keep = 0;
	const size_t len = label != nullptr ? std::strlen(label) : 0;
	if (text == nullptr || len == 0 || !KeptPart(label, keepSuffix, &start, &keep)) {
		return 0;
	}
	int n = 0;
	for (char* at = std::strstr(text, label); at != nullptr; at = std::strstr(at + keep, label)) {
		std::memmove(at, label + start, keep);
		std::memmove(at + keep, at + len, std::strlen(at + len) + 1);
		++n;
	}
	return n;
}

}  // namespace skill_text

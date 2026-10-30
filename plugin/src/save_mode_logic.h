// Save format and cancelled saves (docs/bugs.md #512; save_mode.cpp, unit test plugin/tests/save_mode_test.cpp).
// D2R-XL 2012 needs D2RLoader's extended save format ([d2rcore.save_format] mode = "extended" in the mod's own
// d2rloader.toml, written by the installer, kept by the downloader as a player file). Without it D2RLoader writes D2R's retail
// format, whose 9-bit stat ids end at 510 (511 is the end-of-list mark): an item that carries one of Median's stats 511-537
// (many uniques, set items, runewords and 52 magic prefixes) cannot be written, D2R asserts "Character has too many items"
// (PlrSave.cpp:1980) and D2RLoader cancels the whole save batch every time until the item is gone. No Windows headers here.
#pragma once

#include <cstddef>
#include <cstdio>
#include <cstring>
#include <string>

namespace save_mode {

enum class Mode { Missing, Extended, Other };

inline auto Trim(const std::string& s) -> std::string {
	size_t a = 0;
	size_t b = s.size();
	while (a < b && (s[a] == ' ' || s[a] == '\t' || s[a] == '\r' || s[a] == '\n' || s[a] == '\xef' || s[a] == '\xbb' || s[a] == '\xbf')) {
		++a;
	}
	while (b > a && (s[b - 1] == ' ' || s[b - 1] == '\t' || s[b - 1] == '\r' || s[b - 1] == '\n')) {
		--b;
	}
	return s.substr(a, b - a);
}

// `key = "value"` (or 'value', a comment after it is fine); false for comments and other keys. `value` is the unquoted text.
inline auto KeyValue(const std::string& line, const char* key, std::string& value) -> bool {
	const std::string t = Trim(line);
	const size_t n = std::strlen(key);
	if (t.compare(0, n, key) != 0) {
		return false;
	}
	std::string rest = Trim(t.substr(n));
	if (rest.empty() || rest[0] != '=') {
		return false;
	}
	rest = Trim(rest.substr(1));
	if (rest.size() >= 2 && (rest[0] == '"' || rest[0] == '\'')) {
		const size_t end = rest.find(rest[0], 1);
		value = end == std::string::npos ? rest.substr(1) : rest.substr(1, end - 1);
	} else {
		const size_t hash = rest.find('#');
		value = Trim(hash == std::string::npos ? rest : rest.substr(0, hash));
	}
	return true;
}

// A table header line `[name]` (spaces inside the brackets allowed); empty when the line is not one.
inline auto Header(const std::string& line) -> std::string {
	const std::string t = Trim(line);
	if (t.size() < 2 || t[0] != '[' || t[1] == '[') {
		return {};
	}
	const size_t end = t.find(']');
	return end == std::string::npos ? std::string{} : Trim(t.substr(1, end - 1));
}

template <typename Fn>
void ForEachLine(const std::string& text, Fn fn) {
	size_t pos = 0;
	size_t index = 0;
	while (pos < text.size()) {
		size_t end = text.find('\n', pos);
		if (end == std::string::npos) {
			end = text.size();
		}
		if (!fn(index++, pos, end, text.substr(pos, end - pos))) {
			return;
		}
		pos = end + 1;
	}
}

// The save format the mod's d2rloader.toml asks for: `mode` in [d2rcore.save_format], or the dotted key at the top.
inline auto ParseMode(const std::string& toml, std::string* valueOut = nullptr) -> Mode {
	std::string section;
	Mode mode = Mode::Missing;
	ForEachLine(toml, [&](size_t, size_t, size_t, const std::string& line) {
		const std::string h = Header(line);
		if (!h.empty()) {
			section = h;
			return true;
		}
		std::string value;
		const bool hit = (section == "d2rcore.save_format" && KeyValue(line, "mode", value)) ||
		                 (section.empty() && KeyValue(line, "d2rcore.save_format.mode", value));
		if (hit) {
			mode = value == "extended" ? Mode::Extended : Mode::Other;
			if (valueOut != nullptr) {
				*valueOut = value;
			}
		}
		return true;
	});
	return mode;
}

// The same file with `mode = "extended"`: an existing `mode` line of the section (or the dotted key) is replaced, else the line
// goes right under an existing [d2rcore.save_format], else the section goes at the top. Everything else stays as it was.
inline auto Repair(const std::string& toml) -> std::string {
	const char* line = "mode = \"extended\"";
	std::string section;
	size_t replaceFrom = std::string::npos;
	size_t replaceTo = 0;
	size_t headerEnd = std::string::npos;
	bool dotted = false;
	ForEachLine(toml, [&](size_t, size_t from, size_t to, const std::string& l) {
		const std::string h = Header(l);
		if (!h.empty()) {
			section = h;
			if (h == "d2rcore.save_format" && headerEnd == std::string::npos) {
				headerEnd = to;
			}
			return true;
		}
		std::string value;
		if ((section == "d2rcore.save_format" && KeyValue(l, "mode", value)) || (section.empty() && KeyValue(l, "d2rcore.save_format.mode", value))) {
			replaceFrom = from;
			replaceTo = to;
			dotted = section.empty();
		}
		return true;
	});
	if (replaceFrom != std::string::npos) {
		std::string keep = toml.substr(replaceFrom, replaceTo - replaceFrom);
		const bool cr = !keep.empty() && keep.back() == '\r';
		return toml.substr(0, replaceFrom) + (dotted ? "d2rcore.save_format." : "") + line + (cr ? "\r" : "") + toml.substr(replaceTo);
	}
	const bool crlf = toml.find("\r\n") != std::string::npos;
	const char* nl = crlf ? "\r\n" : "\n";
	if (headerEnd != std::string::npos) {
		if (headerEnd >= toml.size()) {
			return toml + nl + line + nl;
		}
		return toml.substr(0, headerEnd + 1) + line + nl + toml.substr(headerEnd + 1);
	}
	return std::string("[d2rcore.save_format]") + nl + line + nl + nl + toml;
}

// Lines of D2RLoader's log that mean a save did not reach the disk (the character or the shared stash part of a batch).
inline auto IsSaveFailure(const std::string& line) -> bool {
	return line.find("Character save failed") != std::string::npos || line.find("Shared stash save failed") != std::string::npos;
}

// Counts the save failures in a chunk of the log; `rest` keeps an unfinished last line for the next chunk.
inline auto CountFailures(const std::string& chunk, std::string& rest) -> int {
	const std::string text = rest + chunk;
	const size_t last = text.rfind('\n');
	rest = last == std::string::npos ? text : text.substr(last + 1);
	if (last == std::string::npos) {
		return 0;
	}
	int n = 0;
	ForEachLine(text.substr(0, last + 1), [&](size_t, size_t, size_t, const std::string& l) {
		n += IsSaveFailure(l) ? 1 : 0;
		return true;
	});
	return n;
}

// The screen lines (the notice holds 255 characters).
inline void RepairedNotice(char* out, size_t size) {
	std::snprintf(out, size, "D2R-XL 2012: saves were set to D2R's retail format, which cannot hold Median items. Fixed in the mod's d2rloader.toml: "
	                         "close the game and start it again before you play.");
}

inline void NotRepairedNotice(char* out, size_t size) {
	std::snprintf(out, size, "D2R-XL 2012: saves are in D2R's retail format and cannot hold Median items. Add mode = \"extended\" under "
	                         "[d2rcore.save_format] in mods\\mxl2012\\d2rloader\\config\\d2rloader.toml, then restart.");
}

inline void FailureNotice(char* out, size_t size, int count, int hour, int minute, bool retail) {
	std::snprintf(out, size, "D2R-XL 2012: SAVE FAILED %d time%s (last %02d:%02d): progress since the last good save is not on disk.%s", count,
	              count == 1 ? "" : "s", hour, minute,
	              retail ? " Saves are in retail format: restart the game (the setting was fixed) or drop the newest unique / set / runeword item."
	                     : " See d2rloader.log; report it.");
}

}  // namespace save_mode

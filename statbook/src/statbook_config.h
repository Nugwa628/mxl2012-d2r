// The Stat Book plugin's config (statbook.toml, section [statbook]) and its gamepad tab rule. Pure: no Windows headers.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace statbook {

enum class PadButtons : uint8_t { Auto, Bumpers, Triggers, Off };

struct Config {
	bool sheetRows = true;      // the Magic / Physical Resistance rows on page 1 (part sheetres)
	bool advancedStats = true;  // D2R's Advanced Stats panel in groups (part advstats)
	bool book = true;           // the themed pages and All Stats
	PadButtons pad = PadButtons::Auto;
	// the ControllerActionBegin action ids of the four buttons (the message's action +0x10); -1: not known
	// D2R's controller action ids as the gamepad menu gets them: LB 19, RB 20, LT 7, RT 8 (lane sbresearch); -1 turns one off
	int32_t bumperLeft = 19, bumperRight = 20, triggerLeft = 7, triggerRight = 8;
	bool padLog = false;  // log every controller action the gamepad menu gets (page and id) to statbook.log
	bool sideTabs = false;  // tabs = "side": the book as a panel beside the sheet, its tabs down its side (else "top": folder tabs)
};

namespace config_detail {

inline auto Bool(const char* v, size_t n, bool fallback) noexcept -> bool {
	if (n >= 4 && std::strncmp(v, "true", 4) == 0) {
		return true;
	}
	if (n >= 5 && std::strncmp(v, "false", 5) == 0) {
		return false;
	}
	return fallback;
}

inline auto Int(const char* v, size_t n, int32_t fallback) noexcept -> int32_t {
	char buf[16] = {};
	size_t k = 0;
	for (; k < n && k + 1 < sizeof(buf) && (v[k] == '-' || (v[k] >= '0' && v[k] <= '9')); ++k) {
		buf[k] = v[k];
	}
	if (k == 0 || (k == 1 && buf[0] == '-')) {
		return fallback;
	}
	const long r = std::strtol(buf, nullptr, 10);
	return r < -1 || r > 0xffff ? fallback : static_cast<int32_t>(r);
}

}  // namespace config_detail

// key = value lines of [statbook]; unknown keys and bad values keep the defaults.
inline auto ParseConfig(const char* text) noexcept -> Config {
	Config c;
	if (text == nullptr) {
		return c;
	}
	bool inSection = false;
	for (const char* line = text; *line != '\0';) {
		const char* end = line;
		while (*end != '\0' && *end != '\n') {
			++end;
		}
		const char* p = line;
		while (p < end && (*p == ' ' || *p == '\t')) {
			++p;
		}
		if (p < end && *p == '[') {
			inSection = static_cast<size_t>(end - p) >= 10 && std::strncmp(p, "[statbook]", 10) == 0;
		} else if (inSection && p < end && *p != '#') {
			const char* eq = p;
			while (eq < end && *eq != '=') {
				++eq;
			}
			const char* k = eq;
			while (k > p && (k[-1] == ' ' || k[-1] == '\t')) {
				--k;
			}
			const size_t kn = static_cast<size_t>(k - p);
			const char* v = eq < end ? eq + 1 : end;
			while (v < end && (*v == ' ' || *v == '"')) {
				++v;
			}
			const size_t vn = static_cast<size_t>(end - v);
			auto key = [&](const char* name) { return std::strlen(name) == kn && std::strncmp(p, name, kn) == 0; };
			if (key("sheet_rows")) {
				c.sheetRows = config_detail::Bool(v, vn, c.sheetRows);
			} else if (key("advanced_stats")) {
				c.advancedStats = config_detail::Bool(v, vn, c.advancedStats);
			} else if (key("book")) {
				c.book = config_detail::Bool(v, vn, c.book);
			} else if (key("pad_tabs")) {
				c.pad = std::strncmp(v, "bumpers", vn < 7 ? vn : 7) == 0 && vn >= 7    ? PadButtons::Bumpers
				        : std::strncmp(v, "triggers", vn < 8 ? vn : 8) == 0 && vn >= 8 ? PadButtons::Triggers
				        : std::strncmp(v, "off", vn < 3 ? vn : 3) == 0 && vn >= 3      ? PadButtons::Off
				                                                                       : PadButtons::Auto;
			} else if (key("pad_bumper_left")) {
				c.bumperLeft = config_detail::Int(v, vn, c.bumperLeft);
			} else if (key("pad_bumper_right")) {
				c.bumperRight = config_detail::Int(v, vn, c.bumperRight);
			} else if (key("pad_trigger_left")) {
				c.triggerLeft = config_detail::Int(v, vn, c.triggerLeft);
			} else if (key("pad_trigger_right")) {
				c.triggerRight = config_detail::Int(v, vn, c.triggerRight);
			} else if (key("pad_log")) {
				c.padLog = config_detail::Bool(v, vn, c.padLog);
			} else if (key("tabs")) {
				if (vn >= 4 && std::strncmp(v, "side", 4) == 0) {
					c.sideTabs = true;
				} else if (vn >= 3 && std::strncmp(v, "top", 3) == 0) {
					c.sideTabs = false;
				}
			}
		}
		line = *end == '\0' ? end : end + 1;
	}
	return c;
}

// statbook.toml with [statbook] tabs set to "side" or "top": the value of the key replaced in place (its comment and the
// rest of the file kept), else the key added as the section's first line, else the section added at the end. false when
// `out` is too small.
inline auto WithTabs(const char* toml, bool side, char* out, size_t size) noexcept -> bool {
	const char* value = side ? "\"side\"" : "\"top\"";
	const char* text = toml != nullptr ? toml : "";
	const char* table = nullptr;  // the line after [statbook]
	bool inside = false;
	for (const char* line = text; *line != '\0';) {
		const char* nl = std::strchr(line, '\n');
		const char* end = nl != nullptr ? nl : line + std::strlen(line);
		const char* p = line;
		while (p < end && (*p == ' ' || *p == '\t')) {
			++p;
		}
		if (p < end && *p == '[') {
			inside = static_cast<size_t>(end - p) >= 10 && std::strncmp(p, "[statbook]", 10) == 0;
			if (inside && table == nullptr) {
				table = nl != nullptr ? nl + 1 : end;
			}
		} else if (inside && static_cast<size_t>(end - p) >= 4 && std::strncmp(p, "tabs", 4) == 0) {
			const char* q = p + 4;
			while (q < end && (*q == ' ' || *q == '\t')) {
				++q;
			}
			if (q < end && *q == '=') {
				++q;
				while (q < end && (*q == ' ' || *q == '\t')) {
					++q;
				}
				const char* old = q;  // the old value: a quoted string or a bare word
				const char* oldEnd = old;
				if (oldEnd < end && *oldEnd == '"') {
					++oldEnd;
					while (oldEnd < end && *oldEnd != '"') {
						++oldEnd;
					}
					if (oldEnd < end) {
						++oldEnd;
					}
				} else {
					while (oldEnd < end && *oldEnd != ' ' && *oldEnd != '\t' && *oldEnd != '\r' && *oldEnd != '#') {
						++oldEnd;
					}
				}
				const int n = std::snprintf(out, size, "%.*s%s%s", static_cast<int>(old - text), text, value, oldEnd);
				return n >= 0 && static_cast<size_t>(n) < size;
			}
		}
		line = nl != nullptr ? nl + 1 : end;
	}
	int n = 0;
	if (table != nullptr) {
		n = std::snprintf(out, size, "%.*stabs = %s\n%s", static_cast<int>(table - text), text, value, table);
	} else {
		const size_t len = std::strlen(text);
		const char* sep = len == 0 || text[len - 1] == '\n' ? "" : "\n";
		n = std::snprintf(out, size, "%s%s\n[statbook]\ntabs = %s\n", text, sep, value);
	}
	return n >= 0 && static_cast<size_t>(n) < size;
}

// Auto: the bumpers when Controller QOL is in the game (it pages its menus with the triggers and leaves LB / RB free on the
// sheet), else the triggers (plain D2R moves between panels with LB / RB). Lane sbresearch findings.
inline auto PadChoice(PadButtons wanted, bool controllerQol) noexcept -> PadButtons {
	return wanted == PadButtons::Auto ? (controllerQol ? PadButtons::Bumpers : PadButtons::Triggers) : wanted;
}

// The tab step for a controller action on the sheet: -1, +1, or 0 (not ours: D2R handles it).
inline auto PadStep(const Config& c, PadButtons choice, int32_t action) noexcept -> int {
	if (action < 0) {
		return 0;
	}
	if (choice == PadButtons::Bumpers) {
		return action == c.bumperLeft ? -1 : action == c.bumperRight ? 1 : 0;
	}
	if (choice == PadButtons::Triggers) {
		return action == c.triggerLeft ? -1 : action == c.triggerRight ? 1 : 0;
	}
	return 0;
}

}  // namespace statbook

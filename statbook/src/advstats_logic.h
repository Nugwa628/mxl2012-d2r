// Pure part of the grouped Advanced Stats panel (advstats.cpp, bugs #581 / #582; unit test plugin/tests/advstats_test.cpp). No
// Windows headers, no game calls.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace advstats {

// D2R's AdvancedStatsPanel (D2Client UI\Panels\AdvancedStatsPanel.cpp, build 93847, HD only: the legacy layout
// advancedstatspanel.json is an empty stub). Vtable 0x1fdd690; Update (slot 2, 0x14ed3a0) runs every frame while the panel is
// open: it closes the panel when its unit (+0x168) is gone, re-texts row i of the list container (+0x170) from record i of the
// "always" vector (+0x178 data, +0x180 count, 0x144-byte itemstatcost record copies) through 0x14eb250, then rebuilds the list
// (0x886250 clear + builder 0x14eaf40) when the set of non-zero rows of the "nonzero" vector (+0x190 / +0x198) differs from the
// ids shown (+0x1c0 / +0x1c8). The builder (also run when the panel opens, 0x14ecff2) pushes the advdisplay 1 records into
// +0x178 (0x14edd50) and adds their rows (0x14ead50: clones the "OptionTemplate", texts its "StatText" through 0x14eb250), then
// the advdisplay 2 records that are not 0. 0x14eb250(panel, outString, record) texts one row: GetStat(unit, stat, 0) (0x2f5020)
// through the item tooltip formatter 0x2d97e0, so a row needs a descfunc and has no heading.
//
// The part replaces the builder: it lists data/advanced_stats.tsv (advstats_table.h) in groups, a heading row before each
// group that has a row to show, all of it in the "always" vector so D2R's own Update re-texts every row each frame, and leaves
// the "nonzero" vector empty so D2R never rebuilds on its own. A wrapper on the Update slot rebuilds when the set of rows to
// show changes (a buff, a state or an item that turns a stat on or off; #582). Rows of the panel's own kinds (headings, Avoid,
// elemental adds, skill speeds) are texted here; plain stat rows keep D2R's text, which is the item tooltip's wording.
inline constexpr uint64_t VtableRva = 0x1fdd690;
inline constexpr uint64_t UpdateSlotRva = VtableRva + 2 * 8;  // 0x1fdd6a0
inline constexpr uint64_t UpdateRva = 0x14ed3a0;
inline constexpr uint8_t UpdateEntry[] = {0x40, 0x55, 0x53, 0x56, 0x57, 0x48, 0x8d, 0xac, 0x24, 0xa8, 0xfd, 0xff, 0xff, 0x48, 0x81, 0xec, 0x58, 0x03, 0x00, 0x00};
// builder: push rbx..r14 / sub rsp,0x38 / xor esi,esi / mov rbp,rcx (18 bytes, whole instructions)
inline constexpr uint64_t BuildRva = 0x14eaf40;
inline constexpr uint8_t BuildEntry[] = {0x40, 0x53, 0x55, 0x56, 0x57, 0x41, 0x54, 0x41, 0x56, 0x48, 0x83, 0xec, 0x38, 0x33, 0xf6, 0x48, 0x8b, 0xe9};
// row text: push rbp/rbx/rdi/r15 / lea rbp,[rsp-0x478] / sub rsp,0x578 (21 bytes, whole instructions)
inline constexpr uint64_t TextRva = 0x14eb250;
inline constexpr uint8_t TextEntry[] = {0x40, 0x55, 0x53, 0x57, 0x41, 0x57, 0x48, 0x8d, 0xac, 0x24, 0x88, 0xfb, 0xff, 0xff, 0x48, 0x81, 0xec, 0x78, 0x05, 0x00, 0x00};
inline constexpr uint64_t PushRva = 0x14edd50;  // (vector, record): push_back of a 0x144-byte record copy
inline constexpr uint8_t PushEntry[] = {0x4c, 0x8b, 0xdc, 0x53, 0x56, 0x57, 0x41, 0x56, 0x48, 0x83, 0xec, 0x38, 0x49, 0x89, 0x6b, 0x10};
inline constexpr uint64_t RowAddRva = 0x14ead50;  // (panel, record): one row widget
inline constexpr uint8_t RowAddEntry[] = {0x4c, 0x8b, 0xdc, 0x55, 0x57, 0x41, 0x56, 0x48, 0x81, 0xec, 0x90, 0x00, 0x00, 0x00, 0x48, 0x8b};
inline constexpr uint64_t ClearRva = 0x886250;  // (list container): removes its rows
inline constexpr uint8_t ClearEntry[] = {0x40, 0x53, 0x48, 0x83, 0xec, 0x30, 0x48, 0x8b, 0xd9, 0x48, 0x8b, 0x89, 0xd8, 0x00, 0x00, 0x00};
inline constexpr uint64_t ResizeRva = 0x76210;  // (string, length): room for `length` chars in D2R's string
inline constexpr uint8_t ResizeEntry[] = {0x4c, 0x8b, 0xdc, 0x49, 0x89, 0x5b, 0x08, 0x49, 0x89, 0x6b, 0x18, 0x49, 0x89, 0x73, 0x20, 0x49};
inline constexpr uint64_t GetStatRva = 0x2f5020;  // thunk (unit, stat, layer) -> value
inline constexpr uint8_t GetStatEntry[] = {0xff, 0x25, 0xf2, 0x51, 0xb3, 0x03};
inline constexpr uint64_t TablesRva = 0x300a90;  // (data flag) -> data tables
inline constexpr uint8_t TablesEntry[] = {0x48, 0x83, 0xec, 0x28, 0x0f, 0xb6, 0xc1, 0x48, 0x89, 0x44, 0x24, 0x38, 0x48, 0x83, 0xf8, 0x04};
inline constexpr uint64_t FlagHolderRva = 0x76010;  // returns the object whose byte +0x9cf is the data flag (as the builder reads it)
inline constexpr uint8_t FlagHolderEntry[] = {0x48, 0x8d, 0x05, 0x89, 0xb0, 0x9a, 0x02, 0xc3};
inline constexpr size_t DataFlagOffset = 0x9cf;
inline constexpr size_t StatsData = 0x1258;  // itemstatcost records
inline constexpr size_t StatsCount = 0x1260;
inline constexpr size_t RecordSize = 0x144;
inline constexpr size_t RecordValShift = 0x14;
inline constexpr size_t PanelUnit = 0x168;
inline constexpr size_t PanelContainer = 0x170;
inline constexpr size_t PanelAlways = 0x178;      // {data, count, capacity}
inline constexpr size_t PanelNonzero = 0x190;     // {data, count, capacity}
inline constexpr size_t PanelShownCount = 0x1c8;  // count of the ids D2R last showed from the "nonzero" vector

enum class Kind : uint8_t {
	Stat,   // one stat, D2R's tooltip text
	Range,  // min and max stat: "Adds %d-%d Fire Damage"
	Value,  // a percent stat based on 100 (attackrate, velocitypercent): own text with value - 100, hidden at 0 or 100
	Avoid,  // passive_dodge / avoid / evade: one line when equal, else one line each
};

struct Group {
	const char* key;
	const char* english;
};

struct Row {
	uint8_t group;
	Kind kind;
	bool always;
	uint16_t stat[3];
	const char* key;      // own text (Range / Value), else nullptr
	const char* english;  // its English text
	const char* name;     // itemstatcost row name(s), for the report and the tests
};

// The Avoid row's texts: index 0 when all three stats are equal, else 1..3 for dodge / avoid / evade.
inline constexpr Group AvoidTexts[4] = {{"AdvStatsAvoidAll", "%d%% Chance to Avoid Damage"},
                                        {"AdvStatsDodge", "%d%% Chance to Dodge Melee Attacks"},
                                        {"AdvStatsAvoidMissile", "%d%% Chance to Avoid Missiles"},
                                        {"AdvStatsEvade", "%d%% Chance to Evade Attacks while Moving"}};

// One row of the built list: a group heading, or part `part` of table row `index` (Avoid: 0 = all equal, 1..3 one stat each).
struct Item {
	uint16_t index = 0;
	uint8_t heading = 0;
	uint8_t part = 0;
	friend constexpr auto operator==(const Item&, const Item&) noexcept -> bool = default;
};

inline constexpr size_t MaxItems = 256;

// Value rows: the stat is 100 + the bonus once the unit is set up (0 before), so the row shows and texts the bonus.
inline constexpr int32_t ValueBase = 100;
inline constexpr auto ValueShown(int32_t v) noexcept -> bool {
	return v != 0 && v != ValueBase;
}

// The list for `values` (stat id -> value >> ValShift, as D2R's 0x14eb1b0 reads it): per group in order, a heading and then
// the group's rows in table order that are `always` or not 0; a group without such a row is left out. Returns the count.
template <class Values>
auto BuildPlan(size_t groupCount, const Row* rows, size_t rowCount, Values&& values, Item* out, size_t cap) noexcept -> size_t {
	size_t n = 0;
	auto add = [&](Item item) {
		if (n < cap) {
			out[n++] = item;
		}
	};
	for (size_t g = 0; g < groupCount; ++g) {
		const size_t headingAt = n;
		add(Item{static_cast<uint16_t>(g), 1, 0});
		const size_t first = n;
		for (size_t i = 0; i < rowCount; ++i) {
			const Row& r = rows[i];
			if (r.group != g) {
				continue;
			}
			const auto index = static_cast<uint16_t>(i);
			switch (r.kind) {
				case Kind::Value:
					if (r.always || ValueShown(values(r.stat[0]))) {
						add(Item{index, 0, 0});
					}
					break;
				case Kind::Stat:
					if (r.always || values(r.stat[0]) != 0) {
						add(Item{index, 0, 0});
					}
					break;
				case Kind::Range:
					if (r.always || values(r.stat[0]) != 0 || values(r.stat[1]) != 0) {
						add(Item{index, 0, 0});
					}
					break;
				case Kind::Avoid: {
					const int32_t v[3] = {values(r.stat[0]), values(r.stat[1]), values(r.stat[2])};
					if (v[0] == v[1] && v[1] == v[2]) {
						if (r.always || v[0] != 0) {
							add(Item{index, 0, 0});
						}
					} else {
						for (uint8_t k = 0; k < 3; ++k) {
							if (r.always || v[k] != 0) {
								add(Item{index, 0, static_cast<uint8_t>(k + 1)});
							}
						}
					}
					break;
				}
			}
		}
		if (n == first) {
			n = headingAt;  // nothing to show in this group: no heading either
		}
	}
	return n;
}

// The panel rebuilds when the list it would build now differs from the one it shows.
inline auto SamePlan(const Item* a, size_t an, const Item* b, size_t bn) noexcept -> bool {
	if (an != bn) {
		return false;
	}
	for (size_t i = 0; i < an; ++i) {
		if (!(a[i] == b[i])) {
			return false;
		}
	}
	return true;
}

// printf-like fill of `pattern` with `count` ints: %d, %+d and %% only (the pattern comes from a strings file, so it is never
// handed to printf). A %d past the values prints 0. Always 0-terminates; returns the length written.
inline auto Fill(const char* pattern, const int32_t* values, size_t count, char* out, size_t size) noexcept -> size_t {
	if (size == 0) {
		return 0;
	}
	size_t n = 0, next = 0;
	auto put = [&](char c) {
		if (n + 1 < size) {
			out[n++] = c;
		}
	};
	for (const char* p = pattern; p != nullptr && *p != '\0'; ++p) {
		if (p[0] == '%' && p[1] == '%') {
			put('%');
			++p;
			continue;
		}
		const bool plus = p[0] == '%' && p[1] == '+' && p[2] == 'd';
		if (plus || (p[0] == '%' && p[1] == 'd')) {
			const int64_t v = next < count ? values[next] : 0;
			++next;
			char digits[24];
			size_t d = 0;
			uint64_t mag = v < 0 ? static_cast<uint64_t>(-v) : static_cast<uint64_t>(v);
			do {
				digits[d++] = static_cast<char>('0' + mag % 10);
				mag /= 10;
			} while (mag != 0);
			if (v < 0) {
				put('-');
			} else if (plus) {
				put('+');
			}
			while (d > 0) {
				put(digits[--d]);
			}
			p += plus ? 2 : 1;
			continue;
		}
		put(*p);
	}
	out[n] = '\0';
	return n;
}

// A heading's text: the group name between dashes (the panel's text box prints colour codes as they are).
inline auto HeadingText(const char* name, char* out, size_t size) noexcept -> size_t {
	const int32_t none[1] = {0};
	char text[160];
	Fill(name, none, 0, text, sizeof(text));
	size_t n = 0;
	const char* const parts[3] = {"- ", text, " -"};
	for (const char* part : parts) {
		for (const char* p = part; *p != '\0' && n + 1 < size; ++p) {
			out[n++] = *p;
		}
	}
	if (size > 0) {
		out[n < size ? n : size - 1] = '\0';
	}
	return n;
}

// The text of an own row (Range / Value / Avoid part); `text(key, english)` gives the localized pattern. Stat rows return false
// (D2R texts them).
template <class Values, class Text>
auto RowText(const Row& r, uint8_t part, Values&& values, Text&& text, char* out, size_t size) noexcept -> bool {
	int32_t v[2] = {0, 0};
	switch (r.kind) {
		case Kind::Stat:
			return false;
		case Kind::Value:
			v[0] = values(r.stat[0]) - ValueBase;
			Fill(text(r.key, r.english), v, 1, out, size);
			return true;
		case Kind::Range:
			v[0] = values(r.stat[0]);
			v[1] = values(r.stat[1]);
			Fill(text(r.key, r.english), v, 2, out, size);
			return true;
		case Kind::Avoid:
			if (part > 3) {
				return false;
			}
			v[0] = values(r.stat[part == 0 ? 0 : part - 1]);
			Fill(text(AvoidTexts[part].key, AvoidTexts[part].english), v, 1, out, size);
			return true;
	}
	return false;
}

}  // namespace advstats

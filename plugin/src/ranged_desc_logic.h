// Pure part of the Ctrl stat range line for descfuncs D2R has no range case for (ranged_desc.cpp; unit test
// plugin/tests/ranged_desc_test.cpp). No Windows headers, no game calls.
#pragma once

#include <cstddef>
#include <cstdint>

namespace ranged_desc {

// D2R's ranged mod string (0x2d7850, D2Client mods.cpp: item, ItemStatCost record, min, max, param, group flag, out buffer,
// mode) switches on the record's descfunc (jump table 0x2d8b44, descfunc 1-29). Descfuncs 5, 10, 11, 17, 18, 22 and 23 have no
// case: they log "Tried to get a ranged mod string on an invalid DescFunc type" (mods.cpp:998, bug #617) and leave the line
// empty, so with Ctrl held the tooltip shows a blank line where the stat was. Median keeps item_reanimate (23, "Reanimate as:"
// on many uniques, runewords and set items), item_howl (5) and item_replenish_durability (11) there. The hook builds those
// lines with D2R's own plain mod string (0x2d6520) for min and for max and merges the two: every number that differs becomes
// D2R's range "(min-max)", the rest of the text stays D2R's ("5% Reanimate as: Crimson Templar" and "3% ..." ->
// "(3-5)% Reanimate as: Crimson Templar").
constexpr auto NoRangeCase(int descfunc) noexcept -> bool {
	return descfunc == 5 || descfunc == 10 || descfunc == 11 || descfunc == 17 || descfunc == 18 || descfunc == 22 || descfunc == 23;
}

// The descfunc 0x2d7850 switches on: the group descfunc (record +0x3c) when the group flag is set, else modes 2 / 3 force
// 30 / 31, else the stat's own descfunc (record +0x32). Read at 0x2d787d-0x2d78e5 of the 93847 dump.
constexpr auto SwitchDescfunc(uint8_t ownDescfunc, uint8_t groupDescfunc, bool group, int32_t mode) noexcept -> int {
	if (group) {
		return groupDescfunc;
	}
	if (mode == 2) {
		return 30;
	}
	if (mode == 3) {
		return 31;
	}
	return ownDescfunc;
}

constexpr auto IsDigit(char c) noexcept -> bool {
	return c >= '0' && c <= '9';
}

// Length of a colour code at s[i]: D2R's "ÿc<x>" as UTF-8 (C3 BF 'c' x) or Latin-1 (FF 'c' x); 0 when there is none. Its
// letter can be a digit ("ÿc3"), which must not be read as part of a number.
constexpr auto ColourAt(const char* s, size_t i) noexcept -> size_t {
	const auto b = static_cast<unsigned char>(s[i]);
	if (b == 0xc3 && static_cast<unsigned char>(s[i + 1]) == 0xbf && s[i + 2] == 'c' && s[i + 3] != '\0') {
		return 4;
	}
	if (b == 0xff && s[i + 1] == 'c' && s[i + 2] != '\0') {
		return 3;
	}
	return 0;
}

// Writes the merge of `lo` (the line at min) and `hi` (the line at max) to `out` (size `outSize`, always 0-terminated).
// Both lines are cut into numbers (digit runs outside colour codes) and the text between them; when that text is the same in
// both, each number pair that differs is written "(lo-hi)" and equal ones as they are. Returns false (and writes `hi`) when the
// text differs or `out` is too small.
inline auto MergeRange(const char* lo, const char* hi, char* out, size_t outSize) noexcept -> bool {
	if (out == nullptr || outSize == 0) {
		return false;
	}
	size_t i = 0;
	size_t j = 0;
	size_t o = 0;
	bool ok = lo != nullptr && hi != nullptr;
	auto put = [&](char c) {
		if (o + 1 < outSize) {
			out[o++] = c;
		} else {
			ok = false;
		}
	};
	while (ok && (lo[i] != '\0' || hi[j] != '\0')) {
		const size_t ci = ColourAt(lo, i);
		const size_t cj = ColourAt(hi, j);
		if (ci != 0 || cj != 0) {
			if (ci != cj) {
				ok = false;
				break;
			}
			for (size_t k = 0; k < ci; ++k) {
				if (lo[i + k] != hi[j + k]) {
					ok = false;
				}
				put(lo[i + k]);
			}
			i += ci;
			j += cj;
			continue;
		}
		if (IsDigit(lo[i]) && IsDigit(hi[j])) {
			size_t ni = i;
			size_t nj = j;
			while (IsDigit(lo[ni])) {
				++ni;
			}
			while (IsDigit(hi[nj])) {
				++nj;
			}
			bool same = ni - i == nj - j;
			for (size_t k = 0; same && k < ni - i; ++k) {
				same = lo[i + k] == hi[j + k];
			}
			if (!same) {
				put('(');
			}
			for (size_t k = i; k < ni; ++k) {
				put(lo[k]);
			}
			if (!same) {
				put('-');
				for (size_t k = j; k < nj; ++k) {
					put(hi[k]);
				}
				put(')');
			}
			i = ni;
			j = nj;
			continue;
		}
		if (lo[i] != hi[j]) {
			ok = false;
			break;
		}
		put(lo[i]);
		++i;
		++j;
	}
	if (!ok) {
		o = 0;
		if (hi != nullptr) {
			while (hi[o] != '\0' && o + 1 < outSize) {
				out[o] = hi[o];
				++o;
			}
		}
	}
	out[o] = '\0';
	return ok;
}

}  // namespace ranged_desc

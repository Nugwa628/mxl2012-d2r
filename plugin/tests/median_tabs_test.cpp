// Standalone test of the stash's MEDIAN / ORBS tab rules (median_tabs_logic.h; not part of the plugin DLL). Lane medtab.
#include "../src/median_tabs_logic.h"

#include <cstdio>
#include <cstring>

namespace {
int failures = 0;
void Check(bool ok, const char* what) {
	if (!ok) {
		++failures;
		std::printf("FAIL: %s\n", what);
	}
}

auto Contains(const char* const* names, size_t n, const char* name) -> bool {
	for (size_t i = 0; i < n; ++i) {
		if (std::strcmp(names[i], name) == 0) {
			return true;
		}
	}
	return false;
}
}  // namespace

int main() {
	using namespace median_tabs;

	// live (RotW): each tab shows its own group
	Groups g = Visible(5, false, true);
	Check(g.median && !g.orbs && !g.runesOwn, "tab 5 shows MEDIAN only");
	g = Visible(6, false, true);
	Check(g.orbs && !g.median && !g.runesOwn, "tab 6 shows ORBS only");
	g = Visible(4, true, true);
	Check(g.runesOwn && !g.median && !g.orbs && !g.matPicture && !g.selVanilla && !g.selMedian, "Runes: D2R's slots, no selector");
	g = Visible(3, false, true);
	Check(g.matVanilla && !g.matMedian && g.selVanilla && !g.selMedian && !g.matPicture, "Materials, Vanilla page");
	g = Visible(3, true, true);
	Check(!g.matVanilla && g.matMedian && !g.selVanilla && g.selMedian && g.matPicture, "Materials, Median page");
	g = Visible(0, true, true);
	Check(!g.matPicture && !g.selVanilla && !g.selMedian, "Personal: no selector, no Median picture");

	// not live (non-RotW, or the off word): D2R's Materials page, no selector, tabs bounce
	g = Visible(3, true, false);
	Check(g.matVanilla && !g.matMedian && !g.selVanilla && !g.selMedian && !g.matPicture, "not live: D2R's Materials page only");
	Check(Bounce(5, false) && Bounce(6, false) && !Bounce(4, false) && !Bounce(0, false), "not live: 5 and 6 bounce");
	Check(!Bounce(5, true) && !Bounce(6, true), "live: 5 and 6 stay");

	// the getter stub: 5 and 6 read as Runes
	Check(GetterTab(0) == 0 && GetterTab(4) == 4 && GetterTab(5) == 4 && GetterTab(6) == 4, "getter: 5 / 6 -> 4");
	Check(GetterTab(255) == 4, "getter: any byte above 4 -> 4");

	// the stub and the redirected calls: outside controller-qol's checked 128 bytes of the getter, tabflash's call left out
	unsigned char stub[14];
	StubBytes(stub);
	const unsigned char stubWant[14] = {0x50, 0xe8, 0x78, 0xff, 0xff, 0xff, 0x59, 0x3c, 0x04, 0x76, 0x02, 0xb0, 0x04, 0xc3};
	Check(std::memcmp(stub, stubWant, sizeof(stub)) == 0, "stub: push rax / call 0x23af50 / pop rcx / cap at 4 / ret");
	Check(StubRva >= GetterRva + 128 && StubRva + sizeof(stub) <= 0x23afe0, "stub: after the checked bytes, inside the int3 pad");
	unsigned char call[5];
	CallBytes(0x23bbd2, GetterRva, call);
	const unsigned char flashCall[5] = {0xe8, 0x79, 0xf3, 0xff, 0xff};  // tab_flash_logic.h ShownTest
	Check(std::memcmp(call, flashCall, 5) == 0, "call bytes: the getter call at 0x23bbd2 as D2R has it");
	bool flashSiteLeft = true;
	bool outside = true;
	for (unsigned long long site : GetterCallers) {
		flashSiteLeft = flashSiteLeft && site != 0x23bbd2;
		outside = outside && (site + 5 <= GetterRva || site >= GetterRva + 128);
	}
	Check(sizeof(GetterCallers) / sizeof(GetterCallers[0]) == 21, "21 direct callers (22 less tabflash's)");
	Check(flashSiteLeft && outside, "callers: not tabflash's site, none inside the getter");
	CallBytes(0x23e655, StubRva, call);
	const unsigned char stubCall[5] = {0xe8, 0x78, 0xc9, 0xff, 0xff};
	Check(std::memcmp(call, stubCall, 5) == 0, "call bytes: 0x23e655 -> 0x23afd2 (backwards rel32)");

	// "@" codes: the 9 placeholders become the real codes, nothing else changes
	Check(sizeof(medtab_names::AtCodes) / sizeof(medtab_names::AtCodes[0]) == 9, "9 '@' codes");
	char code[] = {'b', '_', 'b', 'X'};
	Check(RestoreAtCode(code, 3) && std::memcmp(code, "b@bX", 4) == 0, "b_b -> b@b (only its 3 characters)");
	Check(!RestoreAtCode(code, 3), "b@b stays");
	char bang[] = {'!', '_', 'B'};
	Check(RestoreAtCode(bang, 3) && std::memcmp(bang, "!@B", 3) == 0, "!_B -> !@B");
	char rune[] = {'r', '0', '1'};
	Check(!RestoreAtCode(rune, 3) && std::memcmp(rune, "r01", 3) == 0, "r01 stays");
	char shorter[] = {'b', '_'};
	Check(!RestoreAtCode(shorter, 2), "a prefix is not a match");
	char other[] = {'x', '_', 'x'};
	Check(!RestoreAtCode(other, 3), "x_x is not one of the 9");
	for (const char* at : medtab_names::AtCodes) {
		Check(std::strchr(at, '@') == nullptr && std::strchr(at, medtab_names::Placeholder) != nullptr, "the table holds placeholders");
	}

	// the groups the plugin shows and hides
	Check(Contains(medtab_names::Selector, sizeof(medtab_names::Selector) / sizeof(char*), medtab_names::LayoutMark), "the layout mark is the Vanilla selector");
	Check(Contains(medtab_names::Median, sizeof(medtab_names::Median) / sizeof(char*), "b_b"), "Goodberry on MEDIAN as b_b");
	Check(Contains(medtab_names::MatMedian, sizeof(medtab_names::MatMedian) / sizeof(char*), "u_v"), "Poser! on the Median Materials page");
	Check(Contains(medtab_names::RunesOwn, sizeof(medtab_names::RunesOwn) / sizeof(char*), "r01"), "the Runes page's own slots");

	if (failures == 0) {
		std::printf("median_tabs: all checks passed\n");
	}
	return failures == 0 ? 0 : 1;
}

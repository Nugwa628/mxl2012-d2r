// Standalone test of part rotwwarn's rules (rotw_warn_logic.h; not part of the plugin DLL).
#include "../src/rotw_warn_logic.h"

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
}  // namespace

int main() {
	using namespace rotw_warn;
	// signatures
	Pattern p;
	Check(Parse("48 8B ?? 05", p) && p.size == 4 && p.bytes[0] == 0x48 && p.bytes[1] == 0x8b && p.any[2] && !p.any[3] && p.bytes[3] == 0x05, "parse with a wildcard");
	Check(!Parse("", p) && !Parse("4", p) && !Parse("4G", p) && !Parse("488B", p) && !Parse(nullptr, p), "malformed patterns refused");
	Check(Parse(OwnsRotwPattern, p) && p.size == 102, "the entitlement signature parses");
	Check(p.bytes[p.size - 8] == 'r' && p.bytes[p.size - 1] == 'c', "and ends with the text rotw-dlc");
	Check(Parse(ClientChatPattern, p) && p.size == 47, "the chat handler signature parses");
	const uint8_t data[] = {0x90, 0x48, 0x8b, 0x11, 0x05, 0x90, 0x48, 0x8b, 0x22, 0x06};
	Parse("48 8B ?? 05", p);
	Check(FindUnique(data, sizeof(data), p) == 1, "one match found at its offset");
	Parse("48 8B ??", p);
	Check(FindUnique(data, sizeof(data), p) == -1, "two matches: not unique");
	Parse("48 8B ?? 07", p);
	Check(FindUnique(data, sizeof(data), p) == -1, "no match");
	Check(FindUnique(data, 2, p) == -1, "data shorter than the pattern");
	// tabs
	Check(!NeedsRotw(0) && !NeedsRotw(1) && NeedsRotw(2) && NeedsRotw(6) && !NeedsRotw(7) && !NeedsRotw(-1), "tabs 2-6 need RotW");
	for (int t = 0; t <= LastTab; ++t) {
		Check(Decide(t, true) == Verdict::Open, "owned: every tab opens");
	}
	Check(Decide(0, false) == Verdict::Open && Decide(1, false) == Verdict::Open, "not owned: Personal and Shared open");
	for (int t = FirstRotwTab; t <= LastTab; ++t) {
		Check(Decide(t, false) == Verdict::Block, "not owned: RotW tabs blocked");
	}
	Check(FallbackTab(1) == 1 && FallbackTab(0) == 0, "back to the tab shown before");
	Check(FallbackTab(3) == 0 && FallbackTab(-1) == 0 && FallbackTab(9) == 0, "else Personal");
	// the warning line
	Check(WarnNow(5000, 0, WarnGapMs) && !WarnNow(5000, 4000, WarnGapMs) && WarnNow(6000, 4000, WarnGapMs), "one line per 2 s");
	// the banner
	Check(!BannerShown(1000, 0) && !BannerShown(5000, 4000) && !BannerShown(4000, 4000), "no banner: none yet or ended");
	Check(BannerShown(1000, 1000 + BannerMs) && BannerShown(3999, 4000), "shown until its end");
	Check(std::strstr(BannerLayoutHd, BannerPanelName) != nullptr && std::strstr(BannerLayoutSd, BannerPanelName) != nullptr, "layouts name the panel");
	Check(std::strstr(BannerLayoutHd, "\"priority\": 9000") != nullptr && std::strstr(BannerLayoutSd, "\"priority\": 9000") != nullptr, "over the stash");
	Check(std::strstr(BannerLayoutHd, "ClickCatcher") == nullptr && std::strstr(BannerLayoutSd, "ClickCatcher") == nullptr, "clicks go through");
	char line[160];
	WarningLine(line, sizeof(line), "Reign of the Warlock");
	Check(std::strcmp(line, "This stash tab needs Reign of the Warlock.") == 0, "the English line");
	WarningLine(line, sizeof(line), "");
	Check(std::strcmp(line, "This stash tab needs Reign of the Warlock.") == 0, "empty name: the English name");
	WarningLine(line, sizeof(line), nullptr);
	Check(std::strcmp(line, "This stash tab needs Reign of the Warlock.") == 0, "no name: the English name");
	WarningLine(line, sizeof(line), "Die Herrschaft des Hexenmeisters");
	Check(std::strcmp(line, "This stash tab needs Die Herrschaft des Hexenmeisters.") == 0, "D2R's localized name");
	WarningLine(Line::Store, line, sizeof(line), nullptr);
	Check(std::strcmp(line, "That stash tab needs Reign of the Warlock.") == 0, "#591: the line for an item kept out");
	WarningLine(Line::Send, line, sizeof(line), "Reign of the Warlock");
	Check(std::strcmp(line, "Send to stash needs Reign of the Warlock.") == 0, "#591: the line for Send to stash");
	WarningLine(Line::Tab, line, sizeof(line), "");
	Check(std::strcmp(line, "This stash tab needs Reign of the Warlock.") == 0, "the tab line by kind");
	// #591: items kept out of the RotW pages
	Check(StoreBlocked(true, true, false), "#591: found, gate on, not owned: kept out");
	Check(!StoreBlocked(true, true, true), "#591: owned: items go in as before");
	Check(!StoreBlocked(false, true, false), "#591: the check not found: D2R's behaviour");
	Check(!StoreBlocked(true, false, false), "#591: gate off (the control): D2R's behaviour");
	Check(IsTransferAsk(0x15fa9a) && IsTransferAsk(0x15fdbc) && !IsTransferAsk(0x15a0f9) && !IsTransferAsk(0), "#591: only the transfer's questions warn");
	Check(sizeof(HasSlotEntry) >= 14 && sizeof(DepositEntry) >= 14, "#591: hook entries cover a 14-byte jump");
	Check(HasSlotEntry[0] == 0x48 && DepositEntry[sizeof(DepositEntry) - 4] == 0xec && DepositEntry[sizeof(DepositEntry) - 3] == 0x06,
	      "#591: the deposit entry ends with mov r8d, 0x6ec");
	// dev switch
	Check(ParseOwnedTest("no") == OwnedTest::No && ParseOwnedTest("NO") == OwnedTest::No && ParseOwnedTest("Yes") == OwnedTest::Yes, "no / yes");
	Check(ParseOwnedTest("d2r-no") == OwnedTest::D2rNo && ParseOwnedTest("D2R-NO") == OwnedTest::D2rNo && ParseOwnedTest("d2r-yes") == OwnedTest::Game,
	      "d2r-no patches D2R's own check");
	Check(ParseOwnedTest("") == OwnedTest::Game && ParseOwnedTest("nope") == OwnedTest::Game && ParseOwnedTest(nullptr) == OwnedTest::Game, "anything else: D2R's answer");
	if (failures == 0) {
		std::printf("rotwwarn_tests: all passed\n");
	}
	return failures;
}

// Unit tests of the Stat Book's config and gamepad tab rule (src/statbook_config.h).
#include "../src/statbook_config.h"

#include <cstdio>
#include <cstring>

using namespace statbook;

namespace {
int g_failed = 0;
void Check(bool ok, const char* what) {
	if (!ok) {
		std::printf("FAIL: %s\n", what);
		++g_failed;
	}
}
}  // namespace

int main() {
	const Config d = ParseConfig(nullptr);
	Check(d.sheetRows && d.advancedStats && d.book && d.pad == PadButtons::Auto && d.bumperLeft == 19 && d.bumperRight == 20 && d.triggerLeft == 7 && d.triggerRight == 8 && !d.padLog,
	      "defaults");
	const Config c = ParseConfig("# x\n[other]\nbook = false\n[statbook]\nsheet_rows = false\nbook = true\npad_tabs = \"triggers\"\n"
	                             "pad_trigger_left = 7\npad_trigger_right=8\npad_bumper_left = 99999999\npad_log = true\n");
	Check(!c.sheetRows && c.book, "booleans, other sections ignored");
	Check(c.pad == PadButtons::Triggers && c.triggerLeft == 7 && c.triggerRight == 8, "pad buttons and ids");
	Check(c.bumperLeft == 19, "out of range id keeps the default");
	Check(c.padLog, "pad_log");
	Check(ParseConfig("[statbook]\npad_tabs = \"bumpers\"\n").pad == PadButtons::Bumpers, "bumpers");
	Check(ParseConfig("[statbook]\npad_tabs = \"off\"\n").pad == PadButtons::Off, "off");
	Check(ParseConfig("[statbook]\npad_tabs = \"what\"\n").pad == PadButtons::Auto, "unknown: auto");
	Check(ParseConfig("[statbook]\r\nbook = false\r\n").book == false, "CRLF");
	Check(PadChoice(PadButtons::Auto, true) == PadButtons::Bumpers && PadChoice(PadButtons::Auto, false) == PadButtons::Triggers,
	      "auto: bumpers with Controller QOL, else triggers");
	Check(PadChoice(PadButtons::Triggers, true) == PadButtons::Triggers, "explicit choice kept");
	Config ids;
	ids.bumperLeft = 5;
	ids.bumperRight = 6;
	ids.triggerLeft = 7;
	ids.triggerRight = 8;
	Check(PadStep(ids, PadButtons::Bumpers, 5) == -1 && PadStep(ids, PadButtons::Bumpers, 6) == 1 && PadStep(ids, PadButtons::Bumpers, 7) == 0, "bumpers");
	Check(PadStep(ids, PadButtons::Triggers, 8) == 1 && PadStep(ids, PadButtons::Triggers, 5) == 0, "triggers");
	Check(PadStep(Config{}, PadButtons::Bumpers, -1) == 0 && PadStep(Config{}, PadButtons::Bumpers, 0) == 0, "no action never matches");
	Config unset;
	unset.bumperLeft = unset.bumperRight = -1;
	Check(PadStep(unset, PadButtons::Bumpers, -1) == 0 && PadStep(unset, PadButtons::Bumpers, 19) == 0, "unset ids never match");
	Check(PadStep(Config{}, PadButtons::Bumpers, 19) == -1 && PadStep(Config{}, PadButtons::Triggers, 8) == 1, "default ids");
	Check(PadStep(ids, PadButtons::Off, 5) == 0, "off");

	// tabs = "top" | "side"
	Check(!d.sideTabs, "tabs: top by default");
	Check(ParseConfig("[statbook]\ntabs = \"side\"\n").sideTabs, "tabs side");
	Check(!ParseConfig("[statbook]\ntabs = \"top\"\n").sideTabs, "tabs top");
	Check(ParseConfig("[statbook]\ntabs = side\r\n").sideTabs, "tabs bare word, CRLF");
	Check(!ParseConfig("[statbook]\ntabs = \"left\"\n").sideTabs, "tabs unknown: top");
	Check(!ParseConfig("[other]\ntabs = \"side\"\n").sideTabs, "tabs of another section ignored");
	Check(!ParseConfig("[statbook]\ntabs_x = \"side\"\n").sideTabs, "a longer key is not tabs");
	char out[512];
	Check(WithTabs("[statbook]\nbook = true\ntabs = \"top\"  # top or side\npad_log = false\n", true, out, sizeof(out)) &&
	          std::strcmp(out, "[statbook]\nbook = true\ntabs = \"side\"  # top or side\npad_log = false\n") == 0,
	      "WithTabs replaces the value in place");
	Check(ParseConfig(out).sideTabs && !ParseConfig(out).padLog && ParseConfig(out).book, "WithTabs: the rest still parses");
	Check(WithTabs(out, false, out + 256, 256) && std::strcmp(out + 256, "[statbook]\nbook = true\ntabs = \"top\"  # top or side\npad_log = false\n") == 0,
	      "WithTabs back to top");
	Check(WithTabs("[statbook]\r\ntabs = side\r\n", false, out, sizeof(out)) && std::strcmp(out, "[statbook]\r\ntabs = \"top\"\r\n") == 0,
	      "WithTabs bare word, CRLF kept");
	Check(WithTabs("[statbook]\nbook = true\n", true, out, sizeof(out)) && std::strcmp(out, "[statbook]\ntabs = \"side\"\nbook = true\n") == 0,
	      "WithTabs adds the key to the section");
	Check(WithTabs("[other]\ntabs = \"top\"\n", true, out, sizeof(out)) &&
	          std::strcmp(out, "[other]\ntabs = \"top\"\n\n[statbook]\ntabs = \"side\"\n") == 0,
	      "WithTabs adds the section, other sections untouched");
	Check(WithTabs(nullptr, true, out, sizeof(out)) && ParseConfig(out).sideTabs, "WithTabs on no file");
	Check(!WithTabs("[statbook]\ntabs = \"top\"\n", true, out, 8), "WithTabs: too small");
	if (g_failed == 0) {
		std::printf("statbook config tests: all passed\n");
	}
	return g_failed == 0 ? 0 : 1;
}

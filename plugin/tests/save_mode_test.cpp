// Standalone test of the save format check and the cancelled-save count (save_mode_logic.h, docs/bugs.md #512; not part of
// the plugin DLL).
#include "../src/save_mode_logic.h"

#include <cstdio>
#include <cstring>
#include <string>

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
	using save_mode::Mode;
	using save_mode::ParseMode;
	using save_mode::Repair;
	const std::string installed = "[d2rcore.save_format]\nmode = \"extended\"\n\n[d2rcore.automap]\n# show_area_name = true\n";
	Check(ParseMode(installed) == Mode::Extended, "the installer's file: extended");
	Check(ParseMode("\xef\xbb\xbf[d2rcore.save_format]\r\nmode='extended' # Median\r\n") == Mode::Extended, "BOM, CRLF, single quotes, comment");
	Check(ParseMode("d2rcore.save_format.mode = \"extended\"\n[d2rcore.items]\n") == Mode::Extended, "dotted key at the top");
	Check(ParseMode("[d2rcore.save_format]\n# mode = \"extended\"\n") == Mode::Missing, "a commented line does not count");
	Check(ParseMode("[d2rcore.items]\nmode = \"extended\"\n") == Mode::Missing, "mode of another section does not count");
	std::string value;
	Check(ParseMode("[d2rcore.save_format]\nmode = \"retail\"\n", &value) == Mode::Other && value == "retail", "retail asked for");
	// The player's file of bug #512: another mod's settings, no save format.
	const std::string player = "[d2rloader]\ndefault_mod = \"othermod\"\n\n[d2rcore.stash]\nadd_shared_tabs = 100\n";
	Check(ParseMode(player) == Mode::Missing, "the player's file: missing");

	std::string fixed = Repair(player);
	Check(ParseMode(fixed) == Mode::Extended, "repair adds the section");
	Check(fixed.find(player) != std::string::npos, "repair keeps the rest of the file");
	Check(fixed.compare(0, 21, "[d2rcore.save_format]") == 0, "the section goes at the top (before [d2rloader] keys)");
	fixed = Repair("[d2rcore.save_format]\nmode = \"retail\"\n[x]\na = 1\n");
	Check(fixed == "[d2rcore.save_format]\nmode = \"extended\"\n[x]\na = 1\n", "a retail line is replaced");
	fixed = Repair("[a]\nb = 1\n[d2rcore.save_format]\n# mode = \"extended\"\n");
	Check(fixed == "[a]\nb = 1\n[d2rcore.save_format]\nmode = \"extended\"\n# mode = \"extended\"\n", "the line goes under the existing header");
	fixed = Repair("[d2rcore.save_format]");
	Check(ParseMode(fixed) == Mode::Extended, "header on the last line without a newline");
	fixed = Repair("d2rcore.save_format.mode = \"retail\"\r\n[b]\r\n");
	Check(fixed == "d2rcore.save_format.mode = \"extended\"\r\n[b]\r\n", "dotted key replaced, CRLF kept");
	fixed = Repair("[c]\r\nd = 2\r\n");
	Check(fixed == "[d2rcore.save_format]\r\nmode = \"extended\"\r\n\r\n[c]\r\nd = 2\r\n", "CRLF file gets CRLF lines");
	Check(ParseMode(Repair("")) == Mode::Extended, "a missing file is made");
	Check(Repair(installed) == installed, "a right file is not changed");

	// D2RLoader's lines of the player's log (character name left out here).
	std::string rest;
	const std::string a = "[2026-10-29 23:52:52.154] [ERROR] Character save failed before the disk write: character=\"X\" mod=\"mxl2012\" format=retail\n"
	                      "[2026-10-29 23:52:52.158] [ERROR] Save batch cancelled. Existing files were not replaced.\n[2026-10-29 23:53:22.215] [ERROR] Charac";
	Check(save_mode::CountFailures(a, rest) == 1 && rest == "[2026-10-29 23:53:22.215] [ERROR] Charac", "one whole failure line, the cut one waits");
	Check(save_mode::CountFailures("ter save failed before the disk write\n", rest) == 1 && rest.empty(), "the cut line is counted when it ends");
	Check(save_mode::CountFailures("[x] Shared stash save failed: section=page\n[x] Character save rejected: its save format\n", rest) == 1,
	      "a shared stash failure counts, a load rejection does not");
	Check(save_mode::CountFailures("no newline yet", rest) == 0 && rest == "no newline yet", "nothing counted before the line ends");

	char n[256];
	save_mode::RepairedNotice(n, sizeof(n));
	Check(std::strlen(n) < 255 && std::strstr(n, "start it again") != nullptr, "repaired notice fits");
	save_mode::NotRepairedNotice(n, sizeof(n));
	Check(std::strlen(n) < 255 && std::strstr(n, "extended") != nullptr, "not repaired notice fits");
	save_mode::FailureNotice(n, sizeof(n), 112, 1, 21, true);
	Check(std::strlen(n) < 255 && std::strstr(n, "SAVE FAILED 112 times (last 01:21)") != nullptr, "failure notice, retail");
	save_mode::FailureNotice(n, sizeof(n), 1, 9, 5, false);
	Check(std::strlen(n) < 255 && std::strstr(n, "1 time (last 09:05)") != nullptr, "failure notice, one");

	if (failures == 0) {
		std::printf("save_mode: all tests passed\n");
	}
	return failures == 0 ? 0 : 1;
}

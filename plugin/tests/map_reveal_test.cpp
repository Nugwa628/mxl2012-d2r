// Standalone test of the pity map reveal's pure part (map_reveal_logic.h; not part of the plugin DLL).
#include "../src/map_reveal_logic.h"

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
	using namespace map_reveal;

	// percent: whole, rounded down
	Check(Percent(0, 0) == 0, "no rooms: 0 %");
	Check(Percent(1280, 6272) == 20, "Cold Plains on arrival (probe): 20.4 % -> 20");
	Check(Percent(2240, 2240) == 100, "town fully active: 100 %");
	Check(Percent(699, 1000) == 69, "69.9 % reads 69");

	// threshold: exact compare, 0 = always, 101 = off, excluded levels
	Check(Decide(70, false, 700, 1000) == Gate::Ready, "70.0 % reaches 70");
	Check(Decide(70, false, 699, 1000) == Gate::Below, "69.9 % does not");
	Check(Decide(70, false, 4391, 6272) == Gate::Ready, "4391 / 6272 = 70.01 % reaches 70");
	Check(Decide(70, false, 4390, 6272) == Gate::Below, "4390 / 6272 = 69.99 % does not");
	Check(Decide(0, false, 0, 6272) == Gate::Ready, "threshold 0: at once");
	Check(Decide(0, false, 0, 0) == Gate::Ready, "threshold 0: also with no area read");
	Check(Decide(100, false, 6271, 6272) == Gate::Below, "threshold 100: every room");
	Check(Decide(100, false, 6272, 6272) == Gate::Ready, "threshold 100 at 100 %");
	Check(Decide(101, false, 6272, 6272) == Gate::Off, "threshold 101: off even at 100 %");
	Check(Decide(70, true, 6272, 6272) == Gate::Excluded, "an excluded level never");
	Check(Decide(101, true, 0, 1) == Gate::Off, "off wins over excluded");
	Check(Decide(70, false, 0, 0) == Gate::Below, "an empty level is not ready");

	// towns and the exclusion list
	Settings s;
	for (const int t : Towns) {
		Check(Excluded(t, s), "the five towns are excluded");
	}
	Check(!Excluded(2, s) && !Excluded(3, s) && !Excluded(8, s) && !Excluded(136, s), "other levels are not (empty list)");
	s.exclude[0] = 73;
	s.nExclude = 1;
	Check(Excluded(73, s) && !Excluded(74, s), "a listed level is excluded");

	// settings: [mapreveal] of mxl2012-core.toml
	Settings p;
	Check(!ParseSettings("", &p) && p.threshold == DefaultThreshold && p.nExclude == 0, "empty text: defaults");
	Check(!ParseSettings(nullptr, &p) && p.threshold == 70, "no text: defaults");
	const char* shipped =
	    "# D2R-XL 2012 core plugin settings\n\n[mapreveal]\n# Reveal ... in %. 0 = always, 101 = off.\nthreshold = 70\n"
	    "# Level ids with no reveal besides the towns, e.g. exclude = [73, 74]\nexclude = []\n";
	Check(ParseSettings(shipped, &p) && p.threshold == 70 && p.nExclude == 0, "the shipped file: 70, nothing excluded");
	Check(ParseSettings("[mapreveal]\r\nthreshold = 55\r\nexclude = [73, 74 ,120]\r\n", &p) && p.threshold == 55 && p.nExclude == 3 &&
	          p.exclude[0] == 73 && p.exclude[1] == 74 && p.exclude[2] == 120,
	      "CRLF, a value and a list");
	Check(ParseSettings("[mapreveal]\nthreshold=0\n", &p) && p.threshold == 0, "0 = always");
	Check(ParseSettings("[mapreveal]\nthreshold = 101\n", &p) && p.threshold == 101, "101 = off");
	Check(ParseSettings("[mapreveal]\nthreshold = 250\n", &p) && p.threshold == 101, "above 101 is off");
	Check(ParseSettings("[mapreveal]\nthreshold = -5\n", &p) && p.threshold == 0, "below 0 is always");
	Check(ParseSettings("[mapreveal]\nthreshold = \"x\"\n", &p) && p.threshold == 70, "an unreadable value keeps the default");
	Check(ParseSettings("[mapreveal]\nthreshold = 40 # less\n", &p) && p.threshold == 40, "a comment after the value");
	Check(ParseSettings("[other]\nthreshold = 10\n[mapreveal]\nexclude = [8]\n[more]\nthreshold = 20\n", &p) && p.threshold == 70 &&
	          p.nExclude == 1 && p.exclude[0] == 8,
	      "only the [mapreveal] table's keys");
	Check(!ParseSettings("[mapreveal2]\nthreshold = 10\n", &p) && p.threshold == 70, "another table name");
	Check(ParseSettings("[mapreveal]\nexclude = [0, 300, 5]\n", &p) && p.nExclude == 1 && p.exclude[0] == 5, "ids out of range skipped");
	Check(ParseSettings("[mapreveal]\nthresholds = 10\n", &p) && p.threshold == 70, "a longer key is not the threshold");

	// per-level marks and the once-only announcement
	static Level l;
	int dummy = 0;
	ResetLevel(&l, &dummy);
	Check(l.first == &dummy && !Seen(l, 0) && !l.announced && !l.revealed, "a new level starts empty");
	Mark(&l, 0);
	Mark(&l, 65);
	Mark(&l, MaxRooms - 1);
	Mark(&l, MaxRooms);  // ignored
	Mark(&l, -1);        // ignored
	Check(Seen(l, 0) && Seen(l, 65) && Seen(l, MaxRooms - 1) && !Seen(l, 1) && !Seen(l, 64) && !Seen(l, MaxRooms), "bits by room place");
	Check(!ShouldAnnounce(&l, Gate::Below), "below: no line");
	Check(ShouldAnnounce(&l, Gate::Ready), "ready: one line");
	Check(!ShouldAnnounce(&l, Gate::Ready), "ready again: no second line");
	ResetLevel(&l, &dummy);
	l.revealed = true;
	Check(!ShouldAnnounce(&l, Gate::Ready), "a revealed level: no line");
	ResetLevel(&l, &dummy);
	Check(!ShouldAnnounce(&l, Gate::Off) && !ShouldAnnounce(&l, Gate::Excluded), "off / excluded: no line");

	// key names and lines
	char k[24];
	KeyName('L', 0, k, sizeof(k));
	Check(std::strcmp(k, "L") == 0, "L");
	KeyName('K', 1, k, sizeof(k));
	Check(std::strcmp(k, "Shift+K") == 0, "Shift+K");
	KeyName(0x74, 2, k, sizeof(k));
	Check(std::strcmp(k, "Ctrl+F5") == 0, "Ctrl+F5");
	KeyName(0, 1, k, sizeof(k));
	Check(k[0] == '\0', "no key: empty");
	KeyName(0xBA, 0, k, sizeof(k));
	Check(std::strcmp(k, "key 0xBA") == 0, "another key by its code");
	char line[160];
	AvailableLine(line, sizeof(line), 71, "L");
	Check(std::strcmp(line, "Map: 71% of this level explored. Press L to reveal the rest.") == 0, "available line");
	AvailableLine(line, sizeof(line), 71, "");
	Check(std::strstr(line, "Reveal Level Map key") != nullptr, "available line without a key");
	RefusedLine(line, sizeof(line), Gate::Below, 45, 70, false);
	Check(std::strcmp(line, "Map: 45% of this level explored (70% needed).") == 0, "refused line with the percent");
	RefusedLine(line, sizeof(line), Gate::Ready, 80, 70, true);
	Check(std::strcmp(line, "Map: this level is already revealed.") == 0, "already revealed");
	RefusedLine(line, sizeof(line), Gate::Excluded, 100, 70, false);
	Check(std::strcmp(line, "Map: no reveal in this area.") == 0, "excluded");
	RefusedLine(line, sizeof(line), Gate::Off, 100, 101, false);
	Check(std::strstr(line, "off") != nullptr, "off");
	RevealedLine(line, sizeof(line), 74, 98, 98);
	Check(std::strcmp(line, "Map: rest of the level revealed (74% explored).") == 0, "revealed line");
	RevealedLine(line, sizeof(line), 74, 90, 98);
	Check(std::strcmp(line, "Map: level revealed in part (90 of 98 rooms).") == 0, "partial reveal line");

	// chat packet 0x26 for the client handler
	uint8_t pkt[ChatPacketMax];
	const size_t n = BuildChatPacket(pkt, sizeof(pkt), ColourYellow, "Hi");
	Check(n == 0x0b + 3 && pkt[0] == 0x26 && pkt[1] == 4 && pkt[2] == 0 && pkt[3] == 0 && pkt[8] == 9 && pkt[9] == 0, "header");
	Check(pkt[0x0a] == 0 && std::strcmp(reinterpret_cast<const char*>(pkt + 0x0b), "Hi") == 0, "empty name, then the text");
	char longText[400];
	std::memset(longText, 'a', sizeof(longText) - 1);
	longText[sizeof(longText) - 1] = '\0';
	Check(BuildChatPacket(pkt, sizeof(pkt), 0, longText) == ChatPacketMax && pkt[ChatPacketMax - 1] == 0, "text cut at 255 bytes");
	Check(BuildChatPacket(pkt, 5, 0, "Hi") == 0, "too small a buffer");

	if (failures == 0) {
		std::printf("mapreveal_tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}

// Standalone test of the level map reveal's pure part (map_reveal_logic.h; not part of the plugin DLL).
#include "../src/map_reveal_logic.h"

#include <cstdio>
#include <cstring>
#include <initializer_list>

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

	// the exclusion list (empty by default: every level, towns too, can be revealed; bug #559)
	Settings s;
	for (const int t : {1, 40, 75, 103, 109, 2, 8, 34, 92, 93, 136}) {
		Check(!Excluded(t, s), "nothing excluded by default (towns, sewers, catacombs, small levels)");
	}
	s.exclude[0] = 73;
	s.nExclude = 1;
	Check(Excluded(73, s) && !Excluded(74, s), "a listed level is excluded");

	// the act towns, revealed on each arrival (owner, 2026-11-08)
	for (const int t : {1, 40, 75, 103, 109}) {
		Check(IsTown(t), "an act town");
	}
	for (const int t : {0, 2, 39, 41, 74, 76, 102, 104, 108, 110, 136}) {
		Check(!IsTown(t), "not a town");
	}
	Check(TownLayer(1) == 0 && TownLayer(40) == 27 && TownLayer(75) == 57 && TownLayer(103) == 77 && TownLayer(109) == 79, "the towns' layers");
	Check(TownLayer(2) == -1 && TownLayer(136) == -1, "no layer for other levels");
	TownWatch w;
	const auto poll = [&w](int level) { return TownArrival(&w, level, TownLayer(level)); };
	Check(!TownArrival(&w, 0, -1), "no level: nothing");
	Check(!TownArrival(&w, 2, 1), "a field: nothing");
	Check(!poll(1) && !poll(1), "town: waits for the level to settle");
	Check(poll(1), "town: revealed on the third poll");
	Check(!poll(1) && !poll(1), "town: once per arrival");
	Check(!TownArrival(&w, 2, 1), "out of town again");
	Check(!poll(1) && !poll(1) && poll(1), "back in town: revealed again");
	Check(!poll(40) && !poll(40) && poll(40), "town to town (act change)");
	Check(!TownArrival(&w, 0, -1) && !poll(40) && !poll(40) && poll(40), "a new game in the same town");
	Check(!TownArrival(&w, 2, 1) && !poll(75) && !TownArrival(&w, 2, 1) && !poll(75) && !poll(75) && poll(75),
	      "a town left before it settled: counted from the new arrival");
	Check(!TownArrival(&w, 2, 1), "out of town before the act change");
	for (int i = 0; i < 20; ++i) {
		Check(!TownArrival(&w, 109, 57), "act change: never while the layer is still the old town's");
	}
	Check(!TownArrival(&w, 109, -1), "act change: no layer yet");
	Check(!poll(109) && !poll(109) && poll(109), "act change: three polls once the layer is the town's");
	Check(!TownArrival(&w, 2, 1), "out of town");
	Check(!poll(103) && !TownArrival(&w, 103, 57) && !poll(103) && !poll(103) && poll(103), "the layer lost again: the count starts over");

	// settings: [mapreveal] of mxl2012-core.toml
	Settings p;
	Check(!ParseSettings("", &p) && p.nExclude == 0 && !p.oldThreshold, "empty text: defaults");
	Check(!ParseSettings(nullptr, &p) && p.nExclude == 0, "no text: defaults");
	const char* shipped =
	    "# D2R-XL 2012 core plugin settings\n\n[mapreveal]\n# Level ids where the key reveals nothing, e.g. exclude = [73, 74]\n"
	    "exclude = []\n";
	Check(ParseSettings(shipped, &p) && p.nExclude == 0 && !p.oldThreshold, "the shipped file: nothing excluded");
	const char* old016 =
	    "# D2R-XL 2012 core plugin settings\n\n[mapreveal]\n# Reveal ... in %. 0 = always, 101 = off.\nthreshold = 70\n"
	    "# Level ids with no reveal besides the towns, e.g. exclude = [73, 74]\nexclude = []\n";
	Check(ParseSettings(old016, &p) && p.nExclude == 0 && p.oldThreshold, "the 0.1.16 file: read, its threshold ignored");
	Check(ParseSettings("[mapreveal]\nthreshold = 101\n", &p) && p.oldThreshold && p.nExclude == 0, "an old 'off' threshold: ignored too");
	Check(ParseSettings("[mapreveal]\nthreshold = \"x\"\nexclude = [8]\n", &p) && p.nExclude == 1 && p.exclude[0] == 8,
	      "an unreadable old threshold does not stop the list");
	Check(ParseSettings("[mapreveal]\r\nexclude = [73, 74 ,120]\r\n", &p) && p.nExclude == 3 && p.exclude[0] == 73 && p.exclude[1] == 74 &&
	          p.exclude[2] == 120,
	      "CRLF and a list");
	Check(ParseSettings("[mapreveal]\nexclude = [8] # caves\n", &p) && p.nExclude == 1, "a comment after the value");
	Check(ParseSettings("[other]\nexclude = [10]\n[mapreveal]\nexclude = [8]\n[more]\nexclude = [20]\n", &p) && p.nExclude == 1 &&
	          p.exclude[0] == 8,
	      "only the [mapreveal] table's keys");
	Check(!ParseSettings("[mapreveal2]\nexclude = [10]\n", &p) && p.nExclude == 0, "another table name");
	Check(ParseSettings("[mapreveal]\nexclude = [0, 300, 5]\n", &p) && p.nExclude == 1 && p.exclude[0] == 5, "ids out of range skipped");
	Check(ParseSettings("[mapreveal]\nthresholds = 10\n", &p) && !p.oldThreshold, "a longer key is not the old threshold");

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
	RefusedLine(line, sizeof(line));
	Check(std::strcmp(line, "Map: no reveal in this area.") == 0, "excluded");
	RevealedLine(line, sizeof(line), 98, 98);
	Check(std::strcmp(line, "Map: level revealed.") == 0, "revealed line");
	RevealedLine(line, sizeof(line), 90, 98);
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

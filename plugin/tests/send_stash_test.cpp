// Standalone test of the send-to-stash button's pure part (send_stash_logic.h, mxl_send_stash.h; not part of the plugin DLL).
#include "../src/mxl_send_stash.h"
#include "../src/send_stash_logic.h"

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
	using namespace send_stash;
	// codes as the items record keeps them (4 bytes, space padded)
	Check(CodeOf("r01") == (static_cast<uint32_t>('r') | ('0' << 8) | ('1' << 16) | (' ' << 24)), "r01 -> 'r01 '");
	Check(CodeOf("r01 ") == CodeOf("r01"), "padded and bare codes are the same");
	Check(CodeOf("g$a") == CodeOf("g$a "), "Median's gem codes");
	char text[5];
	CodeText(CodeOf("yo1"), text);
	Check(std::strcmp(text, "yo1") == 0, "code text without the padding");

	// the generated list: D2R's slot codes plus Median's 48 (tools/send_stash.py header)
	Check(mxl_send_stash::CodeCount == sizeof(mxl_send_stash::Codes) / sizeof(mxl_send_stash::Codes[0]), "the count matches the list");
	Check(mxl_send_stash::CodeCount >= 91 + 48, "D2R's 91 and Median's 48 codes");
	const char* const slotted[] = {"r01", "r33", "r34", "r56", "gcw", "gpw", "skz", "yo1", "yo5", "g$a", "9$e", "7$c", "5$e", "pk1"};
	for (const char* c : slotted) {
		Check(IsSlotCode(CodeOf(c), mxl_send_stash::Codes), c);
	}
	const char* const unslotted[] = {"box", "hp1", "key", "r57", "cm1", "ssd", "tbk", "isc"};
	for (const char* c : unslotted) {
		Check(!IsSlotCode(CodeOf(c), mxl_send_stash::Codes), "an item without a slot stays");
	}
	for (unsigned i = 0; i < mxl_send_stash::CodeCount; ++i) {
		Check(std::strlen(mxl_send_stash::Codes[i]) == 4, "every code is padded to 4");
		for (unsigned j = 0; j < i; ++j) {
			Check(std::strcmp(mxl_send_stash::Codes[i], mxl_send_stash::Codes[j]) != 0, "no code twice");
		}
	}
	Check(std::strcmp(mxl_send_stash::MessagePanel, "mxl2012-core/SendStash") == 0, "the click message's panel");

	// which button shows
	Check(Decide(false, false, true) == Show::None, "no player: nothing set");
	Check(Decide(true, false, true) == Show::Button, "single player / host with the RotW stash: the button");
	Check(Decide(true, false, false) == Show::NoSlots, "classic / expansion game: greyed");
	Check(Decide(true, true, true) == Show::Joined, "a joiner: greyed while joiners are off");
	Check(Decide(true, true, false) == Show::Joined, "a joiner of a classic game: the joiner reason");
	Check(Decide(true, true, true, true) == Show::Button, "joiners switched on: the button");
	Check(!JoinersOn, "joiners stay off until a two-instance game test (owner, 2026-11-05)");
	Check(RefusalLine(Show::Button) == nullptr && RefusalLine(Show::None) == nullptr, "no refusal line when the button works");
	Check(std::strstr(RefusalLine(Show::NoSlots), "Reign of the Warlock") != nullptr, "#554: a greyed click says why (classic / expansion)");
	Check(std::strstr(RefusalLine(Show::Joined), "joined") != nullptr, "#554: a greyed click says why (joiner)");
	Check(std::strlen(RefusalLine(Show::NoSlots)) < ChatTextSize && std::strlen(RefusalLine(Show::Joined)) < ChatTextSize, "refusal lines fit the chat record");
	Check(ButtonActive(Show::NoSlots, Show::NoSlots) && !ButtonActive(Show::Button, Show::NoSlots), "#554: greyed shown, the live button hidden and disabled");
	Check(ButtonActive(Show::Button, Show::Button) && !ButtonActive(Show::Joined, Show::Button), "the live button shown, the greyed ones disabled");

	// the plan: the slot's count plus the items planned for it stay under 99
	{
		const Candidate items[] = {{1, CodeOf("r01"), 10, 97}, {2, CodeOf("gcv"), 20, 0}, {3, CodeOf("r01"), 10, 97},
		                           {4, CodeOf("r01"), 10, 97},  {5, CodeOf("r02"), 11, 99}, {6, CodeOf("gcv"), 20, 0}};
		Verdict v[6];
		Plan(items, 6, v);
		Check(v[0] == Verdict::Send && v[2] == Verdict::Send, "97 + 2 = 99: two El runes go");
		Check(v[3] == Verdict::Full, "the third El rune would make 100: it stays");
		Check(v[4] == Verdict::Full, "a full slot (99): it stays");
		Check(v[1] == Verdict::Send && v[5] == Verdict::Send, "a new slot takes both");
	}
	{
		const Candidate items[] = {{1, CodeOf("r01"), 10, 98}, {2, CodeOf("r01"), 10, 98}};
		Verdict v[2];
		Plan(items, 2, v);
		Check(v[0] == Verdict::Send && v[1] == Verdict::Full, "98: one more, the server refuses at more than 0x62");
	}

	// the summary line (owner's wording)
	char line[ChatTextSize];
	Stayed stayed[4] = {};
	size_t n = 0;
	n = AddStayed(stayed, n, 4, "El Rune");
	n = AddStayed(stayed, n, 4, "Chipped Ruby");
	n = AddStayed(stayed, n, 4, "Chipped Ruby");
	Summary(line, sizeof(line), 14, stayed, n, 0);
	Check(std::strcmp(line, "Sent 14 items. 3 stayed: stack full (El Rune, Chipped Ruby x2).") == 0, line);
	Summary(line, sizeof(line), 1, nullptr, 0, 0);
	Check(std::strcmp(line, "Sent 1 item.") == 0, line);
	Summary(line, sizeof(line), 0, stayed, 1, 0);
	Check(std::strcmp(line, "Sent 0 items. 1 stayed: stack full (El Rune).") == 0, line);
	Summary(line, sizeof(line), 0, nullptr, 0, 0);
	Check(std::strcmp(line, "No storable/stackable items in the backpack.") == 0, line);
	Summary(line, sizeof(line), 3, nullptr, 0, 2);
	Check(std::strcmp(line, "Sent 3 items. 2 were not taken.") == 0, line);
	Summary(line, sizeof(line), 3, nullptr, 0, 1);
	Check(std::strcmp(line, "Sent 3 items. 1 was not taken.") == 0, line);
	{
		Stayed many[24] = {};
		size_t m = 0;
		char name[48];
		for (int i = 0; i < 24; ++i) {
			std::snprintf(name, sizeof(name), "A Rather Long Item Name %02d", i);
			m = AddStayed(many, m, 24, name);
		}
		Check(m == 24 && AddStayed(many, m, 24, "one more") == 24, "the list keeps its cap");
		Summary(line, sizeof(line), 5, many, m, 0);
		const size_t len = std::strlen(line);
		Check(len < ChatTextSize, "the line fits the chat record");
		Check(len > 5 && std::strcmp(line + len - 5, "...).") == 0, "a long list ends with ...");
	}

	// the chat record
	uint8_t rec[ChatRecordSize];
	BuildChat(rec, ChatLogLine, ChatWhite, "Sent 2 items.");
	Check(rec[0] == 0x26 && rec[1] == 4 && rec[8] == 0, "packet 0x26, a message log line, white");
	Check(std::strcmp(reinterpret_cast<const char*>(rec + ChatText), "Sent 2 items.") == 0, "the text at +0x47");
	Check(rec[ChatText - 1] == 0 && rec[0x0a] == 0, "no speaker name");

	// constants the server path depends on
	Check(StackCap == 99 && OpAdvancedStash == 0x63 && SubDeposit == 0, "deposit packet and cap");
	Check(TakenTimeoutMs == 1000, "a refused item is known after 1 s");
	Check(sizeof(SendEntry) == 16 && sizeof(LocalIdEntry) == 7, "entry byte lengths");

	// the string table's icon marker is dropped from a name, plain names are kept
	Check(std::strcmp(PlainName("\xee\x81\xbe;El Rune"), "El Rune") == 0, "icon marker dropped");
	Check(std::strcmp(PlainName("Chipped Ruby"), "Chipped Ruby") == 0 && std::strcmp(PlainName("a;b"), "a;b") == 0, "plain names kept");

	if (failures == 0) {
		std::printf("send_stash: all checks passed\n");
	}
	return failures == 0 ? 0 : 1;
}

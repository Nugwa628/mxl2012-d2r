// Standalone test of the grouped Advanced Stats panel (advstats_logic.h, advstats_table.h; not part of the plugin DLL).
#include "../src/advstats_logic.h"
#include "../src/advstats_table.h"

#include <cstdio>
#include <cstring>
#include <map>
#include <string>

namespace {
int failures = 0;
void Check(bool ok, const char* what) {
	if (!ok) {
		++failures;
		std::printf("FAIL: %s\n", what);
	}
}

using namespace advstats;
constexpr size_t RowCount = sizeof(Rows) / sizeof(Rows[0]);
constexpr size_t GroupCount = sizeof(Groups) / sizeof(Groups[0]);

auto IndexOf(const char* name) -> int {
	for (size_t i = 0; i < RowCount; ++i) {
		if (std::strcmp(Rows[i].name, name) == 0) {
			return static_cast<int>(i);
		}
	}
	return -1;
}

struct Plan {
	Item items[MaxItems];
	size_t n = 0;
};

auto Make(const std::map<int, int>& stats) -> Plan {
	Plan p;
	p.n = BuildPlan(GroupCount, Rows, RowCount, [&](uint16_t id) { auto it = stats.find(id); return it == stats.end() ? 0 : it->second; }, p.items,
	                MaxItems);
	return p;
}

auto Has(const Plan& p, const char* name, uint8_t part = 0) -> bool {
	const int i = IndexOf(name);
	for (size_t k = 0; k < p.n; ++k) {
		if (p.items[k].heading == 0 && p.items[k].index == i && p.items[k].part == part) {
			return true;
		}
	}
	return false;
}

auto HasHeading(const Plan& p, size_t group) -> bool {
	for (size_t k = 0; k < p.n; ++k) {
		if (p.items[k].heading != 0 && p.items[k].index == group) {
			return true;
		}
	}
	return false;
}

auto Fmt(const char* pattern, std::initializer_list<int32_t> v) -> std::string {
	char out[128];
	Fill(pattern, v.begin(), v.size(), out, sizeof(out));
	return out;
}
}  // namespace

int main() {
	// the hooked code
	Check(UpdateSlotRva == 0x1fdd6a0, "Update is slot 2 of vtable 0x1fdd690");
	Check(sizeof(BuildEntry) == 18 && sizeof(TextEntry) == 21 && sizeof(UpdateEntry) == 20, "entry byte counts end on whole instructions");
	Check(BuildEntry[0] == 0x40 && BuildEntry[1] == 0x53 && TextEntry[0] == 0x40 && TextEntry[1] == 0x55, "builder / text start with push");
	Check(RecordSize == 0x144 && StatsData == 0x1258 && StatsCount == 0x1260, "itemstatcost records as the builder reads them");

	// the table: groups in order, every row in a valid group, groups contiguous, own rows with their texts
	Check(GroupCount == 10, "ten groups");
	Check(std::strcmp(Groups[0].english, "Offense") == 0 && std::strcmp(Groups[GroupCount - 1].english, "Other") == 0, "Offense first, Other last");
	bool groupsOk = true, ordered = true, ownOk = true;
	for (size_t i = 0; i < RowCount; ++i) {
		groupsOk &= Rows[i].group < GroupCount;
		ordered &= i == 0 || Rows[i - 1].group <= Rows[i].group;
		if (Rows[i].kind == Kind::Range || Rows[i].kind == Kind::Value) {
			ownOk &= Rows[i].key != nullptr && Rows[i].english != nullptr && std::strstr(Rows[i].english, "%") != nullptr;
		} else {
			ownOk &= Rows[i].key == nullptr;
		}
	}
	Check(groupsOk && ordered && ownOk, "rows sorted by group, own rows carry a key and a %d text");
	const int avoid = IndexOf("passive_dodge,passive_avoid,passive_evade");
	Check(avoid >= 0 && Rows[avoid].kind == Kind::Avoid && Rows[avoid].stat[0] == 338 && Rows[avoid].stat[1] == 339 && Rows[avoid].stat[2] == 340,
	      "Avoid row reads passive_dodge 338 / passive_avoid 339 / passive_evade 340");
	Check(avoid >= 0 && std::strcmp(Groups[Rows[avoid].group].english, "Defense") == 0, "Avoid is under Defense");
	const int fire = IndexOf("firemindam,firemaxdam");
	Check(fire >= 0 && Rows[fire].kind == Kind::Range && Rows[fire].stat[0] == 48 && Rows[fire].stat[1] == 49, "fire adds 48-49");
	const int ias = IndexOf("attackrate"), move = IndexOf("velocitypercent");
	Check(ias >= 0 && Rows[ias].kind == Kind::Value && Rows[ias].stat[0] == 68 && move >= 0 && Rows[move].stat[0] == 67, "skill speeds 68 / 67");
	Check(ias >= 0 && std::strcmp(Groups[Rows[ias].group].english, "Speed") == 0, "skill attack speed is under Speed");
	int always = 0;
	for (const Row& r : Rows) {
		always += r.always ? 1 : 0;
	}
	Check(always == 12, "the twelve always rows (MF, GF, FCR, IAS, FHR, FBR, FRW, leeches, OW, CB, DS)");

	// a naked character: only the always rows and their headings
	const Plan none = Make({});
	Check(Has(none, "item_fastercastrate") && Has(none, "item_magicbonus") && !Has(none, "fireresist"), "always rows shown at 0, others not");
	Check(HasHeading(none, 0) && HasHeading(none, 4) && HasHeading(none, 5) && HasHeading(none, GroupCount - 1), "Offense / Speed / Life & Mana / Other headings");
	Check(!HasHeading(none, 3) && !HasHeading(none, 8), "no Resistances / Summons heading without a row");
	Check(none.items[0].heading == 1 && none.items[0].index == 0, "the list starts with the Offense heading");
	bool headingBeforeRows = true;
	int lastGroup = -1;
	for (size_t k = 0; k < none.n; ++k) {
		const int g = none.items[k].heading ? none.items[k].index : Rows[none.items[k].index].group;
		if (none.items[k].heading) {
			headingBeforeRows &= g > lastGroup;
			lastGroup = g;
		} else {
			headingBeforeRows &= g == lastGroup;
		}
	}
	Check(headingBeforeRows, "each row follows its own group's heading, groups in order");

	// Perfect Being: equal dodge / avoid / evade = one Avoid line; unequal = one line each that is not 0
	const Plan pb = Make({{338, 41}, {339, 41}, {340, 41}});
	Check(Has(pb, "passive_dodge,passive_avoid,passive_evade", 0) && !Has(pb, "passive_dodge,passive_avoid,passive_evade", 1), "equal avoid: one line");
	Check(HasHeading(pb, Rows[avoid].group), "Defense heading with Avoid");
	const Plan mixed = Make({{338, 20}, {340, 35}});
	Check(!Has(mixed, "passive_dodge,passive_avoid,passive_evade", 0) && Has(mixed, "passive_dodge,passive_avoid,passive_evade", 1) &&
	          !Has(mixed, "passive_dodge,passive_avoid,passive_evade", 2) && Has(mixed, "passive_dodge,passive_avoid,passive_evade", 3),
	      "unequal avoid: dodge and evade lines");

	// refresh (#582): Ecstatic Frenzy's stats change the list, so the Update wrapper rebuilds; the same stats do not
	const Plan unbuffed = Make({{67, 100}, {68, 100}});
	Check(!Has(unbuffed, "attackrate") && !Has(unbuffed, "velocitypercent"), "skill speeds at their base of 100 are not shown");
	const Plan frenzy = Make({{67, 135}, {68, 145}, {52, 10}, {53, 20}, {182, -100}});
	Check(!SamePlan(none.items, none.n, frenzy.items, frenzy.n), "a buff that turns rows on changes the list");
	Check(Has(frenzy, "attackrate") && Has(frenzy, "velocitypercent") && Has(frenzy, "magicmindam,magicmaxdam") && Has(frenzy, "armor_override_percent"),
	      "Ecstatic Frenzy: skill speeds, magic adds, defense = 0");
	const Plan frenzy2 = Make({{67, 140}, {68, 160}, {52, 12}, {53, 24}, {182, -100}});
	Check(SamePlan(frenzy.items, frenzy.n, frenzy2.items, frenzy2.n), "a value change alone keeps the list (D2R re-texts it each frame)");
	const Plan oneAdd = Make({{53, 5}});
	Check(Has(oneAdd, "magicmindam,magicmaxdam"), "adds show with only a max");

	// texts
	Check(Fmt("Adds %d-%d Fire Damage", {3, 9}) == "Adds 3-9 Fire Damage", "range text");
	Check(Fmt("%+d%% Attack Speed from Skills", {50}) == "+50% Attack Speed from Skills", "%+d%%");
	Check(Fmt("%+d%% x", {-25}) == "-25% x" && Fmt("%d%%", {0}) == "0%", "negative and zero");
	Check(Fmt("%d %d %d", {7}) == "7 0 0", "a %d past the values prints 0");
	Check(Fmt("%s%x%", {1}) == "%s%x%", "other % sequences are copied, never formatted");
	char small[6];
	Fill("Adds %d-%d", std::initializer_list<int32_t>{100, 200}.begin(), 2, small, sizeof(small));
	Check(std::strlen(small) == 5, "a short buffer is cut and 0-terminated");
	char heading[64];
	HeadingText("Life & Mana", heading, sizeof(heading));
	Check(std::strcmp(heading, "- Life & Mana -") == 0, "heading between dashes, no colour code (the panel prints it as is)");
	auto english = [](const char*, const char* e) { return e; };
	auto pbValues = [](uint16_t id) { return id == 338 ? 20 : id == 340 ? 35 : id == 339 ? 41 : 0; };
	char text[128];
	Check(RowText(Rows[avoid], 0, pbValues, english, text, sizeof(text)) && std::strcmp(text, "20% Chance to Avoid Damage") == 0, "avoid all line");
	Check(RowText(Rows[avoid], 2, pbValues, english, text, sizeof(text)) && std::strcmp(text, "41% Chance to Avoid Missiles") == 0, "avoid missiles line");
	Check(RowText(Rows[avoid], 3, pbValues, english, text, sizeof(text)) && std::strcmp(text, "35% Chance to Evade Attacks while Moving") == 0, "evade line");
	auto speeds = [](uint16_t id) { return id == 68 ? 145 : id == 67 ? 90 : 0; };
	Check(RowText(Rows[ias], 0, speeds, english, text, sizeof(text)) && std::strcmp(text, "+45% Attack Speed from Skills") == 0, "skill attack speed = value - 100");
	Check(RowText(Rows[move], 0, speeds, english, text, sizeof(text)) && std::strcmp(text, "-10% Movement Speed from Skills") == 0, "a slow shows negative");
	auto adds = [](uint16_t id) { return id == 48 ? 5 : id == 49 ? 12 : 0; };
	Check(RowText(Rows[fire], 0, adds, english, text, sizeof(text)) && std::strcmp(text, "Adds 5-12 Fire Damage") == 0, "fire adds line");
	Check(!RowText(Rows[IndexOf("fireresist")], 0, adds, english, text, sizeof(text)), "a plain stat row keeps D2R's text");
	auto localized = [](const char* key, const char* e) { return std::strcmp(key, "AdvStatsAddsFire") == 0 ? "Feuer %d-%d" : e; };
	Check(RowText(Rows[fire], 0, adds, localized, text, sizeof(text)) && std::strcmp(text, "Feuer 5-12") == 0, "the localized pattern is used");

	if (failures == 0) {
		std::printf("advstats tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}

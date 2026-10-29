// Standalone test of the harness command parsing (harness_cmds_logic.h; not part of the plugin DLL).
#include "../src/harness_cmds_logic.h"

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
	using namespace hcmd;

	Tokens t;
	Split("  quest 4  1\tset\r\n", &t);
	Check(t.n == 4 && std::strcmp(t.tok[0], "quest") == 0 && std::strcmp(t.tok[3], "set") == 0, "split on blanks");
	Split("", &t);
	Check(t.n == 0, "empty line");
	Split("a b c d e f g h i j k l m n o p q r s t u v w x y z", &t);
	Check(t.n == MaxTokens, "token limit");

	long long v = 0;
	Check(ParseInt("156", &v) && v == 156, "decimal");
	Check(ParseInt("0x9c", &v) && v == 156, "hex");
	Check(ParseInt("-5", &v) && v == -5, "negative");
	Check(!ParseInt("", &v) && !ParseInt("12a", &v) && !ParseInt("0x", &v) && !ParseInt("-", &v), "bad numbers");

	int stat = 0, layer = 0;
	Check(ParseStatArg("532=3", &stat, &layer, &v) && stat == 532 && layer == 0 && v == 3, "stat=value");
	Check(ParseStatArg("70:2=-4", &stat, &layer, &v) && stat == 70 && layer == 2 && v == -4, "stat:layer=value");
	Check(StatIdByName("lightresist") == -1 && StatIdByName(nullptr) == -1, "no stat names compiled in yet (placeholder)");
	Check(StatIdByName("passive_mastery_gethit_rate") == -1 && !ParseStatArg("passive_mastery_gethit_rate=1", &stat, &layer, &v),
	      "a row whose *ID is not its number has no name");
	Check(!ParseStatArg("nosuchstat=3", &stat, &layer, &v) && StatIdByName("") == -1, "unknown stat name");
	Check(!ParseStatArg("inv", &stat, &layer, &v) && !ParseStatArg("=3", &stat, &layer, &v) && !ParseStatArg("5=x", &stat, &layer, &v),
	      "not a stat argument");

	Check(CodeToDword("tbk") == 0x206b6274U && CodeToDword("box") == 0x20786f62U && CodeToDword("3o[ ") == 0x205b6f33U, "codes");
	char code[5];
	DwordToCode(0x206b6274U, code);
	Check(std::strcmp(code, "tbk") == 0, "code back");
	DwordToCode(CodeToDword("r01"), code);
	Check(std::strcmp(code, "r01") == 0, "rune code");

	Check(LowerEq("Nearest", "nearest") && !LowerEq("near", "nearest"), "case-insensitive compare");

	Check(ParseBodyLoc("rhand") == 4 && ParseBodyLoc("RING") == 6 && ParseBodyLoc("lring") == 7 && ParseBodyLoc("belt") == 8, "body names");
	Check(ParseBodyLoc("3") == 3 && ParseBodyLoc("0x0c") == 12 && ParseBodyLoc("13") == 0 && ParseBodyLoc("0") == 0 &&
	          ParseBodyLoc("tail") == 0 && ParseBodyLoc(nullptr) == 0,
	      "body numbers and rejects");

	uint8_t pkt[256];
	Check(BuildWalkPacket(pkt, 3, 0x1234, 0x0567, 0x1240, 0x0570) == 210 && pkt[0] == 3 && pkt[1] == 0x34 && pkt[2] == 0x12 &&
	          pkt[3] == 0x67 && pkt[4] == 0x05 && pkt[5] == 0x40 && pkt[6] == 0x12 && pkt[7] == 0x70 && pkt[8] == 0x05 && pkt[9] == 0 &&
	          pkt[209] == 0,
	      "walk packet");
	Check(BuildSelectSkillPacket(pkt, 154, true) == 9 && pkt[0] == 0x3c && pkt[1] == 154 && pkt[4] == 0x80 && pkt[5] == 0xff && pkt[8] == 0xff,
	      "select skill packet left");
	Check(BuildSelectSkillPacket(pkt, 300, false) == 9 && pkt[1] == 0x2c && pkt[2] == 0x01 && pkt[4] == 0, "select skill packet right");

	CastTarget ct;
	Split("cast 154", &t);
	Check(ParseCastTarget(t, 2, &ct) && ct.kind == CastTarget::Self, "cast without target");
	Split("cast 154 self", &t);
	Check(ParseCastTarget(t, 2, &ct) && ct.kind == CastTarget::Self, "cast self");
	Split("cast 154 6100 5200", &t);
	Check(ParseCastTarget(t, 2, &ct) && ct.kind == CastTarget::Point && ct.x == 6100 && ct.y == 5200, "cast point");
	Split("cast 154 unit 0x1f", &t);
	Check(ParseCastTarget(t, 2, &ct) && ct.kind == CastTarget::Unit && ct.id == 31, "cast unit");
	Split("cast 154 nearest", &t);
	Check(ParseCastTarget(t, 2, &ct) && ct.kind == CastTarget::Nearest && ct.cls == -1, "cast nearest");
	Split("cast 154 nearest 18", &t);
	Check(ParseCastTarget(t, 2, &ct) && ct.kind == CastTarget::Nearest && ct.cls == 18, "cast nearest class");
	Split("cast 154 5", &t);
	Check(!ParseCastTarget(t, 2, &ct), "one coordinate is not a target");
	Split("cast 154 -5 3", &t);
	Check(!ParseCastTarget(t, 2, &ct), "negative coordinate");
	Split("cast 154 70000 3", &t);
	Check(!ParseCastTarget(t, 2, &ct), "coordinate over 16 bits");
	Split("cast 154 unit", &t);
	Check(!ParseCastTarget(t, 2, &ct), "unit without id");

	SeenUnits seen;
	Check(seen.Add(10, 5) && seen.Add(11, 5) && seen.Add(12, 7) && !seen.Add(10, 5) && seen.n == 3, "seen units are distinct");
	char sum[100];
	Check(seen.Summary(sum, sizeof(sum)) == 2 && std::strcmp(sum, "class 5 x2, class 7 x1") == 0, "seen summary");
	seen.Reset();
	Check(seen.n == 0 && seen.Summary(sum, sizeof(sum)) == 0 && sum[0] == '\0', "seen reset");
	for (uint32_t i = 0; i < SeenUnits::Max + 5; ++i) {
		seen.Add(i, 1);
	}
	Check(seen.n == SeenUnits::Max && seen.overflow == 5, "seen overflow counted");

	UnitRef ref;
	Check(ParseUnitRef("player", &ref) && ref.kind == UnitRef::Player && ParseUnitRef("MERC", &ref) && ref.kind == UnitRef::Merc, "unit refs");
	Check(ParseUnitRef("mon:0x1f", &ref) && ref.kind == UnitRef::Monster && ref.id == 31 && ParseUnitRef("mon:7", &ref) && ref.id == 7, "monster ref");
	Check(!ParseUnitRef("mon:", &ref) && !ParseUnitRef("mon:-3", &ref) && !ParseUnitRef("monster", &ref) && !ParseUnitRef("12", &ref) &&
	          !ParseUnitRef(nullptr, &ref) && ref.kind == UnitRef::None,
	      "bad unit refs");

	RollTally roll;
	roll.Add(0, false);
	roll.Add(3, true);
	roll.Add(3, false);
	roll.Add(99, false);
	roll.Add(-1, false);
	char sock[80];
	roll.Sockets(sock, sizeof(sock));
	Check(roll.n == 5 && roll.ethereal == 1 && roll.sockets[0] == 2 && roll.sockets[3] == 2 && roll.sockets[RollTally::MaxSockets] == 1 &&
	          std::strcmp(sock, "0:2 3:2 8:1") == 0,
	      "roll tally");
	roll.AddQuality(2, false);
	roll.AddQuality(7, true);
	roll.AddQuality(7, false);
	roll.AddQuality(99, true);
	char qual[80];
	roll.Qualities(qual, sizeof(qual));
	Check(roll.automagic == 2 && roll.qualities[2] == 1 && roll.qualities[7] == 2 && roll.qualities[RollTally::MaxQuality] == 1 &&
	          std::strcmp(qual, "2:1 7:2 10:1") == 0,
	      "roll tally: qualities and automagic");

	AvoidTally av;
	const int results[] = {0, 0, 2, 4, 8, 0x10, 0x10, 0x40};
	for (int r : results) {
		av.Add(r);
	}
	Check(av.n == 8 && av.none == 2 && av.avoid == 1 && av.dodge == 1 && av.evade == 1 && av.block == 2 && av.other == 1 && av.Successes() == 6,
	      "avoid tally");
	Check(LifeLost(100 * 256, 40 * 256) == 60 && LifeLost(100 * 256, 130 * 256) == -30 && LifeLost(5, 5) == 0, "life lost");

	SlotTable st;
	Check(ParseSlotTable("cltdo", &st) && st.tableRva == 0x235f7d0 && st.boundRva == 0x235f7c4, "slot table cltdo");
	Check(ParseSlotTable("SRVHIT", &st) && st.tableRva == 0x2391030 && st.boundRva == 0x2391404, "slot table srvhit, any case");
	Check(ParseSlotTable("srvdo", &st) && st.boundRva == 0 && st.fixedBound == 191, "slot table srvdo has a fixed size");
	Check(ParseSlotTable("mcltdo", &st) && st.boundRva == 0x2358a60, "slot table mcltdo");
	Check(!ParseSlotTable("srvprg", &st), "no prg tables (their bounds are not known yet)");
	Check(ParseSlotTable("cltdo", &st) && WatchableTable(st) && ParseSlotTable("srvhit", &st) && WatchableTable(st), "watch: cltdo and srvhit");
	Check(ParseSlotTable("mcltdo", &st) && !WatchableTable(st) && ParseSlotTable("srvdo", &st) && !WatchableTable(st),
	      "watch: no missile client do (float argument), no srvdo");

	// bug #5: the warp inside an act, the NPC travel across acts
	Check(!UseNpcTravel(0, 0, false, false) && UseNpcTravel(0, 3, false, false), "level: warp in the act, NPC travel across");
	Check(UseNpcTravel(0, 0, false, true) && !UseNpcTravel(0, 3, true, false), "level: forced move");

	// bug #8: client hit 0 (like server hit 0) is "no function", client do 0 is a real (stubbed) call
	Check(!CallsEmptySlot(MissileTable::CltHit, 0, 81, true) && !CallsEmptySlot(MissileTable::SrvHit, 0, 71, true), "hit index 0 is no call");
	Check(CallsEmptySlot(MissileTable::CltDo, 0, 91, true), "client do index 0 is called");
	Check(CallsEmptySlot(MissileTable::CltHit, 80, 81, true) && !CallsEmptySlot(MissileTable::CltHit, 81, 81, true) &&
	          !CallsEmptySlot(MissileTable::CltHit, -1, 81, true) && !CallsEmptySlot(MissileTable::SrvHit, 5, 71, false),
	      "empty slot below the bound only");

	// `item` / `identify` (lane monitems)
	Check(ParseQualityWord("Unique") == 7 && ParseQualityWord("set") == 5 && ParseQualityWord("magic") == 4 &&
	          ParseQualityWord("rare") == 6 && ParseQualityWord("normal") == 2 && ParseQualityWord("xyz") == 0,
	      "quality words");
	ItemSpec is;
	Split("item rin", &t);
	Check(ParseItemSpec(t, 2, &is) && is.quality == 2 && is.row == -1 && is.ilvl == 0 && is.page == 0 && is.nstats == 0, "item: defaults");
	Split("item amu unique 12", &t);
	Check(ParseItemSpec(t, 2, &is) && is.quality == 7 && is.row == 12 && is.ilvl == 255, "item: unique row, item level 255");
	Split("item amu unique", &t);
	Check(ParseItemSpec(t, 2, &is) && is.quality == 7 && is.row == -1 && is.ilvl == 0, "item: unique without a row");
	Split("item lrg set 3 ilvl=40 cube", &t);
	Check(ParseItemSpec(t, 2, &is) && is.quality == 5 && is.row == 3 && is.ilvl == 40 && is.page == 3, "item: set row, own item level");
	Split("item rin magic ground 532=3", &t);
	Check(ParseItemSpec(t, 2, &is) && is.quality == 4 && is.row == -1 && is.page == -1 && is.nstats == 1 && is.stats[0][0] == 532 &&
	          is.values[0] == 3,
	      "item: magic on the ground with a stat");
	Split("item rin magic 5", &t);
	Check(!ParseItemSpec(t, 2, &is) && is.bad == 3, "item: a row only after set / unique");
	Split("item amu uniq=7", &t);
	Check(ParseItemSpec(t, 2, &is) && is.quality == 7 && is.row == 7, "item: uniq=");
	// `equip` (lane states): a body location word
	Split("equip jav rhand", &t);
	Check(ParseItemSpec(t, 2, &is) && is.bodyLoc == 4 && is.quality == 2 && is.page == 0, "equip: rhand");
	Split("equip rin magic lring 0=20", &t);
	Check(ParseItemSpec(t, 2, &is) && is.bodyLoc == 7 && is.quality == 4 && is.nstats == 1, "equip: magic ring on lring with a stat");
	Split("item rin", &t);
	Check(ParseItemSpec(t, 2, &is) && is.bodyLoc == 0, "item: no body location");
	Split("equip jav 4", &t);
	Check(!ParseItemSpec(t, 2, &is) && is.bad == 2, "equip: a bare number is not a body location");
	// bug #391: the update packet's command flag, equip (8) on a body location, put in a page (2) otherwise
	Check(PlaceCmdKind(4) == 8 && PlaceCmdKind(7) == 8 && PlaceCmdKind(0) == 2 && PlaceCmdKind(-1) == 2, "equip: update kind per body location");
	Split("item amu set=0", &t);
	Check(ParseItemSpec(t, 2, &is) && is.quality == 5 && is.row == 0, "item: set= row 0");
	Split("item amu uniq=7 q=4", &t);
	Check(!ParseItemSpec(t, 2, &is), "item: a row and another quality");
	Split("item amu q=9", &t);
	Check(!ParseItemSpec(t, 2, &is) && is.bad == 2, "item: quality out of range");
	Split("item amu unique 70000", &t);
	Check(!ParseItemSpec(t, 2, &is), "item: row out of range");
	Split("item amu ilvl=0", &t);
	Check(!ParseItemSpec(t, 2, &is), "item: item level 0");
	Split("item amu unique 3 unid", &t);
	Check(ParseItemSpec(t, 2, &is) && is.unid && is.row == 3, "item: unid");
	Split("item rin", &t);
	Check(ParseItemSpec(t, 2, &is) && !is.unid, "item: identified by default");
	Split("item lrg normal 194=3", &t);
	Check(ParseItemSpec(t, 2, &is) && is.nstats == 1 && is.stats[0][0] == StatSockets && is.values[0] == 3, "item: sockets as stat 194");
	Check(GenIndexFor(7, 12) == 13 && GenIndexFor(5, 0) == 1 && GenIndexFor(4, 3) == 0 && GenIndexFor(7, -1) == 0, "generator index");
	Check(UniqueSpawnedOffset(0) == 0x3638 && UniqueSpawnedOffset(33) == 0x363c && UniqueSpawnedMask(33) == 2U &&
	          UniqueSpawnedMask(31) == 0x80000000U,
	      "unique spawned bits");
	IdentifyTarget it;
	Split("identify", &t);
	Check(ParseIdentify(t, &it) && it.all, "identify: all by default");
	Split("identify all", &t);
	Check(ParseIdentify(t, &it) && it.all, "identify all");
	Split("identify 0x2a", &t);
	Check(ParseIdentify(t, &it) && !it.all && it.id == 42, "identify one id");
	Split("identify foo", &t);
	Check(!ParseIdentify(t, &it), "identify: bad id");
	Split("identify 1 2", &t);
	Check(!ParseIdentify(t, &it), "identify: one id only");

	// mercenaries: 1.13c's revive price and the hireling panel's packet
	Check(RevivePrice113(1) == 0 && RevivePrice113(2) == 30 && RevivePrice113(3) == 60 && RevivePrice113(10) == 750,
	      "revive price: level squared, halved (integer), times 15");
	Check(RevivePrice113(81) == 49200 && RevivePrice113(82) == 50000 && RevivePrice113(150) == 50000, "revive price: at most 50,000");
	uint8_t mp[17] = {};
	MercItemPacket(0x11223344U, 7U, 0xffffffffU, 4U, mp);
	Check(mp[0] == 0x51 && mp[1] == 0x44 && mp[4] == 0x11 && mp[5] == 7 && mp[9] == 0xff && mp[12] == 0xff && mp[13] == 4 && mp[16] == 0,
	      "merc item packet 0x51: cursor item, merc, merc item, body location (little endian)");
	uint8_t bytes[8] = {};
	Split("pkt 16 0a ff", &t);
	Check(ParseHexBytes(t, 1, bytes, sizeof(bytes)) == 3 && bytes[0] == 0x16 && bytes[1] == 0x0a && bytes[2] == 0xff, "pkt: hex bytes");
	Split("pkt 1 F", &t);
	Check(ParseHexBytes(t, 1, bytes, sizeof(bytes)) == 2 && bytes[0] == 1 && bytes[1] == 15, "pkt: one digit, upper case");
	Split("pkt 16 0x1", &t);
	Check(ParseHexBytes(t, 1, bytes, sizeof(bytes)) == 0, "pkt: 0x prefix is not a byte");
	Split("pkt 16 zz", &t);
	Check(ParseHexBytes(t, 1, bytes, sizeof(bytes)) == 0, "pkt: not hex");
	Split("pkt 1 2 3 4 5 6 7 8 9", &t);
	Check(ParseHexBytes(t, 1, bytes, sizeof(bytes)) == 0, "pkt: longer than the buffer");
	Split("pkt", &t);
	Check(ParseHexBytes(t, 1, bytes, sizeof(bytes)) == 0, "pkt: no bytes");
	uint8_t pick[PickupPacketSize] = {};
	Check(BuildPickupPacket(pick, 0x01020304U, 0x1234, 7, true) == 17 && pick[0] == 0x16 && pick[1] == 4 && pick[4] == 1 && pick[5] == 0x34 &&
	          pick[6] == 0x12 && pick[9] == 7 && pick[13] == 1 && pick[16] == 0,
	      "pickup packet: id, x, y, to-inventory flag");
	BuildPickupPacket(pick, 7U, 1, 2, false);
	Check(pick[1] == 7 && pick[13] == 0, "pickup packet: to the cursor");

	IstatSpec is2;
	Split("istat 12 194", &t);
	Check(ParseIstat(t, &is2) && is2.id == 12 && is2.stat == 194 && is2.layer == 0 && !is2.scan, "istat: id and stat");
	Split("istat 12 97 0x1c1", &t);
	Check(ParseIstat(t, &is2) && is2.layer == 0x1c1, "istat: layer");
	Split("istat 12 204 scan", &t);
	Check(ParseIstat(t, &is2) && is2.scan, "istat: scan");
	Split("istat 12", &t);
	Check(!ParseIstat(t, &is2), "istat: needs a stat");
	Split("istat 12 70000", &t);
	Check(!ParseIstat(t, &is2), "istat: stat out of range");
	Split("istat 12 1 2 3", &t);
	Check(!ParseIstat(t, &is2), "istat: too many words");
	QuestArgs qa;
	Split("quest 40 dump", &t);
	Check(ParseQuestArgs(t, &qa) && qa.op == QuestArgs::Dump && qa.quest == 40, "quest dump");
	Split("quest 7 0", &t);
	Check(ParseQuestArgs(t, &qa) && qa.op == QuestArgs::Get && qa.bit == 0, "quest get by default");
	Split("quest 0x1a 15 set", &t);
	Check(ParseQuestArgs(t, &qa) && qa.op == QuestArgs::Set && qa.quest == 26 && qa.bit == 15, "quest set");
	Split("quest 3 2 CLEAR", &t);
	Check(ParseQuestArgs(t, &qa) && qa.op == QuestArgs::Clear, "quest clear");
	Split("quest 3 16 set", &t);
	Check(!ParseQuestArgs(t, &qa), "quest: bit 16");
	Split("quest 200 1", &t);
	Check(!ParseQuestArgs(t, &qa), "quest: id out of range");
	Split("quest 3 1 flip", &t);
	Check(!ParseQuestArgs(t, &qa), "quest: bad op");
	Split("quest 3", &t);
	Check(!ParseQuestArgs(t, &qa), "quest: no bit");
	Split("quest 3 dump x", &t);
	Check(!ParseQuestArgs(t, &qa), "quest: dump takes nothing more");

	Check(ParseMenuLine("list", 4) == -1 && ParseMenuLine("Cancel", 4) == -2, "menu list / cancel");
	Check(ParseMenuLine("0", 4) == 0 && ParseMenuLine("2", 4) == 2 && ParseMenuLine("3", 4) == -3, "menu: lines before Cancel only");
	Check(ParseMenuLine("5", 9) == -3 && ParseMenuLine("4", 9) == 4, "menu: at most 5 lines");
	Check(ParseMenuLine("-1", 4) == -3 && ParseMenuLine("x", 4) == -3 && ParseMenuLine(nullptr, 4) == -3, "menu: bad words");

	long long cls = 0;
	Check(ParseNpcTarget("nearest", &cls) && cls == -1, "npc target nearest");
	Check(ParseNpcTarget("155", &cls) && cls == 155, "npc target class");
	Check(!ParseNpcTarget("x", &cls) && !ParseNpcTarget("-3", &cls) && !ParseNpcTarget(nullptr, &cls), "npc target rejects");
	Check(sizeof(InteractOffsets) / sizeof(InteractOffsets[0]) == 10 && InteractOffsets[0][0] == 2 && InteractReach == 5.0, "interact spots");

	Split("xp 5000", &t);
	Check(ParseXp(t, &v) && v == 5000, "xp amount");
	Split("xp 0", &t);
	Check(!ParseXp(t, &v), "xp: zero");
	Split("xp 0x80000000", &t);
	Check(!ParseXp(t, &v), "xp: over 32 bits");
	Split("xp", &t);
	Check(!ParseXp(t, &v), "xp: no amount");

	Check(PresetToState(100, 12) == 512 && PresetToState(0, 0) == 0, "preset position in state units");
	Check(PlaceOffsets[0][0] == 0 && PlaceOffsets[0][1] == 0 && sizeof(PlaceOffsets) / sizeof(PlaceOffsets[0]) == 13, "place: the spot itself first");
	Check(DrlgRoomLevel == 0x90 && LevelId == 0x1f8 && DrlgRoomPresets == 0x98 && PresetY == 0x24, "DRLG offsets of 0x3dad90 / 0x360fc0");

	std::printf(failures == 0 ? "harness: all tests passed\n" : "harness: %d failures\n", failures);
	return failures == 0 ? 0 : 1;
}

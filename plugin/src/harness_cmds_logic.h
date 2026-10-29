// Pure parsing for the test harness gameplay commands (harness_cmds.cpp; unit test plugin/tests/harness_cmds_test.cpp).
// A command line is "h <verb> <args...>": whitespace separated tokens, numbers decimal or 0x hex.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

#include "mxl2012_stat_names.h"

namespace hcmd {

constexpr int MaxTokens = 24;  // a 17-byte server packet through `pkt` is 18 tokens
constexpr size_t MaxLine = 512;

struct Tokens {
	char text[MaxLine] = {};
	const char* tok[MaxTokens] = {};
	int n = 0;
};

// Splits `line` on spaces / tabs (at most MaxTokens, the rest of an over-long line is dropped).
inline void Split(const char* line, Tokens* t) noexcept {
	t->n = 0;
	size_t len = 0;
	while (line != nullptr && line[len] != '\0' && len < MaxLine - 1) {
		t->text[len] = line[len];
		++len;
	}
	t->text[len] = '\0';
	char* p = t->text;
	while (*p != '\0' && t->n < MaxTokens) {
		while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n') {
			*p++ = '\0';
		}
		if (*p == '\0') {
			break;
		}
		t->tok[t->n++] = p;
		while (*p != '\0' && *p != ' ' && *p != '\t' && *p != '\r' && *p != '\n') {
			++p;
		}
	}
}

inline auto LowerEq(const char* a, const char* b) noexcept -> bool {
	if (a == nullptr || b == nullptr) {
		return false;
	}
	for (; *a != '\0' && *b != '\0'; ++a, ++b) {
		const char x = (*a >= 'A' && *a <= 'Z') ? static_cast<char>(*a + 32) : *a;
		const char y = (*b >= 'A' && *b <= 'Z') ? static_cast<char>(*b + 32) : *b;
		if (x != y) {
			return false;
		}
	}
	return *a == '\0' && *b == '\0';
}

// Decimal or 0x hex, optional leading '-'. The whole string must be a number.
inline auto ParseInt(const char* s, long long* out) noexcept -> bool {
	if (s == nullptr || *s == '\0') {
		return false;
	}
	bool neg = false;
	if (*s == '-') {
		neg = true;
		++s;
	}
	unsigned base = 10;
	if (s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) {
		base = 16;
		s += 2;
	}
	if (*s == '\0') {
		return false;
	}
	unsigned long long v = 0;
	for (; *s != '\0'; ++s) {
		unsigned d = 0;
		if (*s >= '0' && *s <= '9') {
			d = static_cast<unsigned>(*s - '0');
		} else if (base == 16 && *s >= 'a' && *s <= 'f') {
			d = static_cast<unsigned>(*s - 'a' + 10);
		} else if (base == 16 && *s >= 'A' && *s <= 'F') {
			d = static_cast<unsigned>(*s - 'A' + 10);
		} else {
			return false;
		}
		v = v * base + d;
		if (v > 0x7fffffffffffffffULL) {
			return false;
		}
	}
	*out = neg ? -static_cast<long long>(v) : static_cast<long long>(v);
	return true;
}

// Stat id of a name in the build's itemstatcost.txt (mxl2012_stat_names.h), case-insensitive, or -1 when there is no such name (a row whose `*ID` is not its number has none).
inline auto StatIdByName(const char* name) noexcept -> int {
	if (name == nullptr || *name == '\0') {
		return -1;
	}
	for (int i = 0; i < mxl2012_stat_names::Count; ++i) {
		if (mxl2012_stat_names::Names[i] != nullptr && LowerEq(name, mxl2012_stat_names::Names[i])) {
			return i;
		}
	}
	return -1;
}

// "532=3", "532:1=3" or "fireresist=155" (stat id or itemstatcost name, optional layer, value). Anything else is not a stat.
inline auto ParseStatArg(const char* s, int* stat, int* layer, long long* value) noexcept -> bool {
	if (s == nullptr) {
		return false;
	}
	const char* eq = std::strchr(s, '=');
	if (eq == nullptr || eq == s) {
		return false;
	}
	char left[24] = {};
	const size_t n = static_cast<size_t>(eq - s);
	if (n >= sizeof(left)) {
		return false;
	}
	std::memcpy(left, s, n);
	char* colon = std::strchr(left, ':');
	long long st = 0, ly = 0, v = 0;
	if (colon != nullptr) {
		*colon = '\0';
		if (!ParseInt(colon + 1, &ly)) {
			return false;
		}
	}
	if (!ParseInt(left, &st)) {
		st = StatIdByName(left);
	}
	if (st < 0 || !ParseInt(eq + 1, &v) || st > 0xffff || ly < 0 || ly > 0xffff) {
		return false;
	}
	*stat = static_cast<int>(st);
	*layer = static_cast<int>(ly);
	*value = v;
	return true;
}

// Item code of up to 4 characters ("tbk", "box") as the little-endian dword the game uses, space padded.
inline auto CodeToDword(const char* code) noexcept -> uint32_t {
	uint32_t v = 0;
	for (int i = 0; i < 4; ++i) {
		const unsigned char c = (code != nullptr && static_cast<size_t>(i) < std::strlen(code)) ? static_cast<unsigned char>(code[i]) : ' ';
		v |= static_cast<uint32_t>(c) << (8 * i);
	}
	return v;
}

inline void DwordToCode(uint32_t v, char out[5]) noexcept {
	for (int i = 0; i < 4; ++i) {
		const char c = static_cast<char>((v >> (8 * i)) & 0xff);
		out[i] = (c >= 32 && c < 127) ? c : '?';
	}
	out[4] = '\0';
	for (int i = 3; i > 0 && out[i] == ' '; --i) {
		out[i] = '\0';
	}
}

// --- body locations (bodylocs.txt order) ----------------------------------------------------------------------------
// "head", "amulet", "body", "rhand", "lhand", "rring", "lring", "belt", "boots", "gloves", "altr", "altl" or a number
// 1-12. Returns 0 for anything else.
inline auto ParseBodyLoc(const char* s) noexcept -> int {
	struct Name {
		const char* name;
		int loc;
	};
	static const Name names[] = {
	    {"head", 1},  {"helm", 1},   {"neck", 2},  {"amulet", 2}, {"torso", 3}, {"body", 3},  {"armor", 3}, {"rhand", 4},
	    {"rarm", 4},  {"weapon", 4}, {"lhand", 5}, {"larm", 5},   {"shield", 5}, {"rring", 6}, {"ring", 6},  {"lring", 7},
	    {"belt", 8},  {"feet", 9},   {"boots", 9}, {"gloves", 10}, {"altr", 11}, {"altl", 12},
	};
	long long v = 0;
	if (ParseInt(s, &v)) {
		return (v >= 1 && v <= 12) ? static_cast<int>(v) : 0;
	}
	for (const Name& n : names) {
		if (LowerEq(s, n.name)) {
			return n.loc;
		}
	}
	return 0;
}

// --- client packets built for the server handlers --------------------------------------------------------------------
// D2R's walk / run packets (ids 1 and 3, handlers 0x4ac050 / 0x4ace40) are 210 bytes: u8 id, u16 x, u16 y (where the
// client thinks it stands), u16 x, u16 y (the destination), u8 path length (0 = the server finds the path), then up to 50
// four-byte path nodes. Returns the packet size.
constexpr size_t WalkPacketSize = 210;
inline auto BuildWalkPacket(uint8_t* out, uint8_t id, int curX, int curY, int destX, int destY) noexcept -> size_t {
	std::memset(out, 0, WalkPacketSize);
	out[0] = id;
	const uint16_t v[4] = {static_cast<uint16_t>(curX), static_cast<uint16_t>(curY), static_cast<uint16_t>(destX),
	                       static_cast<uint16_t>(destY)};
	std::memcpy(out + 1, &v[0], 2);
	std::memcpy(out + 3, &v[1], 2);
	std::memcpy(out + 5, &v[2], 2);
	std::memcpy(out + 7, &v[3], 2);
	return WalkPacketSize;
}

// Packet 0x3c (select a skill, handler 0x4b4250): u8 id, u32 skill id (bit 31 = left button), u32 item id (-1 = none).
inline auto BuildSelectSkillPacket(uint8_t* out, int skillId, bool left) noexcept -> size_t {
	const uint32_t a = static_cast<uint32_t>(skillId) | (left ? 0x80000000U : 0U);
	const uint32_t b = 0xffffffffU;
	out[0] = 0x3c;
	std::memcpy(out + 1, &a, 4);
	std::memcpy(out + 5, &b, 4);
	return 9;
}

// --- function tables of `slot <table> [index]` (d2r.h; image 0x6ab3782c) --------------------------------------------------
struct SlotTable {
	const char* name = "";
	uint64_t tableRva = 0;
	uint64_t boundRva = 0;  // int32 count the dispatcher accepts; 0 = fixed size below
	int32_t fixedBound = 0;
};
inline auto ParseSlotTable(const char* s, SlotTable* out) noexcept -> bool {
	static constexpr struct {
		const char* name;
		uint64_t table, bound;
		int32_t fixed;
	} Tables[] = {
		{"cltdo", 0x235f7d0, 0x235f7c4, 0},    // skill client do (cltdofunc)
		{"srvdo", 0x238ea00, 0, 191},          // skill server do (srvdofunc)
		{"mcltdo", 0x2358430, 0x2358a60, 0},   // missile client do (pCltDoFunc)
		{"mclthit", 0x2358710, 0x2358a64, 0},  // missile client hit (pCltHitFunc)
		{"srvhit", 0x2391030, 0x2391404, 0},   // missile server hit (pSrvHitFunc)
	};
	for (const auto& t : Tables) {
		if (LowerEq(s, t.name)) {
			*out = SlotTable{t.name, t.table, t.bound, t.fixed};
			return true;
		}
	}
	return false;
}

// --- `watch cltdo|srvhit <index>`: which tables a slot watch may wrap -----------------------------------------------------
// Both dispatchers pass three register arguments and read a return value (skill client do: unit, skill, level -> non-zero when
// it made something; missile server hit: game, missile, target), so one counting thunk fits both. The other tables of
// ParseSlotTable take other arguments (missile client do: a float) and are refused.
inline auto WatchableTable(const SlotTable& t) noexcept -> bool {
	return LowerEq(t.name, "cltdo") || LowerEq(t.name, "srvhit");
}

// --- `missilescan`: does a missiles.txt index land on an empty slot the game would call? ----------------------------------
// The client missile tick calls the client do entry of every index below the bound, 0 included (bug #24b: slot 0 is empty in
// D2R, hence the stubs). Client hit and server hit 0 mean "no function": their dispatchers skip it (server hit 0x464ac0 tests
// 0 < index; client hit: row 0, the arrow, has pCltHitFunc 0 and hits without a crash), so 0 is no empty-slot call there.
enum class MissileTable { CltDo, CltHit, SrvHit };
constexpr auto CallsEmptySlot(MissileTable table, int index, int bound, bool slotEmpty) noexcept -> bool {
	const int first = table == MissileTable::CltDo ? 0 : 1;
	return slotEmpty && index >= first && index < bound;
}

// --- `level`: which move (bug #5). The NPC travel only opens a portal inside one act; the warp is for the same act. -------
constexpr auto UseNpcTravel(int actFrom, int actTo, bool forceWarp, bool forceNpc) noexcept -> bool {
	return forceNpc || (!forceWarp && actFrom != actTo);
}

// --- cast target: "[x y] | unit <id> | nearest [class] | self" starting at token `from` -----------------------------------
struct CastTarget {
	enum Kind { Self, Point, Unit, Nearest } kind = Self;
	long long x = 0, y = 0, id = 0, cls = -1;
};
inline auto ParseCastTarget(const Tokens& t, int from, CastTarget* out) noexcept -> bool {
	*out = CastTarget();
	if (t.n <= from) {
		return true;
	}
	if (LowerEq(t.tok[from], "self")) {
		return t.n == from + 1;
	}
	if (LowerEq(t.tok[from], "unit")) {
		out->kind = CastTarget::Unit;
		return t.n == from + 2 && ParseInt(t.tok[from + 1], &out->id) && out->id >= 0;
	}
	if (LowerEq(t.tok[from], "nearest")) {
		out->kind = CastTarget::Nearest;
		if (t.n == from + 2) {
			return ParseInt(t.tok[from + 1], &out->cls) && out->cls >= 0;
		}
		return t.n == from + 1;
	}
	out->kind = CastTarget::Point;
	return t.n == from + 2 && ParseInt(t.tok[from], &out->x) && ParseInt(t.tok[from + 1], &out->y) && out->x >= 0 && out->y >= 0 &&
	       out->x < 0x10000 && out->y < 0x10000;
}

// --- units seen since a reset (missiles are short lived: a poll of the live list misses most of them) -----------------
struct SeenUnits {
	static constexpr int Max = 1024;
	uint32_t id[Max] = {};
	int32_t cls[Max] = {};
	int n = 0;
	int overflow = 0;
	void Reset() noexcept {
		n = 0;
		overflow = 0;
	}
	// true when the unit was new
	auto Add(uint32_t unitId, int32_t unitClass) noexcept -> bool {
		for (int i = 0; i < n; ++i) {
			if (id[i] == unitId && cls[i] == unitClass) {
				return false;
			}
		}
		if (n >= Max) {
			++overflow;
			return false;
		}
		id[n] = unitId;
		cls[n] = unitClass;
		++n;
		return true;
	}
	// "class 12 x3, class 80 x1" (classes in order of appearance), returns the number of classes
	auto Summary(char* out, size_t size) const noexcept -> int {
		int classes[64];
		int counts[64];
		int k = 0;
		for (int i = 0; i < n; ++i) {
			int j = 0;
			while (j < k && classes[j] != cls[i]) {
				++j;
			}
			if (j == k && k < 64) {
				classes[k] = cls[i];
				counts[k] = 0;
				++k;
			}
			if (j < k) {
				++counts[j];
			}
		}
		size_t len = 0;
		if (size > 0) {
			out[0] = '\0';
		}
		for (int j = 0; j < k && len + 24 < size; ++j) {
			len += static_cast<size_t>(std::snprintf(out + len, size - len, "%sclass %d x%d", j > 0 ? ", " : "", classes[j], counts[j]));
		}
		return k;
	}
};

// --- unit references of the verify verbs: "player", "merc" (the player's mercenary), "mon:<unit id>" ------------------------
struct UnitRef {
	enum Kind { None, Player, Merc, Monster } kind = None;
	long long id = 0;
};
inline auto ParseUnitRef(const char* s, UnitRef* out) noexcept -> bool {
	*out = UnitRef();
	if (s == nullptr) {
		return false;
	}
	if (LowerEq(s, "player")) {
		out->kind = UnitRef::Player;
		return true;
	}
	if (LowerEq(s, "merc")) {
		out->kind = UnitRef::Merc;
		return true;
	}
	if ((s[0] == 'm' || s[0] == 'M') && (s[1] == 'o' || s[1] == 'O') && (s[2] == 'n' || s[2] == 'N') && s[3] == ':') {
		out->kind = UnitRef::Monster;
		return ParseInt(s + 4, &out->id) && out->id >= 0;
	}
	return false;
}

// --- tallies of the verify verbs ---------------------------------------------------------------------------------------
// `itemroll`: items made in a loop and freed again; sockets 0..7+ and the ethereal flag counted.
struct RollTally {
	static constexpr int MaxSockets = 8;
	int n = 0;
	int sockets[MaxSockets + 1] = {};  // the last slot holds MaxSockets and more
	int ethereal = 0;
	static constexpr int MaxQuality = 10;
	int qualities[MaxQuality + 1] = {};  // the quality the generator really gave (the last slot holds MaxQuality and more)
	int automagic = 0;                   // items with an automagic affix id
	void Add(int socketCount, bool isEthereal) noexcept {
		++n;
		++sockets[socketCount < 0 ? 0 : (socketCount > MaxSockets ? MaxSockets : socketCount)];
		ethereal += isEthereal ? 1 : 0;
	}
	void AddQuality(int quality, bool hasAutomagic) noexcept {
		++qualities[quality < 0 ? 0 : (quality > MaxQuality ? MaxQuality : quality)];
		automagic += hasAutomagic ? 1 : 0;
	}
	// "2:1500 5:490" (only the qualities seen)
	auto Qualities(char* out, size_t size) const noexcept -> void {
		size_t len = 0;
		if (size > 0) {
			out[0] = '\0';
		}
		for (int i = 0; i <= MaxQuality && len + 12 < size; ++i) {
			if (qualities[i] != 0) {
				len += static_cast<size_t>(std::snprintf(out + len, size - len, "%s%d:%d", len > 0 ? " " : "", i, qualities[i]));
			}
		}
	}
	// "0:12 1:14 2:15 ..." (only the sockets seen)
	auto Sockets(char* out, size_t size) const noexcept -> void {
		size_t len = 0;
		if (size > 0) {
			out[0] = '\0';
		}
		for (int i = 0; i <= MaxSockets && len + 12 < size; ++i) {
			if (sockets[i] != 0) {
				len += static_cast<size_t>(std::snprintf(out + len, size - len, "%s%d:%d", len > 0 ? " " : "", i, sockets[i]));
			}
		}
	}
};

// `avoid`: results of D2R's avoid check 0x44ef70 (0 none, 2 avoid, 4 dodge, 8 evade, 0x10 block).
struct AvoidTally {
	int n = 0, none = 0, avoid = 0, dodge = 0, evade = 0, block = 0, other = 0;
	void Add(int result) noexcept {
		++n;
		switch (result) {
			case 0: ++none; break;
			case 2: ++avoid; break;
			case 4: ++dodge; break;
			case 8: ++evade; break;
			case 0x10: ++block; break;
			default: ++other; break;
		}
	}
	auto Successes() const noexcept -> int { return n - none; }
};

// The life a target lost to a hit, in whole life points (the stat is in 1/256), negative when the hit healed it.
constexpr auto LifeLost(int lifeBefore, int lifeAfter) noexcept -> int {
	return (lifeBefore - lifeAfter) / 256;
}

// --- `item` / `identify` (lane monitems) -------------------------------------------------------------------------------
// Item qualities of the generator (D2: 1 low, 2 normal, 3 superior, 4 magic, 5 set, 6 rare, 7 unique, 8 crafted); 0 = not a
// quality word.
inline auto ParseQualityWord(const char* s) noexcept -> int {
	static constexpr struct {
		const char* name;
		int quality;
	} Words[] = {{"low", 1},  {"normal", 2}, {"superior", 3}, {"magic", 4}, {"set", 5},
	             {"rare", 6}, {"unique", 7}, {"crafted", 8},  {"craft", 8}};
	for (const auto& w : Words) {
		if (LowerEq(s, w.name)) {
			return w.quality;
		}
	}
	return 0;
}

// `item <code> [<quality word> [row]] [q=n] [uniq=row] [set=row] [ilvl=n] [inv|cube|ground] [unid] [stat=value ...]`, the tokens
// after the code. A row (set or unique only) is the 0-based record of setitems.txt / uniqueitems.txt (= line number - 2 of
// the built table); it asks the generator for that row (block +0x50 = row + 1) and sets the item level to 255 unless
// ilvl= is given, so the row's `lvl` always passes.
struct ItemSpec {
	static constexpr int MaxStats = 8;
	int stats[MaxStats][3] = {};
	long long values[MaxStats] = {};
	int nstats = 0;
	int quality = 2;
	int ilvl = 0;  // 0 = the game's default for the player (255 with a row)
	int page = 0;  // 0 backpack, 3 cube, -1 ground
	int row = -1;  // set / unique row asked for, -1 none
	int bad = -1;  // index of the token that could not be read
	int bodyLoc = 0;  // `equip`: body location 1-12 named by a word (head, rhand, lring, ...), 0 none
	bool unid = false;
};
inline auto ParseItemSpec(const Tokens& t, int from, ItemSpec* spec) noexcept -> bool {
	*spec = ItemSpec();
	bool ilvlGiven = false;
	for (int i = from; i < t.n; ++i) {
		const char* a = t.tok[i];
		long long v = 0;
		int q = 0;
		if (LowerEq(a, "inv")) {
			spec->page = 0;
		} else if (LowerEq(a, "cube")) {
			spec->page = 3;
		} else if (LowerEq(a, "ground")) {
			spec->page = -1;
		} else if (LowerEq(a, "unid")) {
			spec->unid = true;
		} else if ((q = ParseQualityWord(a)) != 0) {
			spec->quality = q;
			if ((q == 5 || q == 7) && i + 1 < t.n && ParseInt(t.tok[i + 1], &v)) {
				if (v < 0 || v > 0xffff) {
					spec->bad = i + 1;
					return false;
				}
				spec->row = static_cast<int>(v);
				++i;
			}
		} else if (std::strncmp(a, "q=", 2) == 0 && ParseInt(a + 2, &v) && v >= 1 && v <= 8) {
			spec->quality = static_cast<int>(v);
		} else if ((std::strncmp(a, "uniq=", 5) == 0 || std::strncmp(a, "set=", 4) == 0) &&
		           ParseInt(a + (a[0] == 'u' ? 5 : 4), &v) && v >= 0 && v <= 0xffff) {
			spec->quality = a[0] == 'u' ? 7 : 5;
			spec->row = static_cast<int>(v);
		} else if (std::strncmp(a, "ilvl=", 5) == 0 && ParseInt(a + 5, &v) && v >= 1 && v <= 255) {
			spec->ilvl = static_cast<int>(v);
			ilvlGiven = true;
		} else if (spec->nstats < ItemSpec::MaxStats &&
		           ParseStatArg(a, &spec->stats[spec->nstats][0], &spec->stats[spec->nstats][1], &spec->values[spec->nstats])) {
			++spec->nstats;
		} else if (long long n = 0; std::strchr(a, '=') == nullptr && !ParseInt(a, &n) && ParseBodyLoc(a) != 0) {
			spec->bodyLoc = ParseBodyLoc(a);  // words only: a bare number stays a row / an error
		} else {
			spec->bad = i;
			return false;
		}
	}
	if (spec->row >= 0 && spec->quality != 5 && spec->quality != 7) {
		spec->bad = from;  // a row and a later q= of another quality
		return false;
	}
	if (spec->row >= 0 && !ilvlGiven) {
		spec->ilvl = 255;
	}
	return true;
}

// The generator block's "index asked for" (+0x50): row + 1 for a set / unique row, 0 = the generator picks.
constexpr auto GenIndexFor(int quality, int row) noexcept -> int32_t {
	return (row >= 0 && (quality == 5 || quality == 7)) ? row + 1 : 0;
}

// The game's "this unique already dropped in this game" bits (game + 0x3638, one bit per unique index below 0x1000; the
// generator 0x443910 refuses a unique whose bit is set).
constexpr int UniqueSpawnedBase = 0x3638;
constexpr int UniqueSpawnedLimit = 0x1000;
constexpr auto UniqueSpawnedOffset(int32_t index) noexcept -> int { return UniqueSpawnedBase + (index >> 5) * 4; }
constexpr auto UniqueSpawnedMask(int32_t index) noexcept -> uint32_t { return 1U << (index & 31); }

// `identify [all|<item unit id>]`: all = every item of the player (backpack, cube, stash, worn).
struct IdentifyTarget {
	bool all = true;
	long long id = 0;
};
inline auto ParseIdentify(const Tokens& t, IdentifyTarget* out) noexcept -> bool {
	*out = IdentifyTarget();
	if (t.n == 1 || (t.n == 2 && LowerEq(t.tok[1], "all"))) {
		return true;
	}
	out->all = false;
	return t.n == 2 && ParseInt(t.tok[1], &out->id) && out->id >= 0 && out->id <= 0xffffffffLL;
}

// --- acts verbs (lane acts): `quest`, `menu`, `interact` / `msg` targets, `xp` --------------------------------------------
// `quest <id> dump` | `quest <id> <bit 0-15> [get|set|clear]` (get is the default). Quest ids are D2R's 0..40 (+ the
// game's extra words up to 0x7f); a bad line answers false.
struct QuestArgs {
	enum Op { Dump, Get, Set, Clear } op = Get;
	long long quest = 0, bit = 0;
};
inline auto ParseQuestArgs(const Tokens& t, QuestArgs* out) noexcept -> bool {
	*out = QuestArgs();
	if (t.n < 3 || !ParseInt(t.tok[1], &out->quest) || out->quest < 0 || out->quest > 0x7f) {
		return false;
	}
	if (LowerEq(t.tok[2], "dump")) {
		out->op = QuestArgs::Dump;
		return t.n == 3;
	}
	if (!ParseInt(t.tok[2], &out->bit) || out->bit < 0 || out->bit > 15 || t.n > 4) {
		return false;
	}
	if (t.n == 3 || LowerEq(t.tok[3], "get")) {
		out->op = QuestArgs::Get;
	} else if (LowerEq(t.tok[3], "set")) {
		out->op = QuestArgs::Set;
	} else if (LowerEq(t.tok[3], "clear")) {
		out->op = QuestArgs::Clear;
	} else {
		return false;
	}
	return true;
}

// `menu list` | `menu cancel` | `menu <line>`: the NPC menu record holds up to 5 lines plus Cancel (`lines` counts Cancel).
// Returns the line index, -1 for list, -2 for cancel, -3 for a bad line.
constexpr int MenuMaxLines = 5;
inline auto ParseMenuLine(const char* word, int lines) noexcept -> int {
	if (word == nullptr) {
		return -3;
	}
	if (LowerEq(word, "list")) {
		return -1;
	}
	if (LowerEq(word, "cancel")) {
		return -2;
	}
	long long line = 0;
	if (!ParseInt(word, &line) || line < 0 || line >= lines - 1 || line >= MenuMaxLines) {
		return -3;
	}
	return static_cast<int>(line);
}

// `interact nearest|<npc class>`, `msg nearest|<npc class> <message>`, `moveto nearest [class]|<unit id>`: -1 = any class.
inline auto ParseNpcTarget(const char* word, long long* cls) noexcept -> bool {
	*cls = -1;
	if (word == nullptr) {
		return false;
	}
	return LowerEq(word, "nearest") || (ParseInt(word, cls) && *cls >= 0 && *cls <= 0xffff);
}

// The spot next to an NPC where `interact` stands the player (the server takes a talk within a few sub-tiles): offsets
// tried in this order, first the four diagonals at 2, then straight at 3, then farther diagonals.
constexpr int InteractOffsets[][2] = {{2, 2}, {-2, 2}, {2, -2}, {-2, -2}, {3, 0}, {0, 3}, {-3, 0}, {0, -3}, {4, 4}, {-4, -4}};
constexpr double InteractReach = 5.0;

// `xp <amount>`: the experience award takes a signed 32-bit amount.
inline auto ParseXp(const Tokens& t, long long* amount) noexcept -> bool {
	return t.n == 2 && ParseInt(t.tok[1], amount) && *amount > 0 && *amount <= 0x7fffffffLL;
}

// `presets` / `place`: D2R's DRLG room records (waypoint arrival 0x3dad90, room level 0x2efc10 -> 0x360fc0).
constexpr int Room1Drlg = 0x18, DrlgRoomLevel = 0x90, LevelId = 0x1f8, LevelFirstRoom = 0x10, DrlgRoomNext = 0x48;
constexpr int DrlgRoomPresets = 0x98, DrlgRoomTileX = 0x60, DrlgRoomTileY = 0x64;
constexpr int PresetClass = 4, PresetX = 8, PresetNext = 0x10, PresetType = 0x20, PresetY = 0x24;
// A preset's position in `state` units (sub-tiles): the room's tile origin * 5 plus the preset's sub-tile inside the room.
constexpr auto PresetToState(int roomTile, int presetSub) noexcept -> int { return roomTile * 5 + presetSub; }
constexpr int PlaceOffsets[][2] = {{0, 0}, {3, 0}, {0, 3}, {-3, 0}, {0, -3}, {5, 5}, {-5, 5}, {5, -5}, {-5, -5}, {8, 0}, {0, 8}, {-8, 0}, {0, -8}};

constexpr uint32_t ItemFlagIdentified = 0x10;  // item data flag word (+0x18)
constexpr uint32_t ItemFlagSocketed = 0x800;   // `item ... 194=<n>` sets it with the socket count
constexpr int StatSockets = 194;               // item_numsockets

// Item update packet (0x535f60): its 5th argument is the item's command flag (item data +0x14), which picks the client's action.
// 2 = put in a page (the trade executor 0x527e93), 8 = equip on a body location (the item-to-body packet 0x1a, handler
// 0x4aa450, success branch 0x4aa682: clears item flag 0x4000, sends (1, 8, body loc), then stats-changed). Bug #391.
constexpr int32_t ItemCmdToPage = 2, ItemCmdEquip = 8;
constexpr uint32_t ItemFlagEquipClear = 0x4000;  // cleared by D2R's own equip before the send
constexpr auto PlaceCmdKind(int bodyLoc) noexcept -> int32_t { return bodyLoc > 0 ? ItemCmdEquip : ItemCmdToPage; }

// --- mercenaries (lane mercs2) -----------------------------------------------------------------------------------------
// 1.13c's revive price: level squared, halved, times 15, at most 50,000 gold. D2R reads the three numbers from hireling.txt
// (resurrectcostmultiplier / divisor / max; txt_migrate writes 15 / 2 / 50000 on every row) and falls back to the same
// constants in code (0x3c1ad0), so `mercprice` compares the game's function with this.
inline constexpr auto RevivePrice113(int level) noexcept -> int {
	const long long cost = static_cast<long long>(level) * level / 2 * 15;
	return cost < 50000 ? static_cast<int>(cost) : 50000;
}

// Client packet 0x51 (17 bytes), what a click on the hireling panel sends (server handler 0x4c0e20): the item on the player's
// cursor (or -1), the mercenary's unit id, the mercenary item taken off (or -1) and the body location (below 11).
inline void MercItemPacket(uint32_t cursorItem, uint32_t merc, uint32_t mercItem, uint32_t bodyLoc, uint8_t out[17]) noexcept {
	out[0] = 0x51;
	const uint32_t v[4] = {cursorItem, merc, mercItem, bodyLoc};
	for (int i = 0; i < 4; ++i) {
		for (int b = 0; b < 4; ++b) {
			out[1 + i * 4 + b] = static_cast<uint8_t>(v[i] >> (8 * b));
		}
	}
}

// --- player-path verbs (lane realpath; lane cube uses them too): client packets handed to the server's own handlers ---------------------------------
// `pkt <hex byte> ...`: the packet as the client sends it, two hex digits per token. Returns the byte count,
// 0 when a token is not one or two hex digits or there are none.
inline auto ParseHexBytes(const Tokens& t, int from, uint8_t* out, size_t cap) noexcept -> size_t {
	size_t n = 0;
	for (int i = from; i < t.n; ++i) {
		const char* s = t.tok[i];
		const size_t len = std::strlen(s);
		if (len < 1 || len > 2 || n >= cap) {
			return 0;
		}
		unsigned v = 0;
		for (size_t k = 0; k < len; ++k) {
			const char ch = s[k];
			const int d = ch >= '0' && ch <= '9' ? ch - '0' : ch >= 'a' && ch <= 'f' ? ch - 'a' + 10 : ch >= 'A' && ch <= 'F' ? ch - 'A' + 10 : -1;
			if (d < 0) {
				return 0;
			}
			v = v * 16 + static_cast<unsigned>(d);
		}
		out[n++] = static_cast<uint8_t>(v);
	}
	return n;
}

// Packet 0x16 (pick an item up from the ground, D2R 17 bytes): u8 id, u32 item id,
// u32 x, u32 y (the item's position), u32 to-inventory flag (0 = to the cursor, 1 = a plain click: straight into the backpack,
// or onto an empty body location). The client sends it when the player clicks an item on the ground.
constexpr size_t PickupPacketSize = 17;
inline auto BuildPickupPacket(uint8_t* out, uint32_t itemId, uint32_t x, uint32_t y, bool toInventory) noexcept -> size_t {
	std::memset(out, 0, PickupPacketSize);
	out[0] = 0x16;
	const uint32_t v[4] = {itemId, x, y, toInventory ? 1U : 0U};
	std::memcpy(out + 1, v, sizeof(v));
	return PickupPacketSize;
}

// `istat <item unit id> <stat> [layer | scan]` (lane cube): read one stat of an item (a cube output's mods). `scan` lists the
// layers 0..0xffff that hold a value (skill-parameter stats: layer = skill << 6 | level, or the skill id).
struct IstatSpec {
	long long id = -1, stat = -1, layer = 0;
	bool scan = false;
};
inline auto ParseIstat(const Tokens& t, IstatSpec* s) noexcept -> bool {
	*s = IstatSpec{};
	if (t.n < 3 || t.n > 4 || !ParseInt(t.tok[1], &s->id) || s->id < 0 || !ParseInt(t.tok[2], &s->stat) || s->stat < 0 || s->stat > 0xffff) {
		return false;
	}
	if (t.n == 4) {
		if (LowerEq(t.tok[3], "scan")) {
			s->scan = true;
		} else if (!ParseInt(t.tok[3], &s->layer) || s->layer < 0 || s->layer > 0xffff) {
			return false;
		}
	}
	return true;
}

constexpr int StatGold = 14, StatGoldBank = 15;  // `gold` (lane realpath)

}  // namespace hcmd

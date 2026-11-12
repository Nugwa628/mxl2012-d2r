// Pure part of the developer menu (devmenu.cpp, docs/dev-menu.md; unit test plugin/tests/devmenu_test.cpp). No Windows headers, no game
// calls: the catalog file's parser, the name search, the gate that refuses every action outside a single-player game, the arithmetic
// of a level raise and the travel route.
#pragma once

#include <algorithm>
#include <cctype>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>
#include <string_view>
#include <vector>

#include "panel_logic.h"

namespace devmenu {

// The rules every native panel of the plugin shares (panel_logic.h): the menu's search box, paging and line cutting are those.
using panel_logic::EditingKey;
using panel_logic::Ellipsize;
using panel_logic::Fold;
using panel_logic::Matches;
using panel_logic::OnBox;
using panel_logic::Page;
using panel_logic::PageOf;
using panel_logic::SplitTabs;
using panel_logic::StandInKey;
using panel_logic::ToInt;
using panel_logic::TypedKey;
using panel_logic::WrapText;

// --- catalog (tools/devmenu_catalog.py writes it, data/mxl2012-devmenu/catalog.tsv in the mod) ----------------------------------------------
inline constexpr int CatalogFormat = 3;
inline constexpr int MaxLevel = 120;
inline constexpr int ClassCount = 8;
inline constexpr int MaxRunes = 6;

enum class Category : uint8_t { All, Unique, Set, Charm, Quest, Base, Runeword };
inline constexpr int CategoryCount = 7;
inline constexpr const char* const CategoryNames[CategoryCount] = {"All", "Uniques", "Sets", "Charms", "Quest / misc", "Bases", "Runewords"};

// Items::Quality values (D2RLPlugin/item.h)
inline constexpr uint32_t QualityNormal = 2, QualitySet = 5, QualityUnique = 7;

constexpr auto MakeCode(const char* s, size_t n) noexcept -> uint32_t {
	uint32_t v = 0;
	for (size_t i = 0; i < 4; ++i) {
		v |= static_cast<uint32_t>(i < n ? static_cast<uint8_t>(s[i]) : static_cast<uint8_t>(' ')) << (8U * i);
	}
	return v;
}

struct Item {
	Category cat = Category::Unique;
	uint32_t code = 0;
	uint32_t quality = QualityNormal;  // QualityNormal, QualitySet or QualityUnique
	int32_t row = -1;                  // zero-based uniqueitems / setitems record, -1 for the rest
	int sockets = 0;                   // a normal item's maximum sockets (catalog); uniques and sets keep their row's
	std::string name;
	std::string tag;  // "retired row" or empty
};

struct Kit {
	uint32_t base = 0;
	int sockets = 0;
	std::vector<uint32_t> runes;
	std::string name;
};

struct Level {
	int id = 0;
	int act = 0;
	int note = 0;  // 0 none, 1 map only (uber arena), 2 portal-only area
	int waypoint = 255;
	std::string name;
};

// An uber level (its entrance says "DANGER - Uberquest Area"): the menu warps to `entry`, the area right before it, never into it.
struct Uber {
	int id = 0;     // the uber level
	int entry = 0;  // the level with its entrance (`how` 0) or its red portal (`how` 1)
	int how = 0;
	std::string name;
};

struct Catalog {
	bool ok = false;
	std::string hash;
	std::vector<Item> items;  // all categories but runewords, in the file's order
	std::vector<Kit> kits;
	std::vector<Level> levels;
	std::vector<Uber> ubers;  // levels.txt order
	int thresholds[ClassCount][MaxLevel] = {};
	std::string error;
};

// Parses the catalog file's text. On a malformed file `ok` stays false and `error` names the problem: the menu then refuses everything.
inline auto ParseCatalog(std::string_view text) -> Catalog {
	Catalog c;
	bool header = false;
	size_t from = 0;
	while (from < text.size()) {
		size_t nl = text.find('\n', from);
		if (nl == std::string_view::npos) {
			nl = text.size();
		}
		std::string_view line = text.substr(from, nl - from);
		from = nl + 1;
		if (!line.empty() && line.back() == '\r') {
			line.remove_suffix(1);
		}
		if (line.empty()) {
			continue;
		}
		const auto f = SplitTabs(line);
		if (f[0] == "#devmenu") {
			if (f.size() < 3 || ToInt(f[1]) != CatalogFormat) {
				c.error = "unknown catalog format";
				return c;
			}
			c.hash = std::string(f[2]);
			header = true;
		} else if (f[0] == "I" && f.size() >= 7 && f[2].size() <= 4) {
			static constexpr struct {
				char letter;
				Category cat;
			} Cats[] = {{'U', Category::Unique}, {'S', Category::Set}, {'C', Category::Charm}, {'Q', Category::Quest}, {'B', Category::Base}};
			Item it;
			bool known = false;
			for (const auto& k : Cats) {
				if (f[1].size() == 1 && f[1][0] == k.letter) {
					it.cat = k.cat;
					known = true;
				}
			}
			if (!known) {
				continue;
			}
			it.code = MakeCode(f[2].data(), f[2].size());
			const int q = ToInt(f[3], 0);
			it.quality = q == 5 ? QualitySet : q == 7 ? QualityUnique : QualityNormal;
			it.row = ToInt(f[4]);
			it.sockets = ToInt(f[5], 0);
			it.name = std::string(f[6]);
			if (f.size() > 7) {
				it.tag = std::string(f[7]);
			}
			c.items.push_back(std::move(it));
		} else if (f[0] == "K" && f.size() >= 5 && f[1].size() <= 4) {
			Kit k;
			k.base = MakeCode(f[1].data(), f[1].size());
			k.sockets = ToInt(f[2], 0);
			std::string_view runes = f[3];
			while (!runes.empty()) {
				size_t comma = runes.find(',');
				if (comma == std::string_view::npos) {
					comma = runes.size();
				}
				k.runes.push_back(MakeCode(runes.data(), comma));
				runes.remove_prefix(comma == runes.size() ? comma : comma + 1);
			}
			k.name = std::string(f[4]);
			if (k.runes.empty() || k.runes.size() > MaxRunes) {
				c.error = "bad runeword line";
				return c;
			}
			c.kits.push_back(std::move(k));
		} else if (f[0] == "L" && f.size() >= 6) {
			Level l;
			l.id = ToInt(f[1]);
			l.act = ToInt(f[2], 0);
			l.note = ToInt(f[3], 0);
			l.waypoint = ToInt(f[4], 255);
			l.name = std::string(f[5]);
			if (l.id > 0) {
				c.levels.push_back(std::move(l));
			}
		} else if (f[0] == "U" && f.size() >= 5) {
			Uber u;
			u.id = ToInt(f[1]);
			u.entry = ToInt(f[2]);
			u.how = ToInt(f[3], 0);
			u.name = std::string(f[4]);
			if (u.id > 0 && u.entry > 0) {
				c.ubers.push_back(std::move(u));
			}
		} else if (f[0] == "X" && f.size() == static_cast<size_t>(MaxLevel) + 2) {
			const int cls = ToInt(f[1]);
			if (cls >= 0 && cls < ClassCount) {
				for (int i = 0; i < MaxLevel; ++i) {
					c.thresholds[cls][i] = ToInt(f[static_cast<size_t>(i) + 2], -1);
				}
			}
		}
	}
	if (!header) {
		c.error = "no catalog header";
		return c;
	}
	if (c.items.empty() || c.levels.empty()) {
		c.error = "empty catalog";
		return c;
	}
	c.ok = true;
	return c;
}

// --- search ---------------------------------------------------------------------------------------------------------------------------
// The empty sockets asked for when an item is spawned: a normal item gets its maximum (the catalog's count, 0 for an item that cannot have
// sockets); a unique or set item asks for none, so it keeps its row's fixed `sock` property or stays without sockets, as Median makes it.
inline auto SpawnSockets(const Item& item) -> uint32_t {
	return item.quality == QualityNormal && item.sockets > 0 ? static_cast<uint32_t>(item.sockets) : 0;
}

// Real sockets. D2 has two parts to a socketed item: the socket count (stat 194, item_numsockets) and the item flag "socketed" (0x800 in the
// item data's flag word); the item service's socketCount sets both. Until lane devmenu4 normal items were created unidentified (stateFlags 0),
// and D2R's tooltip shows an unidentified item's sockets as "Max Sockets: N" instead of "Socketed (N)". Every spawned item is now created
// identified, as D2 makes every normal item; the native item is then read back (count and flag) for the status and the check.
inline constexpr uint32_t ItemFlagIdentified = 0x10;
inline constexpr uint32_t ItemFlagSocketed = 0x800;
inline constexpr int StatNumSockets = 194;

inline auto SpawnIdentified(uint32_t /*quality*/) -> bool {
	return true;
}

// The item has usable sockets: a count, the socketed flag and identified (nothing asked: nothing to check). The count can be lower than asked
// when the game caps it; the status says "n of m".
inline auto SocketsReal(uint32_t wanted, uint32_t flags, int32_t count) -> bool {
	return wanted == 0 || (count > 0 && (flags & ItemFlagSocketed) != 0 && (flags & ItemFlagIdentified) != 0);
}

// One row of a result list: an index into Catalog::items, kits or levels.
struct Hit {
	bool kit = false;
	int index = 0;
};

// The Items tab's results: category filter + name search, in the catalog's order, runeword kits last.
inline auto SearchItems(const Catalog& c, Category cat, std::string_view query) -> std::vector<Hit> {
	std::vector<Hit> out;
	if (cat != Category::Runeword) {
		for (size_t i = 0; i < c.items.size(); ++i) {
			if ((cat == Category::All || c.items[i].cat == cat) && Matches(c.items[i].name, query)) {
				out.push_back({false, static_cast<int>(i)});
			}
		}
	}
	if (cat == Category::All || cat == Category::Runeword) {
		for (size_t i = 0; i < c.kits.size(); ++i) {
			if (Matches(c.kits[i].name, query)) {
				out.push_back({true, static_cast<int>(i)});
			}
		}
	}
	return out;
}

inline auto SearchLevels(const Catalog& c, std::string_view query) -> std::vector<int> {
	std::vector<int> out;
	for (size_t i = 0; i < c.levels.size(); ++i) {
		if (Matches(c.levels[i].name, query)) {
			out.push_back(static_cast<int>(i));
		}
	}
	return out;
}

inline auto FindLevel(const Catalog& c, int id) -> const Level* {
	for (const Level& l : c.levels) {
		if (l.id == id) {
			return &l;
		}
	}
	return nullptr;
}

// One row of the Travel tab: a heading (index 0 "Uber levels", 1 "Areas"; no arrow), an uber level (index into Catalog::ubers) or an area
// (index into Catalog::levels).
struct TravelRow {
	enum Kind : uint8_t { Heading, UberLevel, Area } kind = Area;
	int index = 0;
};

inline constexpr const char* const TravelHeadings[] = {"Uber levels: to the area in brackets", "Areas"};

// The Travel tab's results: the uber levels whose name matches (or all of them for "uber") under their heading, then the areas as before.
// An uber level is found by its own name; the area list still holds it too (an arrow there goes inside).
inline auto SearchTravel(const Catalog& c, std::string_view query) -> std::vector<TravelRow> {
	std::vector<TravelRow> out;
	for (size_t i = 0; i < c.ubers.size(); ++i) {
		if (Matches("Uber " + c.ubers[i].name, query)) {
			if (out.empty()) {
				out.push_back({TravelRow::Heading, 0});
			}
			out.push_back({TravelRow::UberLevel, static_cast<int>(i)});
		}
	}
	const std::vector<int> areas = SearchLevels(c, query);
	if (!out.empty() && !areas.empty()) {
		out.push_back({TravelRow::Heading, 1});
	}
	for (int i : areas) {
		out.push_back({TravelRow::Area, i});
	}
	return out;
}

// The text of an uber level's row: its name and, in brackets, the area the arrow puts the player in (the heading says so). Fits the
// HD row (52 characters) for all 16 of Median 2012's.
inline auto UberRowText(const Catalog& c, const Uber& u) -> std::string {
	const Level* entry = FindLevel(c, u.entry);
	const std::string where = entry != nullptr ? entry->name : "level " + std::to_string(u.entry);
	return u.name + " (" + where + (u.how == 1 ? " portal)" : ")");
}

// The status after arriving for an uber level.
inline auto UberArrivalText(const Catalog& c, const Uber& u) -> std::string {
	const Level* entry = FindLevel(c, u.entry);
	return "You arrived in " + (entry != nullptr ? entry->name : std::string("?")) + ", right before " + u.name + ": its " +
	       (u.how == 1 ? "red portal" : "entrance") + " is in this area.";
}

// --- the gate (every action, at the button and again on the game thread) -----------------------------------------------------------------
enum class Refusal : uint8_t {
	None,
	NoCatalog,
	NotInGame,
	Joined,       // the game runs on another machine or process: this client has no local server
	Networked,    // a local server, but it accepts other players (TCP host) or has more than one client
	Busy,         // another action is still running
	BadTarget,    // the row no longer validates
	NoGameThread  // the loader's game thread queue refused
};

struct GateState {
	bool catalogOk = false;
	bool inGame = false;       // a local player unit exists on the client
	bool localServer = false;  // a server frame of this process found that player
	int clients = 0;           // clients of the local server game (0 when not read)
	bool listening = true;     // this process holds a listening TCP socket (true also when the socket table could not be read)
	bool busy = false;
};

constexpr auto Gate(const GateState& s) noexcept -> Refusal {
	if (!s.catalogOk) {
		return Refusal::NoCatalog;
	}
	if (!s.inGame) {
		return Refusal::NotInGame;
	}
	if (!s.localServer) {
		return Refusal::Joined;
	}
	if (s.listening || s.clients != 1) {
		return Refusal::Networked;
	}
	if (s.busy) {
		return Refusal::Busy;
	}
	return Refusal::None;
}

constexpr auto RefusalText(Refusal r) noexcept -> const char* {
	switch (r) {
	case Refusal::None:
		return "";
	case Refusal::NoCatalog:
		return "Catalog file not found in the mod: the menu is off.";
	case Refusal::NotInGame:
		return "Enter a game first.";
	case Refusal::Joined:
		return "Not available in multiplayer games.";
	case Refusal::Networked:
		return "Not available in multiplayer (TCP/IP) games.";
	case Refusal::Busy:
		return "Please wait: the last action is still running.";
	case Refusal::BadTarget:
		return "That entry is not valid any more.";
	case Refusal::NoGameThread:
		return "The game did not accept the action.";
	}
	return "";
}

// --- level raise ----------------------------------------------------------------------------------------------------------------------
enum class Raise : uint8_t { Ok, NotHigher, TooHigh, NoTable };

constexpr auto CheckRaise(int currentLevel, int targetLevel, int maxLevel, bool tableOk) noexcept -> Raise {
	if (!tableOk) {
		return Raise::NoTable;
	}
	if (targetLevel > maxLevel) {
		return Raise::TooHigh;
	}
	return targetLevel <= currentLevel ? Raise::NotHigher : Raise::Ok;
}

// Experience to award so that a player with `current` total experience reaches `targetLevel`, from the class's thresholds (element i is
// the total for level i + 1). Zero when the total is reached already or the table has no value.
inline auto XpToReach(const int* thresholds, int targetLevel, long long current) noexcept -> long long {
	if (targetLevel < 1 || targetLevel > MaxLevel || thresholds[targetLevel - 1] < 0) {
		return 0;
	}
	const long long need = static_cast<long long>(thresholds[targetLevel - 1]) - current;
	return need > 0 ? need : 0;
}

// The class id of a character (charstats order, the X lines' order), clamped against a bad value.
constexpr auto ClassOk(int cls) noexcept -> bool {
	return cls >= 0 && cls < ClassCount;
}

// --- travel ---------------------------------------------------------------------------------------------------------------------------
// Same act: the waypoint move; another act: the NPC travel (inside one act the latter only opens a portal: harness `level`, bug #5).
constexpr auto UseNpcTravel(int actFrom, int actTo) noexcept -> bool {
	return actFrom != actTo;
}

// The waypoint numbers the current tables use (each once).
inline auto WaypointNumbers(const Catalog& c) -> std::vector<int> {
	std::vector<int> out;
	for (const Level& l : c.levels) {
		if (l.waypoint >= 0 && l.waypoint < 255 && std::find(out.begin(), out.end(), l.waypoint) == out.end()) {
			out.push_back(l.waypoint);
		}
	}
	std::sort(out.begin(), out.end());
	return out;
}

// The waypoint panel draws an act's tab only when the character's quest words say the act opened (game_checks RP_ACT_OPEN, set in saves
// by tools/rc_setup.py): word 7 / 15 / 23 (acts I-III done) open tabs II-IV, 26 and 28 together open V. Bit 12 = completed before, bit 0
// rewarded; the unlock sets them as closed-save edits did, without touching any other quest state.
inline constexpr int ActWords[] = {7, 15, 23, 26, 28};
inline constexpr int ActWordBits[] = {0, 12};

}  // namespace devmenu

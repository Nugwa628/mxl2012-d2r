// Standalone test of the sprite-card direction hooks' pure part (sprite_dir_logic.h; not part of the plugin DLL).
#include "../src/sprite_dir_logic.h"

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
	using namespace sprite_dir;
	// D2R's table at 0x237ff10 (0x3aeb30 reads it): the eighth of a circle each of the 64 path directions falls in
	constexpr unsigned char d2r[64] = {0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4,
	                                   4, 4, 4, 4, 5, 5, 5, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 6, 6, 7, 7, 7, 7, 7, 7, 7, 7, 0, 0, 0, 0};
	for (int d = 0; d < 64; ++d) {
		Check(KeyOf(d) == d2r[d], "a direction's key is the game's own eighth");
	}
	Check(StartTime(0.5f, 0.76f) == 0.5f * 0.76f && StartTime(0.6875f, 0.6f) == 0.6875f * 0.6f, "a start fraction is a time within one loop");
	Check(StartTime(0.0f, 0.76f) == 0.0f && StartTime(-1.0f, 0.76f) == 0.0f && StartTime(1.0f, 0.76f) == 0.0f &&
	          StartTime(3.0f, 0.76f) == 0.0f && StartTime(0.5f, 0.0f) == 0.0f,
	      "no fraction, one at or past the end, and a clip without length start at 0");
	Check(KeyOf(64) == 0 && KeyOf(-1) == 0 && KeyOf(68) == 1 && KeyOf(-4) == 0 && KeyOf(-5) == 7, "directions off the circle wrap");
	for (int d = -200; d < 200; ++d) {
		Check(KeyOf(d) >= 0 && KeyOf(d) < Keys, "every key is one of the eight");
	}

	// only state machines under the card folder are ours
	const char card[] = "data/hd/character/enemy/mxl/flip/_7ek/_7ek_state_machine.json";
	Check(IsCardMachine(card, sizeof(card)), "a card unit's machine");
	const char slashes[] = "Data\\HD\\Character\\Enemy\\MXL\\Flip\\_7ek\\_7ek_state_machine.json";
	Check(IsCardMachine(slashes, sizeof(slashes)), "either slash, any case");
	const char stock[] = "data/hd/character/enemy/fallen/fallen_state_machine.json";
	Check(!IsCardMachine(stock, sizeof(stock)), "a D2R monster's machine");
	const char player[] = "data/hd/character/player/sorceress/sorceress_state_machine.json";
	Check(!IsCardMachine(player, sizeof(player)), "a player's machine");
	const char near1[] = "data/hd/character/enemy/mxl/flipper/x.json";
	Check(!IsCardMachine(near1, sizeof(near1)), "a folder that only starts like ours");
	const char empty[] = "";
	Check(!IsCardMachine(empty, sizeof(empty)), "an empty name");
	const char marker[] = "/mxl/flip/";
	Check(IsCardMachine(marker, sizeof(marker)), "the marker alone");
	char endless[32];
	std::memset(endless, 'a', sizeof(endless));
	std::memcpy(endless, "/mxl/flip/", 10);
	Check(!IsCardMachine(endless, sizeof(endless)), "a name without an end inside the buffer is not read as ours");

	// the watch list
	Watch w;
	int units[80] = {};
	Check(w.Count() == 0 && w.FindUnit(&units[0]) == nullptr && w.FindEntity(1) == nullptr, "an empty list finds nothing");
	Entry* e = w.Set(&units[0], 100, 0x10001, 3);
	Check(w.Count() == 1 && e != nullptr && e->key == 3 && w.FindUnit(&units[0]) == e && w.FindEntity(0x10001) == e, "one unit");
	w.Set(&units[0], 100, 0x10002, 5);
	Check(w.Count() == 1 && w.FindEntity(0x10001) == nullptr && w.FindEntity(0x10002) != nullptr && w.FindUnit(&units[0])->key == 5,
	      "the same unit with a new entity replaces its entry");
	w.Set(&units[1], 101, 0x10002, 6);
	Check(w.Count() == 1 && w.FindUnit(&units[0]) == nullptr && w.FindUnit(&units[1])->unitId == 101,
	      "an entity that went to another unit replaces the old unit's entry");
	w.Remove(w.FindUnit(&units[1]));
	Check(w.Count() == 0, "removed");
	w.Remove(nullptr);
	Check(w.Count() == 0, "removing nothing");
	for (int i = 0; i < Watch::Size; ++i) {
		w.Set(&units[i], 200 + static_cast<uint32_t>(i), 0x20000 + static_cast<uint32_t>(i), i & 7);
	}
	Check(w.Count() == Watch::Size, "a full list");
	w.Set(&units[70], 270, 0x20070, 1);
	Check(w.Count() == Watch::Size && w.FindUnit(&units[0]) == nullptr && w.FindUnit(&units[1]) != nullptr &&
	          w.FindUnit(&units[70]) != nullptr,
	      "a full list drops its oldest entry for a new unit");
	w.Remove(w.FindUnit(&units[5]));
	Check(w.Count() == Watch::Size - 1 && w.FindUnit(&units[5]) == nullptr && w.FindUnit(&units[63]) != nullptr, "one out of the middle");
	int walked = 0;
	for (int i = w.Count() - 1; i >= 0; --i) {
		if (w.At(i)->unitId % 2 == 0) {
			w.Remove(w.At(i));
		}
		++walked;
	}
	bool odd = w.Count() > 0;
	for (int i = 0; i < w.Count(); ++i) {
		odd = odd && w.At(i)->unitId % 2 == 1;
	}
	Check(walked == Watch::Size - 1 && odd, "a walk from the end removing entries visits each once and keeps the rest");
	w.Clear();
	Check(w.Count() == 0 && w.FindUnit(&units[70]) == nullptr, "cleared");

	// the weapon class keys the eight facings use are the first eight of the engine's fourteen
	Check(Keys == 8, "eight facings");
	if (failures == 0) {
		std::printf("sprite_dir: all checks passed\n");
	}
	return failures == 0 ? 0 : 1;
}

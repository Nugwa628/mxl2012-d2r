// Standalone test of arealvl's pure part (area_level_logic.h; not part of the plugin DLL).
#include "../src/area_level_logic.h"

#include <cstdio>
#include <vector>

namespace {
int failures = 0;
void Check(bool ok, const char* what) {
	if (!ok) {
		++failures;
		std::printf("FAIL: %s\n", what);
	}
}

void Put16(std::vector<uint8_t>& t, size_t at, int16_t v) {
	t[at] = static_cast<uint8_t>(v & 0xff);
	t[at + 1] = static_cast<uint8_t>((v >> 8) & 0xff);
}

// A levels table of `rows` records with MonLvl = 1 / 2 / 3 and MonLvlEx = lvl, lvl + 1, lvl + 2 for row `row`.
void SetRow(std::vector<uint8_t>& t, int row, int16_t ex) {
	using namespace area_level;
	const size_t r = static_cast<size_t>(row) * LevelsStride;
	for (int d = 0; d < 3; ++d) {
		Put16(t, r + LevelsMonLvl + 2 * d, static_cast<int16_t>(d + 1));
		Put16(t, r + LevelsMonLvlEx + 2 * d, ex > 0 ? static_cast<int16_t>(ex + d) : ex);
	}
}
}  // namespace

int main() {
	using namespace area_level;
	const int rows = 5;
	std::vector<uint8_t> t(rows * LevelsStride, 0);
	SetRow(t, 2, 75);    // Blood Moor-like: 75 / 76 / 77
	SetRow(t, 3, 300);   // above a byte
	SetRow(t, 4, 0);     // a town: no area level
	const uint8_t* p = t.data();

	// MonLvlEx per difficulty (what D2R's 0x32c700 reads for an expansion game)
	Check(AreaLevel(p, rows, 2, 0, true) == 75, "Normal reads MonLvlEx[0]");
	Check(AreaLevel(p, rows, 2, 1, true) == 76, "Nightmare reads MonLvlEx[1]");
	Check(AreaLevel(p, rows, 2, 2, true) == 77, "Hell reads MonLvlEx[2]");
	Check(AreaLevel(p, rows, 3, 2, true) == 302, "a 16-bit level");
	Check(AreaLevel(p, rows, 2, 1, false) == 2, "classic reads MonLvl");
	// no line
	Check(AreaLevel(p, rows, 4, 0, true) == 0, "a level without an area level");
	Check(AreaLevel(p, rows, 0, 0, true) == 0, "level 0 (none)");
	Check(AreaLevel(p, rows, rows, 0, true) == 0, "a level past the table");
	Check(AreaLevel(p, rows, -1, 0, true) == 0, "a negative level");
	Check(AreaLevel(p, rows, 2, 3, true) == 0 && AreaLevel(p, rows, 2, -1, true) == 0, "an unknown difficulty");
	Check(AreaLevel(nullptr, rows, 2, 0, true) == 0, "no table");

	// the lookup's answer
	DesecratedLevel none{0, 0, {}, 1234};
	Check(Fill(&none, 75) && none.has == 1 && none.level == 75 && none.next == 0, "not terrorized: the area level, no zone timer");
	DesecratedLevel tz{88, 1, {}, 0};
	Check(!Fill(&tz, 75) && tz.level == 88, "a terrorized level keeps D2R's level");
	DesecratedLevel town{0, 0, {}, 7};
	Check(!Fill(&town, 0) && town.has == 0 && town.next == 7, "no area level: D2R's answer as it was");
	Check(!Fill(nullptr, 75), "no output");

	if (failures == 0) {
		std::printf("arealvl tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}

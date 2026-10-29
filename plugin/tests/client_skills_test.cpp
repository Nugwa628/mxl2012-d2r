// Standalone test of the client wall geometry (client_skills_logic.h; not part of the plugin DLL).
#include "../src/client_skills_logic.h"

#include <cstdio>
#include <cstdlib>

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
	using client_skills::AreaAuraRuns;
	using client_skills::HasClientMissile;
	using client_skills::WallFrom;
	// Target inside the range: the wall stands on the target point, the missiles fly out perpendicular to caster -> target.
	auto w = WallFrom(100, 100, 110, 100, 20);
	Check(w.x == 110 && w.y == 100, "target within range: start on the target");
	Check(w.leftX == 110 && w.leftY == 90 && w.rightX == 110 && w.rightY == 110, "east cast: missiles to north and south");
	// Perpendicular: (left - start) . (target - caster) == 0, and both sides mirror each other.
	Check((w.leftX - w.x) * (110 - 100) + (w.leftY - w.y) * (100 - 100) == 0, "left is perpendicular");
	Check(w.leftX + w.rightX == 2 * w.x && w.leftY + w.rightY == 2 * w.y, "left and right mirror around the start");

	// Target beyond the range: pulled back along the line to |range| from the caster.
	w = WallFrom(0, 0, 0, 50, 20);
	Check(w.x == 0 && w.y == 20, "target beyond range: clamped to 20");
	w = WallFrom(0, 0, 30, 40, -10);  // negative calc: the absolute value is the limit
	Check(w.x == 6 && w.y == 8, "negative range uses its absolute value");
	// Exactly at the range: clamped onto the same point.
	w = WallFrom(0, 0, 20, 0, 20);
	Check(w.x == 20 && w.y == 0, "at the range");
	// Range 0: no limit.
	w = WallFrom(0, 0, 500, 0, 0);
	Check(w.x == 500 && w.y == 0, "range 0: no clamp");
	// Target on the caster: nothing to clamp, both missiles get the caster's spot as their target (no direction).
	w = WallFrom(7, 7, 7, 7, 20);
	Check(w.x == 7 && w.leftX == 7 && w.rightY == 7, "target on the caster");

	// bug #6: the curse / start 18 wrappers run D2R's function only with a client missile
	Check(!HasClientMissile(-1, 2723) && !HasClientMissile(2723, 2723) && HasClientMissile(0, 2723) && HasClientMissile(2722, 2723),
	      "client missile present");
	// bug #31: the area aura applier runs only for a radius of 1 or more
	Check(!AreaAuraRuns(0) && !AreaAuraRuns(-3) && AreaAuraRuns(1) && AreaAuraRuns(18), "area aura radius guard");

	if (failures == 0) {
		std::printf("client skills tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}

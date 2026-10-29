// Pure geometry of the client wall function (client_skills.cpp CltDoWall; unit test plugin/tests/client_skills_test.cpp).
// No Windows headers, no game calls.
#pragma once

#include <cmath>
#include <cstdint>

namespace client_skills {

// The two client missiles of CltDoWall: both start on the target point (pulled to within |range| of the caster when it
// lies farther; range 0 = no limit) and fly out perpendicular to the cast direction, one to each side.
struct Wall {
	int32_t x, y;               // start of both missiles
	int32_t leftX, leftY;       // target point of the first missile
	int32_t rightX, rightY;     // target point of the second
};

inline auto WallFrom(int32_t ux, int32_t uy, int32_t tx, int32_t ty, int32_t range) noexcept -> Wall {
	if (range != 0) {
		const double dx = tx - ux, dy = ty - uy;
		const double distance = std::sqrt(dx * dx + dy * dy);
		const double limit = range < 0 ? -static_cast<double>(range) : static_cast<double>(range);
		if (distance >= limit && distance > 0.0) {
			tx = ux + static_cast<int32_t>(dx * limit / distance);
			ty = uy + static_cast<int32_t>(dy * limit / distance);
		}
	}
	Wall w{};
	w.x = tx;
	w.y = ty;
	w.leftX = tx + (ty - uy);
	w.leftY = ty - (tx - ux);
	w.rightX = tx - (ty - uy);
	w.rightY = ty + (tx - ux);
	return w;
}

// The in-place wrappers of D2R's client curse (cltdofunc 30) and client start 18 (cltstfunc 18) run D2R's function only for
// a row with a client missile: D2R asserts "nMissile >= 0 && nMissile < NumMissileStats" (SkillsNec.cpp) for one without,
// then draws nothing. Median 2012 rows without one (curses, Mon Hit / Kill Monster Effect 551 / 552, ...) draw nothing in
// 1.13c either (bug #6).
constexpr auto HasClientMissile(int32_t missile, int32_t missileRows) noexcept -> bool {
	return missile >= 0 && missile < missileRows;
}

// D2R's area applier of the server aura functions (0x4327d0 -> 0x4398b0) asserts "nRadius > 0" (D2Game Skills.cpp:420) and
// applies nothing when the skill's aurarangecalc gives 0 or less. Median 2012's monster property auras leave it blank (Belial's
// monprop `aura` 281 Laz Resist Aura, srvdofunc 65; bug #31): 1.13c applies the state to the caster and nobody else. The guard
// skips the call for such a radius (same effect, no assert; an AreaAuraHook).
constexpr auto AreaAuraRuns(int32_t radius) noexcept -> bool {
	return radius >= 1;
}

}  // namespace client_skills

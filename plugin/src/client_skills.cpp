// Client skill "do" functions of Median XL 2012 that D2R no longer has (docs/plugin-plan.md section 2, item A).
//
// Rock Shock (skills.txt row 28) and ParasiteSkill (row 408) are copies of 1.13c's Lightning Strike row: srvdofunc 14 and
// cltdofunc 22. D2R's Lightning Strike row has a blank cltdofunc and D2R's slot 22 is not 1.13c's function, so
// tools/idmap.py moves the two rows to client slot 113 (free in D2R: 110-129) and this file fills it.
//
// The function is a CltDoWall rebuild of D2Sigma's client
// 22 (0x100a7fa0) on D2R's functions. It is not proven to be 1.13c's D2Client function 22: D2Sigma replaced that table
// entry with its own code, and there is no 1.13c D2Client decompile. See docs/plugin-plan.md 2.1 for what differs and the
// game check `rockshock` that has to settle it. Only CltDoWall comes over; nothing else of sigma_skills.cpp.
#include "client_skills.h"

#include "client_skills_logic.h"
#include "d2r.h"

#include <windows.h>

#include <cstdio>
#include <cstring>

namespace {

using d2r::At;
using d2r::Unit;

using CltDoFn = int64_t (*)(Unit* unit, int32_t skill, int32_t level);

volatile LONG g_wallCalls = 0;

// Two cltmissilea placed on the skill's target point, moved within aurarangecalc of the caster, flying out perpendicular
// to the cast direction (flags 0x21). Not ported: D2Sigma's collision test of the spot for the missile's
// size (D2Common 10303, mask 5) and its town check. cltmissileb/c are not read (both 2012 rows repeat cltmissilea there).
auto CltDoWall(Unit* unit, int32_t skillId, int32_t level) noexcept -> int64_t {
	InterlockedIncrement(&g_wallCalls);
	if (unit == nullptr || d2r::api.clientMissile == nullptr || d2r::api.clientTargetXY == nullptr) {
		return 0;
	}
	const uint32_t dataFlag = d2r::api.unitDataFlag(unit);
	const uint8_t* skill = d2r::api.getSkillRecord(dataFlag, skillId);
	if (skill == nullptr) {
		return 0;
	}
	const int32_t missile = At<int16_t>(skill, d2r::SkCltMissileA);
	if (missile < 0 || missile >= d2r::api.missileCount(dataFlag)) {
		return 0;
	}
	int32_t ux = 0, uy = 0, tx = 0, ty = 0;
	if (!d2r::UnitXY(unit, &ux, &uy) || d2r::api.clientTargetXY(unit, &tx, &ty) == 0 || (tx == 0 && ty == 0)) {
		return 0;
	}
	const int32_t range = d2r::api.evalSkillCalc(dataFlag, unit, At<int32_t>(skill, d2r::SkAuraRangeCalc), skillId, level);
	const client_skills::Wall w = client_skills::WallFrom(ux, uy, tx, ty, range);
	d2r::MissileParams params;
	std::memset(&params, 0, sizeof(params));
	params.flags = 0x21;
	params.owner = unit;
	params.missile = missile;
	params.x = w.x;
	params.y = w.y;
	params.skill = skillId;
	params.skillLevel = level;
	params.targetX = w.leftX;
	params.targetY = w.leftY;
	d2r::api.clientMissile(&params, 0);
	params.targetX = w.rightX;
	params.targetY = w.rightY;
	d2r::api.clientMissile(&params, 0);
	return 1;
}

struct ClientSlot {
	int slot;
	CltDoFn function;
	const char* name;
};
constexpr ClientSlot ClientFunctions[] = {
	{CltDoWallSlot, CltDoWall, "client wall (1.13c cltdofunc 22: Rock Shock, ParasiteSkill)"},
};

// --- client functions that need a client missile (bug #6) -----------------------------------------------------------------
// D2R's client curse (cltdofunc 30, 0x2b05d0, reads cltmissilea) and client start 18 (cltstfunc 18, 0x2b0df0, reads
// cltmissilec) assert "nMissile >= 0 && nMissile < NumMissileStats" (D2Client SkillsNec.cpp) when the row has no client missile,
// then draw nothing. Median 2012 has 21 cltdofunc-30 rows without cltmissilea and 20 cltstfunc-18 rows without cltmissilec
// (curses such as Amplify Damage, and the monster rows Mon Hit / Kill Monster Effect 551 / 552 that run when monsters, e.g. the
// ones the hit-6 summoning missiles spawn, hit or kill each other): 1.13c draws nothing for them either. Wrapped in place, as
// CltDoCurse / CltStMissileC: without a client missile return 1 (D2R's own result) and skip the
// call, with one run D2R's function unchanged. No visual is added.
CltDoFn g_cltDoCurse = nullptr;
CltDoFn g_cltStMissileC = nullptr;
volatile LONG g_noMissileSkips = 0;

auto ClientMissileOf(Unit* unit, int32_t skillId, int offset) noexcept -> bool {
	const uint32_t dataFlag = d2r::api.unitDataFlag(unit);
	const uint8_t* skill = d2r::api.getSkillRecord(dataFlag, skillId);
	return skill != nullptr && client_skills::HasClientMissile(At<int16_t>(skill, offset), d2r::api.missileCount(dataFlag));
}

auto CltDoCurse(Unit* unit, int32_t skillId, int32_t level) noexcept -> int64_t {
	if (unit == nullptr || g_cltDoCurse == nullptr) {
		return 0;
	}
	if (!ClientMissileOf(unit, skillId, d2r::SkCltMissileA)) {
		InterlockedIncrement(&g_noMissileSkips);
		return 1;
	}
	g_cltDoCurse(unit, skillId, level);
	return 1;
}

auto CltStMissileC(Unit* unit, int32_t skillId, int32_t level) noexcept -> int64_t {
	if (unit == nullptr || g_cltStMissileC == nullptr) {
		return 0;
	}
	if (!ClientMissileOf(unit, skillId, d2r::SkCltMissileC)) {
		InterlockedIncrement(&g_noMissileSkips);
		return 1;
	}
	return g_cltStMissileC(unit, skillId, level);
}

// Client start 19 (0x2b1290) is the same kind (it reads cltmissilec; SkillsNec.cpp:164 without one, bug #60): Median's Totemic
// Sacrifices (cltstfunc 19, no cltmissilec) is a totemZ skill, and the assert was followed by a hang of the game when the monster
// first cast it. Without a client missile D2R's function returned 0 after the assert; the wrapper returns 1 as for slot 18.
CltDoFn g_cltStMissileC19 = nullptr;

auto CltStMissileC19(Unit* unit, int32_t skillId, int32_t level) noexcept -> int64_t {
	if (unit == nullptr || g_cltStMissileC19 == nullptr) {
		return 0;
	}
	if (!ClientMissileOf(unit, skillId, d2r::SkCltMissileC)) {
		InterlockedIncrement(&g_noMissileSkips);
		return 1;
	}
	return g_cltStMissileC19(unit, skillId, level);
}

// Bug #31: D2R's area applier asserts "nRadius > 0" for an aura whose aurarangecalc is blank (client_skills_logic.h AreaAuraRuns).
constexpr uint64_t RvaAreaAura = 0x4327d0;
// MOV [RSP+0x10],RBX / MOV [RSP+0x18],RBP / MOV [RSP+0x20],RSI / PUSH RDI / SUB RSP,0x60
constexpr uint8_t AreaAuraEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x10, 0x48, 0x89, 0x6c, 0x24, 0x18,
                                     0x48, 0x89, 0x74, 0x24, 0x20, 0x57, 0x48, 0x83, 0xec, 0x60};
using AreaAuraFn = void (*)(void*, void*, uint32_t, uint32_t, int32_t radius, uint32_t, void*, void*, uint32_t, void*, uint32_t);
AreaAuraFn g_areaAura = nullptr;
volatile LONG g_areaAuraSkips = 0;
void AreaAuraHook(void* game, void* unit, uint32_t a, uint32_t b, int32_t radius, uint32_t flags, void* callback, void* context,
                  uint32_t mode, void* file, uint32_t line) noexcept {
	if (!client_skills::AreaAuraRuns(radius)) {
		InterlockedIncrement(&g_areaAuraSkips);
		return;
	}
	g_areaAura(game, unit, a, b, radius, flags, callback, context, mode, file, line);
}

}  // namespace

auto InstallClientNoMissile(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int {
	d2r::Bind(context->exeBase);
	struct Wrap {
		uint64_t table;
		int slot;
		uint64_t rva;
		CltDoFn* original;
		CltDoFn replacement;
		const char* name;
	};
	const Wrap wraps[] = {{d2r::CltDoTable, d2r::CltDoCurseSlot, d2r::RvaCltDoCurse, &g_cltDoCurse, &CltDoCurse, "cltdofunc 30 curse"},
	                      {d2r::CltStTable, d2r::CltStMissileCSlot, d2r::RvaCltStMissileC, &g_cltStMissileC, &CltStMissileC, "cltstfunc 18 start"},
	                      {d2r::CltStTable, d2r::CltStMissileC19Slot, d2r::RvaCltStMissileC19, &g_cltStMissileC19, &CltStMissileC19, "cltstfunc 19 start"}};
	int installed = 0;
	size_t used = 0;
	for (const Wrap& w : wraps) {
		const uint64_t at = w.table + static_cast<uint64_t>(w.slot) * 8;
		const uint64_t have = *reinterpret_cast<const volatile uint64_t*>(context->exeBase + at);
		*w.original = reinterpret_cast<CltDoFn>(context->exeBase + w.rva);
		// Only when the slot still holds D2R's own function (the expected old value of the write).
		const bool ok = have == context->exeBase + w.rva &&
		                context->PatchWriteU64(at, &have, sizeof(have), reinterpret_cast<uint64_t>(w.replacement));
		installed += ok ? 1 : 0;
		if (used < reportSize) {
			const int n = std::snprintf(report + used, reportSize - used, "%s%s without client missile%s", used ? "; " : "", w.name, ok ? "" : " FAILED");
			used += n > 0 ? static_cast<size_t>(n) : 0;
		}
	}
	const bool areaOk = context->InstallInlineHook(RvaAreaAura, AreaAuraEntry, sizeof(AreaAuraEntry), reinterpret_cast<void*>(&AreaAuraHook),
	                                               reinterpret_cast<void**>(&g_areaAura));
	installed += areaOk ? 1 : 0;
	if (used < reportSize) {
		const int n = std::snprintf(report + used, reportSize - used, "%sarea aura without radius%s", used ? "; " : "", areaOk ? "" : " FAILED");
		used += n > 0 ? static_cast<size_t>(n) : 0;
	}
	return installed;
}

auto AreaAuraSkips() noexcept -> long {
	return g_areaAuraSkips;
}

auto ClientNoMissileSkips() noexcept -> long {
	return g_noMissileSkips;
}

auto InstallClientSkills(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int {
	d2r::Bind(context->exeBase);
	static constexpr uint8_t Empty[8] = {};
	const int32_t bound = *reinterpret_cast<const volatile int32_t*>(context->exeBase + d2r::CltDoBound);
	int installed = 0;
	size_t used = 0;
	for (const ClientSlot& f : ClientFunctions) {
		const uint64_t rva = d2r::CltDoTable + static_cast<uint64_t>(f.slot) * 8;
		// The slot must be below the dispatcher's bound and still empty (expected old value 0): else nothing is written.
		const bool ok = f.slot < bound && context->PatchWriteU64(rva, Empty, sizeof(Empty), reinterpret_cast<uint64_t>(f.function));
		installed += ok ? 1 : 0;
		if (used < reportSize) {
			const int n = std::snprintf(report + used, reportSize - used, "%scltdofunc %d %s%s", used ? "; " : "", f.slot, f.name,
			                            ok ? "" : (f.slot < bound ? " FAILED (slot not empty)" : " FAILED (above the table bound)"));
			used += n > 0 ? static_cast<size_t>(n) : 0;
		}
	}
	return installed;
}

auto ClientWallCalls() noexcept -> long {
	return g_wallCalls;
}

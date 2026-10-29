// D2R game image interface for mxl2012-core: RVAs, record offsets and the few game functions the plugin calls.
// All values are for one image (D2R 3.3.0 build 93847 under D2RLoader 1.3.1, PE timestamp 0x6ab3782c); they come
// from a Ghidra analysis of the dumped image. Nothing here may be used unless mxl2012_core.cpp's image check passed.
//
// Trimmed to what mxl2012-core v0.1 uses (docs/plugin-plan.md section 11: the D2Sigma parts and
// their calls are not carried over).
#pragma once

#include <cstddef>
#include <cstdint>

namespace d2r {

struct Game;
struct Unit;

// --- Function tables (8-byte pointers; the bound is the int32 count the dispatcher accepts) -------------------------
// Skill client "do" (skills.txt cltdofunc, record +0x14a): (unit, skill, level) -> non-zero when it ran; dispatcher
// 0x216d20. D2R fills 0-109; 110-129 are free.
inline constexpr uint64_t CltDoTable = 0x235f7d0;
inline constexpr uint64_t CltDoBound = 0x235f7c4;
inline constexpr int CltDoSlots = 130;
// Skill client "start" (skills.txt cltstfunc, record +0x148): same signature; bound at 0x235f7c0.
inline constexpr uint64_t CltStTable = 0x235f590;
inline constexpr uint64_t CltStBound = 0x235f7c0;
// D2R's client curse (cltdofunc 30) and client start 18: both read a client missile and assert without one (bug #6).
inline constexpr int CltDoCurseSlot = 30;
inline constexpr uint64_t RvaCltDoCurse = 0x2b05d0;     // reads cltmissilea
inline constexpr int CltStMissileCSlot = 18;
inline constexpr uint64_t RvaCltStMissileC = 0x2b0df0;  // reads cltmissilec
// Client start 19 (D2R: the Buckshot start, 0x2b1290) reads cltmissilec too and asserts at SkillsNec.cpp:164 without one (bug #60).
inline constexpr int CltStMissileC19Slot = 19;
inline constexpr uint64_t RvaCltStMissileC19 = 0x2b1290;
// Missile client "do" (missiles.txt pCltDoFunc, record +0x28): (missile, float) ; the client missile tick 0x1ba040 calls
// every index below the bound with no null check (bug #24b).
inline constexpr uint64_t MissileCltDoTable = 0x2358430;
inline constexpr uint64_t MissileCltDoBound = 0x2358a60;
// Missile client hit (pCltHitFunc, record +0x2a).
inline constexpr uint64_t MissileCltHitTable = 0x2358710;
inline constexpr uint64_t MissileCltHitBound = 0x2358a64;
// Missile server hit (pSrvHitFunc, record +0x2e): (game, missile, target or null); dispatcher 0x464ac0 calls
// 0 < index < bound with no null check. 61-70 are free in D2R.
inline constexpr uint64_t SrvHitTable = 0x2391030;
inline constexpr uint64_t SrvHitBound = 0x2391404;
// Skill server "do" (srvdofunc), 191 slots.
inline constexpr uint64_t SrvDoTable = 0x238ea00;
inline constexpr int SrvDoSlots = 191;

// --- Functions (RVAs) ----------------------------------------------------------------------------------------------
inline constexpr uint64_t RvaGetSkillRecord = 0x97790;    // (dataFlag, skillId) -> skills record
inline constexpr uint64_t RvaEvalSkillCalc = 0x3b5160;    // (dataFlag, unit, calc, skillId, level) -> value
inline constexpr uint64_t RvaCreateMissile = 0x5371a0;    // (game, &params) -> missile unit (server)
inline constexpr uint64_t RvaMissileRecord = 0x166040;    // (dataFlag, missileId) -> missiles record or null
inline constexpr uint64_t RvaMissileCount = 0x1b89a0;     // (dataFlag) -> rows in missiles.txt
inline constexpr uint64_t RvaUnitDataFlag = 0x34a0e0;     // (unit) -> data flag byte, as client functions read it
inline constexpr uint64_t RvaClientMissile = 0x1b7760;    // (&params, 0): client missile (D2R's client Charged Strike uses it)
inline constexpr uint64_t RvaClientTargetXY = 0x214c80;   // (unit, &x, &y) -> non-zero: the skill's target point (client)

// --- Offsets ------------------------------------------------------------------------------------------------------
inline constexpr int GameDataFlag = 0x106;  // byte passed to the data-table getters

inline constexpr int UnitType = 0x00;  // 0 player, 1 monster, 2 object, 3 missile, 4 item, 5 tile
inline constexpr int UnitClass = 0x04;
inline constexpr int UnitPath = 0x38;  // dynamic path (x at +0x2, y at +0x6) or static path (x +0x10, y +0x14)

// skills.txt record (748 bytes)
inline constexpr int SkAuraRangeCalc = 0x84;
inline constexpr int SkCltMissile = 0x13e;  // int16 cltmissile, then cltmissilea/b/c at +0x140/+0x142/+0x144
inline constexpr int SkCltMissileA = 0x140;
inline constexpr int SkCltMissileC = 0x144;
inline constexpr int SkCltStFunc = 0x148;   // int16
inline constexpr int SkCltDoFunc = 0x14a;   // int16
inline constexpr int SkCalc1 = 0x190;
inline constexpr int SkItemEffect = 0x20a;  // uint16 ItemEffect (0 = the skill is no item event skill, bug #40)

// missiles.txt record
inline constexpr int MisCltDoFunc = 0x28;   // int16 pCltDoFunc
inline constexpr int MisCltHitFunc = 0x2a;  // int16 pCltHitFunc
inline constexpr int MisSrvHitFunc = 0x2e;  // int16 pSrvHitFunc

// Missile creation parameters. Same fields as 1.10's 0x5c-byte block, 0x10 further on after the three pointers.
struct MissileParams {
	uint32_t flags;          // 0x00
	uint32_t pad04;
	Unit* owner;             // 0x08
	Unit* origin;            // 0x10
	Unit* target;            // 0x18
	int32_t missile;         // 0x20
	int32_t x, y;            // 0x24 (0: the origin's position)
	int32_t targetX, targetY;// 0x2c
	int32_t gfxArg;          // 0x34
	int32_t velocity;        // 0x38
	int32_t skill;           // 0x3c
	int32_t skillLevel;      // 0x40
	int32_t loops;           // 0x44
	int32_t unk48;           // 0x48
	int32_t frame;           // 0x4c
	int32_t activateFrame;   // 0x50
	int32_t attBonus;        // 0x54 (1.10 +0x44)
	int32_t unk58;           // 0x58
	int32_t range;           // 0x5c (1.10 +0x4c): used with flag 0x8000
	uint8_t unk60[0x68 - 0x60];
	int32_t seed;            // 0x68: D2R's state-22 trail passes stat 202 of the state list (melt_trail.cpp)
	int32_t unk6c;           // 0x6c
	int32_t initKind;        // 0x70: replaces 1.10's init function pointer (1 = charged-strike bolt, 4 = multishot)
	int32_t initArg;         // 0x74: e.g. the missile's index
	uint8_t rest[0xa0 - 0x78];
};
static_assert(sizeof(MissileParams) == 0xa0);
static_assert(offsetof(MissileParams, missile) == 0x20);
static_assert(offsetof(MissileParams, targetX) == 0x2c);
static_assert(offsetof(MissileParams, skill) == 0x3c);
static_assert(offsetof(MissileParams, attBonus) == 0x54);
static_assert(offsetof(MissileParams, range) == 0x5c);
static_assert(offsetof(MissileParams, seed) == 0x68);
static_assert(offsetof(MissileParams, initKind) == 0x70);

// --- Calls --------------------------------------------------------------------------------------------------------
using GetSkillRecordFn = uint8_t* (*)(uint32_t dataFlag, int32_t skillId);
using EvalSkillCalcFn = int32_t (*)(uint32_t dataFlag, Unit* unit, int32_t calc, int32_t skillId, int32_t level);
using CreateMissileFn = Unit* (*)(Game* game, MissileParams* params);
using MissileRecordFn = const uint8_t* (*)(uint32_t dataFlag, int32_t missileId);
using MissileCountFn = int32_t (*)(uint32_t dataFlag);
using UnitDataFlagFn = uint8_t (*)(Unit* unit);
using ClientMissileFn = Unit* (*)(MissileParams* params, int32_t zero);
using ClientTargetXYFn = int32_t (*)(Unit* unit, int32_t* x, int32_t* y);

// Bound by Bind() from the image base.
struct Api {
	GetSkillRecordFn getSkillRecord;
	EvalSkillCalcFn evalSkillCalc;
	CreateMissileFn createMissile;
	MissileRecordFn missileRecord;
	MissileCountFn missileCount;
	UnitDataFlagFn unitDataFlag;
	ClientMissileFn clientMissile;
	ClientTargetXYFn clientTargetXY;
};
extern Api api;
void Bind(uint64_t exeBase) noexcept;

// --- Helpers ------------------------------------------------------------------------------------------------------
template <typename T>
inline auto At(const void* p, int offset) noexcept -> T {
	return *reinterpret_cast<const T*>(static_cast<const uint8_t*>(p) + offset);
}

inline auto DataFlag(Game* game) noexcept -> uint32_t {
	return At<uint8_t>(game, GameDataFlag);
}

// Position as 0x432b70 reads it.
inline auto UnitXY(Unit* unit, int32_t* x, int32_t* y) noexcept -> bool {
	const int32_t type = At<int32_t>(unit, UnitType);
	const uint8_t* path = At<const uint8_t*>(unit, UnitPath);
	if (path == nullptr) {
		return false;
	}
	if (type == 2 || type == 4 || type == 5) {
		*x = At<int32_t>(path, 0x10);
		*y = At<int32_t>(path, 0x14);
	} else {
		*x = At<uint16_t>(path, 0x2);
		*y = At<uint16_t>(path, 0x6);
	}
	return true;
}

}  // namespace d2r

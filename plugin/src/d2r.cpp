#include "d2r.h"

namespace d2r {

Api api {};

void Bind(uint64_t exeBase) noexcept {
	api.getSkillRecord = reinterpret_cast<GetSkillRecordFn>(exeBase + RvaGetSkillRecord);
	api.evalSkillCalc = reinterpret_cast<EvalSkillCalcFn>(exeBase + RvaEvalSkillCalc);
	api.createMissile = reinterpret_cast<CreateMissileFn>(exeBase + RvaCreateMissile);
	api.missileRecord = reinterpret_cast<MissileRecordFn>(exeBase + RvaMissileRecord);
	api.missileCount = reinterpret_cast<MissileCountFn>(exeBase + RvaMissileCount);
	api.unitDataFlag = reinterpret_cast<UnitDataFlagFn>(exeBase + RvaUnitDataFlag);
	api.clientMissile = reinterpret_cast<ClientMissileFn>(exeBase + RvaClientMissile);
	api.clientTargetXY = reinterpret_cast<ClientTargetXYFn>(exeBase + RvaClientTargetXY);
}

}  // namespace d2r

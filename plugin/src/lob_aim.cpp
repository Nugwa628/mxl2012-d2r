// Laughing Ghost explodes where the player clicked, no farther than its old range (docs/bugs.md #614; off word lobaim).
//
// The skill's row sets `lob` (tools/txt_migrate.py lob_skills), so D2R makes its missile on its lob path: frames from the
// distance to the target point. Both missile creates are hooked at their entry (server 0x5371a0, client 0x1b7760): for a lob
// missile made for the skill (params +0x3c, both sides pass it) whose target lies past the missile's Range, the target point is moved back along the
// line (lob_aim_logic.h) on a copy of the parameters, then D2R's create runs. Every other missile goes through untouched.
#include "lob_aim.h"

#include "d2r.h"
#include "lob_aim_logic.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

using d2r::Game;
using d2r::MissileParams;
using d2r::Unit;

using ServerFn = Unit* (*)(Game* game, MissileParams* params);
using ClientFn = Unit* (*)(MissileParams* params, int32_t zero);
using RangeCalcFn = int32_t (*)(uint8_t dataFlag, Unit* missile, Unit* owner, uint32_t calc, int32_t missileId, int32_t level);
ServerFn g_server = nullptr;
ClientFn g_client = nullptr;
uint64_t g_base = 0;
volatile LONG g_serverMoved = 0;
volatile LONG g_clientMoved = 0;
volatile LONG g_seen = 0;
const D2RL::PluginContext* g_context = nullptr;
volatile LONG g_logged = 0;

// The first casts go to the log: where from, where to, where it lands.
void Note(uint32_t dataFlag, const MissileParams* p, int32_t ox, int32_t oy, int32_t tx, int32_t ty, int32_t nx, int32_t ny, int32_t v, int32_t range) noexcept {
	if (g_context == nullptr || InterlockedIncrement(&g_logged) > 8) {
		return;
	}
	char line[256];
	std::snprintf(line, sizeof(line), "mxl2012-core: lobaim flags 0x%x (data %u) missile %d level %d from %d,%d to %d,%d -> %d,%d (speed %d, range %d frames)",
	              p->flags, dataFlag, p->missile, p->skillLevel, ox, oy, tx, ty, nx, ny, v, range);
	g_context->LogInfo(line);
}

// The copy with the clamped target in `out`; false when the missile is not the aimed one or its target is in range.
auto Clamp(uint32_t dataFlag, const MissileParams* p, MissileParams* out) noexcept -> bool {
	if (p == nullptr || (p->flags & lob_aim::FlagLob) == 0) {
		return false;
	}
	if (p->skill != lob_aim::Skill || p->owner == nullptr || p->missile < 0) {
		return false;
	}
	InterlockedIncrement(&g_seen);
	const uint8_t* rec = d2r::api.missileRecord(dataFlag, p->missile);
	if (rec == nullptr) {
		return false;
	}
	int32_t ox = 0, oy = 0;
	if ((p->flags & lob_aim::FlagOriginXY) != 0) {
		ox = p->x;
		oy = p->y;
	} else if (!d2r::UnitXY(p->origin != nullptr ? p->origin : p->owner, &ox, &oy)) {
		return false;
	}
	int32_t tx = 0, ty = 0;
	const bool unitTarget = p->target != nullptr && p->target != p->owner;
	if (unitTarget) {
		if (!d2r::UnitXY(p->target, &tx, &ty)) {
			return false;
		}
	} else if ((p->flags & lob_aim::FlagRelTarget) != 0) {
		tx = ox + p->targetX;
		ty = oy + p->targetY;
	} else if ((p->flags & lob_aim::FlagAbsTarget) != 0) {
		tx = p->targetX;
		ty = p->targetY;
	} else {
		return false;
	}
	const int32_t v = lob_aim::Velocity(p->flags, p->velocity, d2r::At<uint8_t>(rec, lob_aim::RecVel), d2r::At<uint8_t>(rec, lob_aim::RecVelLev), p->skillLevel);
	const int32_t range = reinterpret_cast<RangeCalcFn>(g_base + lob_aim::RvaRangeCalc)(static_cast<uint8_t>(dataFlag), nullptr, p->owner,
	                                                                                    d2r::At<uint32_t>(rec, lob_aim::RecRangeCalc), p->missile, p->skillLevel);
	const int32_t tx0 = tx, ty0 = ty;
	const bool moved = lob_aim::ClampTarget(ox, oy, &tx, &ty, v, range);
	Note(dataFlag, p, ox, oy, tx0, ty0, tx, ty, v, range);
	if (!moved) {
		return false;
	}
	std::memcpy(out, p, sizeof(*out));
	out->target = nullptr;  // a monster past the range: the ghost goes its way and explodes at the range, as before
	out->flags = (p->flags & ~lob_aim::FlagRelTarget) | lob_aim::FlagAbsTarget;
	out->targetX = tx;
	out->targetY = ty;
	return true;
}

auto ServerHook(Game* game, MissileParams* params) noexcept -> Unit* {
	MissileParams moved;
	if (game != nullptr && Clamp(d2r::DataFlag(game), params, &moved)) {
		InterlockedIncrement(&g_serverMoved);
		return g_server(game, &moved);
	}
	return g_server(game, params);
}

auto ClientHook(MissileParams* params, int32_t zero) noexcept -> Unit* {
	MissileParams moved;
	if (params != nullptr && (params->flags & lob_aim::FlagLob) != 0 && params->owner != nullptr &&
	    Clamp(d2r::api.unitDataFlag(params->owner), params, &moved)) {
		InterlockedIncrement(&g_clientMoved);
		return g_client(&moved, zero);
	}
	return g_client(params, zero);
}

}  // namespace

auto InstallLobAim(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int {
	d2r::Bind(context->exeBase);
	g_base = context->exeBase;
	g_context = context;
	const bool server = context->InstallInlineHook(lob_aim::RvaServer, lob_aim::ServerEntry, sizeof(lob_aim::ServerEntry),
	                                               reinterpret_cast<void*>(&ServerHook), reinterpret_cast<void**>(&g_server));
	const bool client = context->InstallInlineHook(lob_aim::RvaClient, lob_aim::ClientEntry, sizeof(lob_aim::ClientEntry),
	                                               reinterpret_cast<void*>(&ClientHook), reinterpret_cast<void**>(&g_client));
	std::snprintf(report, reportSize, "skill %d (Laughing Ghost) lands at the click, capped at its missile's range: server 0x5371a0%s, client 0x1b7760%s",
	              lob_aim::Skill, server ? "" : " FAILED", client ? "" : " FAILED");
	return (server ? 1 : 0) + (client ? 1 : 0);
}

void LobAimCounts(long* seen, long* server, long* client) noexcept {
	*seen = g_seen;
	*server = g_serverMoved;
	*client = g_clientMoved;
}

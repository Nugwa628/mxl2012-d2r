// Laughing Ghost and Rising Dawn land where the player clicked, up to the screen edge (docs/bugs.md
// #614, #618; off word lobaim).
//
// Their skills.txt rows set `lob` (tools/txt_migrate.py lob_skills), so D2R makes the missile on its lob path: frames from
// the distance to the target point (lob_aim_logic.h). Both missile creates are hooked at their entry (server 0x5371a0,
// client 0x1b7760): for a lob missile of one of the two skills (params +0x3c) the target becomes a fixed world point on a
// copy of the parameters, then D2R's create runs. Every other missile goes through untouched.
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
ServerFn g_server = nullptr;
ClientFn g_client = nullptr;
volatile LONG g_serverMoved = 0;
volatile LONG g_clientMoved = 0;
volatile LONG g_seen = 0;
const D2RL::PluginContext* g_context = nullptr;
volatile LONG g_logged = 0;

// The first casts go to the log: where from, where to, where it lands.
void Note(uint32_t dataFlag, const MissileParams* p, int32_t ox, int32_t oy, int32_t tx, int32_t ty, int32_t nx, int32_t ny, int32_t v) noexcept {
	if (g_context == nullptr || InterlockedIncrement(&g_logged) > 64) {
		return;
	}
	char line[256];
	std::snprintf(line, sizeof(line), "mxl2012-core: lobaim flags 0x%x (data %u) missile %d level %d from %d,%d to %d,%d -> %d,%d (speed %d)",
	              p->flags, dataFlag, p->missile, p->skillLevel, ox, oy, tx, ty, nx, ny, v);
	g_context->LogInfo(line);
}

// The copy with the target as a world point in `out`; false when the missile is not one of the two skills' lob missiles.
auto Aim(uint32_t dataFlag, const MissileParams* p, MissileParams* out) noexcept -> bool {
	if (p == nullptr || (p->flags & lob_aim::FlagLob) == 0) {
		return false;
	}
	if (!lob_aim::IsAimedSkill(p->skill) || p->owner == nullptr || p->missile < 0) {
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
	} else {
		tx = p->targetX;
		ty = p->targetY;
		if (!lob_aim::ResolvePoint(p->flags, ox, oy, &tx, &ty)) {
			return false;
		}
	}
	const int32_t v = lob_aim::Velocity(p->flags, p->velocity, d2r::At<uint8_t>(rec, lob_aim::RecVel), d2r::At<uint8_t>(rec, lob_aim::RecVelLev), p->skillLevel);
	Note(dataFlag, p, ox, oy, tx, ty, tx, ty, v);
	std::memcpy(out, p, sizeof(*out));
	out->target = nullptr;  // a monster target: land where it stood at the cast
	out->flags = (p->flags & ~lob_aim::FlagRelTarget) | lob_aim::FlagAbsTarget;
	out->targetX = tx;
	out->targetY = ty;
	return true;
}

auto ServerHook(Game* game, MissileParams* params) noexcept -> Unit* {
	MissileParams moved;
	if (game != nullptr && Aim(d2r::DataFlag(game), params, &moved)) {
		InterlockedIncrement(&g_serverMoved);
		return g_server(game, &moved);
	}
	return g_server(game, params);
}

auto ClientHook(MissileParams* params, int32_t zero) noexcept -> Unit* {
	MissileParams moved;
	if (params != nullptr && (params->flags & lob_aim::FlagLob) != 0 && params->owner != nullptr &&
	    Aim(d2r::api.unitDataFlag(params->owner), params, &moved)) {
		InterlockedIncrement(&g_clientMoved);
		return g_client(&moved, zero);
	}
	return g_client(params, zero);
}

}  // namespace

auto InstallLobAim(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int {
	d2r::Bind(context->exeBase);
	g_context = context;
	const bool server = context->InstallInlineHook(lob_aim::RvaServer, lob_aim::ServerEntry, sizeof(lob_aim::ServerEntry),
	                                               reinterpret_cast<void*>(&ServerHook), reinterpret_cast<void**>(&g_server));
	const bool client = context->InstallInlineHook(lob_aim::RvaClient, lob_aim::ClientEntry, sizeof(lob_aim::ClientEntry),
	                                               reinterpret_cast<void*>(&ClientHook), reinterpret_cast<void**>(&g_client));
	std::snprintf(report, reportSize, "skills 453 / 512 (Laughing Ghost, Rising Dawn) land at the click: server 0x5371a0%s, client 0x1b7760%s",
	              server ? "" : " FAILED", client ? "" : " FAILED");
	return (server ? 1 : 0) + (client ? 1 : 0);
}

void LobAimCounts(long* seen, long* server, long* client) noexcept {
	*seen = g_seen;
	*server = g_serverMoved;
	*client = g_clientMoved;
}

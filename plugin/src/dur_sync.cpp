// A worn item's durability loss shown on the client (docs/bugs.md #433, off word dursync, lane dursync).
//
// D2R's wear dispatcher stores the layer argument of its durability update (packet 0x3e, sender 0x47a190) with a 16-bit
// store, so the upper bytes of that argument slot keep stack garbage, and the update D2RLoader's sender path passes on never
// takes on the client (dur_sync_logic.h has the instructions and the evidence). The patch stores the whole slot. The loss
// branch, the shared send behind it and the patched store are compared byte for byte first.
#include "dur_sync.h"

#include "dur_sync_logic.h"

#include <cstdio>
#include <cstring>

auto InstallDurSync(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	const auto* base = reinterpret_cast<const uint8_t*>(context->exeBase);
	const bool same = std::memcmp(base + dur_sync::ExpectedRva, dur_sync::Expected, dur_sync::ExpectedSize) == 0 &&
	                  std::memcmp(base + dur_sync::SendRva, dur_sync::Send, sizeof(dur_sync::Send)) == 0;
	const bool ok = same && context->PatchBytes(dur_sync::PatchRva, dur_sync::Old, dur_sync::PatchSize, dur_sync::New, sizeof(dur_sync::New));
	std::snprintf(report, reportSize, "worn items' durability loss reaches the client (layer argument stored whole at 0x441c4b)%s",
	              ok ? "" : (same ? " FAILED (patch refused)" : " FAILED (bytes differ, left as D2R)"));
	return ok;
}

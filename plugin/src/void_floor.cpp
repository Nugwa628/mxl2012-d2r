// The Ancient Tunnels' void in HD (lane tunnelfloor; on by default, off word `void65`).
//
// D2R's HD ground plane is placed under every room except on level 74 (void_floor_logic.h has the instructions). Median's
// level 65 (belial.ds1) is an Arcane platform over the void, and the plane draws stone over that void. The patch skips the
// plane on level 65 too; the platform's floor then has to come from the HD scene (tools/walls_hd.py, built by default,
// MXL2012_BELIAL_WALKWAY=0 leaves them out: D2R's Sanct walkway meshes). Every byte it touches, and the ones round it, are compared first.
#include "void_floor.h"

#include "void_floor_logic.h"

#include <windows.h>

#include <cstdio>
#include <cstring>

auto InstallVoidFloor(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	using namespace void_floor;
	const auto* image = reinterpret_cast<const uint8_t*>(context->exeBase);
	const bool same = std::memcmp(image + SiteRva, Site, sizeof(Site)) == 0 && std::memcmp(image + LoadRva, Load, sizeof(Load)) == 0 &&
	                  std::memcmp(image + NextRoomRva, NextRoom, sizeof(NextRoom)) == 0 && std::memcmp(image + PadRva, Pad, sizeof(Pad)) == 0;
	auto* stub = same ? static_cast<uint8_t*>(VirtualAlloc(nullptr, StubSize, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)) : nullptr;
	bool ok = stub != nullptr;
	if (ok) {
		const Stub bytes = StubBytes(context->exeBase + PlaneRva, context->exeBase + NextRoomRva);
		std::memcpy(stub, bytes.bytes, StubSize);
		DWORD old = 0;
		ok = VirtualProtect(stub, StubSize, PAGE_EXECUTE_READ, &old) != 0;
		FlushInstructionCache(GetCurrentProcess(), stub, StubSize);
	}
	// the pad first, then the site that makes it live
	if (ok) {
		const AbsJump pad = AbsJumpBytes(reinterpret_cast<uint64_t>(stub));
		const SiteBytes site = SitePatch();
		ok = context->PatchBytes(PadRva, Pad, sizeof(Pad), pad.bytes, sizeof(pad.bytes)) &&
		     context->PatchBytes(SiteRva, Site, sizeof(Site), site.bytes, sizeof(site.bytes));
	}
	std::snprintf(report, reportSize, "void65: no HD ground plane on levels 74 and 65 (0x6b4b80 -> pad 0x6b4a22)%s",
	              ok ? "" : (same ? " FAILED (patch refused)" : " FAILED (bytes differ, left as D2R)"));
	return ok;
}

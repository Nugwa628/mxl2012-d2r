// A vendor's first-meeting greeting no longer closes a trade picked while it plays (lane bugs128, off word npcgreet).
//
// A new character's first talk with a vendor plays its greeting (Charsi: "Oh, by the way..."), and D2R shows the NPC menu
// at the same time. Trade or Gamble picked then opened the panel, but when the greeting ended D2R's speech callback opened
// the NPC menu again, which closes every panel: the trade screen shut and the vendor walked off (the same without Vendor
// Stock Refresh; seen in game, lane bugs128). 1.13c shows the menu only after the greeting. Here the menu opener called by
// the speech callback is skipped while a vendor panel is open, and the NPC state stays as the panel set it
// (npc_greet_logic.h). Everything else (other speech ends, the menu from a click) goes to D2R as it is.
#include "npc_greet.h"

#include "npc_greet_logic.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

using SpeechDoneFn = uint64_t (*)(int32_t a1, int32_t a2, int32_t a3);
using MenuOpenFn = uint64_t (*)(void* npc, int32_t flag);

SpeechDoneFn g_speechDone = nullptr;
MenuOpenFn g_menuOpen = nullptr;
volatile int32_t* g_state = nullptr;
bool g_inSpeechDone = false;
int32_t g_stateBefore = 0;
volatile LONG g_kept = 0;

uint64_t SpeechDoneHook(int32_t a1, int32_t a2, int32_t a3) {
	const bool outer = !g_inSpeechDone;
	if (outer) {
		g_stateBefore = *g_state;
		g_inSpeechDone = true;
	}
	const uint64_t r = g_speechDone(a1, a2, a3);
	if (outer) {
		g_inSpeechDone = false;
	}
	return r;
}

uint64_t MenuOpenHook(void* npc, int32_t flag) {
	if (g_inSpeechDone && npc != nullptr && npc_greet::KeepsPanel(g_stateBefore)) {
		*g_state = g_stateBefore;  // the speech callback stored 1 (the menu) just before
		InterlockedIncrement(&g_kept);
		return 0;
	}
	return g_menuOpen(npc, flag);
}

}  // namespace

auto InstallNpcGreet(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	using namespace npc_greet;
	const auto* b = reinterpret_cast<const uint8_t*>(context->exeBase);
	int32_t disp = 0;
	std::memcpy(&disp, MenuStateStore + 2, sizeof(disp));
	const bool same = std::memcmp(b + SpeechDoneRva, SpeechDoneEntry, sizeof(SpeechDoneEntry)) == 0 &&
	                  std::memcmp(b + MenuOpenRva, MenuOpenEntry, sizeof(MenuOpenEntry)) == 0 &&
	                  std::memcmp(b + MenuStateStoreRva, MenuStateStore, sizeof(MenuStateStore)) == 0 &&
	                  std::memcmp(b + MenuCallRva, MenuCall, sizeof(MenuCall)) == 0 &&
	                  std::memcmp(b + RegisterRva, Register, sizeof(Register)) == 0 &&
	                  RipTarget(MenuStateStoreRva, sizeof(MenuStateStore), disp) == StateRva;
	if (!same) {
		std::snprintf(report, reportSize, "npcgreet off: bytes differ at 0x10da20 / 0x1141d0 / 0x10dc73 / 0x10dcb7 / 0x10db4e, left as D2R");
		return false;
	}
	g_state = reinterpret_cast<volatile int32_t*>(context->exeBase + StateRva);
	if (!context->InstallInlineHook(MenuOpenRva, MenuOpenEntry, sizeof(MenuOpenEntry), reinterpret_cast<void*>(&MenuOpenHook),
	                                reinterpret_cast<void**>(&g_menuOpen))) {
		std::snprintf(report, reportSize, "npcgreet off: the NPC menu hook 0x1141d0 was refused");
		return false;
	}
	if (!context->InstallInlineHook(SpeechDoneRva, SpeechDoneEntry, sizeof(SpeechDoneEntry), reinterpret_cast<void*>(&SpeechDoneHook),
	                                reinterpret_cast<void**>(&g_speechDone))) {
		std::snprintf(report, reportSize, "npcgreet off: the speech end hook 0x10da20 was refused (the menu hook passes everything on)");
		return false;
	}
	std::snprintf(report, reportSize,
	              "npcgreet on: a greeting that ends while a vendor panel is open keeps it (speech end 0x10da20, NPC menu 0x1141d0 skipped)");
	return true;
}

auto NpcGreetKept() noexcept -> long {
	return g_kept;
}

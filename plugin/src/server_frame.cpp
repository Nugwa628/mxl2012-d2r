// The per-game server frame hook, shared: the test harness runs its queued verbs there and `spiritwarp` checks the Barbarian
// spirits there. D2RLoader refuses a second inline hook on the same address, so one hook calls each part's callback.
#include "server_frame.h"

#include "d2r.h"

#include <cstdint>

namespace {

constexpr uint64_t RvaFrame = 0x406550;  // (Game*) the per-game server frame, 25 Hz
// MOV [RSP+0x20],RSI / PUSH RBP / PUSH RDI / PUSH R15 / LEA RBP,[RSP-0x47]
constexpr uint8_t FrameEntry[] = {0x48, 0x89, 0x74, 0x24, 0x20, 0x55, 0x57, 0x41, 0x57, 0x48, 0x8d, 0x6c, 0x24, 0xb9};

using FrameFn = void (*)(d2r::Game*);
FrameFn g_original = nullptr;
bool g_tried = false;
bool g_hooked = false;
constexpr int MaxCallbacks = 8;
ServerFrameCallback g_callbacks[MaxCallbacks] = {};
volatile long g_count = 0;

void FrameHook(d2r::Game* game) {
	g_original(game);
	if (game == nullptr) {
		return;
	}
	const long n = g_count;
	for (long i = 0; i < n; ++i) {
		g_callbacks[i](game);
	}
}

}  // namespace

auto InstallServerFrame(const D2RL::PluginContext* context) noexcept -> bool {
	if (!g_tried && context != nullptr) {
		g_tried = true;
		g_hooked = context->InstallInlineHook(RvaFrame, FrameEntry, sizeof(FrameEntry), reinterpret_cast<void*>(&FrameHook),
		                                      reinterpret_cast<void**>(&g_original));
	}
	return g_hooked;
}

auto AddServerFrameCallback(ServerFrameCallback callback) noexcept -> bool {
	if (callback == nullptr || g_count >= MaxCallbacks) {
		return false;
	}
	g_callbacks[g_count] = callback;
	g_count = g_count + 1;  // published after the slot is written; parts are added at load, before any game runs
	return true;
}

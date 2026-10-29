// Crash guard for D2R's unit translation layer (docs/crash-audit.md C14; off word transguard). D2R build 93847.
//
// In long runs D2R's client has died with an access violation at D2R.exe+0x7761DC at a character switch after a
// Druid morph (Save and Exit). The function is the handler of event type 0x10 of the client's UnitTranslationLayer event loop
// (0x77a3b0 -> 0x775fc0(layer, event)): it reads RAX = *event, RBX = [RAX + 0x70] and then the byte [RBX + 0x870]. RBX held two
// 32-bit halves (a count and a capacity), not a pointer: a stale event of D2R's own queue whose payload was freed and reused. No
// plugin code is in the frame, so the cause stays D2R's; the hook only keeps the client alive: an event whose payload cannot be
// read (or whose +0x70 pointer cannot be read at its first bytes and at +0x870) is skipped and logged (first 8) with the
// payload words. VirtualQuery decides what is readable (translation_guard_logic.h).
#include "translation_guard.h"

#include "translation_guard_logic.h"

#include <windows.h>

#include <atomic>
#include <cstdint>
#include <cstdio>

namespace {

using namespace translation_guard;

using HandlerFn = void (*)(void* layer, void** event);

HandlerFn g_original = nullptr;
const D2RL::PluginContext* g_context = nullptr;
std::atomic<unsigned> g_seen{0}, g_skipped{0}, g_logged{0};

auto Readable(uint64_t p, uint64_t n) noexcept -> bool {
	MEMORY_BASIC_INFORMATION mbi{};
	if (p == 0 || VirtualQuery(reinterpret_cast<const void*>(p), &mbi, sizeof(mbi)) != sizeof(mbi) ||
	    !ReadableProtect(mbi.State == MEM_COMMIT, mbi.Protect)) {
		return false;
	}
	return InRegion(reinterpret_cast<uint64_t>(mbi.BaseAddress), mbi.RegionSize, p, n);
}

auto Load(uint64_t p) noexcept -> uint64_t {
	return *reinterpret_cast<const uint64_t*>(p);
}

void TranslationEvent(void* layer, void** event) noexcept {
	g_seen.fetch_add(1);
	uint64_t payload = 0, inner = 0;
	if (!EventSound(event, Readable, Load, &payload, &inner)) {
		g_skipped.fetch_add(1);
		if (g_context != nullptr && g_logged.fetch_add(1) < 8) {
			char line[200];
			std::snprintf(line, sizeof(line), "mxl2012-core: translation event skipped: event %p, payload %016llx, payload+0x70 %016llx (not readable memory)",
			              static_cast<void*>(event), static_cast<unsigned long long>(payload), static_cast<unsigned long long>(inner));
			g_context->LogWarn(line);
		}
		return;
	}
	g_original(layer, event);
}

}  // namespace

void TranslationGuardStats(unsigned* seen, unsigned* skipped) noexcept {
	*seen = g_seen.load();
	*skipped = g_skipped.load();
}

auto TranslationGuardProbe() noexcept -> bool {
	alignas(16) uint8_t payload[0x100] = {};
	*reinterpret_cast<uint64_t*>(payload + PayloadField) = CrashPayloadWord;
	void* event = payload;
	const unsigned before = g_skipped.load();
	TranslationEvent(nullptr, &event);
	return g_skipped.load() == before + 1;
}

auto InstallTranslationGuard(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	g_context = context;
	const bool ok = context->InstallInlineHook(RvaHandler, HandlerEntry, sizeof(HandlerEntry), reinterpret_cast<void*>(&TranslationEvent),
	                                           reinterpret_cast<void**>(&g_original));
	std::snprintf(report, reportSize, "unit translation event handler 0x775fc0: an event with an unreadable payload is skipped (D2R.exe+0x7761DC crash)%s",
	              ok ? "" : " FAILED");
	return ok;
}

// Test plugin for the game-wide plugin folder (CMakeLists.txt). Client role: no character plugin history, no multiplayer match.
#include <D2RLPlugin/api.h>

#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

#ifdef GP_PROBE_HOOK
constexpr const char* Id = "gp-probe-hook";
constexpr const char* CommandName = "gpprobehook";
constexpr auto Flags = D2RL::PluginFlags::Client | D2RL::PluginFlags::NativeHooks;
#else
constexpr const char* Id = "gp-probe-log";
constexpr const char* CommandName = "gpprobe";
constexpr auto Flags = D2RL::PluginFlags::Client;
#endif

constexpr D2RL::PluginInfo Info{
	.infoSize = D2RL::PluginInfoSize,
	.abiVersion = D2RL_PLUGIN_ABI_VERSION,
	.id = Id,
	.name = Id,
	.version = "0.0.1",
	.author = "mxl2012-d2r test",
	.description = "Game-wide plugin folder test (D2R-XL 2012 lane globalplugins).",
	.flags = Flags,
};

const D2RL::PluginContext* g_ctx = nullptr;
char g_report[1024] = "";

void Log(const char* fmt, const char* a = "", const char* b = "") noexcept {
	char line[600];
	std::snprintf(line, sizeof(line), fmt, a, b);
	char full[700];
	std::snprintf(full, sizeof(full), "%s: %s", Id, line);
	g_ctx->LogInfo(full);
	const size_t used = std::strlen(g_report);
	std::snprintf(g_report + used, sizeof(g_report) - used, "%s\n", line);
}

#ifdef GP_PROBE_HOOK
using IsTypeFn = int32_t (*)(void* item, int32_t type);
using RequirementFn = uint64_t (*)(void*, void*, int32_t, uint32_t*, uint32_t*, uint32_t*, int32_t);
IsTypeFn g_isType = nullptr;
RequirementFn g_req = nullptr;
volatile LONG g_isTypeCalls = 0;
volatile LONG g_reqCalls = 0;

int32_t IsTypeHook(void* item, int32_t type) noexcept {
	InterlockedIncrement(&g_isTypeCalls);
	return g_isType(item, type);
}

uint64_t ReqHook(void* i, void* u, int32_t a3, uint32_t* s, uint32_t* d, uint32_t* l, int32_t a7) noexcept {
	InterlockedIncrement(&g_reqCalls);
	return g_req(i, u, a3, s, d, l, a7);
}

constexpr uint64_t RvaControl = 0x373890;  // item type test: mxl2012-core only calls it
constexpr uint64_t RvaClash = 0x36bc50;    // item requirement test: mxl2012-core hooks it (merc_equip.cpp)
// D2R 93847's entry of 0x36bc50, as a plugin written for the plain game expects it
constexpr uint8_t ClashEntry[] = {0x4c, 0x89, 0x4c, 0x24, 0x20, 0x44, 0x89, 0x44, 0x24, 0x18, 0x55, 0x56, 0x57, 0x48, 0x83, 0xec, 0x60};

void Hex(const uint8_t* p, size_t n, char* out, size_t on) noexcept {
	out[0] = '\0';
	for (size_t i = 0; i < n && std::strlen(out) + 3 < on; ++i) {
		std::snprintf(out + std::strlen(out), on - std::strlen(out), "%02x", p[i]);
	}
}

void Owner(uint64_t rva, const uint8_t* expected, uint32_t size) noexcept {
	const D2RL::DiagnosticsService* diag = nullptr;
	if (g_ctx->QueryService(&diag) != D2RL::ServiceQueryResult::Success || diag == nullptr || diag->queryHookStatus == nullptr) {
		Log("diagnostics: no DiagnosticsService");
		return;
	}
	const D2RL::Diagnostics::HookQuery q{.structSize = D2RL::Diagnostics::HookQuerySize, .rva = rva, .expected = expected, .expectedSize = size};
	D2RL::Diagnostics::HookStatus st{};
	st.structSize = D2RL::Diagnostics::HookStatusSize;
	const auto r = diag->queryHookStatus(g_ctx, &q, &st);
	char buf[200];
	std::snprintf(buf, sizeof(buf), "rva 0x%llx result %u state %u kind %u owners %u owner '%.63s'", static_cast<unsigned long long>(rva),
	              static_cast<unsigned>(r), static_cast<unsigned>(st.state), static_cast<unsigned>(st.kind), st.ownerCount, st.ownerPluginId);
	Log("diagnostics %s", buf);
}

void Probe() noexcept {
	const auto* base = reinterpret_cast<const uint8_t*>(g_ctx->exeBase);
	char hex[64];
	// 1. control: a function nobody hooks, its live bytes as the expected ones
	uint8_t live[16];
	std::memcpy(live, base + RvaControl, sizeof(live));
	Hex(live, sizeof(live), hex, sizeof(hex));
	const bool c = g_ctx->InstallInlineHook(RvaControl, live, sizeof(live), reinterpret_cast<void*>(&IsTypeHook), reinterpret_cast<void**>(&g_isType));
	Log("control hook 0x373890 (live %s): %s", hex, c ? "installed" : "REFUSED");
	// 2. clash: 0x36bc50 with the plain game's entry bytes (what a plugin for the plain game passes)
	Hex(base + RvaClash, sizeof(ClashEntry), hex, sizeof(hex));
	Log("0x36bc50 live bytes %s", hex);
	Owner(RvaClash, ClashEntry, sizeof(ClashEntry));
	const bool k = g_ctx->InstallInlineHook(RvaClash, ClashEntry, sizeof(ClashEntry), reinterpret_cast<void*>(&ReqHook), reinterpret_cast<void**>(&g_req));
	Log("clash hook 0x36bc50 with the game's bytes: %s", k ? "installed" : "REFUSED");
	// 3. clash, lenient: the live (already changed) bytes as the expected ones
	if (!k) {
		uint8_t now[sizeof(ClashEntry)];
		std::memcpy(now, base + RvaClash, sizeof(now));
		const bool l = g_ctx->InstallInlineHook(RvaClash, now, sizeof(now), reinterpret_cast<void*>(&ReqHook), reinterpret_cast<void**>(&g_req));
		Log("clash hook 0x36bc50 with the live bytes: %s", l ? "installed (chained)" : "REFUSED");
	}
}
#endif

auto Command(D2R::Game::Client*, const D2RL::ConsoleCommandContext* command, void*) noexcept -> D2RL::ConsoleCommandResult {
	if (command == nullptr || command->plugin == nullptr) {
		return D2RL::ConsoleCommandResult::Failed;
	}
	char line[1400];
#ifdef GP_PROBE_HOOK
	std::snprintf(line, sizeof(line), "%s alive; calls: control %ld, 0x36bc50 %ld\n%s", Id, g_isTypeCalls, g_reqCalls, g_report);
#else
	std::snprintf(line, sizeof(line), "%s alive\n%s", Id, g_report);
#endif
	command->plugin->LogInfo(line);
	command->plugin->WriteConsoleMessage(line);
	return D2RL::ConsoleCommandResult::Handled;
}

}  // namespace

D2RL_PLUGIN_EXPORT auto D2RLoaderGetPluginInfo() noexcept -> const D2RL::PluginInfo* {
	return &Info;
}

D2RL_PLUGIN_EXPORT auto D2RLoaderLoadPlugin(const D2RL::PluginContext* context) noexcept -> bool {
	if (context == nullptr) {
		return false;
	}
	g_ctx = context;
	char path[MAX_PATH * 2] = "?";
	HMODULE self = nullptr;
	GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, reinterpret_cast<LPCSTR>(&Command), &self);
	GetModuleFileNameA(self, path, sizeof(path));
	Log("GPPROBE loaded from %s (active mod %s)", path, context->activeMod != nullptr ? context->activeMod : "?");
#ifdef GP_PROBE_HOOK
	Probe();
#endif
	return context->RegisterConsoleCommand(CommandName, Command, "Game-wide plugin folder test.");
}

D2RL_PLUGIN_EXPORT void D2RLoaderUnloadPlugin() noexcept {
	g_ctx = nullptr;
}

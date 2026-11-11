// drawcap: a D2RLoader plugin around D2R's legacy draw list cap (README.md). Two parts, each with its own switch:
//  - the patch (on by default) raises the cap from 3000 entries to `cap` (12000): the entries move to a buffer of the plugin's
//    per view, and the 7 inserters' cap compares and base leas are changed (drawcap_logic.h, PlanPatch);
//  - the probe (off by default) reads the previous frame's entry count before the build resets it and writes per second the
//    max, mean and frames over the cap for each graphics mode to d2rloader\logs\drawcap-stats.csv.
// Both use one hook on the draw list build. Every site is found by a byte signature in the loaded image; if one does not
// match, or matches twice, the plugin changes nothing and says why in its log. The patch and the hook are applied in one
// D2RLoader transaction with the code's own bytes as the expected bytes.
//
// Config: <scope>\d2rloader\config\drawcap.toml (`patch`, `cap`, `probe`), or an empty drawcap-probe.txt next to drawcap.dll
// for the probe (drawcap-nopatch.txt turns the patch off for one launch; both are test switches). Log: the plugin's own
// D2RLoader log (drawcap.log). Console command: `drawcap` prints the status and the totals per mode.
// Needs only D2RLoader (1.3.1, plugin ABI of the PluginSDK it is built with); nothing of any mod.
#include <D2RLPlugin/api.h>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <cstdio>
#include <cstring>
#include <cwchar>
#include <string>

#include "drawcap_logic.h"

namespace {

constexpr const char* PluginVersion = "0.2.0";

constexpr D2RL::PluginInfo Info{
    .infoSize = D2RL::PluginInfoSize,
    .abiVersion = D2RL_PLUGIN_ABI_VERSION,
    .id = "drawcap",
    .name = "Draw List Cap",
    .version = PluginVersion,
    .author = "D2R-XL 2012",
    .description = "Raises D2R's 3000-entry legacy draw list cap (entries over it were not drawn); optional fill probe.",
    .flags = D2RL::PluginFlags::Client | D2RL::PluginFlags::NativeHooks,
};

constexpr uint32_t LoaderImage131 = 0x6ab3782cU;  // the game image in D2RLoader 1.3.1; only names it in the log line, decides nothing

const D2RL::PluginContext* g_context = nullptr;
char g_status[400] = "not loaded";
drawcap::Config g_config;
drawcap::ScanResult g_scan;
uint64_t g_textRva = 0;
uint64_t g_imageSize = 0;
uint32_t g_countOffset = 0;
uint32_t g_cap = 0;
uint64_t g_hdGlobalRva = 0;
bool g_probeOn = false;
bool g_patchOn = false;
drawcap::PatchPlan g_plan;
size_t g_bufferBytes = 0;
void* g_spare = nullptr;  // the first view's buffer, allocated before the patch; shared by views past the table (logged)
drawcap::ViewTable<16> g_views;
volatile LONG g_sharedViews = 0;
uint64_t g_builds = 0;
HANDLE g_csv = INVALID_HANDLE_VALUE;
drawcap::Stats g_stats;
uint64_t g_lastPeakLog = 0;
volatile LONG g_readFaults = 0;

using BuildFn = uint64_t(__fastcall*)(uint8_t* view, uint64_t a2, uint64_t a3, uint64_t a4);
BuildFn volatile g_build = nullptr;

void Log(const char* line) {
	g_context->LogInfo(line);
}

void Off(const char* why) {
	std::snprintf(g_status, sizeof(g_status), "off: %s", why);
}

auto Nt(uintptr_t base) -> const IMAGE_NT_HEADERS64* {
	const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
	return reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
}

// The loaded image's .text (RVA and size), from its section table.
auto TextSection(uintptr_t base, uint64_t* rva, uint64_t* size) -> bool {
	const IMAGE_NT_HEADERS64* nt = Nt(base);
	const IMAGE_SECTION_HEADER* s = IMAGE_FIRST_SECTION(nt);
	for (unsigned i = 0; i < nt->FileHeader.NumberOfSections; ++i, ++s) {
		if (std::memcmp(s->Name, ".text", 6) == 0) {
			*rva = s->VirtualAddress;
			*size = s->Misc.VirtualSize;
			return *size != 0;
		}
	}
	return false;
}

// The plan reads the loaded code like the scan.
auto SafePlan(const uint8_t* text, size_t size, uint32_t cap) -> void {
	__try {
		g_plan = drawcap::PlanPatch(text, size, g_scan, cap);
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		g_plan = drawcap::PatchPlan{};
		g_plan.failed = "code not readable";
	}
}

// The scan reads the loaded code; a page that cannot be read ends it as "no match" instead of a crash.
auto SafeScan(const uint8_t* text, size_t size, drawcap::ScanResult* out) -> bool {
	__try {
		*out = drawcap::Scan(text, size);
		return true;
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		return false;
	}
}

// A test switch file next to drawcap.dll (drawcap-probe.txt, drawcap-nopatch.txt).
auto SwitchFile(const D2RL::PluginContext* context, const wchar_t* name) -> bool {
	if (context->pluginDirectory == nullptr) {
		return false;
	}
	wchar_t path[MAX_PATH];
	if (std::swprintf(path, MAX_PATH, L"%ls\\%ls", context->pluginDirectory, name) < 0) {
		return false;
	}
	return GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES;
}

// drawcap-stats.csv in the folder of the plugin's D2RLoader log (d2rloader\logs), new for each game start.
auto OpenCsv(const D2RL::PluginContext* context) -> HANDLE {
	wchar_t path[MAX_PATH];
	if (context->pluginLogPath != nullptr && context->pluginLogPath[0] != L'\0') {
		std::wcsncpy(path, context->pluginLogPath, MAX_PATH - 1);
		path[MAX_PATH - 1] = L'\0';
		wchar_t* slash = std::wcsrchr(path, L'\\');
		wchar_t* slash2 = std::wcsrchr(path, L'/');
		slash = slash2 > slash ? slash2 : slash;
		if (slash == nullptr) {
			return INVALID_HANDLE_VALUE;
		}
		slash[1] = L'\0';
	} else if (context->pluginDirectory != nullptr) {
		std::swprintf(path, MAX_PATH, L"%ls\\..\\logs\\", context->pluginDirectory);
	} else {
		return INVALID_HANDLE_VALUE;
	}
	if (std::wcslen(path) + 20 >= MAX_PATH) {
		return INVALID_HANDLE_VALUE;
	}
	std::wcscat(path, L"drawcap-stats.csv");
	return CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, CREATE_ALWAYS,
	                   FILE_ATTRIBUTE_NORMAL, nullptr);
}

void WriteCsv(const char* text, int length) {
	if (g_csv == INVALID_HANDLE_VALUE || length <= 0) {
		return;
	}
	DWORD written = 0;
	WriteFile(g_csv, text, static_cast<DWORD>(length), &written, nullptr);
}

// One frame's values: the count the previous build left, the view rect, the graphics mode. Game memory under SEH.
auto ReadFrame(const uint8_t* view, uint32_t* count, int32_t* w, int32_t* h, int* mode) -> bool {
	__try {
		*count = *reinterpret_cast<const volatile uint32_t*>(view + g_countOffset);
		const auto* rect = reinterpret_cast<const volatile int32_t*>(view + 4);
		*w = rect[2] - rect[0];
		*h = rect[3] - rect[1];
		const uint8_t* panels = *reinterpret_cast<uint8_t* const volatile*>(g_context->exeBase + g_hdGlobalRva);
		*mode = panels == nullptr ? drawcap::Unknown : (panels[drawcap::HdFlagOffset] != 0 ? drawcap::Hd : drawcap::Legacy);
		return true;
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		return false;
	}
}

void Flush(uint64_t now) {
	char line[160];
	for (int m = 0; m < 3; ++m) {
		const drawcap::Window& w = g_stats.window[m];
		WriteCsv(line, drawcap::CsvLine(line, sizeof(line), now, m, w, g_cap));
		if (w.max > g_cap && now - g_lastPeakLog >= 10000) {
			g_lastPeakLog = now;
			char msg[200];
			std::snprintf(msg, sizeof(msg), "drawcap: %s list over the cap: max %u of %u, %u of %u frames over, %llu entries not drawn (view %dx%d)",
			              drawcap::ModeName[m], w.max, g_cap, w.over, w.frames, static_cast<unsigned long long>(w.dropped), w.viewW, w.viewH);
			Log(msg);
		}
	}
	g_stats.Reset(now);
}

auto NewBuffer() -> void* {
	return VirtualAlloc(nullptr, g_bufferBytes, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
}

// The view's entry buffer (made on the first build of a view, kept for the process's life: the game draws from the entries
// after the build returns). The first view gets the buffer allocated before the patch.
auto BufferFor(const uint8_t* view) -> void* {
	void* b = g_views.Find(view);
	if (b != nullptr) {
		return b;
	}
	b = g_views.used == 0 ? g_spare : NewBuffer();
	if (b != nullptr && g_views.Add(view, b)) {
		char line[160];
		std::snprintf(line, sizeof(line), "drawcap: view %zu has a buffer of %u entries (%zu KB)", g_views.used, g_cap, g_bufferBytes / 1024);
		Log(line);
		return b;
	}
	if (b != nullptr && b != g_spare) {
		VirtualFree(b, 0, MEM_RELEASE);
	}
	if (InterlockedIncrement(&g_sharedViews) == 1) {
		g_context->LogWarn("drawcap: more views than the table holds, or no memory: a view shares the first view's buffer");
	}
	return g_spare;
}

// The draw list build. With the patch the inserters take their entry base from TVIEWDATA +0x50, so it is set to the view's
// buffer before the original runs. For the probe the count still holds the last frame's demand here; the original resets it.
uint64_t __fastcall BuildHook(uint8_t* view, uint64_t a2, uint64_t a3, uint64_t a4) {
	++g_builds;
	if (g_patchOn && view != nullptr) {
		*reinterpret_cast<void**>(view + drawcap::EntriesOffset) = BufferFor(view);
	}
	if (g_probeOn && view != nullptr) {
		uint32_t count = 0;
		int32_t w = 0, h = 0;
		int mode = drawcap::Unknown;
		if (ReadFrame(view, &count, &w, &h, &mode)) {
			const uint64_t now = GetTickCount64();
			if (g_stats.Due(now, g_config.intervalMs)) {
				Flush(now);
			}
			g_stats.Add(count, mode, g_cap, w, h);
		} else {
			InterlockedIncrement(&g_readFaults);
		}
	}
	BuildFn original = g_build;
	while (original == nullptr) {  // only between the commit and the store of the call-through pointer (load time)
		SwitchToThread();
		original = *static_cast<BuildFn volatile*>(&g_build);
	}
	return original(view, a2, a3, a4);
}

// The hook on the build (and, with the patch, the edits) in one D2RLoader transaction. False: nothing changed.
auto Commit(const uint8_t* text, uint64_t buildRva, bool withPatch, char* why, size_t whySize) -> bool {
	const D2RL::MutationService* m = nullptr;
	if (g_context->QueryService(&m) != D2RL::ServiceQueryResult::Success || !D2RL::HasMutationServiceField(m, D2RL::MutationServiceRequiredSize)) {
		std::snprintf(why, whySize, "D2RLoader has no mutation service");
		return false;
	}
	using namespace D2RL::Mutations;
	TransactionHandle tx = InvalidTransactionHandle;
	if (m->beginTransaction(g_context, &tx) != Result::Success) {
		std::snprintf(why, whySize, "no transaction");
		return false;
	}
	uint8_t expected[drawcap::HookSize];
	std::memcpy(expected, text + g_scan.build, sizeof(expected));
	const InlineHookRequest hook{
	    .structSize = InlineHookRequestSize,
	    .rva = buildRva,
	    .expected = expected,
	    .expectedSize = sizeof(expected),
	    .target = reinterpret_cast<void*>(&BuildHook),
	};
	OperationHandle hookOp = InvalidOperationHandle;
	Result r = m->stageInlineHook(g_context, tx, &hook, &hookOp);
	for (size_t i = 0; withPatch && r == Result::Success && i < g_plan.editCount; ++i) {
		const drawcap::Edit& e = g_plan.edits[i];
		const BytePatchRequest patch{
		    .structSize = BytePatchRequestSize,
		    .rva = g_textRva + e.at,
		    .expected = e.expected,
		    .expectedSize = e.size,
		    .bytes = e.bytes,
		    .size = e.size,
		};
		OperationHandle op = InvalidOperationHandle;
		r = m->stageBytePatch(g_context, tx, &patch, &op);
	}
	if (r != Result::Success) {
		std::snprintf(why, whySize, "staging refused (result %u)", static_cast<unsigned>(r));
		m->cancelTransaction(g_context, tx);
		return false;
	}
	CommitResult done{.structSize = CommitResultSize};
	r = m->commit(g_context, tx, &done);
	if (r != Result::Success || done.result != Result::Success) {
		std::snprintf(why, whySize, "commit failed (result %u/%u, reason %u, operation %llu, %s)", static_cast<unsigned>(r),
		              static_cast<unsigned>(done.result), static_cast<unsigned>(done.failureReason),
		              static_cast<unsigned long long>(done.operation),
		              HasFlag(done.flags, CommitFlags::OriginalStateRestored) ? "game code restored" : "restore not confirmed");
		m->cancelTransaction(g_context, tx);
		return false;
	}
	void* original = nullptr;
	if (m->getInlineHookOriginal(g_context, tx, hookOp, &original) != Result::Success || original == nullptr) {
		// never seen: the hook would have no way to call the game. D2RLoader removes it all when the plugin unloads.
		std::snprintf(why, whySize, "no call-through pointer for the hook");
		return false;
	}
	g_build = reinterpret_cast<BuildFn>(original);
	return true;
}

auto Start(bool wantProbe, bool wantPatch) -> bool {
	char line[512];
	const uintptr_t base = g_context->exeBase;
	if (base == 0) {
		Off("no game image");
		return false;
	}
	g_imageSize = Nt(base)->OptionalHeader.SizeOfImage;
	uint64_t textSize = 0;
	if (!TextSection(base, &g_textRva, &textSize)) {
		Off("the game image has no .text section");
		return false;
	}
	const auto* text = reinterpret_cast<const uint8_t*>(base + g_textRva);
	if (!SafeScan(text, static_cast<size_t>(textSize), &g_scan)) {
		Off("the game code could not be read");
		return false;
	}
	if (!g_scan.ok) {
		std::snprintf(line, sizeof(line), "signature '%s' did not match (build %zu, reset %zu, HD test %zu matches, %zu cap sites); nothing hooked or patched",
		              g_scan.failed, g_scan.buildMatches, g_scan.resetMatches, g_scan.hdMatches, g_scan.siteCount);
		Off(line);
		return false;
	}
	const uint64_t buildRva = g_textRva + g_scan.build;
	g_hdGlobalRva = g_textRva + g_scan.hdGlobal;
	if (g_hdGlobalRva + 8 > g_imageSize) {
		Off("the HD graphics test's global lies outside the image; nothing hooked or patched");
		return false;
	}
	g_countOffset = g_scan.countOffset;
	g_cap = g_scan.cap;
	std::snprintf(line, sizeof(line), "drawcap: found the draw list build at 0x%llx, count at TVIEWDATA+0x%x, cap %u at %zu sites, HD flag at [0x%llx]+0x%x%s",
	              static_cast<unsigned long long>(buildRva), g_countOffset, g_cap, g_scan.siteCount,
	              static_cast<unsigned long long>(g_hdGlobalRva), drawcap::HdFlagOffset,
	              buildRva == drawcap::BuildRva93847 && g_countOffset == drawcap::CountOffset93847 ? " (the 93847 places)" : " (moved: another build)");
	Log(line);
	for (size_t i = 0; i < g_scan.siteCount && i < 16; ++i) {
		std::snprintf(line, sizeof(line), "drawcap: cap site %zu: cmp at 0x%llx, cap %u, %s count", i + 1,
		              static_cast<unsigned long long>(g_textRva + g_scan.sites[i].compareAt), g_scan.sites[i].cap,
		              g_scan.sites[i].listRelative ? "list-relative" : "view-relative");
		Log(line);
	}
	bool patch = false;
	char patchState[200] = "patch off";
	if (wantPatch) {
		SafePlan(text, static_cast<size_t>(textSize), g_config.cap);
		if (!g_plan.ok) {
			std::snprintf(patchState, sizeof(patchState), "patch off: '%s' did not match at cap site %zu (or cap %u out of range); nothing patched",
			              g_plan.failed ? g_plan.failed : "?", g_plan.failedSite, g_config.cap);
			g_context->LogWarn((std::string("drawcap: ") + patchState).c_str());
		} else {
			g_bufferBytes = static_cast<size_t>(g_config.cap) * drawcap::EntrySize;
			g_spare = NewBuffer();
			if (g_spare == nullptr) {
				std::snprintf(patchState, sizeof(patchState), "patch off: no memory for a buffer of %u entries", g_config.cap);
				g_context->LogWarn((std::string("drawcap: ") + patchState).c_str());
			} else {
				patch = true;
				for (size_t i = 0; i < g_plan.editCount; ++i) {
					const drawcap::Edit& e = g_plan.edits[i];
					int n = std::snprintf(line, sizeof(line), "drawcap: edit %zu at 0x%llx:", i + 1, static_cast<unsigned long long>(g_textRva + e.at));
					for (int k = 0; k < e.size; ++k) {
						n += std::snprintf(line + n, sizeof(line) - static_cast<size_t>(n), " %02x", e.expected[k]);
					}
					n += std::snprintf(line + n, sizeof(line) - static_cast<size_t>(n), " ->");
					for (int k = 0; k < e.size; ++k) {
						n += std::snprintf(line + n, sizeof(line) - static_cast<size_t>(n), " %02x", e.bytes[k]);
					}
					Log(line);
				}
			}
		}
	}
	if (!patch && !wantProbe) {
		std::snprintf(line, sizeof(line), "%s; probe off; nothing hooked", patchState);
		Off(line);
		return false;
	}
	// set before the commit: the hook may run as soon as it is live
	g_probeOn = wantProbe;
	g_patchOn = patch;
	if (patch) {
		g_cap = g_config.cap;
	}
	char why[200] = "";
	if (!Commit(text, buildRva, patch, why, sizeof(why))) {
		g_probeOn = g_patchOn = false;
		g_cap = g_scan.cap;
		std::snprintf(line, sizeof(line), "D2RLoader refused the %s: %s; nothing hooked or patched", patch ? "hook and patch" : "hook", why);
		Off(line);
		if (g_spare != nullptr) {
			VirtualFree(g_spare, 0, MEM_RELEASE);
			g_spare = nullptr;
		}
		return false;
	}
	if (patch) {
		std::snprintf(patchState, sizeof(patchState), "patch on: cap %u (was %u) at %zu sites, %zu KB per view", g_cap, g_scan.cap, g_scan.siteCount,
		              g_bufferBytes / 1024);
	}
	if (wantProbe) {
		g_csv = OpenCsv(g_context);
		if (g_csv == INVALID_HANDLE_VALUE) {
			g_context->LogWarn("drawcap: drawcap-stats.csv could not be created; only peaks go to the log");
		} else {
			std::snprintf(line, sizeof(line), "# drawcap %s, image 0x%08x, build 0x%llx, count +0x%x, cap %u%s, interval %u ms\n%s\n", PluginVersion,
			              Nt(base)->FileHeader.TimeDateStamp, static_cast<unsigned long long>(buildRva), g_countOffset, g_cap,
			              patch ? " (patched)" : "", g_config.intervalMs, drawcap::CsvHeader);
			WriteCsv(line, static_cast<int>(std::strlen(line)));
		}
	}
	std::snprintf(g_status, sizeof(g_status), "%s; %s", patchState, wantProbe ? "probe on (a line per interval in drawcap-stats.csv)" : "probe off");
	return true;
}

auto __cdecl StatusCommand(D2R::Game::Client*, const D2RL::ConsoleCommandContext* command, void*) noexcept -> D2RL::ConsoleCommandResult {
	char line[700];
	int n = std::snprintf(line, sizeof(line), "drawcap %s: %s; %llu builds, %zu views", PluginVersion, g_status,
	                      static_cast<unsigned long long>(g_builds), g_views.used);
	for (int m = 0; m < 3 && n > 0 && static_cast<size_t>(n) < sizeof(line); ++m) {
		const drawcap::Totals& t = g_stats.total[m];
		if (t.frames != 0) {
			n += std::snprintf(line + n, sizeof(line) - static_cast<size_t>(n), "; %s: %llu frames, max %u, %llu over, %llu dropped",
			                   drawcap::ModeName[m], static_cast<unsigned long long>(t.frames), t.max, static_cast<unsigned long long>(t.over),
			                   static_cast<unsigned long long>(t.dropped));
		}
	}
	command->plugin->WriteConsoleMessage(line);
	Log(line);
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
	g_context = context;
	char line[512];
	const uint32_t stamp = context->exeBase != 0 ? Nt(context->exeBase)->FileHeader.TimeDateStamp : 0;
	std::snprintf(line, sizeof(line), "drawcap %s loaded (%s scope, mod %s, D2R %s, image 0x%08x%s)", PluginVersion,
	              context->loadScope == D2RL::LoadScope::Mod ? "mod" : "global", context->activeMod ? context->activeMod : "-",
	              context->buildVersion ? context->buildVersion : "?", stamp, stamp == LoaderImage131 ? ", the D2RLoader 1.3.1 image" : "");
	Log(line);
	char text[2048];
	uint32_t need = 0;
	text[0] = '\0';
	g_config = drawcap::ParseConfig(context->ReadConfig(text, sizeof(text), &need) ? text : nullptr);
	if (SwitchFile(context, L"drawcap-probe.txt")) {
		g_config.probe = true;
		Log("drawcap: drawcap-probe.txt is present: probe on");
	}
	if (g_config.patch && SwitchFile(context, L"drawcap-nopatch.txt")) {
		g_config.patch = false;
		Log("drawcap: drawcap-nopatch.txt is present: patch off");
	}
	std::snprintf(line, sizeof(line), "drawcap: config: patch %s, cap %u, probe %s, interval %u ms", g_config.patch ? "on" : "off", g_config.cap,
	              g_config.probe ? "on" : "off", g_config.intervalMs);
	Log(line);
	if (!g_config.patch && !g_config.probe) {
		Off("patch = false and probe = false in drawcap.toml");
		Log("drawcap: patch and probe off; nothing hooked or patched");
	} else {
		if (!Start(g_config.probe, g_config.patch)) {
			std::snprintf(line, sizeof(line), "drawcap: %s", g_status);
			context->LogWarn(line);
		} else {
			std::snprintf(line, sizeof(line), "drawcap: %s", g_status);
			Log(line);
		}
	}
	if (!context->RegisterConsoleCommand("drawcap", &StatusCommand, "Draw list cap patch and probe status.")) {
		context->LogWarn("drawcap: console command not registered");
	}
	return true;
}

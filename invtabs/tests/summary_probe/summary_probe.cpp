// TEST ONLY: a throwaway D2RLoader plugin that drives the charm-tab summary (src/summary.cpp) in the game without the
// invtabs core. It is not shipped and not part of any build of the mod; docs/invtabs-summary.md "In-game proof" has
// how it is built and run. Build 93847 only: the item walk below uses that build's addresses (the summary itself
// finds its functions by pattern).
//
// Console (D2RLoader), all work on the UI thread:
//   summary-probe refresh [page]   charms of the local player's inventory (all pages, or one page) -> Refresh; logs every
//                                  charm (page, counts, raw stats), the totals and the lines
//   summary-probe open [classic]   registers the panel layout again with the summary fragment sized to the lines (the
//                                  core's way: UnloadPanel, unregister, register), opens it
//   summary-probe apply            sets the row texts (after open)
//   summary-probe scroll <n>       classic window: moves it n lines, then sets the texts
//   summary-probe close
// Log: %MXL_SUMMARY_PROBE_LOG%, else summary-probe.log next to this DLL.
#include "../../src/summary.h"

#include <D2RLPlugin/api.h>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace {

static constexpr D2RL::PluginInfo ProbeInfo {
	.infoSize    = D2RL::PluginInfoSize,
	.abiVersion  = D2RL_PLUGIN_ABI_VERSION,
	.id          = "invtabs-summary-probe",
	.name        = "invtabs summary probe (test)",
	.version     = "0.0.1",
	.author      = "D2R-XL 2012",
	.description = "Test only: the D2R-XL 2012 charm-tab summary in a panel of its own.",
	.flags       = D2RL::PluginFlags::Shared,
};

constexpr char PanelName[]  = "invtabs-summary-probe/Probe";
constexpr char LocalId[]    = "Probe";
constexpr char LayoutHd[]   = "data/global/ui/layouts/invtabs-summary-probe/Probehd.json";
constexpr char LayoutSd[]   = "data/global/ui/layouts/invtabs-summary-probe/Probe.json";
// The summary band: inside the sample modal frame (Panel\Modals\Modal_No_Title_BG, 1232 wide), 11 HD rows high.
constexpr invtabs::summary::Rect AreaHd { 78, 100, 1076, 352 };
constexpr invtabs::summary::Rect AreaSd { 20, 40, 300, 130 };

// Build 93847 (docs/d2r-addresses.md; plugin/src/devmenu.cpp, harness_cmds.cpp use the same).
constexpr std::uintptr_t RvaLocalId = 0x8b2d0, RvaClientPlayer = 0x9a480, RvaInventoryOf = 0x34a360, RvaFirstItem = 0x388c10,
                         RvaNextItem = 0x38aba0, RvaIsType = 0x373890, RvaItemPage = 0x36cfe0;
constexpr int ItemTypeCharm = 13;

const D2RL::PluginContext*  Context   = nullptr;
const D2RL::PanelService*   Panels    = nullptr;
const D2RL::ResourceService* Resources = nullptr;
const D2RL::ThreadService*  Threads   = nullptr;
const D2RL::WidgetService*  Widgets   = nullptr;
D2RL::Panels::RegistrationHandle    Panel  = D2RL::Panels::InvalidHandle;
D2RL::Resources::RegistrationHandle Layout = D2RL::Resources::InvalidHandle;
bool                                Opened = false;
invtabs::summary::Summary           Sum;
std::uintptr_t                      Base = 0;
std::string                         LogPath;
std::string                         Pending; // the console verb waiting for the UI thread

void Log(const char* line) {
	if (FILE* f = std::fopen(LogPath.c_str(), "ab")) {
		std::fprintf(f, "%s\n", line);
		std::fclose(f);
	}
}

void Logf(const char* fmt, ...) {
	char    line[1024];
	va_list ap;
	va_start(ap, fmt);
	std::vsnprintf(line, sizeof(line), fmt, ap);
	va_end(ap);
	Log(line);
}

template <class F> F Fn(std::uintptr_t rva) { return reinterpret_cast<F>(Base + rva); }

std::size_t WalkCharms(int onlyPage, void** out, std::size_t cap) {
	std::size_t n = 0;
	__try {
		void* player = Fn<void* (*)(std::uint32_t)>(RvaClientPlayer)(Fn<std::uint32_t (*)()>(RvaLocalId)());
		if (player == nullptr) return 0;
		void* inv = Fn<void* (*)(void*, const char*, int)>(RvaInventoryOf)(player, __FILE__, __LINE__);
		for (void* item = inv ? Fn<void* (*)(void*)>(RvaFirstItem)(inv) : nullptr; item != nullptr && n < cap;
		     item = Fn<void* (*)(void*)>(RvaNextItem)(item)) {
			if (!Fn<int (*)(void*, int)>(RvaIsType)(item, ItemTypeCharm)) continue;
			const int page = Fn<std::uint8_t (*)(void*)>(RvaItemPage)(item);
			if (onlyPage >= 0 && page != onlyPage) continue;
			out[n++] = item;
		}
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		Log("probe: item walk faulted");
	}
	return n;
}

std::vector<void*> Charms(int onlyPage) {
	void*             buf[512];
	const std::size_t n = WalkCharms(onlyPage, buf, 512);
	return std::vector<void*>(buf, buf + n);
}

int PageOf(void* item) {
	__try {
		return Fn<std::uint8_t (*)(void*)>(RvaItemPage)(item);
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		return -1;
	}
}

std::string Hex(const std::string& s) {
	std::string out;
	char        b[4];
	for (unsigned char c : s) {
		if (c >= 0x20 && c < 0x7f) out.push_back(static_cast<char>(c));
		else {
			std::snprintf(b, sizeof(b), "\\%02X", c);
			out += b;
		}
	}
	return out;
}

void DoRefresh(int page) {
	const auto items = Charms(page);
	Logf("== refresh page=%d charms=%zu", page, items.size());
	for (void* item : items) {
		const auto stats = Sum.ReadItem(item);
		std::string s;
		for (const auto& v : stats) s += " " + std::to_string(v.stat) + ":" + std::to_string(v.param) + "=" + std::to_string(v.value);
		Logf("charm id=%u page=%d counts=%d stats(%zu)%s", *reinterpret_cast<std::uint32_t*>(static_cast<std::uint8_t*>(item) + 8), PageOf(item),
		     Sum.ItemCounts(item) ? 1 : 0, stats.size(), s.c_str());
	}
	Sum.Refresh(items.data(), items.size());
	std::string t;
	for (const auto& v : Sum.Totals()) t += " " + std::to_string(v.stat) + ":" + std::to_string(v.param) + "=" + std::to_string(v.value);
	Logf("counted=%zu skipped=%zu fallback=%d totals(%zu)%s", Sum.Counted(), Sum.Skipped(), Sum.UsedFallback() ? 1 : 0, Sum.Totals().size(), t.c_str());
	Logf("lines=%zu", Sum.Lines().size());
	for (std::size_t i = 0; i < Sum.Lines().size(); ++i) {
		Logf("line %zu: %s", i, invtabs::summary::StripColour(Sum.Lines()[i]).c_str());
		Logf("raw  %zu: %s", i, Hex(Sum.Lines()[i]).c_str());
	}
}

std::string PanelJson(bool classic) {
	using namespace invtabs::summary;
	const LayoutMode mode = classic ? LayoutMode::Classic : LayoutMode::Hd;
	const std::string frag = Sum.Fragment(mode, classic ? AreaSd : AreaHd);
	if (classic) {
		return std::string(R"({"type": "Panel", "name": ")") + PanelName + R"(", "fields": {"anchor": {"x": 0.5, "y": 0.5}, "priority": 8500}, "children": [)"
		       R"({"type": "ImageWidget", "name": "Frame", "fields": {"rect": {"x": -170, "y": -100, "width": 340, "height": 200}, "backgroundColor": {"r": 0, "g": 0, "b": 0, "a": 200}}, "children": [)" +
		       frag + "]}]}";
	}
	return std::string(R"({"type": "Panel", "name": ")") + PanelName + R"(", "fields": {"anchor": {"x": 0.5, "y": 0.5}, "priority": 8500}, "children": [)"
	       R"({"type": "ImageWidget", "name": "Frame", "fields": {"rect": {"x": -627, "y": -270}, "filename": "Panel\\Modals\\Modal_No_Title_BG"}, "children": [)" +
	       frag + "]}]}";
}

bool Register(bool classic) {
	if (Opened && Widgets != nullptr) {
		const D2RL::Widgets::UiAction unload { .structSize = D2RL::Widgets::UiActionSize, .flags = 0, .target = "PanelManager", .command = "UnloadPanel", .text = PanelName };
		(void)Widgets->dispatchUiAction(Context, &unload);
		Opened = false;
	}
	if (Layout != D2RL::Resources::InvalidHandle) (void)Resources->unregisterResource(Context, Layout);
	Layout                = D2RL::Resources::InvalidHandle;
	const std::string json = PanelJson(classic);
	const D2RL::Resources::ResourceRegistration r {
		.structSize = D2RL::Resources::ResourceRegistrationSize,
		.path       = classic ? LayoutSd : LayoutHd,
		.bytes      = json.data(),
		.byteCount  = json.size(),
	};
	const bool ok = Resources->registerResource(Context, &r, &Layout) == D2RL::Resources::Result::Success;
	Logf("layout %s: rows=%zu bytes=%zu %s", classic ? "classic" : "hd", Sum.Rows(), json.size(), ok ? "registered" : "NOT registered");
	if (const char* dump = std::getenv("MXL_SUMMARY_PROBE_LAYOUT")) {
		if (FILE* f = std::fopen(dump, "wb")) {
			std::fwrite(json.data(), 1, json.size(), f);
			std::fclose(f);
		}
	}
	return ok;
}

void RunVerb(const std::string& input) {
	char verb[32] = {}, arg[32] = {};
	(void)std::sscanf(input.c_str(), "%31s %31s", verb, arg);
	const std::string v = verb;
	if (v == "refresh") DoRefresh(arg[0] ? std::atoi(arg) : -1);
	else if (v == "open") {
		if (Register(std::strcmp(arg, "classic") == 0)) {
			const auto r = Panels->openPanel(Context, Panel);
			Opened       = r == D2RL::Panels::Result::Success;
			Logf("open -> %u", static_cast<unsigned>(r));
		}
	} else if (v == "apply") {
		Sum.ApplyTexts(PanelName, true);
		Log("applied");
	} else if (v == "scroll") {
		Sum.ScrollBy(std::atoll(arg));
		Sum.ApplyTexts(PanelName);
		Logf("scrolled %s", arg);
	} else if (v == "close") {
		Logf("close -> %u", static_cast<unsigned>(Panels->closePanel(Context, Panel)));
		Opened = false;
	} else Logf("unknown verb '%s'", input.c_str());
}

void __cdecl OnUi(const D2RL::PluginContext*, void* data) noexcept {
	auto* input = static_cast<std::string*>(data);
	RunVerb(*input);
	delete input;
}

auto Command(D2R::Game::Client*, const D2RL::ConsoleCommandContext* command, void*) noexcept -> D2RL::ConsoleCommandResult {
	if (command == nullptr) return D2RL::ConsoleCommandResult::Failed;
	auto* input = new (std::nothrow) std::string(command->args != nullptr ? std::string(command->args, command->argsLength) : std::string());
	if (input == nullptr) return D2RL::ConsoleCommandResult::Failed;
	Logf("> %s", input->c_str());
	if (Threads->runOnUiThread(Context, OnUi, input) != D2RL::Threads::Result::Success) {
		delete input;
		Log("runOnUiThread failed");
		return D2RL::ConsoleCommandResult::Failed;
	}
	return D2RL::ConsoleCommandResult::Handled;
}

} // namespace

D2RL_PLUGIN_EXPORT auto D2RLoaderGetPluginInfo() noexcept -> const D2RL::PluginInfo* { return &ProbeInfo; }

D2RL_PLUGIN_EXPORT auto D2RLoaderLoadPlugin(const D2RL::PluginContext* context) noexcept -> bool {
	if (context == nullptr) return false;
	Context = context;
	char self[MAX_PATH] = {};
	HMODULE mod = nullptr;
	GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, reinterpret_cast<LPCSTR>(&ProbeInfo), &mod);
	GetModuleFileNameA(mod, self, MAX_PATH);
	if (const char* env = std::getenv("MXL_SUMMARY_PROBE_LOG")) LogPath = env;
	else {
		LogPath = self;
		LogPath = LogPath.substr(0, LogPath.find_last_of("\\/") + 1) + "summary-probe.log";
	}
	if (context->QueryService(&Resources) != D2RL::ServiceQueryResult::Success || context->QueryService(&Panels) != D2RL::ServiceQueryResult::Success ||
	    context->QueryService(&Threads) != D2RL::ServiceQueryResult::Success) {
		Log("probe: services missing");
		return false;
	}
	(void)context->QueryService(&Widgets);
	Base = reinterpret_cast<std::uintptr_t>(GetModuleHandleA(nullptr));
	Logf("probe loaded, game base %p", reinterpret_cast<void*>(Base));
	Sum.Init(reinterpret_cast<const void*>(Base), Log);
	// a first layout so the panel name is known; `open` registers it again with the real row count
	(void)Register(false);
	const D2RL::Panels::PanelRegistration reg { .structSize = D2RL::Panels::PanelRegistrationSize, .flags = D2RL::Panels::PanelFlags::CloseOnEscape, .localId = LocalId };
	if (Panels->registerPanel(context, &reg, &Panel) != D2RL::Panels::Result::Success) {
		Log("probe: panel not registered");
		return false;
	}
	return context->RegisterConsoleCommand("summary-probe", Command, "Test only: the charm-tab summary probe.");
}

D2RL_PLUGIN_EXPORT void D2RLoaderUnloadPlugin() noexcept {}

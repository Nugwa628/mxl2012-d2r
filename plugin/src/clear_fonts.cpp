// The clear legacy fonts setting (owner request 2026-11-07, lane fonttoggle; off word clearfonts; docs/legacy-font-research.md).
//
// mxl2012-core.toml `[fonts] legacy_clear_fonts` (default false) and the Controls action "Clear Legacy Fonts" (`mxl_clear_fonts`,
// default Ctrl+F, rebindable in Options > Controls) choose between D2R's classic fonts and the clearer set the build stages in
// data/local/font/latin/clear/. A press flips the setting at once and writes it back to the file. clear_fonts_logic.h has
// how D2R loads its fonts and what the part changes; HD text never reads these files.
//
// Safety: every byte the part relies on is compared first; the clear set is used only when all its TBLs on disk pass the
// line-height check (the repack's formal11 divide by zero) and the language dir is Latin. Fonts are freed only on the UI
// thread, as D2R's own idle unload does; the current font is first swapped for fontformal10 with D2R's SetFont and selected
// again afterwards.
#include "clear_fonts.h"

#include "clear_fonts_logic.h"

#include <D2RLPlugin/input.h>
#include <D2RLPlugin/threads.h>

#include <windows.h>

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

using namespace clear_fonts;

using LangInitFn = void (*)() noexcept;
using FreeFn = void (*)(uint64_t handle) noexcept;
using SetFontFn = void (*)(int32_t id) noexcept;

const D2RL::PluginContext* g_context = nullptr;
const D2RL::ThreadService* g_threads = nullptr;
const D2RL::InputService* g_input = nullptr;
D2RL::Input::ActionHandle g_action = D2RL::Input::InvalidHandle;
uint64_t g_base = 0;
bool g_on = false;        // installed
bool g_filesOk = false;   // the clear set on disk passed the checks
char g_filesNote[160] = "";
// The table entries point here; the UI thread (SetFont, the language set-up, Apply) is the only reader and writer.
char g_names[Count][NameSize] = {};
std::atomic<bool> g_wanted{false};  // the setting
bool g_live = false;                // the names are the clear set's
std::atomic<uint32_t> g_pending{0};  // bit i: Ids[i] still to be freed
std::atomic<bool> g_tickQueued{false};
std::atomic<long> g_toggles{0}, g_frees{0}, g_handovers{0}, g_langInits{0}, g_writes{0}, g_writeFails{0};

auto Slot(int id) noexcept -> uint64_t* {
	return reinterpret_cast<uint64_t*>(g_base + SlotsRva + SlotStride * static_cast<uint64_t>(id));
}

auto Language() noexcept -> const char* {
	return reinterpret_cast<const char*>(g_base + LanguageRva);
}

void SetNames(bool clear) noexcept {
	for (int i = 0; i < Count; ++i) {
		NameFor(i, clear, g_names[i]);
	}
	if (clear != g_live) {
		g_live = clear;
		g_pending.store((1u << Count) - 1);
	}
}

// UI thread: free the pending fonts' DC6s; the current font is handed to the stand-in first and selected again after.
void Flush() noexcept {
	const auto setFont = reinterpret_cast<SetFontFn>(g_base + SetFontRva);
	const int current = *reinterpret_cast<const int32_t*>(g_base + CurrentFontRva);
	const uint32_t left = g_pending.exchange(0);
	bool reselect = false;
	for (int i = 0; i < Count; ++i) {
		uint64_t* slot = Slot(Ids[i]);
		if ((left & (1u << i)) == 0 || *slot == 0) {
			continue;
		}
		if (!MayFree(Ids[i], *reinterpret_cast<const int32_t*>(g_base + CurrentFontRva), *slot)) {
			setFont(StandIn);
			reselect = true;
		}
		reinterpret_cast<FreeFn>(g_base + FreeDc6Rva)(*slot);
		*slot = 0;
		g_frees.fetch_add(1);
	}
	if (reselect) {
		g_handovers.fetch_add(1);
		setFont(current);
	}
}

// UI thread: the names for the setting and the language now.
void Apply() noexcept {
	SetNames(g_wanted.load() && g_filesOk && IsLatin(Language()));
	Flush();
}

void __cdecl ApplyOnUi(const D2RL::PluginContext*, void*) noexcept {
	g_tickQueued.store(false);
	Apply();
}

void QueueApply() noexcept {
	if (!g_tickQueued.exchange(true) && g_threads->runOnUiThread(g_context, &ApplyOnUi, nullptr) != D2RL::Threads::Result::Success) {
		g_tickQueued.store(false);
	}
}

// The call at 0x902ff4 (through the pad): D2R's names while it sets up the language and loads font 1, then the setting again.
void LangInitHook() noexcept {
	g_langInits.fetch_add(1);
	SetNames(false);
	reinterpret_cast<LangInitFn>(g_base + LangInitRva)();
	Apply();
}

void WriteSetting(bool on) noexcept {
	static char toml[16384];
	static char out[16384 + 128];
	uint32_t need = 0;
	if (!g_context->ReadConfig(toml, sizeof(toml), &need)) {
		toml[0] = '\0';
	}
	if (WithSetting(toml, on, out, sizeof(out)) && g_context->WriteConfig(out)) {
		g_writes.fetch_add(1);
	} else {
		g_writeFails.fetch_add(1);
	}
}

void Toggle(bool on) noexcept {
	g_wanted.store(on);
	g_toggles.fetch_add(1);
	WriteSetting(on);
	Apply();
	char line[160];
	std::snprintf(line, sizeof(line), "mxl2012-core: clearfonts %s (%s)", on ? "on" : "off", g_live == on ? "applied" : g_filesNote);
	g_context->LogInfo(line);
}

void __cdecl ToggleOnUi(const D2RL::PluginContext*, void*) noexcept {
	Toggle(!g_wanted.load());
}

auto __cdecl OnAction(const D2RL::PluginContext*, const D2RL::Input::ActionEvent* event, void*) noexcept -> D2RL::Input::ActionResult {
	if (!D2RL::Input::HasActionEventField(event, D2RL::Input::ActionEventRequiredSize) || event->kind != D2RL::Input::ActionEventKind::Pressed) {
		return D2RL::Input::ActionResult::Ignored;
	}
	(void)g_threads->runOnUiThread(g_context, &ToggleOnUi, nullptr);
	return D2RL::Input::ActionResult::Handled;
}

// <mod>\d2rloader\plugins\mxl2012-core.dll -> <mod>\mxl2012.mpq\data\local\font\latin\clear\: every TBL safe, every DC6 there.
auto CheckFiles(const char* selfPath) noexcept -> bool {
	char dir[MAX_PATH * 3];
	std::snprintf(dir, sizeof(dir), "%s", selfPath != nullptr ? selfPath : "");
	for (int up = 0; up < 3; ++up) {
		char* slash = std::strrchr(dir, '\\');
		if (slash == nullptr) {
			std::snprintf(g_filesNote, sizeof(g_filesNote), "the mod folder is not known");
			return false;
		}
		*slash = '\0';
	}
	for (int i = 0; i < Count; ++i) {
		for (const char* ext : {".tbl", ".dc6"}) {
			char path[MAX_PATH * 3 + 96];
			std::snprintf(path, sizeof(path), "%s\\mxl2012.mpq\\data\\local\\font\\latin\\clear\\%s%s", dir, D2RNames[Ids[i]], ext);
			wchar_t wide[MAX_PATH * 2];
			if (MultiByteToWideChar(CP_UTF8, 0, path, -1, wide, MAX_PATH * 2) == 0) {
				std::snprintf(g_filesNote, sizeof(g_filesNote), "path too long");
				return false;
			}
			HANDLE f = CreateFileW(wide, GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
			if (f == INVALID_HANDLE_VALUE) {
				std::snprintf(g_filesNote, sizeof(g_filesNote), "clear\\%s%s missing in the mod", D2RNames[Ids[i]], ext);
				return false;
			}
			uint8_t tbl[12 + 256 * 14 + 1];
			DWORD got = 0;
			LARGE_INTEGER size{};
			const bool ok = std::strcmp(ext, ".tbl") == 0
			                    ? ReadFile(f, tbl, sizeof(tbl), &got, nullptr) != 0 && TblSafe(tbl, got)
			                    : GetFileSizeEx(f, &size) != 0 && size.QuadPart > 0;
			CloseHandle(f);
			if (!ok) {
				std::snprintf(g_filesNote, sizeof(g_filesNote), "clear\\%s%s refused (bad header or line height 0)", D2RNames[Ids[i]], ext);
				return false;
			}
		}
	}
	std::snprintf(g_filesNote, sizeof(g_filesNote), "%d clear pairs checked", Count);
	return true;
}

auto BytesMatch(uint64_t rva, const uint8_t* bytes, size_t n) noexcept -> bool {
	return std::memcmp(reinterpret_cast<const void*>(g_base + rva), bytes, n) == 0;
}

}  // namespace

auto InstallClearFonts(const D2RL::PluginContext* context, const char* selfPath, char* report, size_t reportSize) noexcept -> bool {
	g_context = context;
	g_base = context->exeBase;
	bool same = BytesMatch(LangCallRva, LangCall, sizeof(LangCall)) && BytesMatch(PadRva, Pad, sizeof(Pad)) &&
	            BytesMatch(UnloadRva, Unload, sizeof(Unload)) && BytesMatch(LoadTestRva, LoadTest, sizeof(LoadTest)) && BytesMatch(SetFontRva, SetFontEntry, sizeof(SetFontEntry)) &&
	            BytesMatch(FreeDc6Rva, FreeDc6Bytes, sizeof(FreeDc6Bytes));
	for (int id = 0; same && id < FontIds; ++id) {
		const uint64_t entry = *reinterpret_cast<const uint64_t*>(g_base + NameTableRva + 8 * static_cast<uint64_t>(id));
		same = entry == g_base + D2RNameRvas[id] && std::strcmp(reinterpret_cast<const char*>(entry), D2RNames[id]) == 0;
	}
	if (!same) {
		std::snprintf(report, reportSize, "clearfonts off: bytes differ (font name table 0x1d84a00 / 0x902ff4 / 0x903002 / 0x90ca80 / 0x90e291 / "
		              "0x90e230 / 0x79d200), left as D2R");
		return false;
	}
	if (context->QueryService(&g_threads) != D2RL::ServiceQueryResult::Success || !D2RL::HasThreadServiceField(g_threads, D2RL::ThreadServiceRequiredSize) ||
	    context->QueryService(&g_input) != D2RL::ServiceQueryResult::Success || !D2RL::HasInputServiceField(g_input, D2RL::InputServiceRequiredSize)) {
		std::snprintf(report, reportSize, "clearfonts off: ThreadService / InputService unavailable");
		return false;
	}
	static char toml[16384];
	uint32_t need = 0;
	g_wanted.store(context->ReadConfig(toml, sizeof(toml), &need) && ParseSetting(toml));
	g_filesOk = CheckFiles(selfPath);
	SetNames(false);
	g_live = false;
	g_pending.store(0);
	// the name entries first (same text as D2R's), then the pad, then the call that makes it live
	bool ok = true;
	for (int i = 0; ok && i < Count; ++i) {
		const uint64_t rva = NameTableRva + 8 * static_cast<uint64_t>(Ids[i]);
		const uint64_t old = g_base + D2RNameRvas[Ids[i]];
		const uint64_t now = reinterpret_cast<uint64_t>(g_names[i]);
		ok = context->PatchBytes(rva, &old, sizeof(old), &now, sizeof(now));
	}
	const AbsJump pad = AbsJumpBytes(reinterpret_cast<uint64_t>(&LangInitHook));
	const CallBytes call = CallTo(LangCallRva, PadRva);
	ok = ok && context->PatchBytes(PadRva, Pad, sizeof(Pad), pad.bytes, sizeof(pad.bytes)) &&
	     context->PatchBytes(LangCallRva, LangCall, sizeof(LangCall), call.bytes, sizeof(call.bytes));
	if (!ok) {
		std::snprintf(report, reportSize, "clearfonts FAILED: a patch was refused (fonts stay D2R's)");
		return false;
	}
	const D2RL::Input::ActionRegistration reg{
	    .structSize = D2RL::Input::ActionRegistrationSize,
	    .flags = 0,
	    .logicalId = "mxl_clear_fonts",
	    .displayName = "Clear Legacy Fonts",
	    .category = "D2R-XL 2012",
	    .defaultPrimary = {.key = D2RL::Input::Key::F, .modifier = D2RL::Input::Modifier::Control},
	    .defaultSecondary = {.key = D2RL::Input::Key::None, .modifier = D2RL::Input::Modifier::None},
	    .callback = &OnAction,
	    .userData = nullptr,
	};
	const auto rc = g_input->registerAction(context, &reg, &g_action);
	const bool action = rc == D2RL::Input::Result::Success && g_action != D2RL::Input::InvalidHandle;
	g_on = true;
	if (g_wanted.load()) {
		QueueApply();  // the language may be set up already
	}
	std::snprintf(report, reportSize, "clearfonts on: legacy_clear_fonts = %s (mxl2012-core.toml [fonts]), %s; Controls action mxl_clear_fonts "
	              "(default Ctrl+F)%s; font name table 0x1d84a00 ids 0 1 2 6 11 12, language set-up 0x902ff4 -> pad 0x903002",
	              g_wanted.load() ? "true" : "false", g_filesNote, action ? "" : " NOT registered");
	return true;
}

void ClearFontsStatus(char* out, size_t size) noexcept {
	uint32_t loaded = 0;
	if (g_base != 0) {
		for (int i = 0; i < Count; ++i) {
			loaded |= (*Slot(Ids[i]) != 0 ? 1u : 0u) << i;
		}
	}
	char language[8] = "-";
	if (g_base != 0) {
		std::snprintf(language, sizeof(language), "%.6s", Language());
	}
	std::snprintf(out, size, "on=%d wanted=%d live=%d files=%d (%s) language=%s current=%d loaded=0x%02x pending=0x%02x toggles=%ld frees=%ld handovers=%ld "
	              "langinits=%ld writes=%ld writefails=%ld names=%s",
	              g_on ? 1 : 0, g_wanted.load() ? 1 : 0, g_live ? 1 : 0, g_filesOk ? 1 : 0, g_filesNote, language,
	              g_base ? *reinterpret_cast<const int32_t*>(g_base + CurrentFontRva) : -1, loaded, g_pending.load(), g_toggles.load(),
	              g_frees.load(), g_handovers.load(), g_langInits.load(), g_writes.load(), g_writeFails.load(), g_names[0]);
}

auto ClearFontsSet(int on) noexcept -> bool {
	if (!g_on) {
		return false;
	}
	Toggle(on < 0 ? !g_wanted.load() : on != 0);
	return true;
}

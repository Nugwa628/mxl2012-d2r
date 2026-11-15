// A stash tab that needs Reign of the Warlock, on an account without it: the tab stays closed, a banner in huge letters across the
// middle of the screen says why, and the same line goes to the message log (docs/bugs.md #590; off word rotwwarn; rules in
// rotw_warn_logic.h).
//
// The stash's tabs 2-6 (Gems, Materials, Runes, MEDIAN, ORBS) are the RotW advanced stash. D2R asks the account's entitlement
// "rotw-dlc" through its own function (found by signature, rotw_warn_logic.h OwnsRotwPattern); the stash's tab update (part medtab,
// median_tabs.cpp) asks RotwWarnBlocks before D2R's update and keeps the tab shown before when the answer is "not owned". Mouse,
// keyboard and the gamepad's LT / RT all change the tab through that update.
// The banner is a native panel of this plugin ("mxl2012-core/RotwWarn", layouts in rotw_warn_logic.h, HD and legacy): a dark band
// with the line in red, centred on the screen. Its layout priority (9000) is above the stash's (5), so D2R draws it over the open
// stash and inventory. It has no click catcher, so clicks go on to the panels under it. Each blocked change opens it (or keeps it
// open) for BannerMs; a UI-thread tick closes it after that. D2RLoader's overlay text is not used: it does not show on this game
// (docs/dev-menu.md). The message log line goes through the client's chat packet handler (found by signature), at most once per 2 s.
// Not found: nothing is blocked (D2R's behaviour) and the report says so.
// Items into those pages without opening them (Ctrl-click, the gamepad's moves, controller-qol's Deposit All; bug #591): hooks of
// 0x15f320 (has the item a RotW slot) and 0x159a30 (the deposit packet) refuse them on such an account, with the banner and line
// "That stash tab needs ..." for a refused try; the inventory's Send to stash button asks RotwWarnStoreBlocked (send_stash.cpp).
// Dev builds: MXL_ROTW_OWNED_TEST=no|yes is this part's answer (D2R keeps its own), =d2r-no patches D2R's check to "not owned";
// MXL_ROTWWARN_TEST=off keeps the tabs as D2R opens them and lets items in (the control).
#include "rotw_warn.h"

#include "panel_shared.h"
#include "rotw_warn_logic.h"

#include <D2RLPlugin/localization.h>
#include <D2RLPlugin/panels.h>
#include <D2RLPlugin/threads.h>

#include <windows.h>

#include <intrin.h>

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

namespace {

using namespace rotw_warn;

using BoolFn = bool (*)() noexcept;
using ChatFn = void (*)(const uint8_t*) noexcept;
using HasSlotFn = bool (*)(uint32_t classId) noexcept;
using DepositFn = void (*)(void* item, void* stash) noexcept;

const D2RL::PluginContext* g_context = nullptr;
const D2RL::LocalizationService* g_strings = nullptr;
BoolFn g_owns = nullptr;
ChatFn g_chat = nullptr;
uint64_t g_ownsRva = 0, g_chatRva = 0;
bool g_gate = true;
OwnedTest g_test = OwnedTest::Game;
std::atomic<uint32_t> g_asks{0}, g_blocked{0}, g_lines{0};
std::atomic<uint64_t> g_lastLine{0};
char g_line[160] = "";
// D2R's answer, asked again at most every OwnedCacheMs
std::atomic<uint64_t> g_ownedAt{0};
std::atomic<bool> g_ownedLast{true};
// the store guard (bug #591)
HasSlotFn g_hasSlot = nullptr;
DepositFn g_deposit = nullptr;
bool g_storeGuard = false;
std::atomic<uint32_t> g_slotNo{0}, g_storeTries{0}, g_depositsBlocked{0};

// The banner panel. UI thread only, except the counters.
const D2RL::PanelService* g_panels = nullptr;
const D2RL::ThreadService* g_threads = nullptr;
D2RL::Panels::RegistrationHandle g_panel = D2RL::Panels::InvalidHandle;
bool g_bannerOn = false;
uint64_t g_bannerUntil = 0;
bool g_ticking = false;
bool g_textSet = false;
Line g_bannerKind = Line::Tab;
std::string g_bannerShown;
panel_shared::Client g_bannerClient;
std::atomic<uint32_t> g_bannerShows{0}, g_bannerOpens{0}, g_bannerCloses{0}, g_bannerTexts{0}, g_bannerFails{0};

auto TextSection(uint64_t base, const uint8_t** start, size_t* size) noexcept -> bool {
	const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
	const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + static_cast<uint64_t>(dos->e_lfanew));
	const IMAGE_SECTION_HEADER* s = IMAGE_FIRST_SECTION(nt);
	for (WORD i = 0; i < nt->FileHeader.NumberOfSections; ++i, ++s) {
		if (std::memcmp(s->Name, ".text", 6) == 0) {
			*start = reinterpret_cast<const uint8_t*>(base + s->VirtualAddress);
			*size = s->Misc.VirtualSize;
			return true;
		}
	}
	return false;
}

auto Find(const uint8_t* text, size_t size, uint64_t textRva, const char* pattern) noexcept -> uint64_t {
	Pattern p;
	if (!Parse(pattern, p)) {
		return 0;
	}
	const long long at = FindUnique(text, size, p);
	return at < 0 ? 0 : textRva + static_cast<uint64_t>(at);
}

auto ExpansionName(char* out, size_t size) noexcept -> const char* {
	uint32_t need = 0;
	if (g_strings == nullptr || g_strings->getStringByKey(g_context, "d2r:RotWLong", out, static_cast<uint32_t>(size), &need) != D2RL::Localization::Result::Success) {
		out[0] = '\0';
	}
	return out;
}

auto BannerOpen() noexcept -> bool {
	D2RL::Panels::PanelInfo info{};
	info.structSize = D2RL::Panels::PanelInfoSize;
	return g_panels->getPanelInfo(g_context, g_panel, &info) == D2RL::Panels::Result::Success && info.presentationState == D2RL::Panels::PresentationState::Open;
}

// UI thread, once per UI update while a banner is due: opens the panel and sets its line (D2R's localized name), closes it when the
// time is up, and queues itself again until then.
void __cdecl BannerTick(const D2RL::PluginContext* context, void*) noexcept {
	if (BannerShown(GetTickCount64(), g_bannerUntil)) {
		if (!BannerOpen()) {
			if (g_panels->openPanel(context, g_panel) != D2RL::Panels::Result::Success) {
				g_bannerFails.fetch_add(1, std::memory_order_relaxed);
				g_ticking = false;
				return;
			}
			g_bannerOpens.fetch_add(1, std::memory_order_relaxed);
			g_textSet = false;
		}
		if (!g_textSet) {
			if (void* panel = panel_shared::NativePanel(g_bannerClient); panel != nullptr) {
				char name[96];
				char line[sizeof(g_line)];
				WarningLine(g_bannerKind, line, sizeof(line), ExpansionName(name, sizeof(name)));
				panel_shared::SetLine(g_bannerClient, panel, BannerLineName, g_bannerShown, line, true);
				g_textSet = true;
				g_bannerTexts.fetch_add(1, std::memory_order_relaxed);
			}
		}
		if (g_threads->runOnUiThread(context, &BannerTick, nullptr) != D2RL::Threads::Result::Success) {
			g_ticking = false;  // the next blocked click starts it again; the panel closes then
		}
		return;
	}
	if (BannerOpen() && g_panels->closePanel(context, g_panel) == D2RL::Panels::Result::Success) {
		g_bannerCloses.fetch_add(1, std::memory_order_relaxed);
	}
	g_ticking = false;
}

// UI thread (the stash's tab update): the banner shows for BannerMs from now. The panel opens on the next UI update, not inside D2R's
// tab update.
void ShowBanner(Line kind) noexcept {
	if (!g_bannerOn) {
		return;
	}
	if (kind != g_bannerKind) {  // an open banner gets the new line
		g_bannerKind = kind;
		g_textSet = false;
	}
	g_bannerUntil = GetTickCount64() + BannerMs;
	g_bannerShows.fetch_add(1, std::memory_order_relaxed);
	if (!g_ticking) {
		g_ticking = g_threads->runOnUiThread(g_context, &BannerTick, nullptr) == D2RL::Threads::Result::Success;
		if (!g_ticking) {
			g_bannerFails.fetch_add(1, std::memory_order_relaxed);
		}
	}
}

auto RegisterBanner(const D2RL::PluginContext* context) noexcept -> bool {
	if (context->QueryService(&g_threads) != D2RL::ServiceQueryResult::Success || !D2RL::HasThreadServiceField(g_threads, D2RL::ThreadServiceRequiredSize) ||
	    context->QueryService(&g_panels) != D2RL::ServiceQueryResult::Success || !D2RL::HasPanelServiceField(g_panels, D2RL::PanelServiceRequiredSize) ||
	    !panel_shared::Init(context)) {
		return false;
	}
	if (!panel_shared::RegisterLayout(context, "RotwWarnhd", BannerLayoutHd, std::strlen(BannerLayoutHd)) ||
	    !panel_shared::RegisterLayout(context, "RotwWarn", BannerLayoutSd, std::strlen(BannerLayoutSd))) {
		return false;
	}
	g_bannerClient.panelName = BannerPanelName;
	D2RL::Panels::PanelRegistration panel{};
	panel.structSize = D2RL::Panels::PanelRegistrationSize;
	panel.flags = D2RL::Panels::PanelFlags::None;
	panel.localId = BannerLocalId;
	return g_panels->registerPanel(context, &panel, &g_panel) == D2RL::Panels::Result::Success;
}

void Warn(Line kind) noexcept {
	ShowBanner(kind);
	const uint64_t now = GetTickCount64();
	if (!WarnNow(now, g_lastLine.load(), WarnGapMs)) {
		return;
	}
	g_lastLine.store(now);
	char name[96];
	WarningLine(kind, g_line, sizeof(g_line), ExpansionName(name, sizeof(name)));
	if (g_chat == nullptr) {
		return;
	}
	uint8_t packet[0x0b + 0x100];
	const size_t len = std::strlen(g_line);
	std::memset(packet, 0, sizeof(packet));
	packet[0] = 0x26;  // chat, type 4: a line in the message log, colour 0 white (map_reveal_logic.h BuildChatPacket)
	packet[1] = 4;
	std::memcpy(packet + 0x0b, g_line, len < 0xff ? len : 0xff);
	g_chat(packet);
	g_lines.fetch_add(1);
}

// 0x15f320: no RotW slot for any item while items stay out; a refused question of the transfer is a try to store one.
auto HasSlotHook(uint32_t classId) noexcept -> bool {
	const bool has = g_hasSlot(classId);
	if (!has || !RotwWarnStoreBlocked()) {
		return has;
	}
	g_slotNo.fetch_add(1, std::memory_order_relaxed);
	if (IsTransferAsk(reinterpret_cast<uint64_t>(_ReturnAddress()) - g_context->exeBase)) {
		g_storeTries.fetch_add(1, std::memory_order_relaxed);
		Warn(Line::Store);
	}
	return false;
}

// 0x159a30: the deposit packet is not sent while items stay out.
void DepositHook(void* item, void* stash) noexcept {
	if (RotwWarnStoreBlocked()) {
		g_depositsBlocked.fetch_add(1, std::memory_order_relaxed);
		Warn(Line::Store);
		return;
	}
	g_deposit(item, stash);
}

}  // namespace

auto InstallRotwWarn(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	g_context = context;
	const uint64_t base = context->exeBase;
#ifndef MXL_RELEASE
	char env[16] = "";
	if (GetEnvironmentVariableA("MXL_ROTW_OWNED_TEST", env, sizeof(env)) > 0) {
		g_test = ParseOwnedTest(env);
	}
	if (GetEnvironmentVariableA("MXL_ROTWWARN_TEST", env, sizeof(env)) > 0 && std::strcmp(env, "off") == 0) {
		g_gate = false;
	}
#endif
	const uint8_t* text = nullptr;
	size_t size = 0;
	if (!TextSection(base, &text, &size)) {
		std::snprintf(report, reportSize, "rotwwarn off: no .text section");
		return false;
	}
	const uint64_t textRva = static_cast<uint64_t>(text - reinterpret_cast<const uint8_t*>(base));
	g_ownsRva = Find(text, size, textRva, OwnsRotwPattern);
	g_chatRva = Find(text, size, textRva, ClientChatPattern);
	if (g_ownsRva == 0) {
		std::snprintf(report, reportSize, "rotwwarn off: D2R's RotW entitlement check not found by its signature (no tab is blocked)");
		return false;
	}
	if (context->QueryService(&g_strings) != D2RL::ServiceQueryResult::Success ||
	    !D2RL::HasLocalizationServiceField(g_strings, D2RL::LocalizationServiceRequiredSize)) {
		g_strings = nullptr;  // the English name
	}
	g_bannerOn = RegisterBanner(context);
	bool ok = true;
	if (g_test == OwnedTest::D2rNo) {  // dev only: mov al, 0 / ret at the entry
		const uint8_t answer[3] = {0xb0, 0, 0xc3};
		uint8_t was[3];
		std::memcpy(was, reinterpret_cast<const void*>(base + g_ownsRva), sizeof(was));
		ok = context->PatchBytes(g_ownsRva, was, sizeof(was), answer, sizeof(answer));
	}
	g_owns = reinterpret_cast<BoolFn>(base + g_ownsRva);
	if (g_chatRva != 0) {
		g_chat = reinterpret_cast<ChatFn>(base + g_chatRva);
	}
	g_storeGuard = ok && context->InstallInlineHook(RvaHasSlot, HasSlotEntry, sizeof(HasSlotEntry), reinterpret_cast<void*>(&HasSlotHook),
	                                                reinterpret_cast<void**>(&g_hasSlot)) &&
	               context->InstallInlineHook(RvaDeposit, DepositEntry, sizeof(DepositEntry), reinterpret_cast<void*>(&DepositHook),
	                                          reinterpret_cast<void**>(&g_deposit));
	std::snprintf(report, reportSize, "rotwwarn %s: stash tabs 2-6 stay closed without Reign of the Warlock (entitlement check 0x%llx, "
	              "message line %s, banner %s, items kept out %s)%s", !ok ? "FAILED" : g_gate ? "on" : "test off (tabs open as D2R)", static_cast<unsigned long long>(g_ownsRva),
	              g_chatRva != 0 ? "on" : "off: chat handler not found", g_bannerOn ? "on" : "off: a loader service or the panel registration failed",
	              g_storeGuard ? "on (0x15f320, 0x159a30)" : "OFF: the bytes of 0x15f320 / 0x159a30 differ or a hook failed",
	              g_test == OwnedTest::No    ? "; TEST: answered 'not owned' (D2R keeps its own answer)"
	              : g_test == OwnedTest::Yes ? "; TEST: answered 'owned'"
	              : g_test == OwnedTest::D2rNo ? "; TEST: D2R's entitlement check patched to 'not owned'"
	                                           : "");
	if (!ok) {
		g_owns = nullptr;
	}
	return ok;
}

auto RotwWarnOwned() noexcept -> bool {
	if (g_test == OwnedTest::No || g_test == OwnedTest::Yes) {
		return g_test == OwnedTest::Yes;
	}
	if (g_owns == nullptr) {
		return true;
	}
	const uint64_t now = GetTickCount64();
	if (WarnNow(now, g_ownedAt.load(std::memory_order_relaxed), OwnedCacheMs)) {
		g_ownedLast.store(g_owns(), std::memory_order_relaxed);
		g_ownedAt.store(now, std::memory_order_relaxed);
	}
	return g_ownedLast.load(std::memory_order_relaxed);
}

auto RotwWarnStoreBlocked() noexcept -> bool {
	return StoreBlocked(g_owns != nullptr, g_gate, RotwWarnOwned());
}

void RotwWarnSendRefused() noexcept {
	ShowBanner(Line::Send);
}

auto RotwWarnBlocks(int to) noexcept -> bool {
	if (g_owns == nullptr || !NeedsRotw(to)) {
		return false;
	}
	g_asks.fetch_add(1);
	if (!g_gate || Decide(to, RotwWarnOwned()) == Verdict::Open) {
		return false;
	}
	g_blocked.fetch_add(1);
	Warn(Line::Tab);
	return true;
}

void RotwWarnStatus(char* out, size_t outSize) noexcept {
	std::snprintf(out, outSize, "owned %s; asks %u, blocked %u, lines %u; banner shows %u, opens %u, closes %u, texts %u, fails %u; "
	              "store guard %s, slot no %u, store tries %u, deposits blocked %u; last line \"%s\"",
	              g_owns == nullptr ? "-" : RotwWarnOwned() ? "yes" : "no", g_asks.load(), g_blocked.load(), g_lines.load(), g_bannerShows.load(),
	              g_bannerOpens.load(), g_bannerCloses.load(), g_bannerTexts.load(), g_bannerFails.load(), g_storeGuard ? "on" : "off", g_slotNo.load(),
	              g_storeTries.load(), g_depositsBlocked.load(), g_line);
}

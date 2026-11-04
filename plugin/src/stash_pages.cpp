// Personal stash page 2 (docs/plugin-plan.md section 8.2; off word stashpage2).
//
// D2RLoader's InventoryService gives a plugin one custom player page: item page 6 in the .d2s plus `<char>.d2rl`, restored on load
// by D2RCore (which stops the load rather than drop an item it cannot place: the "protected page"), moved with the cursor and with
// Ctrl+click like any stash page. This part registers that page (logical id `stash2`) at the stock stash's 10 x 10 and a panel,
// "mxl2012-core/StashPage2", whose layout looks like the personal stash and whose grid is bound to the page (HD and classic layouts
// from tools/stash_page2.py, in mxl_stash_page.h). The stock stash panel has two arrows under D2R's shared-stash ones that send
// PanelManager:TogglePanel:mxl2012-core/StashPage2 (tools/ui_layouts.py, tools/rotw_stash_legacy.py); the plugin panel's "2 / 2"
// strip opens the stock stash again. Both are D2R's own messages and the two panels share the left slot (opening one closes the
// other), so no plugin code is in the switch. On the Shared tab D2R's arrows draw over ours. The plugin hides the stock arrows
// when the page is not there; it would hide them on the other tabs too, but D2R 3.3 sends BankPanelMessage:SelectTab with an
// empty text (seen in game), so the tab it follows stays 0.
//
// Nothing here touches the save or the item lists: the page holds ordinary items, D2RCore saves them. The ItemService is used by the
// test harness only (`stashpage put|list|move|fill|drop`).
#include "stash_pages.h"

#include "mxl_stash_page.h"
#include "stash_pages_logic.h"

#include <D2RLPlugin/inventory.h>
#include <D2RLPlugin/item.h>
#include <D2RLPlugin/panels.h>
#include <D2RLPlugin/resources.h>
#include <D2RLPlugin/shared_events.h>
#include <D2RLPlugin/threads.h>
#include <D2RLPlugin/widgets.h>

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

const D2RL::PluginContext* g_context = nullptr;
const D2RL::InventoryService* g_inventory = nullptr;
const D2RL::PanelService* g_panels = nullptr;
const D2RL::ThreadService* g_threads = nullptr;
const D2RL::WidgetService* g_widgets = nullptr;
const D2RL::ItemService* g_items = nullptr;
D2RL::Inventory::PageRegistrationHandle g_page = 0;
D2RL::Panels::RegistrationHandle g_panel = 0;
bool g_ready = false;
bool g_listening = false;

std::atomic<int> g_tab{0}, g_stripShown{-1};
std::atomic<uint32_t> g_openFailed{0}, g_messages{0}, g_stripSets{0};

constexpr uint32_t UiNames = 16, UiNameSize = 96;  // the last messages (g_messages counts them all)
char g_uiNames[UiNames][UiNameSize] = {};

auto ContainsNoCase(const char* hay, const char* needle) noexcept -> bool {
	if (hay == nullptr || needle == nullptr) {
		return false;
	}
	const size_t n = std::strlen(needle);
	for (; *hay != '\0'; ++hay) {
		size_t i = 0;
		while (i < n && hay[i] != '\0' && (hay[i] | 0x20) == (needle[i] | 0x20)) {
			++i;
		}
		if (i == n) {
			return true;
		}
	}
	return false;
}

// ---- the stock stash's strip: shown on the Personal tab with the page there, hidden otherwise (UI thread only) ----

void __cdecl SetStripOnUiThread(const D2RL::PluginContext*, void*) noexcept {
	if (g_widgets == nullptr) {
		return;
	}
	D2RL::Widgets::WidgetHandle panel = 0, strip = 0;
	if (g_widgets->findPanel(g_context, mxl_stash_page::StockPanel, &panel) == D2RL::Widgets::Result::Success &&
	    g_widgets->findWidget(g_context, panel, mxl_stash_page::StockStrip, &strip) == D2RL::Widgets::Result::Success) {
		const bool show = stash_pages::StripVisible(g_ready, g_tab.load());
		if (g_widgets->setWidgetVisible(g_context, strip, show) == D2RL::Widgets::Result::Success) {
			g_stripShown.store(show ? 1 : 0);
			g_stripSets.fetch_add(1);
		}
	}
}

auto __cdecl OnUiMessage(const D2RL::PluginContext*, const D2RL::SharedEvents::UiMessageEvent* event, void*) noexcept -> D2RL::SharedEvents::UiMessageAction {
	if (event == nullptr || event->target == nullptr || event->command == nullptr) {
		return D2RL::SharedEvents::UiMessageAction::Continue;
	}
	bool update = false;
	if (stash_pages::StockStashOpens(event->command, event->text, mxl_stash_page::StockPanel)) {
		g_tab.store(0);
		update = true;
	}
	const int tab = stash_pages::SelectedTab(event->target, event->command, event->text);
	if (tab >= 0) {
		g_tab.store(tab);
		update = true;
	}
	if (update && g_threads != nullptr) {
		(void)g_threads->runOnUiThread(g_context, &SetStripOnUiThread, nullptr);  // after D2R has handled the message
	}
	if (ContainsNoCase(event->target, "bank") || ContainsNoCase(event->target, "stash") || ContainsNoCase(event->text, "bank") ||
	    ContainsNoCase(event->text, "stash")) {
		char key[UiNameSize];
		std::snprintf(key, sizeof(key), "%s:%s(%s)", event->target, event->command, event->text != nullptr ? event->text : "");
		const uint32_t n = g_messages.fetch_add(1);
		std::memcpy(g_uiNames[n % UiNames], key, sizeof(key));
	}
	return D2RL::SharedEvents::UiMessageAction::Continue;
}

auto WatchUiMessages(const D2RL::PluginContext* context) noexcept -> bool {
	const D2RL::SharedEventService* events = nullptr;
	if (context->QueryService(&events) != D2RL::ServiceQueryResult::Success || !D2RL::HasSharedEventServiceField(events, D2RL::SharedEventServiceRequiredSize)) {
		return false;
	}
	D2RL::SharedEvents::UiMessageListener listener{};
	listener.structSize = D2RL::SharedEvents::UiMessageListenerSize;
	listener.callback = &OnUiMessage;
	D2RL::SharedEvents::ListenerHandle handle = 0;
	return events->registerUiMessageListener(context, &listener, &handle) == D2RL::SharedEvents::Result::Success;
}

// ---- game thread jobs (harness) ----

struct Job {
	std::atomic<int> state{0};  // 0 never queued, 1 queued, 2 finished
	char op[12] = "";
	long long a = 0, b = 0, c = 0;
	char code[8] = "";
	int ok = 0;
	char text[900] = "";
};
Job g_job;

struct Listing {
	char* text = nullptr;
	size_t size = 0;
	size_t used = 0;
	uint32_t count = 0;
	uint64_t wantId = 0;                 // runtime id to find (move)
	D2RL::ItemHandle found = 0;
	uint32_t wantCode = 0;               // collect the handles of the items with this code (drop)
	D2RL::ItemHandle* handles = nullptr;
	uint32_t handleCap = 0, handleCount = 0;
};

auto ContainerName(D2RL::Items::ItemContainer c) noexcept -> const char* {
	switch (c) {
	case D2RL::Items::ItemContainer::CustomPage: return "p2";
	case D2RL::Items::ItemContainer::PersonalStash: return "p1";
	case D2RL::Items::ItemContainer::Inventory: return "inv";
	default: return "??";
	}
}

auto __cdecl OnItem(const D2RL::PluginContext*, const D2RL::Items::ItemInfo* item, void* user) noexcept -> D2RL::Inventory::IterationAction {
	auto* l = static_cast<Listing*>(user);
	++l->count;
	if (l->wantId != 0 && item->runtimeId == l->wantId) {
		l->found = item->handle;
	}
	if (l->wantCode != 0 && item->code == l->wantCode && l->handleCount < l->handleCap) {
		l->handles[l->handleCount++] = item->handle;
	}
	if (l->text != nullptr && l->used + 48 < l->size) {
		char code[5] = {static_cast<char>(item->code), static_cast<char>(item->code >> 8), static_cast<char>(item->code >> 16), static_cast<char>(item->code >> 24), 0};
		for (int i = 3; i >= 0 && code[i] == ' '; --i) {
			code[i] = '\0';
		}
		const int w = std::snprintf(l->text + l->used, l->size - l->used, "%s%s:%s@%d,%d#%u", l->used > 0 ? " " : "", ContainerName(item->container), code,
		                            item->x, item->y, item->runtimeId);
		if (w > 0) {
			l->used += static_cast<size_t>(w);
		}
	}
	return D2RL::Inventory::IterationAction::Continue;
}

auto Scan(const D2RL::PluginContext* context, D2RL::PlayerHandle player, Listing* l) noexcept -> bool {
	D2RL::Inventory::ItemFilter filter{};
	filter.structSize = D2RL::Inventory::ItemFilterSize;
	filter.containerMask = D2RL::Items::ContainerBit(D2RL::Items::ItemContainer::PersonalStash) | D2RL::Items::ContainerBit(D2RL::Items::ItemContainer::CustomPage) |
	                       D2RL::Items::ContainerBit(D2RL::Items::ItemContainer::Inventory);
	return g_inventory->forEachInventoryItem(context, player, &filter, &OnItem, l) == D2RL::Inventory::Result::Success;
}

void FillDestination(D2RL::Items::ItemDestination* d, int page, long long x, long long y) noexcept {
	d->structSize = D2RL::Items::ItemDestinationSize;
	d->container = page == 2 ? D2RL::Items::ItemContainer::CustomPage : D2RL::Items::ItemContainer::PersonalStash;
	d->customPageHandle = page == 2 ? g_page : 0;
	d->placement = x >= 0 && y >= 0 ? D2RL::Items::Placement::Exact : D2RL::Items::Placement::Automatic;
	d->x = x >= 0 ? static_cast<uint32_t>(x) : 0;
	d->y = y >= 0 ? static_cast<uint32_t>(y) : 0;
}

auto CreateOne(const D2RL::PluginContext* context, D2RL::PlayerHandle player, uint32_t code, int page, long long x, long long y, D2RL::ItemHandle* out) noexcept -> int {
	D2RL::Items::ItemCreateSpec spec{};
	spec.structSize = D2RL::Items::ItemCreateSpecSize;
	spec.code = code;
	spec.quality = D2RL::Items::Quality::Normal;
	spec.qualityRecordId = D2RL::Items::RandomQualityRecord;
	spec.itemLevel = 1;
	spec.seedMode = D2RL::Items::SeedMode::Random;
	spec.quantity = D2RL::Items::DefaultValue;
	spec.durability = D2RL::Items::DefaultValue;
	FillDestination(&spec.destination, page, x, y);
	return static_cast<int>(g_items->createItem(context, player, &spec, out));
}

auto CodeOf(const char* text) noexcept -> uint32_t {
	char padded[5];
	stash_pages::PaddedCode(text, padded);
	return D2RL::Items::MakeItemCode(padded[0], padded[1], padded[2], padded[3]);
}

void __cdecl JobOnGameThread(const D2RL::PluginContext* context, void*) noexcept {
	Job& job = g_job;
	job.ok = 0;
	job.text[0] = '\0';
	D2RL::PlayerHandle player = D2RL::InvalidPlayerHandle;
	if (g_inventory->getLocalPlayer(context, &player) != D2RL::Inventory::Result::Success) {
		std::snprintf(job.text, sizeof(job.text), "no local player");
		job.state.store(2);
		return;
	}
	if (std::strcmp(job.op, "put") == 0) {
		D2RL::ItemHandle item = D2RL::InvalidItemHandle;
		const int rc = CreateOne(context, player, CodeOf(job.code), 2, job.a, job.b, &item);
		D2RL::Items::ItemInfo info{};
		info.structSize = D2RL::Items::ItemInfoSize;
		if (rc == 0 && g_items->getItemInfo(context, item, &info) == D2RL::Items::Result::Success) {
			std::snprintf(job.text, sizeof(job.text), "put create=0 container=%u at %d,%d id=%u", static_cast<unsigned>(info.container), info.x, info.y, info.runtimeId);
			job.ok = 1;
		} else {
			std::snprintf(job.text, sizeof(job.text), "put create=%d", rc);
		}
	} else if (std::strcmp(job.op, "fill") == 0) {
		int made = 0, rc = 0;
		for (int i = 0; i < 400 && rc == 0; ++i) {
			D2RL::ItemHandle item = D2RL::InvalidItemHandle;
			rc = CreateOne(context, player, CodeOf(job.code), static_cast<int>(job.a), -1, -1, &item);
			made += rc == 0 ? 1 : 0;
		}
		std::snprintf(job.text, sizeof(job.text), "fill page %lld: %d %s placed, stopped with create=%d", job.a, made, job.code, rc);
		job.ok = made > 0 ? 1 : 0;
	} else if (std::strcmp(job.op, "list") == 0) {
		char items[860] = "";
		Listing l{};
		l.text = items;
		l.size = sizeof(items);
		job.ok = Scan(context, player, &l) ? 1 : 0;
		std::snprintf(job.text, sizeof(job.text), "n=%u %s", l.count, items);
	} else if (std::strcmp(job.op, "move") == 0) {
		Listing l{};
		l.wantId = static_cast<uint64_t>(job.a);
		if (!Scan(context, player, &l) || l.found == 0) {
			std::snprintf(job.text, sizeof(job.text), "move: item #%lld not found on the pages or in the backpack", job.a);
		} else {
			D2RL::Items::ExistingItemOperation op{};
			op.structSize = D2RL::Items::ExistingItemOperationSize;
			op.kind = D2RL::Items::ExistingItemOperationKind::Move;
			op.item = l.found;
			FillDestination(&op.move.destination, static_cast<int>(job.b), stash_pages::CellX(job.c), stash_pages::CellY(job.c));
			D2RL::Items::ExistingItemTransaction tx{};
			tx.structSize = D2RL::Items::ExistingItemTransactionSize;
			tx.player = player;
			tx.operationCount = 1;
			tx.operations = &op;
			D2RL::Items::ExistingItemTransactionResult result{};
			result.structSize = D2RL::Items::ExistingItemTransactionResultSize;
			const auto rc = g_items->executeExistingItemTransaction(context, &tx, &result);
			std::snprintf(job.text, sizeof(job.text), "move rc=%u committed=%u fail=%u", static_cast<unsigned>(rc), result.committedOperationCount, result.failureIndex);
			job.ok = rc == D2RL::Items::Result::Success ? 1 : 0;
		}
	} else if (std::strcmp(job.op, "drop") == 0) {
		// the checks' clean-up: destroy every item of one code on the two pages and in the backpack (codes the checks made)
		static D2RL::ItemHandle handles[512];
		Listing l{};
		l.wantCode = CodeOf(job.code);
		l.handles = handles;
		l.handleCap = 512;
		int destroyed = 0;
		if (Scan(context, player, &l)) {
			for (uint32_t i = 0; i < l.handleCount; ++i) {
				destroyed += g_items->destroyItem(context, player, handles[i], D2RL::Items::SocketedItemPolicy::DestroyContents) == D2RL::Items::Result::Success ? 1 : 0;
			}
		}
		std::snprintf(job.text, sizeof(job.text), "drop %s: %u found, %d destroyed", job.code, l.handleCount, destroyed);
		job.ok = destroyed == static_cast<int>(l.handleCount) ? 1 : 0;
	} else {
		std::snprintf(job.text, sizeof(job.text), "unknown op %s", job.op);
	}
	job.state.store(2);
}

void __cdecl OpenOnUiThread(const D2RL::PluginContext* context, void* user) noexcept {
	const int mode = static_cast<int>(reinterpret_cast<intptr_t>(user));
	if (g_panels == nullptr || g_panel == 0) {
		return;
	}
	const auto rc = mode == 0 ? g_panels->closePanel(context, g_panel) : mode == 1 ? g_panels->openPanel(context, g_panel) : g_panels->togglePanel(context, g_panel);
	if (rc != D2RL::Panels::Result::Success) {
		g_openFailed.fetch_add(1);
	}
}

auto RegisterLayout(const D2RL::ResourceService* resources, const D2RL::PluginContext* context, const char* suffix, const char* layout) noexcept -> bool {
	char path[160];
	std::snprintf(path, sizeof(path), "data/global/ui/layouts/mxl2012-core/%s%s.json", mxl_stash_page::PanelLocalId, suffix);
	D2RL::Resources::ResourceRegistration resource{};
	resource.structSize = D2RL::Resources::ResourceRegistrationSize;
	resource.path = path;
	resource.bytes = layout;
	resource.byteCount = std::strlen(layout);
	D2RL::Resources::RegistrationHandle handle = D2RL::Resources::InvalidHandle;
	return resources->registerResource(context, &resource, &handle) == D2RL::Resources::Result::Success;
}

}  // namespace

void StashPagesOff(const D2RL::PluginContext* context) noexcept {
	g_context = context;
	if (context->QueryService(&g_threads) != D2RL::ServiceQueryResult::Success) {
		g_threads = nullptr;
	}
	if (context->QueryService(&g_widgets) != D2RL::ServiceQueryResult::Success || !D2RL::HasWidgetServiceField(g_widgets, D2RL::WidgetServiceRequiredSize)) {
		g_widgets = nullptr;
	}
	if (!g_listening && g_threads != nullptr && g_widgets != nullptr) {
		g_listening = WatchUiMessages(context);  // hides the stock stash's page 2 arrows when it is built: nothing is behind its arrows
	}
}

auto InstallStashPages(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	StashPagesOff(context);  // the strip stays hidden until the page and panel are registered (g_ready)
	const D2RL::ResourceService* resources = nullptr;
	if (context->QueryService(&g_inventory) != D2RL::ServiceQueryResult::Success ||
	    !D2RL::HasInventoryServiceField(g_inventory, D2RL::InventoryServiceRequiredSize) ||
	    context->QueryService(&resources) != D2RL::ServiceQueryResult::Success ||
	    !D2RL::HasResourceServiceField(resources, D2RL::ResourceServiceRequiredSize) ||
	    context->QueryService(&g_panels) != D2RL::ServiceQueryResult::Success || !D2RL::HasPanelServiceField(g_panels, D2RL::PanelServiceRequiredSize) ||
	    g_threads == nullptr) {
		std::snprintf(report, reportSize, "off: InventoryService / ResourceService / PanelService / ThreadService unavailable");
		return false;
	}
	if (context->QueryService(&g_items) != D2RL::ServiceQueryResult::Success || !D2RL::HasItemServiceField(g_items, D2RL::ItemServiceRequiredSize)) {
		g_items = nullptr;
	}

	// the page: the stock stash's size, any item (default policy), charms on it stay inactive (D2RLoader's default
	// StockInventoryOnly), as in the stash
	D2RL::Inventory::PlayerPageRegistration registration{};
	registration.structSize = D2RL::Inventory::PlayerPageRegistrationSize;
	registration.logicalId = "stash2";
	const auto reg = g_inventory->registerPlayerPage(context, &registration, &g_page);
	if (reg != D2RL::Inventory::Result::Success) {
		std::snprintf(report, reportSize, "off: registerPlayerPage result %u (the loader has one custom page and another plugin owns it)", static_cast<unsigned>(reg));
		return false;
	}
	D2RL::Inventory::PlayerPageConfiguration configuration{};
	configuration.structSize = D2RL::Inventory::PlayerPageConfigurationSize;
	configuration.width = mxl_stash_page::Width;
	configuration.height = mxl_stash_page::Height;
	const auto cfg = g_inventory->configurePlayerPage(context, g_page, &configuration);
	if (cfg != D2RL::Inventory::Result::Success) {
		std::snprintf(report, reportSize, "off: configurePlayerPage %ux%u failed (result %u)", mxl_stash_page::Width, mxl_stash_page::Height, static_cast<unsigned>(cfg));
		return false;
	}

	// the panel: HD and classic layouts (D2R picks the file of the graphics mode)
	const bool hd = RegisterLayout(resources, context, "hd", mxl_stash_page::LayoutHd);
	const bool classic = RegisterLayout(resources, context, "", mxl_stash_page::LayoutClassic);
	D2RL::Panels::PanelRegistration panel{};
	panel.structSize = D2RL::Panels::PanelRegistrationSize;
	panel.flags = D2RL::Panels::PanelFlags::CloseOnEscape | D2RL::Panels::PanelFlags::GameplayLeftSlot;
	panel.localId = mxl_stash_page::PanelLocalId;
	if (!hd || g_panels->registerPanel(context, &panel, &g_panel) != D2RL::Panels::Result::Success) {
		std::snprintf(report, reportSize, "partial: the page is registered but the panel is not (layout resource %s / registerPanel failed)", hd ? "ok" : "refused");
		return false;
	}
	D2RL::Panels::PlayerPageGridBinding binding{};
	binding.structSize = D2RL::Panels::PlayerPageGridBindingSize;
	binding.panel = g_panel;
	binding.page = g_page;
	binding.childName = mxl_stash_page::GridName;
	const bool bound = g_panels->bindPlayerPageGrid(context, &binding) == D2RL::Panels::Result::Success;

	g_ready = bound;
	std::snprintf(report, reportSize, "%s: personal stash page 2 (%u x %u, item page 6, id stash2), grid %s, classic layout %s", g_ready ? "on" : "partial",
	              mxl_stash_page::Width, mxl_stash_page::Height, bound ? "bound" : "NOT bound", classic ? "registered" : "refused");
	return g_ready;
}

void StashPagesStatus(char* out, size_t outSize) noexcept {
	std::snprintf(out, outSize, "%s; panel %s, stock tab %d, strip %s (%u sets), panel opens failed %u, %u stash messages seen",
	              g_ready ? "page ready" : "no page", g_panel != 0 ? "registered" : "none", g_tab.load(),
	              g_stripShown.load() < 0 ? "not set yet" : g_stripShown.load() ? "shown" : "hidden", g_stripSets.load(), g_openFailed.load(), g_messages.load());
}

auto StashPageOpen(int mode) noexcept -> int {
	if (!g_ready || g_threads == nullptr) {
		return -1;
	}
	return g_threads->runOnUiThread(g_context, &OpenOnUiThread, reinterpret_cast<void*>(static_cast<intptr_t>(mode))) == D2RL::Threads::Result::Success ? 0 : -1;
}

auto StashPageState() noexcept -> int {
	if (!g_ready) {
		return -1;
	}
	D2RL::Panels::PanelInfo info{};
	info.structSize = D2RL::Panels::PanelInfoSize;
	if (g_panels->getPanelInfo(g_context, g_panel, &info) != D2RL::Panels::Result::Success) {
		return -1;
	}
	return static_cast<int>(info.presentationState);
}

void StashPageTab(int* tab, int* stripShown) noexcept {
	*tab = g_tab.load();
	*stripShown = g_stripShown.load();
}

auto StashPageUiAction(const char* target, const char* command, const char* text) noexcept -> int {
	if (g_widgets == nullptr) {
		return -1;
	}
	D2RL::Widgets::UiAction action{};
	action.structSize = D2RL::Widgets::UiActionSize;
	action.target = target;
	action.command = command;
	action.text = text;
	return static_cast<int>(g_widgets->dispatchUiAction(g_context, &action));
}

void StashPageWidget(const char* panel, const char* child, char* out, size_t outSize) noexcept {
	if (g_widgets == nullptr) {
		std::snprintf(out, outSize, "no WidgetService");
		return;
	}
	D2RL::Widgets::WidgetHandle p = 0, w = 0;
	const auto rp = g_widgets->findPanel(g_context, panel, &p);
	if (rp != D2RL::Widgets::Result::Success) {
		std::snprintf(out, outSize, "findPanel(%s) = %u", panel, static_cast<unsigned>(rp));
		return;
	}
	w = p;
	if (child != nullptr && child[0] != '\0') {
		const auto rw = g_widgets->findWidget(g_context, p, child, &w);
		if (rw != D2RL::Widgets::Result::Success) {
			std::snprintf(out, outSize, "findPanel(%s) ok, findWidget(%s) = %u", panel, child, static_cast<unsigned>(rw));
			return;
		}
	}
	D2RL::Widgets::Rect r{};
	const auto rr = g_widgets->getWidgetRect(g_context, w, &r);
	std::snprintf(out, outSize, "%s/%s rect result %u x=%d y=%d w=%d h=%d", panel, child != nullptr ? child : "", static_cast<unsigned>(rr), r.x, r.y, r.width, r.height);
}

auto StashPageSetVisible(const char* panel, const char* child, bool visible) noexcept -> int {
	if (g_widgets == nullptr) {
		return -1;
	}
	D2RL::Widgets::WidgetHandle p = 0, w = 0;
	if (g_widgets->findPanel(g_context, panel, &p) != D2RL::Widgets::Result::Success ||
	    g_widgets->findWidget(g_context, p, child, &w) != D2RL::Widgets::Result::Success) {
		return -2;
	}
	return static_cast<int>(g_widgets->setWidgetVisible(g_context, w, visible));
}

void StashPageMessages(char* out, size_t outSize) noexcept {
	size_t used = 0;
	out[0] = '\0';
	const uint32_t total = g_messages.load();
	const uint32_t first = total > UiNames ? total - UiNames : 0;
	for (uint32_t i = total; i > first && used + 1 < outSize; --i) {  // newest first: a long list is cut at the oldest
		const int w = std::snprintf(out + used, outSize - used, "%s%s", used > 0 ? " " : "", g_uiNames[(i - 1) % UiNames]);
		used = w > 0 && used + static_cast<size_t>(w) < outSize ? used + static_cast<size_t>(w) : outSize;
	}
}

auto StashPageJob(const char* op, long long a, long long b, long long c, const char* code, char* out, size_t outSize) noexcept -> int {
	if (!g_ready || g_items == nullptr || g_threads == nullptr) {
		std::snprintf(out, outSize, "stash page or ItemService not ready");
		return 0;
	}
	if (g_job.state.load() == 1) {
		std::snprintf(out, outSize, "a job is still queued");
		return 0;
	}
	std::snprintf(g_job.op, sizeof(g_job.op), "%s", op);
	std::snprintf(g_job.code, sizeof(g_job.code), "%s", code != nullptr ? code : "");
	g_job.a = a;
	g_job.b = b;
	g_job.c = c;
	g_job.state.store(1);
	if (g_threads->runOnGameThread(g_context, &JobOnGameThread, nullptr) != D2RL::Threads::Result::Success) {
		g_job.state.store(0);
		std::snprintf(out, outSize, "runOnGameThread refused");
		return 0;
	}
	std::snprintf(out, outSize, "queued");
	return 1;
}

auto StashPageResult(char* out, size_t outSize) noexcept -> int {
	const int state = g_job.state.load();
	if (state == 0) {
		std::snprintf(out, outSize, "never queued");
		return -2;
	}
	if (state == 1) {
		std::snprintf(out, outSize, "pending");
		return -1;
	}
	std::snprintf(out, outSize, "%s", g_job.text);
	return g_job.ok;
}

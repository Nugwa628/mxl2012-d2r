// Personal stash page 2 on D2RLoader's custom player page (stash_pages.cpp; docs/plugin-plan.md section 8.2, off word stashpage2).
//
// D2R has one personal stash page. D2RLoader lets ONE plugin own ONE custom player page (item page 6 in the .d2s plus
// `<char>.d2rl`, saved and restored by D2RCore), so the port has two personal pages: the stock stash (page 1) and a plugin panel
// with the same look and the same 10 x 10 grid (page 2). Both panels carry a "n / 2" strip with two arrows
// (tools/stash_page2.py). The shared stash keeps its tabs (d2rloader.toml add_shared_tabs, bug #535).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Registers the page, its panel (HD and classic layout resources, PanelService, grid binding) and the UI message listener that
// shows the stock stash's strip on the Personal tab only. D2RLoaderLoadPlugin only. True when page and panel are registered.
auto InstallStashPages(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;

// The part is off (mxl2012-core-off.txt): only the listener that hides the stock stash's page 2 arrows, because nothing is
// behind its arrows. InstallStashPages does the same when it cannot register the page.
void StashPagesOff(const D2RL::PluginContext* context) noexcept;

// "<state>; ..." for the mxl2012 console command.
void StashPagesStatus(char* out, size_t outSize) noexcept;

// ---- test harness (harness_cmds.cpp `stashpage`; client side = UI thread) ----

// Open / close / toggle the plugin panel. 0 queued, -1 not available.
auto StashPageOpen(int mode /* 0 close, 1 open, 2 toggle */) noexcept -> int;
// PanelState of the plugin panel: 0 unknown, 1 closed, 2 open, -1 not registered.
auto StashPageState() noexcept -> int;
// The stock stash tab last selected (0 Personal) and whether the strip was last set visible.
void StashPageTab(int* tab, int* stripShown) noexcept;
// A native UI message through WidgetService ("PanelManager", "OpenPanel", "BankExpansionLayout"). The service's result, -1 without it.
auto StashPageUiAction(const char* target, const char* command, const char* text) noexcept -> int;
// Rect of a stock or plugin panel (child = "" for the panel itself); text for the harness.
void StashPageWidget(const char* panel, const char* child, char* out, size_t outSize) noexcept;
// setWidgetVisible on a panel's child (UI thread).
auto StashPageSetVisible(const char* panel, const char* child, bool visible) noexcept -> int;
// The last stash related UI messages seen (target:command(text) ...).
void StashPageMessages(char* out, size_t outSize) noexcept;

// Queued work on the game thread (ItemService is game-thread only). op: "put <code> [x y]" creates an item on page 2, "list" lists
// the items of page 2, the personal stash and the backpack, "move <runtime id> <page 1|2> [x y]" moves one item (one atomic
// transaction), "fill <page>" fills a page with 1x1 runes until full, "drop <code>" destroys the items of that code on the two
// pages and in the backpack (the checks' clean-up). Returns 1 queued, 0 refused (text says why); StashPageResult has the answer.
auto StashPageJob(const char* op, long long a, long long b, long long c, const char* code, char* out, size_t outSize) noexcept -> int;
// 1 finished ok, 0 finished failed, -1 pending, -2 never queued; the text in `out`.
auto StashPageResult(char* out, size_t outSize) noexcept -> int;

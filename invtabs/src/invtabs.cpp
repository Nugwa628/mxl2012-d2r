// invtabs: inventory tabs on D2RLoader's custom player page (D2R-XL 2012, D2R 3.3 build 93847, D2RLoader 1.3.1).
// See docs/invtabs.md.
//
// Based on wild-healer's Player Page Host 1.0.2 and Wild Healer's Charm Inventory (D2R-Tools,
// github.com/wild-healer/D2R-Tools, commit 6722cc5, plugins/aaa-player-page-host and
// plugins/wild-healers-charm-inventory). Taken from them, adapted: the page registration and policies, the panel and
// grid layout, the grid widget wrappers that show one area of the page, the Ctrl+click placement (first free cell of the
// shown area, moved by the plugin with the area's type rule), the inventory button / Controls action / console command.
// Used with credit; shipping waits for wild-healer's OK.
//
// What it does:
//   - Registers the custom page (always, also when disabled: D2RCore refuses a character with page items and no page
//     owner) at 16 x 16. Charms count from it (and from the stock inventory with inventory_charms).
//   - The tabs come from invtabs.toml ([tabs.<name>]); each is an area of the page with its own type list and panel.
//     The charm tab is pinned at 0,0 (CharmInv 1.0.1's 10 x 4 charms are in it). Where each tab sits and how far its
//     items reach is remembered in invtabs-layout.txt beside the config: a config that would leave an item outside its
//     tab (a tab shrunk, moved or removed) or that overlaps is refused and the remembered layout stays. The plugin never
//     moves or deletes an item on its own.
//   - Each tab is a panel whose grid shows the whole page through the game's grid widget; the widget's vtable entries are
//     wrapped (found by signature) so a tab grid shows and accepts only its area. Without the signatures the tab shows
//     the whole page and drops are checked by type only.
//   - The page's item policy accepts an item in a tab when one of its types (with Equiv parents) is in the tab's list.
//   - Ctrl+click on a backpack item while a tab is shown moves it to the first free cell of that tab (when its type
//     list takes it); Ctrl+click on a tab item is D2RLoader's own move back to the backpack.
//   - The charm tab shows the summary of the counting charms' bonuses (summary.h) above its grid.
//   - TCP/IP games (docs/invtabs-mp.md, mp_protocol.h): only the hosting game changes items. A joined player's drag and
//     drop is the game's own request, judged by the hosting game's item policy; its Ctrl+click is a Move message the
//     hosting game plans and runs for that player. A joined player whose tab table differs from the hosting game's (or
//     whose hosting game has no invtabs channel) gets read-only tabs: take out only, with the reason above the summary.

#include <D2RLPlugin/api.h>

#define NOMINMAX
#include <windows.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <mutex>
#include <sstream>
#include <string>
#include <vector>

#include "invtabs_logic.h"
#include "invtabs_natives.h"
#include "layouts.h"
#include "mp_protocol.h"
#include "pad_route.h"
#include "summary.h"

namespace {

namespace Inv     = D2RL::Inventory;
namespace Panels  = D2RL::Panels;
namespace Res     = D2RL::Resources;
namespace Clicks  = D2RL::ItemInteractions;
namespace Tables  = D2RL::CustomTables;
namespace Items   = D2RL::Items;
namespace Widgets = D2RL::Widgets;
namespace Lay     = invtabs::layout;
namespace Net     = D2RL::Network;
namespace Mp      = invtabs::mp;
using invtabs::Area;

constexpr const char* PluginId      = "invtabs";
constexpr const char* PluginVersion = "0.2.0";
// D2RLoader's logical id of the page (kept stable: saved page items belong to the page).
constexpr const char* LogicalPageId = "charms";
constexpr const char* MemoryFile    = "invtabs-layout.txt";

constexpr D2RL::PluginInfo Info {
	.infoSize    = D2RL::PluginInfoSize,
	.abiVersion  = D2RL_PLUGIN_ABI_VERSION,
	.id          = PluginId,
	.name        = "Inventory Tabs",
	.version     = PluginVersion,
	.author      = "D2R-XL 2012, after wild-healer's Player Page Host",
	.description = "Tabs on the custom player page; the first is the charm inventory.",
	.flags       = D2RL::PluginFlags::Client | D2RL::PluginFlags::NativeHooks,
};

// ---- tabs ----

struct TabState {
	invtabs::Tab               cfg;
	std::string                id;    // panel local id: the name with a capital first letter (Charms)
	Area                       area;
	std::vector<invtabs::TypeCode> types; // under TypesLock
	bool                       classic = false; // has a classic layout (fits, and its classic art is in the mod)
	Panels::RegistrationHandle panel   = Panels::InvalidHandle;
	Res::RegistrationHandle    hd = Res::InvalidHandle, legacy = Res::InvalidHandle;
	std::string                hdText, legacyText;
	Tables::TableHandle        table = Tables::InvalidHandle;
	bool                       opened = false; // opened once since the layout was registered (UnloadPanel before a new one)
};

std::vector<TabState>      Tabs; // set at load; their areas and panels are fixed afterwards
TabState                   AllTab;
std::mutex                 TypesLock;
std::array<std::atomic<std::uint64_t>, invtabs::AllSlot + 1> LastDrawn {};
std::array<std::atomic<bool>, invtabs::AllSlot + 1>          DrawnClassic {};

std::string PanelName(const std::string& localId) { return std::string(PluginId) + "/" + localId; }

TabState* SlotTab(int slot) noexcept {
	if (slot >= 0 && slot < static_cast<int>(Tabs.size())) return &Tabs[static_cast<std::size_t>(slot)];
	return slot == invtabs::AllSlot ? &AllTab : nullptr;
}

Area AreaOfSlot(int slot) noexcept {
	if (slot >= 0 && slot < static_cast<int>(Tabs.size())) return Tabs[static_cast<std::size_t>(slot)].area;
	if (slot == invtabs::AllSlot) return { 0, 0, invtabs::PageSize, invtabs::PageSize };
	return {};
}

// ---- services, log ----

const D2RL::PluginContext*    Context {};
const D2RL::InventoryService* Inventory {};
const D2RL::PanelService*     PanelApi {};
const D2RL::ResourceService*  ResourceApi {};
const D2RL::ItemService*      ItemApi {};
const D2RL::ThreadService*    ThreadApi {};
const D2RL::WidgetService*    WidgetApi {};
const D2RL::CustomTableService* TableApi {};
Inv::PageRegistrationHandle   Page = Inv::InvalidHandle;
invtabs::Config               Settings;
invtabs::pad::Handles         PadHandles;

void Log(bool warn, const char* format, ...) noexcept {
	if (!Context) return;
	char    line[1024] = "invtabs: ";
	va_list args;
	va_start(args, format);
	std::vsnprintf(line + 9, sizeof(line) - 9, format, args);
	va_end(args);
	warn ? Context->LogWarn(line) : Context->LogInfo(line);
}

template <typename Service>
const Service* Query(const char* name) {
	const Service* service = nullptr;
	if (Context->QueryService(&service) != D2RL::ServiceQueryResult::Success || !service) {
		Log(true, "%s service unavailable", name);
		return nullptr;
	}
	return service;
}

// ---- natives (found by signature) ----

using InventoryFn   = void* (*)(void* unit, const char* file, int line) noexcept;
using ItemFn        = std::uint8_t* (*)(void* inventoryOrItem) noexcept;
using NodeModeFn    = int (*)(void* item) noexcept;
using CursorItemFn  = void* (*)() noexcept;
using GridOwnerFn   = void* (*)(void* widget) noexcept;
using PointToCellFn = void (*)(void* widget, std::uint64_t* out, std::uint64_t point) noexcept;
using ItemSizeFn    = void (*)(void* item, std::uint8_t* width, std::uint8_t* height, const char* file, int line) noexcept;
using DrawFn        = std::uint64_t (*)(void* widget, void* a, void* b, void* c) noexcept;
using ItemRectFn    = std::int32_t* (*)(void* widget, std::int32_t* out, std::uint64_t cell) noexcept;
using CellRectFn    = std::int32_t* (*)(void* widget, std::int32_t* out, std::uint64_t size, std::uint64_t cell) noexcept;
using ValidCellFn   = bool (*)(void* widget, std::uint64_t cell) noexcept;
using CellFn        = std::uint64_t* (*)(void* widget, std::uint64_t* out, std::uint64_t point) noexcept;
using IsTypeFn      = int (*)(void* item, int itemTypeRow) noexcept;

constexpr int         VtDraw = 3, VtItemRect = 16, VtValidCell = 18, VtCellAtPoint = 19, VtCellRect = 31;
constexpr std::size_t WidgetPage = 0x630, WidgetMarker = 0x634;
constexpr std::size_t UnitData = 0x10, UnitPath = 0x38, PathX = 0x10, PathY = 0x14, DataPage = 0x55;
constexpr std::uint8_t PageHidden = 0xFE, PageBackpack = 0;
constexpr int          NodeInGrid = 1;
constexpr const char*  SourceName = "invtabs";

std::uintptr_t Base {};
bool           NativesOk {};
InventoryFn    InventoryOf {};
ItemFn         FirstItem {};
ItemFn         NextItem {};
NodeModeFn     NodeMode {};
CursorItemFn   CursorItem {};
GridOwnerFn    GridOwner {};
PointToCellFn  PointToCell {};
ItemSizeFn     ItemSize {};
IsTypeFn       ItemIsType {}; // optional (TypeCheckPattern): null counts every backpack item as a charm for "left out"
void**         Vtable {};
DrawFn         NextDraw {};
ItemRectFn     NextItemRect {};
ValidCellFn    NextValidCell {};
CellFn         NextCellAtPoint {};
CellRectFn     NextCellRect {};

// The client's own player unit and the page byte of the custom page, as the last drawn tab grid saw them (UI thread).
std::atomic<void*>        ClientOwner {};
std::atomic<int>          CustomPageByte { -1 };

// The exe's .text section.
bool TextSection(const std::uint8_t*& start, std::size_t& size) noexcept {
	const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(Base);
	if (!dos || dos->e_magic != IMAGE_DOS_SIGNATURE) return false;
	const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(Base + static_cast<std::uintptr_t>(dos->e_lfanew));
	if (nt->Signature != IMAGE_NT_SIGNATURE) return false;
	const IMAGE_SECTION_HEADER* section = IMAGE_FIRST_SECTION(nt);
	for (WORD i = 0; i < nt->FileHeader.NumberOfSections; ++i, ++section)
		if (std::memcmp(section->Name, ".text", 6) == 0) {
			start = reinterpret_cast<const std::uint8_t*>(Base + section->VirtualAddress);
			size  = section->Misc.VirtualSize;
			return true;
		}
	return false;
}

// Every pattern must match exactly once; else the area limits stay off (one log line per missing pattern).
bool Locate() noexcept {
	const std::uint8_t* text = nullptr;
	std::size_t         size = 0;
	if (!TextSection(text, size)) {
		Log(true, "the game's .text section was not found: tab areas off (each tab shows the whole page)");
		return false;
	}
	const auto*       image   = reinterpret_cast<const std::uint8_t*>(Base);
	const std::size_t textRva = static_cast<std::size_t>(reinterpret_cast<std::uintptr_t>(text) - Base);
	const auto        resolve = [&](const invtabs::NativePattern& native, bool required) -> std::uintptr_t {
		const std::int64_t rva = invtabs::ResolveNative(image, textRva, size, native);
		if (rva < 0) {
			Log(true, "pattern %s: not exactly 1 match: %s", native.name,
			    required ? "tab areas off (each tab shows the whole page)" : "the summary's \"left out\" count includes every backpack item");
			return 0;
		}
		if (static_cast<std::uint64_t>(rva) != native.rva93847)
			Log(false, "pattern %s at D2R+0x%llX (0x%llX on 93847)", native.name, static_cast<unsigned long long>(rva), static_cast<unsigned long long>(native.rva93847));
		return Base + static_cast<std::uintptr_t>(rva);
	};
	ItemIsType = reinterpret_cast<IsTypeFn>(resolve(invtabs::TypeCheckPattern, false));
	std::array<std::uintptr_t, invtabs::NativeCount> found {};
	bool                                             all = true;
	for (int i = 0; i < invtabs::NativeCount; ++i) {
		found[static_cast<std::size_t>(i)] = resolve(invtabs::NativePatterns[i], true);
		all                                = all && found[static_cast<std::size_t>(i)];
	}
	if (!all) return false;
	InventoryOf = reinterpret_cast<InventoryFn>(found[invtabs::InventoryOf]);
	FirstItem   = reinterpret_cast<ItemFn>(found[invtabs::FirstItem]);
	NextItem    = reinterpret_cast<ItemFn>(found[invtabs::NextItem]);
	NodeMode    = reinterpret_cast<NodeModeFn>(found[invtabs::NodeMode]);
	CursorItem  = reinterpret_cast<CursorItemFn>(found[invtabs::CursorItem]);
	GridOwner   = reinterpret_cast<GridOwnerFn>(found[invtabs::GridOwner]);
	PointToCell = reinterpret_cast<PointToCellFn>(found[invtabs::PointToCell]);
	ItemSize    = reinterpret_cast<ItemSizeFn>(found[invtabs::ItemSize]);
	Vtable      = reinterpret_cast<void**>(found[invtabs::GridVtable]);
	return true;
}

// ---- what the tabs hold: the remembered layout (invtabs-layout.txt) ----

std::mutex                         MemoryLock;
std::vector<invtabs::Remembered>   Memory;  // the layout in effect with the item reach seen so far
bool                               MemoryDirty = false;

std::wstring MemoryPath() {
	std::wstring path = Context && Context->pluginConfigPath ? Context->pluginConfigPath : L"";
	const auto   cut  = path.find_last_of(L"\\/");
	path              = cut == std::wstring::npos ? std::wstring() : path.substr(0, cut + 1);
	return path + L"invtabs-layout.txt";
}

std::string ReadFile(const std::wstring& path) {
	std::ifstream in(path, std::ios::binary);
	return in ? std::string(std::istreambuf_iterator<char>(in), {}) : std::string();
}

void SaveMemory() {
	std::lock_guard guard(MemoryLock);
	if (!MemoryDirty) return;
	const std::wstring path = MemoryPath(), temp = path + L".tmp";
	{
		std::ofstream out(temp, std::ios::binary | std::ios::trunc);
		out << invtabs::FormatMemory(Memory);
		out.flush();
		if (!out) {
			Log(true, "could not write %s", MemoryFile);
			return;
		}
	}
	// written whole to the .tmp first, then put in place by one rename: a crash leaves the old file or the new one
	if (!MoveFileExW(temp.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) Log(true, "could not replace %s (error %lu)", MemoryFile, GetLastError());
	else MemoryDirty = false;
}

// An item of w x h at page cell x,y: widens the reach of the tab it is in.
void NoteItem(int x, int y, int w, int h) {
	std::lock_guard guard(MemoryLock);
	for (auto& m : Memory)
		if (invtabs::Inside(m.area, x, y)) {
			const Area before = m.used;
			invtabs::AddUsed(m.used, x, y, w, h);
			if (before.x != m.used.x || before.y != m.used.y || before.w != m.used.w || before.h != m.used.h) MemoryDirty = true;
			return;
		}
}

// ---- grid wrappers (UI thread) ----

// The slot of one of our grid widgets (tab index, AllSlot for the whole page), -1 for any other grid.
int SlotOf(const void* widget, bool* classic = nullptr) noexcept {
	float marker[2] {};
	std::memcpy(marker, static_cast<const std::uint8_t*>(widget) + WidgetMarker, sizeof(marker));
	const int slot = invtabs::SlotOfMarker(marker[0], marker[1]);
	if (classic) *classic = invtabs::ClassicMarker(marker[1]);
	return slot == invtabs::AllSlot || (slot >= 0 && slot < static_cast<int>(Tabs.size())) ? slot : -1;
}

int AreaSlotOf(const void* widget) noexcept {
	const int slot = widget ? SlotOf(widget) : -1;
	return slot == invtabs::AllSlot ? -1 : slot;
}

struct Seen {
	std::uint8_t* item;
	int           x, y;
	bool          inside;
};

// Page items outside the area get the page byte PageHidden for the stock draw, then their own back (also when the
// draw faults). Collects the area's items (for the reach and the summary). No C++ objects in here: __try needs a frame
// without unwinding.
std::uint64_t DrawArea(void* widget, void* a, void* b, void* c, const Area& area, Seen* seen, std::size_t& seenCount, std::uint64_t& signature,
                       void*& owner) noexcept {
	owner                 = GridOwner(widget);
	void* const inventory = owner ? InventoryOf(owner, SourceName, __LINE__) : nullptr;
	if (!inventory) return 0; // nothing rather than the whole page in the wrong place
	const std::uint8_t page = static_cast<const std::uint8_t*>(widget)[WidgetPage];
	std::uint8_t*      hidden[1024];
	std::size_t        count  = 0;
	std::uint64_t      result = 0;
	__try {
		int walked = 0;
		for (std::uint8_t* item = FirstItem(inventory); item && walked < 8192; item = NextItem(item), ++walked) {
			if (NodeMode(item) != NodeInGrid) continue;
			auto* const data = *reinterpret_cast<std::uint8_t**>(item + UnitData);
			auto* const path = *reinterpret_cast<std::uint8_t**>(item + UnitPath);
			if (!data || !path) continue;
			const int  x = *reinterpret_cast<std::int32_t*>(path + PathX), y = *reinterpret_cast<std::int32_t*>(path + PathY);
			const bool mine = data[DataPage] == page && invtabs::Inside(area, x, y);
			if (mine || data[DataPage] == PageBackpack) {
				signature = signature * 1099511628211ULL ^ (reinterpret_cast<std::uintptr_t>(item) + (static_cast<std::uint64_t>(x) << 8) + (static_cast<std::uint64_t>(y) << 16)
				                                           + (static_cast<std::uint64_t>(data[DataPage]) << 24));
				if (seenCount < 512) seen[seenCount++] = { item, x, y, mine };
			}
			if (data[DataPage] != page || mine) continue;
			if (count == sizeof(hidden) / sizeof(hidden[0])) break;
			data[DataPage]  = PageHidden;
			hidden[count++] = data;
		}
		result = NextDraw(widget, a, b, c);
	} __finally {
		for (std::size_t i = 0; i < count; ++i) hidden[i][DataPage] = page;
	}
	return result;
}

std::array<std::uint64_t, invtabs::AllSlot + 1> LastSignature {};
std::atomic<bool>                               SummaryQueued {};
std::atomic<bool>                               SummaryFresh {};
void __cdecl SummaryTask(const D2RL::PluginContext*, void*) noexcept;

// After a draw: the reach of the area's items when they changed; the summary when the charm tab opened or its charms
// (or the backpack's) changed.
void AfterDraw(int slot, const Seen* seen, std::size_t seenCount, std::uint64_t signature, bool fresh) noexcept {
	if (signature == LastSignature[static_cast<std::size_t>(slot)] && !fresh) return;
	LastSignature[static_cast<std::size_t>(slot)] = signature;
	for (std::size_t i = 0; i < seenCount; ++i) {
		if (!seen[i].inside) continue;
		std::uint8_t w = 1, h = 1;
		ItemSize(seen[i].item, &w, &h, SourceName, __LINE__);
		try {
			NoteItem(seen[i].x, seen[i].y, w, h);
		} catch (...) {
		}
	}
	if (slot == 0 && ThreadApi && !SummaryQueued.exchange(true)) {
		SummaryFresh = SummaryFresh.load() || fresh;
		if (ThreadApi->runOnUiThread(Context, SummaryTask, nullptr) != D2RL::Threads::Result::Success) SummaryQueued = false;
	}
}

std::uint64_t HookDraw(void* widget, void* a, void* b, void* c) noexcept {
	bool      classic = false;
	const int slot    = widget ? SlotOf(widget, &classic) : -1;
	if (slot < 0) return NextDraw(widget, a, b, c);
	const std::uint64_t now  = GetTickCount64();
	const std::uint64_t last = LastDrawn[static_cast<std::size_t>(slot)].exchange(now);
	DrawnClassic[static_cast<std::size_t>(slot)].store(classic);
	CustomPageByte.store(static_cast<const std::uint8_t*>(widget)[WidgetPage]);
	if (slot == invtabs::AllSlot) return NextDraw(widget, a, b, c);
	Seen          seen[512];
	std::size_t   seenCount = 0;
	std::uint64_t signature = 1469598103934665603ULL;
	void*         owner     = nullptr;
	const auto    result    = DrawArea(widget, a, b, c, AreaOfSlot(slot), seen, seenCount, signature, owner);
	if (owner) ClientOwner.store(owner);
	AfterDraw(slot, seen, seenCount, signature, !last || now - last > 300);
	return result;
}

std::int32_t* HookItemRect(void* widget, std::int32_t* out, std::uint64_t cell) noexcept {
	const int slot = AreaSlotOf(widget);
	return NextItemRect(widget, out, slot < 0 ? cell : invtabs::PageToWidget(AreaOfSlot(slot), cell));
}

std::int32_t* HookCellRect(void* widget, std::int32_t* out, std::uint64_t size, std::uint64_t cell) noexcept {
	const int slot = AreaSlotOf(widget);
	return NextCellRect(widget, out, size, slot < 0 ? cell : invtabs::PageToWidget(AreaOfSlot(slot), cell));
}

// Take only: no cell takes a held item. The whole-page view (always), and every tab of a joined TCP/IP player whose link
// to the hosting game is not full (DropsOff). Refused here, in this client's own grid, before the game asks anyone.
std::atomic<bool> DropsOff {};

bool TakeOnly(int slot) noexcept {
	return (slot == invtabs::AllSlot || DropsOff.load()) && CursorItem && CursorItem() != nullptr;
}

bool HookValidCell(void* widget, std::uint64_t cell) noexcept {
	const int any = widget ? SlotOf(widget) : -1;
	if (any >= 0 && TakeOnly(any)) return false;
	const int slot = any == invtabs::AllSlot ? -1 : any;
	if (slot < 0) return NextValidCell(widget, cell);
	return cell != invtabs::NoCell && invtabs::Inside(AreaOfSlot(slot), invtabs::CellX(cell), invtabs::CellY(cell)) && NextValidCell(widget, cell);
}

std::uint64_t* HookCellAtPoint(void* widget, std::uint64_t* out, std::uint64_t point) noexcept {
	const int any = widget ? SlotOf(widget) : -1;
	if (any >= 0 && TakeOnly(any)) {
		*out = invtabs::NoCell;
		return out;
	}
	const int slot = any == invtabs::AllSlot ? -1 : any;
	if (slot < 0) return NextCellAtPoint(widget, out, point);
	std::uint64_t cell = invtabs::NoCell;
	PointToCell(widget, &cell, point); // widget cell; with an item held, its top-left cell
	int w = 1, h = 1;
	if (void* const held = CursorItem()) {
		std::uint8_t iw = 1, ih = 1;
		ItemSize(held, &iw, &ih, SourceName, __LINE__);
		w = iw, h = ih;
	}
	const std::uint64_t page = invtabs::WidgetToPage(AreaOfSlot(slot), cell, w, h);
	*out                     = page != invtabs::NoCell && NextValidCell(widget, page) ? page : invtabs::NoCell;
	return out;
}

bool PatchVtable() noexcept {
	void* entries[VtCellRect + 1] {};
	std::memcpy(entries, Vtable, sizeof(entries));
	for (const int index : { VtDraw, VtItemRect, VtValidCell, VtCellAtPoint, VtCellRect })
		if (!entries[index]) return false;
	NextDraw        = reinterpret_cast<DrawFn>(entries[VtDraw]);
	NextItemRect    = reinterpret_cast<ItemRectFn>(entries[VtItemRect]);
	NextValidCell   = reinterpret_cast<ValidCellFn>(entries[VtValidCell]);
	NextCellAtPoint = reinterpret_cast<CellFn>(entries[VtCellAtPoint]);
	NextCellRect    = reinterpret_cast<CellRectFn>(entries[VtCellRect]);
	DWORD protect   = 0;
	if (!VirtualProtect(Vtable, (VtCellRect + 1) * sizeof(void*), PAGE_READWRITE, &protect)) return false;
	Vtable[VtDraw]        = reinterpret_cast<void*>(&HookDraw);
	Vtable[VtItemRect]    = reinterpret_cast<void*>(&HookItemRect);
	Vtable[VtValidCell]   = reinterpret_cast<void*>(&HookValidCell);
	Vtable[VtCellAtPoint] = reinterpret_cast<void*>(&HookCellAtPoint);
	Vtable[VtCellRect]    = reinterpret_cast<void*>(&HookCellRect);
	VirtualProtect(Vtable, (VtCellRect + 1) * sizeof(void*), protect, &protect);
	for (const int index : { VtDraw, VtItemRect, VtValidCell, VtCellAtPoint, VtCellRect }) {
		const auto at = reinterpret_cast<std::uintptr_t>(entries[index]);
		Log(false, "grid vtable entry %d wrapped (was %s0x%llX)", index, at - Base < 0x8000000 ? "D2R+" : "", static_cast<unsigned long long>(at - Base < 0x8000000 ? at - Base : at));
	}
	return true;
}

void RestoreVtable() noexcept {
	if (!Vtable || !NextDraw) return;
	DWORD protect = 0;
	if (!VirtualProtect(Vtable, (VtCellRect + 1) * sizeof(void*), PAGE_READWRITE, &protect)) return;
	const auto put = [](int index, void* ours, void* next) {
		if (Vtable[index] == ours) Vtable[index] = next; // a wrapper put on top of ours keeps its place
	};
	put(VtDraw, reinterpret_cast<void*>(&HookDraw), reinterpret_cast<void*>(NextDraw));
	put(VtItemRect, reinterpret_cast<void*>(&HookItemRect), reinterpret_cast<void*>(NextItemRect));
	put(VtValidCell, reinterpret_cast<void*>(&HookValidCell), reinterpret_cast<void*>(NextValidCell));
	put(VtCellAtPoint, reinterpret_cast<void*>(&HookCellAtPoint), reinterpret_cast<void*>(NextCellAtPoint));
	put(VtCellRect, reinterpret_cast<void*>(&HookCellRect), reinterpret_cast<void*>(NextCellRect));
	VirtualProtect(Vtable, (VtCellRect + 1) * sizeof(void*), protect, &protect);
}

bool AreasOn() noexcept { return NativesOk && NextDraw; }

// The slot whose grid is on screen (drawn in the last 300 ms), or -1.
int ShownSlot() noexcept {
	const std::uint64_t now    = GetTickCount64();
	int                 best   = -1;
	std::uint64_t       latest = 0;
	for (int slot = 0; slot <= invtabs::AllSlot; ++slot) {
		const std::uint64_t at = LastDrawn[static_cast<std::size_t>(slot)].load();
		if (at && now - at < 300 && at > latest) best = slot, latest = at;
	}
	return best;
}

// ---- the page's item policy ----

thread_local int CtrlSlot = -1; // the slot a Ctrl+click move of this plugin is for (game thread)
std::atomic<int> WelcomedPeers {}; // hosting game: joined players of other PCs whose tab table equals ours (Hello accepted)

bool SlotAccepts(int slot, const Inv::ItemPolicyRequest* request) {
	std::vector<invtabs::TypeCode> types;
	for (std::uint32_t i = 0; request->matchingItemTypes && i < request->matchingItemTypeCount; ++i) types.push_back(invtabs::TrimCode(request->matchingItemTypes[i].value));
	std::lock_guard guard(TypesLock);
	if (slot >= 0) return invtabs::Accepts(Tabs[static_cast<std::size_t>(slot)].types, types);
	for (const auto& tab : Tabs)
		if (invtabs::Accepts(tab.types, types)) return true;
	return false;
}

auto __cdecl OnPagePolicy(const D2RL::PluginContext*, const Inv::ItemPolicyRequest* request, void*) noexcept -> Inv::ItemPolicyDecision {
	using Decision = Inv::ItemPolicyDecision;
	if (!request) return Decision::Reject;
	if (request->reason == Inv::ItemPlacementReason::SavedItemRestore) return Decision::Allow; // never lose a saved item
	if (!Settings.enabled) return Decision::Reject;
	try {
		static std::atomic<int> told {};
		if (CtrlSlot >= 0) return SlotAccepts(CtrlSlot, request) ? Decision::Allow : Decision::Reject;
		if (DropsOff.load()) return Decision::Reject; // a joined player with read-only tabs (this client's own check)
		// A hosted game with joined players: the request does not say whose drop it is, so what is on THIS screen (the
		// tab shown here, this cursor) must not judge another player's drop. The type rule of any tab decides; the area
		// is limited by each client's own grid (same plugin, same tab table: WelcomedPeers), the whole-page view by
		// TakeOnly, and a Ctrl+click only ever arrives as this plugin's own move (CtrlSlot above).
		if (WelcomedPeers.load() > 0) return SlotAccepts(-1, request) ? Decision::Allow : Decision::Reject;
		const int slot = AreasOn() ? ShownSlot() : -1;
		if (slot == invtabs::AllSlot) {
			if (told.fetch_add(1) < 20) Log(false, "a drop into the whole-page view: refused (take only)");
			return Decision::Reject;
		}
		if (slot >= 0) {
			// D2RLoader's own Ctrl+click transfer (nothing held) picks any free cell of the page: refused; this plugin's
			// own Ctrl+click move comes with CtrlSlot.
			if (!CursorItem()) {
				if (told.fetch_add(1) < 20) Log(false, "a Ctrl+click transfer this plugin did not place: refused");
				return Decision::Reject;
			}
			return SlotAccepts(slot, request) ? Decision::Allow : Decision::Reject;
		}
		// No tab drawn here: a joined player's move in a hosted game, or the areas are off. The type rule of any tab.
		return SlotAccepts(-1, request) ? Decision::Allow : Decision::Reject;
	} catch (...) {
		return Decision::Reject;
	}
}

// ---- Ctrl+click from the backpack into the shown tab (game thread) ----

struct CtrlMove {
	int                slot;
	D2RL::ItemHandle   item;
	std::uint32_t      runtimeId;
};

struct PageItem {
	D2RL::ItemHandle handle;
	int              x, y;
	std::uint32_t    runtimeId;
};

auto __cdecl CollectPageItem(const D2RL::PluginContext*, const Items::ItemInfo* item, void* user) noexcept -> Inv::IterationAction {
	if (item && item->container == Items::ItemContainer::CustomPage) {
		try {
			static_cast<std::vector<PageItem>*>(user)->push_back({ item->handle, item->x, item->y, item->runtimeId });
		} catch (...) {
		}
	}
	return Inv::IterationAction::Continue;
}

struct Lookup {
	std::uint32_t    runtimeId;
	D2RL::ItemHandle handle;
};

auto __cdecl FindByRuntimeId(const D2RL::PluginContext*, const Items::ItemInfo* item, void* user) noexcept -> Inv::IterationAction {
	auto* want = static_cast<Lookup*>(user);
	if (!item || item->runtimeId != want->runtimeId) return Inv::IterationAction::Continue;
	want->handle = item->handle;
	return Inv::IterationAction::Stop;
}

void __cdecl SizeOfNative(const D2RL::PluginContext*, void* native, void* user) noexcept {
	auto* size = static_cast<std::uint8_t*>(user);
	if (native && ItemSize) ItemSize(native, &size[0], &size[1], SourceName, __LINE__);
}

// The item's size on the game thread (1 x 1 when it cannot be read).
void SizeOf(D2RL::ItemHandle item, int& w, int& h) {
	std::uint8_t size[2] { 1, 1 };
	if (ItemApi && ItemApi->editNativeItem) (void)ItemApi->editNativeItem(Context, item, SizeOfNative, size);
	w = std::max<int>(1, size[0]), h = std::max<int>(1, size[1]);
}

bool LocalPlayer(D2RL::PlayerHandle& player) { return Inventory && Inventory->getLocalPlayer(Context, &player) == Inv::Result::Success; }

// The page's items with their sizes; with `note` (this PC's own player) it also widens the remembered reach of each tab.
std::vector<std::pair<PageItem, std::pair<int, int>>> ScanPage(D2RL::PlayerHandle player, bool note = true) {
	std::vector<PageItem> items;
	const Inv::ItemFilter filter { .structSize = sizeof(Inv::ItemFilter), .containerMask = Items::ContainerBit(Items::ItemContainer::CustomPage) };
	(void)Inventory->forEachInventoryItem(Context, player, &filter, CollectPageItem, &items);
	std::vector<std::pair<PageItem, std::pair<int, int>>> out;
	for (const auto& item : items) {
		int w = 1, h = 1;
		SizeOf(item.handle, w, h);
		if (note) NoteItem(item.x, item.y, w, h);
		out.push_back({ item, { w, h } });
	}
	return out;
}

void __cdecl RunCtrlMove(const D2RL::PluginContext*, void* user) noexcept {
	const CtrlMove move = *static_cast<CtrlMove*>(user);
	delete static_cast<CtrlMove*>(user);
	try {
		D2RL::PlayerHandle player {};
		if (!ItemApi || !LocalPlayer(player)) return;
		// The click's handle names the UI's item; the move needs this thread's own handle of the same item (same runtime id).
		Lookup lookup { move.runtimeId, D2RL::InvalidItemHandle };
		const Inv::ItemFilter inventory { .structSize = sizeof(Inv::ItemFilter), .containerMask = Items::ContainerBit(Items::ItemContainer::Inventory) };
		(void)Inventory->forEachInventoryItem(Context, player, &inventory, FindByRuntimeId, &lookup);
		if (lookup.handle == D2RL::InvalidItemHandle) {
			Log(false, "Ctrl+click: item %u is no longer in the backpack", move.runtimeId);
			return;
		}
		int w = 1, h = 1;
		SizeOf(lookup.handle, w, h);
		std::array<std::array<bool, invtabs::PageSize>, invtabs::PageSize> taken {}; // [y][x]
		for (const auto& [item, size] : ScanPage(player)) {
			if (item.runtimeId == move.runtimeId) continue;
			for (int cy = std::max(item.y, 0); cy < std::min(item.y + size.second, invtabs::PageSize); ++cy)
				for (int cx = std::max(item.x, 0); cx < std::min(item.x + size.first, invtabs::PageSize); ++cx) taken[static_cast<std::size_t>(cy)][static_cast<std::size_t>(cx)] = true;
		}
		const Area area = AreaOfSlot(move.slot);
		int        x = -1, y = -1;
		for (int tx = area.x; x < 0 && tx + w <= area.x + area.w; ++tx)
			for (int ty = area.y; ty + h <= area.y + area.h; ++ty) {
				bool free = true;
				for (int cy = ty; free && cy < ty + h; ++cy)
					for (int cx = tx; free && cx < tx + w; ++cx) free = !taken[static_cast<std::size_t>(cy)][static_cast<std::size_t>(cx)];
				if (free) {
					x = tx, y = ty;
					break;
				}
			}
		const auto& tab = Tabs[static_cast<std::size_t>(move.slot)];
		if (x < 0) {
			Log(false, "Ctrl+click: no room for a %dx%d item in tab %s", w, h, tab.cfg.name.c_str());
			return;
		}
		Items::ExistingItemOperation operation { .structSize = sizeof(Items::ExistingItemOperation), .kind = Items::ExistingItemOperationKind::Move, .item = lookup.handle };
		operation.move.destination = { .structSize = sizeof(Items::ItemDestination), .container = Items::ItemContainer::CustomPage, .placement = Items::Placement::Exact,
			                           .customPageHandle = Page, .x = static_cast<std::uint32_t>(x), .y = static_cast<std::uint32_t>(y) };
		const Items::ExistingItemTransaction transaction { .structSize = sizeof(Items::ExistingItemTransaction), .player = player, .operationCount = 1, .operations = &operation };
		Items::ExistingItemTransactionResult result { .structSize = sizeof(Items::ExistingItemTransactionResult) };
		CtrlSlot         = move.slot;
		const auto moved = ItemApi->executeExistingItemTransaction(Context, &transaction, &result);
		CtrlSlot         = -1;
		Log(false, "Ctrl+click: item %u (%dx%d) to page cell %d,%d of tab %s: %s (item result %u)", move.runtimeId, w, h, x, y, tab.cfg.name.c_str(),
		    moved == Items::Result::Success ? "moved" : "not moved (the tab does not take it, or the move was refused)", static_cast<unsigned>(moved));
		if (moved == Items::Result::Success) NoteItem(x, y, w, h);
	} catch (...) {
		CtrlSlot = -1;
	}
}

// ---- TCP/IP games (docs/invtabs-mp.md, mp_protocol.h) ----
// Only the hosting game changes items. A joined player's drag and drop is the game's own request to the hosting game,
// which asks OnPagePolicy there. Its Ctrl+click is a Move message: the hosting game finds the item among THAT player's
// own items (getPeerPlayer, never an id from the message), picks the cell itself inside the tab and moves it with the
// tab's type rule. A joined player's link is "full" only when the hosting game runs the same protocol and the same tab
// table (Hello / Welcome compare a hash of the tabs' places, sizes and types); anything else leaves its tabs read-only
// (TakeOnly: take out, never put in), with the reason above the summary. Not built, by decision 1 of docs/invtabs.md (the
// plugin never moves an item on its own): the design's reconciler that would move a wrongly placed item to the backpack.

const D2RL::NetworkService* NetApi {};
Net::ChannelHandle          Channel = Net::InvalidChannelHandle;
std::atomic<bool>           InGame {}, Remote {}; // Remote: this client joined a game that another PC hosts
enum class LinkStep : int { Idle, Connecting, Connected, Refused };
std::atomic<LinkStep>       Step { LinkStep::Idle };
std::mutex                  LinkLock; // Link
Mp::JoinerLink              Link;
std::atomic<Mp::JoinMode>   LinkMode { Mp::JoinMode::Local };
// Why a joined player's tabs are take-out only: what the notice above the summary tells the player.
enum class ReadOnlyWhy : int { Connecting, OtherSetup, OtherProtocol, NoCharmInventory };
std::atomic<ReadOnlyWhy>    WhyReadOnly { ReadOnlyWhy::Connecting };
std::atomic<bool>           NoticeDirty {};
std::uint64_t               LinkTriedAt {}, HelloAt {}; // UI thread (NetTick, OnPlayerReady)
int                         LinkTries {}, Hellos {};
std::atomic<std::uint32_t>  MoveSeq {};

struct Peer {
	Net::PeerHandle handle {};
	bool            welcomed {};
	Mp::RateLimiter limiter;
};
std::mutex        PeerLock;
std::vector<Peer> Peers;

// The tab table as the protocol hashes it: every tab's name, place, size and type list; the charm tab counts charms.
std::vector<Mp::Tab> MpTabs() {
	std::vector<Mp::Tab> out;
	std::lock_guard      guard(TypesLock);
	for (std::size_t i = 0; i < Tabs.size(); ++i) {
		const Area a = Tabs[i].area;
		out.push_back({ Tabs[i].cfg.name,
		                { static_cast<std::uint8_t>(a.x), static_cast<std::uint8_t>(a.y), static_cast<std::uint8_t>(a.w), static_cast<std::uint8_t>(a.h) }, i == 0, Tabs[i].types });
	}
	return out;
}

// Equal on two PCs = the same tabs at the same places taking the same types, and the same charm rule setting.
std::uint64_t TableHashNow() { return Mp::TableHash(MpTabs()) ^ (Settings.inventoryCharms ? 0x9E3779B97F4A7C15ULL : 0); }

const char* ModeName(Mp::JoinMode mode) noexcept {
	switch (mode) {
	case Mp::JoinMode::Local: return "local";
	case Mp::JoinMode::Full: return "joined, full";
	case Mp::JoinMode::ViewOnly: return "joined, read-only";
	default: return "joined, connecting (read-only)";
	}
}

const char* MoveResultName(Mp::MoveResult r) noexcept {
	switch (r) {
	case Mp::MoveResult::Moved: return "moved";
	case Mp::MoveResult::NotWelcome: return "refused: this player's tabs are read-only in this game";
	case Mp::MoveResult::BadMessage: return "refused: bad message";
	case Mp::MoveResult::UnknownTab: return "refused: no such tab";
	case Mp::MoveResult::NotFound: return "refused: the item is not in that player's backpack";
	case Mp::MoveResult::TypeRefused: return "refused: the tab does not take this item";
	case Mp::MoveResult::NoRoom: return "refused: no room in the tab";
	case Mp::MoveResult::RateLimited: return "refused: too many moves at once";
	case Mp::MoveResult::NotOnPage: return "refused: the item is not on the page";
	default: return "failed (the hosting game's log has the item result)";
	}
}

// The link state changed (any thread): what this client may do, and the notice above the summary.
void LinkChanged() noexcept {
	Mp::JoinMode mode = Mp::JoinMode::Local;
	std::string  why;
	if (Remote.load()) {
		std::lock_guard guard(LinkLock);
		mode = Link.Mode();
		why  = std::string(Link.Why());
	}
	const Mp::JoinMode before = LinkMode.exchange(mode);
	DropsOff                  = Remote.load() && mode != Mp::JoinMode::Full;
	NoticeDirty               = true;
	if (before != mode) Log(mode == Mp::JoinMode::ViewOnly, "multiplayer: %s%s%s", ModeName(mode), why.empty() ? "" : ": ", why.c_str());
	if (ThreadApi && !SummaryQueued.exchange(true)) {
		SummaryFresh = true;
		if (ThreadApi->runOnUiThread(Context, SummaryTask, nullptr) != D2RL::Threads::Result::Success) SummaryQueued = false;
	}
}

void ResetLink(bool inGame, bool remote) {
	InGame      = inGame;
	Remote      = inGame && remote;
	Step        = LinkStep::Idle;
	WhyReadOnly = ReadOnlyWhy::Connecting;
	LinkTries   = 0;
	Hellos      = 0;
	LinkTriedAt = HelloAt = 0;
	{
		std::lock_guard guard(LinkLock);
		Link.Reset(); // Unknown, "connecting"
	}
	{
		std::lock_guard guard(PeerLock);
		Peers.clear(); // a new game: new players
		WelcomedPeers = 0;
	}
	LinkChanged();
}

void RefuseLink() noexcept {
	{
		std::lock_guard guard(LinkLock);
		Link.OnRefused();
	}
	WhyReadOnly = ReadOnlyWhy::NoCharmInventory;
	LinkChanged();
}

void SendMoveDone(Net::PeerHandle peer, const Mp::Move& move, Mp::MoveResult result, int x = 0xFF, int y = 0xFF) noexcept {
	try {
		const auto bytes = Mp::EncodeMoveDone({ move.seq, move.runtimeId, result, static_cast<std::uint8_t>(x), static_cast<std::uint8_t>(y) });
		if (const auto sent = NetApi->sendToClient(Context, Channel, peer, Mp::kMsgMoveDone, bytes.data(), static_cast<std::uint32_t>(bytes.size())); sent != Net::Result::Success)
			Log(true, "multiplayer: could not answer a move (network result %u)", static_cast<unsigned>(sent));
	} catch (...) {
	}
}

struct PeerMove {
	Net::PeerHandle peer;
	Mp::Move        move;
};

// Hosting game, game thread: a joined player's Ctrl+click, for that player.
void __cdecl RunPeerMove(const D2RL::PluginContext*, void* user) noexcept {
	const PeerMove job = *static_cast<PeerMove*>(user);
	delete static_cast<PeerMove*>(user);
	const Mp::Move& m = job.move;
	try {
		D2RL::PlayerHandle player {};
		if (const auto found = NetApi->getPeerPlayer(Context, Channel, job.peer, &player); found != Net::Result::Success || !player) {
			Log(true, "multiplayer: a joined player's move: their player was not found (network result %u)", static_cast<unsigned>(found));
			return SendMoveDone(job.peer, m, Mp::MoveResult::Failed);
		}
		const bool into = m.kind == Mp::MoveKind::IntoTab;
		if (into && m.tab >= Tabs.size()) return SendMoveDone(job.peer, m, Mp::MoveResult::UnknownTab);
		// The item must be one of THAT player's own: in the backpack for a move into a tab, on the page for a move out.
		Lookup                lookup { m.runtimeId, D2RL::InvalidItemHandle };
		const Inv::ItemFilter from { .structSize = sizeof(Inv::ItemFilter), .containerMask = Items::ContainerBit(into ? Items::ItemContainer::Inventory : Items::ItemContainer::CustomPage) };
		(void)Inventory->forEachInventoryItem(Context, player, &from, FindByRuntimeId, &lookup);
		if (lookup.handle == D2RL::InvalidItemHandle) {
			Log(false, "multiplayer: a joined player's move of item %u: not %s", m.runtimeId, into ? "in their backpack" : "on their page");
			return SendMoveDone(job.peer, m, into ? Mp::MoveResult::NotFound : Mp::MoveResult::NotOnPage);
		}
		Items::ExistingItemOperation operation { .structSize = sizeof(Items::ExistingItemOperation), .kind = Items::ExistingItemOperationKind::Move, .item = lookup.handle };
		int x = 0xFF, y = 0xFF, w = 1, h = 1;
		if (into) {
			SizeOf(lookup.handle, w, h);
			std::vector<Mp::PageItem> page;
			for (const auto& [item, size] : ScanPage(player, false)) page.push_back({ item.runtimeId, item.x, item.y, size.first, size.second });
			const Area a    = Tabs[m.tab].area;
			const auto cell = Mp::FirstFreeCell({ static_cast<std::uint8_t>(a.x), static_cast<std::uint8_t>(a.y), static_cast<std::uint8_t>(a.w), static_cast<std::uint8_t>(a.h) }, page, w, h, m.runtimeId);
			if (!cell) return SendMoveDone(job.peer, m, Mp::MoveResult::NoRoom);
			x                          = cell->x, y = cell->y;
			operation.move.destination = { .structSize = sizeof(Items::ItemDestination), .container = Items::ItemContainer::CustomPage, .placement = Items::Placement::Exact,
				                           .customPageHandle = Page, .x = static_cast<std::uint32_t>(x), .y = static_cast<std::uint32_t>(y) };
		} else {
			operation.move.destination = { .structSize = sizeof(Items::ItemDestination), .container = Items::ItemContainer::Inventory, .placement = Items::Placement::Automatic };
		}
		const Items::ExistingItemTransaction transaction { .structSize = sizeof(Items::ExistingItemTransaction), .player = player, .operationCount = 1, .operations = &operation };
		Items::ExistingItemTransactionResult result { .structSize = sizeof(Items::ExistingItemTransactionResult) };
		if (into) CtrlSlot = m.tab; // the tab's type rule, asked by D2RLoader through OnPagePolicy
		const auto moved = ItemApi->executeExistingItemTransaction(Context, &transaction, &result);
		CtrlSlot         = -1;
		const auto answer = moved == Items::Result::Success ? Mp::MoveResult::Moved : moved == Items::Result::PolicyRejected ? Mp::MoveResult::TypeRefused : Mp::MoveResult::Failed;
		if (into) Log(false, "multiplayer: a joined player's item %u (%dx%d) to page cell %d,%d of tab %s: %s (item result %u)", m.runtimeId, w, h, x, y, Tabs[m.tab].cfg.name.c_str(),
			              MoveResultName(answer), static_cast<unsigned>(moved));
		else Log(false, "multiplayer: a joined player's item %u from the page to their backpack: %s (item result %u)", m.runtimeId, MoveResultName(answer), static_cast<unsigned>(moved));
		SendMoveDone(job.peer, m, answer, answer == Mp::MoveResult::Moved ? x : 0xFF, answer == Mp::MoveResult::Moved ? y : 0xFF);
	} catch (...) {
		CtrlSlot = -1;
		SendMoveDone(job.peer, m, Mp::MoveResult::Failed);
	}
}

// Hosting game: a message of a joined player.
void __cdecl OnHostMessage(const D2RL::PluginContext*, Net::ChannelHandle, Net::PeerHandle peer, std::uint16_t id, const void* data, std::uint32_t size, void*) noexcept {
	try {
		const std::span<const std::uint8_t> bytes(static_cast<const std::uint8_t*>(data), data ? size : 0);
		if (id == Mp::kMsgHello) {
			const auto hello = Mp::DecodeHello(bytes);
			if (!hello) return;
			const Mp::Welcome answer = Mp::HostAnswerHello(*hello, TableHashNow(), PluginVersion);
			{
				std::lock_guard guard(PeerLock);
				auto            known = std::find_if(Peers.begin(), Peers.end(), [&](const Peer& p) { return p.handle == peer; });
				if (known == Peers.end()) Peers.emplace_back().handle = peer, known = Peers.end() - 1;
				known->welcomed = answer.verdict == Mp::WelcomeVerdict::Accepted;
				WelcomedPeers   = static_cast<int>(std::count_if(Peers.begin(), Peers.end(), [](const Peer& p) { return p.welcomed; }));
			}
			Log(answer.verdict != Mp::WelcomeVerdict::Accepted, "multiplayer: a joined player said hello (invtabs %s, protocol %u): %s", hello->version.c_str(), hello->protocol,
			    answer.verdict == Mp::WelcomeVerdict::Accepted ? "same tabs, welcome" : answer.verdict == Mp::WelcomeVerdict::TableMismatch ? "other tabs than this game's: their tabs are read-only"
			                                                                                                                              : "another protocol: their tabs are read-only");
			const auto out = Mp::EncodeWelcome(answer);
			if (const auto sent = NetApi->sendToClient(Context, Channel, peer, Mp::kMsgWelcome, out.data(), static_cast<std::uint32_t>(out.size())); sent != Net::Result::Success)
				Log(true, "multiplayer: could not answer a joined player (network result %u)", static_cast<unsigned>(sent));
			return;
		}
		if (id == Mp::kMsgMove) {
			const auto move = Mp::DecodeMove(bytes);
			if (!move) return; // wrong size or field: dropped (nothing to answer to)
			bool welcomed = false, allowed = false;
			{
				std::lock_guard guard(PeerLock);
				const auto      known = std::find_if(Peers.begin(), Peers.end(), [&](const Peer& p) { return p.handle == peer; });
				if (known != Peers.end()) welcomed = known->welcomed, allowed = known->welcomed && known->limiter.Allow(GetTickCount64());
			}
			if (!welcomed) return SendMoveDone(peer, *move, Mp::MoveResult::NotWelcome);
			if (!allowed) return SendMoveDone(peer, *move, Mp::MoveResult::RateLimited);
			if (Page == Inv::InvalidHandle || !ItemApi || !ThreadApi || !AreasOn()) return SendMoveDone(peer, *move, Mp::MoveResult::Failed);
			auto* job = new (std::nothrow) PeerMove { peer, *move };
			if (const auto queued = job ? ThreadApi->runOnGameThread(Context, RunPeerMove, job) : D2RL::Threads::Result::Busy; queued != D2RL::Threads::Result::Success) {
				delete job;
				Log(true, "multiplayer: a joined player's move could not be queued (thread result %u)", static_cast<unsigned>(queued));
				SendMoveDone(peer, *move, Mp::MoveResult::Failed);
			}
			return;
		}
		static std::atomic<int> told {};
		if (told.fetch_add(1) < 5) Log(true, "multiplayer: unknown message %u (%u bytes) of a joined player ignored", id, size);
	} catch (...) {
	}
}

// Joined player: the hosting game's answers.
void __cdecl OnClientMessage(const D2RL::PluginContext*, Net::ChannelHandle, std::uint16_t id, const void* data, std::uint32_t size, void*) noexcept {
	try {
		const std::span<const std::uint8_t> bytes(static_cast<const std::uint8_t*>(data), data ? size : 0);
		if (id == Mp::kMsgWelcome) {
			const auto welcome = Mp::DecodeWelcome(bytes);
			if (!welcome || !Remote.load()) return;
			{
				std::lock_guard guard(LinkLock);
				Link.OnWelcome(*welcome, false);
			}
			if (welcome->verdict != Mp::WelcomeVerdict::Accepted)
				WhyReadOnly = welcome->verdict == Mp::WelcomeVerdict::TableMismatch ? ReadOnlyWhy::OtherSetup : ReadOnlyWhy::OtherProtocol;
			Log(false, "multiplayer: the hosting game runs invtabs %s (protocol %u)", welcome->version.c_str(), welcome->protocol);
			LinkChanged();
			return;
		}
		if (id == Mp::kMsgMoveDone) {
			if (const auto done = Mp::DecodeMoveDone(bytes)) {
				if (done->result == Mp::MoveResult::Moved && done->x != 0xFF) Log(false, "multiplayer: the hosting game moved item %u to page cell %u,%u", done->runtimeId, done->x, done->y);
				else Log(done->result != Mp::MoveResult::Moved, "multiplayer: the hosting game's answer for item %u: %s", done->runtimeId, MoveResultName(done->result));
			}
			return;
		}
		static std::atomic<int> told {};
		if (told.fetch_add(1) < 5) Log(true, "multiplayer: unknown message %u (%u bytes) of the hosting game ignored", id, size);
	} catch (...) {
	}
}

void __cdecl OnLinkState(const D2RL::PluginContext*, const Net::ConnectionEvent* event, void*) noexcept {
	if (!event) return;
	try {
		if (!Remote.load()) { // the hosting game (or a local game): a joined player left
			if (event->state != Net::ConnectionState::Disconnected || event->peer == Net::InvalidPeerHandle) return;
			std::lock_guard guard(PeerLock);
			const auto      gone = std::remove_if(Peers.begin(), Peers.end(), [&](const Peer& p) { return p.handle == event->peer; });
			if (gone != Peers.end()) Log(false, "multiplayer: a joined player left");
			Peers.erase(gone, Peers.end());
			WelcomedPeers = static_cast<int>(std::count_if(Peers.begin(), Peers.end(), [](const Peer& p) { return p.welcomed; }));
			return;
		}
		switch (event->state) {
		case Net::ConnectionState::Connected:
			Step = LinkStep::Connected;
			Log(false, "multiplayer: connected to the hosting game's invtabs");
			break;
		case Net::ConnectionState::Rejected:
			if (event->reason == Net::RejectionReason::HostUnavailable) {
				Step = LinkStep::Idle; // tried again by the ticker
				break;
			}
			Step = LinkStep::Refused;
			Log(true, "multiplayer: the hosting game refused the invtabs channel (reason %u)", static_cast<unsigned>(event->reason));
			RefuseLink();
			break;
		case Net::ConnectionState::Disconnected:
			if (Step.load() == LinkStep::Connected) Log(false, "multiplayer: disconnected from the hosting game");
			Step = LinkStep::Idle;
			break;
		default: break;
		}
	} catch (...) {
	}
}

// Joined player, UI thread (the ticker): connects once in a game and says hello until the hosting game answers.
void __cdecl NetTick(const D2RL::PluginContext*, void*) noexcept {
	if (!NetApi || Channel == Net::InvalidChannelHandle || !InGame.load() || !Remote.load() || LinkMode.load() != Mp::JoinMode::Unknown) return;
	try {
		const std::uint64_t now  = GetTickCount64();
		const LinkStep      step = Step.load();
		if (step == LinkStep::Refused) return;
		if (step == LinkStep::Idle || (step == LinkStep::Connecting && now - LinkTriedAt > 5000)) {
			if (LinkTries >= 30) return RefuseLink(); // no invtabs channel on the hosting game: read-only
			if (LinkTries > 0 && now - LinkTriedAt < 2000) return;
			LinkTriedAt      = now;
			const auto tried = NetApi->connectToHost(Context, Channel);
			++LinkTries;
			if (tried == Net::Result::Success) {
				if (step == LinkStep::Idle) Step = LinkStep::Connecting;
			} else if (tried == Net::Result::Incompatible) {
				Step = LinkStep::Refused;
				Log(true, "multiplayer: the hosting game uses another D2RLoader transport");
				RefuseLink();
			}
			if (LinkTries <= 3 || LinkTries == 10 || LinkTries == 30) Log(false, "multiplayer: connecting to the hosting game: network result %u (try %d of 30)", static_cast<unsigned>(tried), LinkTries);
			return;
		}
		if (step != LinkStep::Connected && NetApi->getChannelInfo) { // the channel's own state, in case the event did not come
			Net::ChannelInfo info { .structSize = Net::ChannelInfoSize };
			if (NetApi->getChannelInfo(Context, Channel, &info) == Net::Result::Success) {
				if (info.connectionState == Net::ConnectionState::Connected) Step = LinkStep::Connected;
				else if (info.connectionState == Net::ConnectionState::Rejected && info.rejectionReason != Net::RejectionReason::HostUnavailable) {
					Step = LinkStep::Refused;
					Log(true, "multiplayer: the hosting game refused the invtabs channel (reason %u)", static_cast<unsigned>(info.rejectionReason));
					return RefuseLink();
				}
			}
		}
		if (Step.load() != LinkStep::Connected || (Hellos > 0 && now - HelloAt < 3000)) return;
		if (Hellos >= 5) return RefuseLink(); // connected, but nothing answers our hello
		const auto hello = Mp::EncodeHello({ Mp::kProtocol, TableHashNow(), PluginVersion });
		const auto sent  = NetApi->sendToHost(Context, Channel, Mp::kMsgHello, hello.data(), static_cast<std::uint32_t>(hello.size()));
		++Hellos;
		HelloAt = now;
		Log(sent != Net::Result::Success, "multiplayer: hello to the hosting game: network result %u", static_cast<unsigned>(sent));
	} catch (...) {
	}
}

std::atomic<bool> Ticking {};
HANDLE            TickerThread {};

DWORD WINAPI Ticker(void*) {
	while (Ticking) {
		Sleep(250);
		if (Ticking && ThreadApi && Remote.load() && LinkMode.load() == Mp::JoinMode::Unknown) (void)ThreadApi->runOnUiThread(Context, NetTick, nullptr);
	}
	return 0;
}

void StartNetwork() {
	if (Context->QueryService(&NetApi) != D2RL::ServiceQueryResult::Success || !D2RL::HasNetworkServiceField(NetApi, D2RL::NetworkServiceRequiredSize)) {
		NetApi = nullptr;
		Log(true, "multiplayer: no network service in this D2RLoader: a joined player's tabs are read-only");
		return;
	}
	const Net::ChannelRegistration channel {
		.structSize         = Net::ChannelRegistrationSize,
		.localChannelId     = Mp::kChannelId,
		.compatibilityToken = Mp::kCompatTag,
		.hostMessage        = OnHostMessage,
		.clientMessage      = OnClientMessage,
		.connectionState    = OnLinkState,
	};
	if (const auto registered = NetApi->registerChannel(Context, &channel, &Channel); registered != Net::Result::Success) {
		Channel = Net::InvalidChannelHandle;
		Log(true, "multiplayer: the network channel was refused (result %u): a joined player's tabs are read-only", static_cast<unsigned>(registered));
		return;
	}
	if (!ThreadApi) return;
	Ticking      = true;
	TickerThread = CreateThread(nullptr, 0, Ticker, nullptr, 0, nullptr);
	Log(false, "multiplayer: network channel registered (protocol %u)", Mp::kProtocol);
}

void StopNetwork() noexcept {
	Ticking = false;
	if (TickerThread) WaitForSingleObject(TickerThread, 2000), CloseHandle(TickerThread), TickerThread = nullptr;
	if (NetApi && Channel != Net::InvalidChannelHandle) (void)NetApi->unregisterChannel(Context, Channel);
	Channel = Net::InvalidChannelHandle;
}

// A joined player's Ctrl+click: asked of the hosting game. Always consumed (nothing may move on this client alone).
void SendMove(Mp::MoveKind kind, int slot, std::uint32_t runtimeId) noexcept {
	try {
		if (LinkMode.load() != Mp::JoinMode::Full || !NetApi || Channel == Net::InvalidChannelHandle) {
			std::string why;
			{
				std::lock_guard guard(LinkLock);
				why = std::string(Link.Why());
			}
			Log(false, "Ctrl+click: this tab is read-only in this game (%s)", why.c_str());
			return;
		}
		const Mp::Move move { MoveSeq.fetch_add(1) + 1, runtimeId, kind, static_cast<std::uint8_t>(kind == Mp::MoveKind::IntoTab ? slot : 0) };
		const auto     out  = Mp::EncodeMove(move);
		const auto     sent = NetApi->sendToHost(Context, Channel, Mp::kMsgMove, out.data(), static_cast<std::uint32_t>(out.size()));
		Log(sent != Net::Result::Success, "Ctrl+click: item %u %s: asked of the hosting game (network result %u)", runtimeId,
		    kind == Mp::MoveKind::IntoTab ? "into the tab" : "out of the page", static_cast<unsigned>(sent));
	} catch (...) {
	}
}

auto __cdecl OnItemClick(const D2RL::PluginContext*, const Clicks::ItemInteractionEvent* event, void*) noexcept -> Clicks::Decision {
	if (!event || event->action != Clicks::Action::Activate) return Clicks::Decision::Continue;
	const bool pack = event->container == Items::ItemContainer::Inventory, paged = event->container == Items::ItemContainer::CustomPage;
	if (!pack && !paged) return Clicks::Decision::Continue;
	const bool ctrl = (event->modifiers & Clicks::ModifierBit(Clicks::Modifier::Control)) || (GetAsyncKeyState(VK_CONTROL) & 0x8000);
	if (!ctrl || Page == Inv::InvalidHandle || !Settings.enabled) return Clicks::Decision::Continue;
	const int slot = AreasOn() ? ShownSlot() : -1;
	if (slot < 0) return Clicks::Decision::Continue; // no tab on screen: not for the page
	// A page item: D2RLoader's own move back to the backpack in a local or hosted game; a joined player asks the host.
	if (paged && !Remote.load()) return Clicks::Decision::Continue;
	if (pack && slot == invtabs::AllSlot) return Clicks::Decision::Consume; // the whole-page view takes nothing
	Items::ItemInfo info { .structSize = Items::ItemInfoSize };
	if (ItemApi->getItemInfo(Context, event->item, &info) != Items::Result::Success) return Clicks::Decision::Consume;
	if (Remote.load()) {
		SendMove(paged ? Mp::MoveKind::OutOfPage : Mp::MoveKind::IntoTab, slot, info.runtimeId);
		return Clicks::Decision::Consume;
	}
	auto* move = new (std::nothrow) CtrlMove { slot, event->item, info.runtimeId };
	if (const auto queued = move ? ThreadApi->runOnGameThread(Context, RunCtrlMove, move) : D2RL::Threads::Result::Busy; queued != D2RL::Threads::Result::Success) {
		delete move;
		Log(true, "Ctrl+click: the move could not be queued (thread result %u)", static_cast<unsigned>(queued));
	}
	return Clicks::Decision::Consume;
}

// ---- art ----

bool RegisterResource(const std::string& path, const std::string& bytes, Res::RegistrationHandle* out = nullptr) {
	const Res::ResourceRegistration resource {
		.structSize = Res::ResourceRegistrationSize,
		.path       = path.c_str(),
		.bytes      = bytes.data(),
		.byteCount  = bytes.size(),
	};
	Res::RegistrationHandle handle = Res::InvalidHandle;
	if (ResourceApi->registerResource(Context, &resource, &handle) == Res::Result::Success) {
		if (out) *out = handle;
		return true;
	}
	Log(true, "could not register %s", path.c_str());
	return false;
}

// d2rloader\invtabs\<name> (HD and its lowend half).
bool RegisterSprite(const std::string& name, const std::vector<Lay::Picture>& frames) {
	std::vector<Lay::Picture> low;
	for (const auto& frame : frames) low.push_back(Lay::Half(frame));
	const std::string path = std::string("data/hd/global/ui/d2rloader/") + PluginId + "/" + name;
	return RegisterResource(path + ".sprite", Lay::SpriteFile(frames)) && RegisterResource(path + ".lowend.sprite", Lay::SpriteFile(low));
}

// A file of the mod's own data (data/...) as installed: <mods>\<mod>\<mod>.mpq\data\... . D2RLoader 1.3.1's
// modDirectory is that <mod>.mpq folder (seen in game); the SDK does not say, so the folders above are tried too.
std::wstring ModDataRoot;

std::string ReadModFile(const std::string& rel) {
	if (!Context || !Context->modDirectory || !Context->activeMod) return {};
	std::wstring relW;
	for (const char c : rel) relW += c == '/' ? L'\\' : static_cast<wchar_t>(c);
	if (!ModDataRoot.empty()) return ReadFile(ModDataRoot + relW);
	std::wstring dir = Context->modDirectory, mod;
	if (!dir.empty() && dir.back() != L'\\' && dir.back() != L'/') dir += L'\\';
	for (const char* c = Context->activeMod; *c; ++c) mod += static_cast<wchar_t>(*c);
	for (const std::wstring& root : { dir, dir + mod + L".mpq\\", dir + mod + L"\\" + mod + L".mpq\\" }) {
		if (GetFileAttributesW((root + L"data").c_str()) == INVALID_FILE_ATTRIBUTES) continue;
		ModDataRoot = root;
		return ReadFile(root + relW);
	}
	static std::atomic<int> told {};
	if (told.fetch_add(1) == 0) Log(true, "the mod's data folder was not found under %ls (mod %s)", Context->modDirectory, Context->activeMod);
	return {};
}

bool ModFileExists(const std::string& rel) { return !ReadModFile(rel).empty(); }

std::optional<Lay::Picture> StockGrid;

std::string CellsSprite(int slot, int cols, int rows, int cell) {
	const std::string name = "cells" + std::to_string(slot);
	if (!RegisterSprite(name, { Lay::GridPicture(StockGrid ? &*StockGrid : nullptr, cols, rows, cell) })) return {};
	return std::string("d2rloader\\") + PluginId + "\\" + name;
}

// The inventory button: 4 frames (normal, pressed, disabled, hovered), D2R's stash tab picture cut down is not ours to
// cut at run time, so a small framed square with a charm shape.
constexpr int ButtonSize = 56;
std::vector<Lay::Picture> ButtonFrames() {
	std::vector<Lay::Picture> frames;
	for (int frame = 0; frame < 4; ++frame) {
		Lay::Picture p     = Lay::Blank(ButtonSize, ButtonSize);
		const int    light = frame == 3 ? 40 : frame == 1 ? -10 : 0;
		const int    dy    = frame == 1 ? 2 : 0;
		for (int y = 0; y < ButtonSize; ++y)
			for (int x = 0; x < ButtonSize; ++x) {
				unsigned char* px   = p.at(x, y);
				const int      edge = std::min({ x, y, ButtonSize - 1 - x, ButtonSize - 1 - y });
				int            r = 30, g = 26, b = 22;
				if (edge < 3) r = 160, g = 128, b = 72;
				else if (edge < 5) r = 50, g = 42, b = 32;
				const double cx = 28.0, cy = 31.0 + dy;
				const double ox = (x - cx) / 11.0, oy = (y - cy) / 15.0;
				const double rx = x - cx, ry = y - (13.0 + dy);
				const double ring = std::sqrt(rx * rx + ry * ry);
				if (ox * ox + oy * oy <= 1.0) r = 120, g = 150, b = 190;
				if (ox * ox + oy * oy <= 1.0 && ox * ox + oy * oy > 0.72) r = 200, g = 170, b = 90;
				if (ring >= 3.0 && ring <= 5.5) r = 200, g = 170, b = 90;
				px[0] = static_cast<unsigned char>(std::clamp(r + light, 0, 255));
				px[1] = static_cast<unsigned char>(std::clamp(g + light, 0, 255));
				px[2] = static_cast<unsigned char>(std::clamp(b + light, 0, 255));
				px[3] = static_cast<unsigned char>(frame == 2 ? 120 : 255);
			}
		frames.push_back(std::move(p));
	}
	return frames;
}

// ---- the summary (charm tab) ----

invtabs::summary::Summary SummaryHd, SummaryClassic, SummaryPad; // the HD / classic tab panels, the controller panel
bool                      SummaryOn = false;

void SummaryLog(const char* line) { Log(false, "%s", line); }

// The client's grid items of the backpack and of the charm tab's area (UI thread). No C++ objects: __try.
std::size_t CharmUnits(void* owner, int pageByte, const Area& area, void** out, std::size_t room) noexcept {
	std::size_t n = 0;
	__try {
		void* const inventory = owner ? InventoryOf(owner, SourceName, __LINE__) : nullptr;
		int         walked    = 0;
		for (std::uint8_t* item = inventory ? FirstItem(inventory) : nullptr; item && walked < 8192 && n < room; item = NextItem(item), ++walked) {
			if (NodeMode(item) != NodeInGrid) continue;
			auto* const data = *reinterpret_cast<std::uint8_t**>(item + UnitData);
			auto* const path = *reinterpret_cast<std::uint8_t**>(item + UnitPath);
			if (!data || !path) continue;
			const int x = *reinterpret_cast<std::int32_t*>(path + PathX), y = *reinterpret_cast<std::int32_t*>(path + PathY);
			if (!(Settings.inventoryCharms && data[DataPage] == PageBackpack) && !(data[DataPage] == pageByte && invtabs::Inside(area, x, y))) continue;
			// charms only (type char with its Equiv children): the summary's "left out" are charms that do not count
			if (ItemIsType && !ItemIsType(item, invtabs::CharmTypeRow)) continue;
			out[n++] = item;
		}
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		return 0;
	}
	return n;
}

std::string SummaryFragment(invtabs::summary::Summary& summary, invtabs::summary::LayoutMode mode, const Lay::Box& box) {
	if (!SummaryOn || box.h <= 0) return {};
	return summary.Fragment(mode, { box.x, box.y, box.w, box.h });
}

// ---- layouts ----

std::vector<Lay::TabRef> TabRefs() {
	std::vector<Lay::TabRef> refs;
	for (const auto& t : Tabs) refs.push_back({ PanelName(t.id), t.cfg.label });
	return refs;
}

std::string HdText(int slot) {
	auto* tab = SlotTab(slot);
	if (slot == invtabs::AllSlot) {
		const auto g     = Lay::HdLayoutOf(invtabs::PageSize, invtabs::PageSize, 1, false);
		const auto cells = CellsSprite(slot, invtabs::PageSize, invtabs::PageSize, g.cell);
		return Lay::HdPanel({ { PanelName(tab->id), "Player page" } }, 0, slot, invtabs::PageSize, invtabs::PageSize, g, cells, "", "Player page (all tabs)");
	}
	const auto g     = Lay::HdLayoutOf(tab->area.w, tab->area.h, static_cast<int>(Tabs.size()), slot == 0);
	const auto cells = CellsSprite(slot, tab->area.w, tab->area.h, g.cell);
	const auto frag  = slot == 0 ? SummaryFragment(SummaryHd, invtabs::summary::LayoutMode::Hd, g.band) : std::string();
	return Lay::HdPanel(TabRefs(), slot, slot, tab->area.w, tab->area.h, g, cells, frag, tab->cfg.label);
}

std::string ClassicText(int slot) {
	auto* tab = SlotTab(slot);
	if (!tab || !tab->classic) return {};
	std::vector<Lay::ClassicTab> refs;
	int                          self = -1;
	for (std::size_t i = 0; i < Tabs.size(); ++i)
		if (Tabs[i].classic) {
			if (static_cast<int>(i) == slot) self = static_cast<int>(refs.size());
			refs.push_back({ PanelName(Tabs[i].id), Tabs[i].cfg.label, Tabs[i].cfg.name });
		}
	const auto frag = slot == 0 ? SummaryFragment(SummaryClassic, invtabs::summary::LayoutMode::Classic, Lay::ClassicSummaryText(tab->area.h)) : std::string();
	return Lay::ClassicPanel(refs, self, slot, tab->area.w, tab->area.h, frag);
}

// Registers the slot's layouts again when they changed (the panel is unloaded first when it was loaded).
bool SyncLayout(int slot) {
	auto* tab = SlotTab(slot);
	if (!tab) return false;
	const std::string hd = HdText(slot), legacy = ClassicText(slot);
	if (hd == tab->hdText && legacy == tab->legacyText && tab->hd != Res::InvalidHandle) return true;
	if (tab->opened && WidgetApi) {
		const std::string       name = PanelName(tab->id);
		const Widgets::UiAction unload { .structSize = Widgets::UiActionSize, .flags = 0, .target = "PanelManager", .command = "UnloadPanel", .text = name.c_str() };
		(void)WidgetApi->dispatchUiAction(Context, &unload);
		tab->opened = false;
	}
	for (auto* handle : { &tab->hd, &tab->legacy })
		if (*handle != Res::InvalidHandle) (void)ResourceApi->unregisterResource(Context, *handle), *handle = Res::InvalidHandle;
	const std::string dir = std::string("data/global/ui/layouts/") + PluginId + "/" + tab->id;
	if (!RegisterResource(dir + "hd.json", hd, &tab->hd)) return false;
	tab->hdText = hd;
	if (!legacy.empty() && RegisterResource(dir + ".json", legacy, &tab->legacy)) tab->legacyText = legacy;
	else tab->legacyText.clear();
	return true;
}

bool PanelOpen(const TabState& tab) {
	if (tab.panel == Panels::InvalidHandle) return false;
	Panels::PanelInfo info { .structSize = Panels::PanelInfoSize };
	return PanelApi->getPanelInfo(Context, tab.panel, &info) == Panels::Result::Success && info.presentationState == Panels::PresentationState::Open;
}

// The controller panel (gamepad menu) is open.
bool PadOpen() {
	if (PadHandles.panel == Panels::InvalidHandle) return false;
	Panels::PanelInfo info { .structSize = Panels::PanelInfoSize };
	return PanelApi->getPanelInfo(Context, PadHandles.panel, &info) == Panels::Result::Success && info.presentationState == Panels::PresentationState::Open;
}

// The notice of a joined player's read-only tabs, above the summary's totals (UI thread).
void ApplyNotice() {
	if (!NoticeDirty.exchange(false)) return;
	std::vector<std::string> lines;
	const Mp::JoinMode       mode = LinkMode.load();
	if (Remote.load() && mode != Mp::JoinMode::Full && mode != Mp::JoinMode::Local) {
		// Plain words for the player; the log has the technical reason (LinkChanged).
		std::string text;
		switch (WhyReadOnly.load()) {
		case ReadOnlyWhy::OtherSetup: text = "The host's charm inventory is set up differently from yours."; break;
		case ReadOnlyWhy::OtherProtocol: text = "The host's charm inventory does not match yours."; break;
		case ReadOnlyWhy::NoCharmInventory: text = "The host does not have this charm inventory."; break;
		default: text = "Connecting to the host's charm inventory."; break;
		}
		text += " You can take charms out here, but not put them in.";
		std::istringstream words(text);
		std::string        word, line;
		while (words >> word) { // 40 characters a line: the classic panel's width
			if (!line.empty() && line.size() + 1 + word.size() > 40) lines.push_back(line), line.clear();
			line += (line.empty() ? "" : " ") + word;
		}
		if (!line.empty()) lines.push_back(line);
	}
	SummaryHd.SetNotice(lines);
	SummaryClassic.SetNotice(lines);
	SummaryPad.SetNotice(lines);
}

void __cdecl SummaryTask(const D2RL::PluginContext*, void*) noexcept {
	SummaryQueued     = false;
	const bool fresh  = SummaryFresh.exchange(false);
	if (!SummaryOn || Tabs.empty()) return;
	try {
		ApplyNotice();
		void* units[512];
		const std::size_t n = CharmUnits(ClientOwner.load(), CustomPageByte.load(), Tabs[0].area, units, 512);
		SummaryHd.Refresh(units, n);
		SummaryClassic.Refresh(units, n);
		SummaryPad.Refresh(units, n);
		static std::atomic<int> told {};
		if (told.fetch_add(1) < 40)
			Log(false, "summary: %zu charm(s) looked at, %zu counted, %zu left out, %zu line(s)", n, SummaryHd.Counted(), SummaryHd.Skipped(), SummaryHd.Lines().size());
		if (PadOpen()) { // the controller panel has fixed rows (no scrolling on the pad): lines past them are not shown
			SummaryPad.ApplyTexts(invtabs::pad::PanelName(0).c_str(), fresh);
			if (told.load() < 40) Log(false, "summary: on the controller panel, %zu line(s) of %zu row(s)", SummaryPad.Lines().size(), SummaryPad.Rows());
			return;
		}
		const bool        classic = DrawnClassic[0].load();
		const std::string name    = PanelName(Tabs[0].id);
		Tabs[0].opened            = true;
		if (!classic && SummaryHd.NeedsRelayout()) {
			const bool open = PanelOpen(Tabs[0]);
			if (open) (void)PanelApi->closePanel(Context, Tabs[0].panel);
			if (SyncLayout(0) && open) (void)PanelApi->openPanel(Context, Tabs[0].panel); // the texts follow on its first draw
			return;
		}
		(classic ? SummaryClassic : SummaryHd).ApplyTexts(name.c_str(), fresh);
	} catch (...) {
	}
}

// ---- panels ----

Panels::RegistrationHandle AddPanel(int slot) {
	auto* tab = SlotTab(slot);
	if (!SyncLayout(slot)) return Panels::InvalidHandle;
	const Panels::PanelRegistration registration {
		.structSize = Panels::PanelRegistrationSize,
		.flags      = Panels::PanelFlags::CloseOnEscape | Panels::PanelFlags::GameplayLeftSlot,
		.localId    = tab->id.c_str(),
	};
	Panels::RegistrationHandle panel = Panels::InvalidHandle;
	if (const auto r = PanelApi->registerPanel(Context, &registration, &panel); r != Panels::Result::Success) {
		Log(true, "could not register panel %s (result %u)", tab->id.c_str(), static_cast<unsigned>(r));
		return Panels::InvalidHandle;
	}
	const Panels::PlayerPageGridBinding binding {
		.structSize = Panels::PlayerPageGridBindingSize,
		.panel      = panel,
		.page       = Page,
		.childName  = "invtabs/Grid",
	};
	if (const auto r = PanelApi->bindPlayerPageGrid(Context, &binding); r != Panels::Result::Success) {
		Log(true, "could not bind the grid of %s (result %u)", tab->id.c_str(), static_cast<unsigned>(r));
		(void)PanelApi->unregisterPanel(Context, panel);
		return Panels::InvalidHandle;
	}
	return panel;
}

void AddButton() {
	if (!RegisterSprite("button", ButtonFrames())) return;
	char button[1024] {};
	std::snprintf(button, sizeof(button),
	              R"({"type": "ButtonWidget", "name": "invtabs/InventoryButton", "fields": {"rect": {"x": 214, "y": 1375}, "filename": "d2rloader/invtabs/button", "normalFrame": 0, "pressedFrame": 1, "disabledFrame": 2, "hoveredFrame": 3, )"
	              R"("tooltipString": %s, "sound": "cursor_menu_select_hd", "onClickMessage": %s}})",
	              Lay::Json(Tabs[0].cfg.label).c_str(), Lay::Json("PanelManager:TogglePanel:" + PanelName(Tabs[0].id)).c_str());
	if (!RegisterResource("data/global/ui/layouts/invtabs/InventoryButtonhd.json", button)) return;
	const Panels::ChildLayoutRegistration child {
		.structSize = Panels::ChildLayoutRegistrationSize,
		.flags      = Panels::ChildLayoutFlags::KeyboardMouseOnly,
		.stockPanel = Panels::StockPanel::PlayerInventory,
		.localId    = "InventoryButton",
	};
	Panels::ChildLayoutHandle handle {};
	if (const auto r = PanelApi->registerChildLayout(Context, &child, &handle); r != Panels::Result::Success) Log(true, "could not add the inventory button (result %u)", static_cast<unsigned>(r));
}

// ---- open / close ----

void Show(TabState* tab, int mode) { // mode 1 open, 0 close, -1 toggle
	if (!tab || tab->panel == Panels::InvalidHandle) {
		Context->WriteConsoleMessage("invtabs: no such tab (see the D2RLoader log)");
		return;
	}
	const bool open = PanelOpen(*tab);
	if (mode < 0) mode = open ? 0 : 1;
	if (mode) tab->opened = true;
	const auto r = mode ? PanelApi->openPanel(Context, tab->panel) : PanelApi->closePanel(Context, tab->panel);
	if (r != Panels::Result::Success) Log(true, "%s %s: result %u", mode ? "open" : "close", tab->id.c_str(), static_cast<unsigned>(r));
}

TabState* TabNamed(const std::string& name) {
	if (name.empty()) return Tabs.empty() ? nullptr : &Tabs[0];
	for (auto& t : Tabs)
		if (_stricmp(t.cfg.name.c_str(), name.c_str()) == 0) return &t;
	return nullptr;
}

std::string StatusLine() {
	const Area a = Tabs[0].area;
	char       line[256] {};
	std::snprintf(line, sizeof(line), "invtabs %s: page 16x16, %zu tab(s), charm tab %dx%d at %d,%d (%s), areas %s", PluginVersion, Tabs.size(), a.w, a.h, a.x, a.y,
	              PanelOpen(Tabs[0]) ? "open" : "closed", AreasOn() ? "on" : "off");
	std::string out = line;
	for (std::size_t i = 1; i < Tabs.size(); ++i) {
		const Area b = Tabs[i].area;
		std::snprintf(line, sizeof(line), "; tab %s %dx%d at %d,%d (%s)", Tabs[i].cfg.name.c_str(), b.w, b.h, b.x, b.y, PanelOpen(Tabs[i]) ? "open" : "closed");
		out += line;
	}
	// which tab's grid the game actually drew in the last 300 ms (tests: the panel is on screen, not only "open")
	const int shown = ShownSlot();
	const auto* seen = shown >= 0 ? SlotTab(shown) : nullptr;
	std::snprintf(line, sizeof(line), "; drawn %s%s; pad %s", seen ? seen->cfg.name.c_str() : "none",
	              seen ? (DrawnClassic[static_cast<std::size_t>(shown)].load() ? " classic" : " hd") : "",
	              PadHandles.route == Panels::InvalidControllerRouteHandle ? "off" : PadOpen() ? "open" : "closed");
	out += line;
	// the TCP/IP link: local (single player or this game hosts, then with the number of welcomed joined players), or joined
	std::snprintf(line, sizeof(line), "; link %s", ModeName(LinkMode.load()));
	out += line;
	if (const int peers = WelcomedPeers.load(); peers > 0) out += ", " + std::to_string(peers) + " joined";
	return out;
}

auto Command(D2R::Game::Client*, const D2RL::ConsoleCommandContext* command, void*) noexcept -> D2RL::ConsoleCommandResult {
	try {
		std::string args = command && command->args ? std::string(command->args, command->argsLength) : std::string();
		std::istringstream words(args);
		std::string        verb, name;
		words >> verb >> name;
		if (Tabs.empty() || Page == Inv::InvalidHandle) {
			Context->WriteConsoleMessage("invtabs: no tabs (disabled, or the page belongs to another plugin)");
			return D2RL::ConsoleCommandResult::Handled;
		}
		if (verb == "all") Show(&AllTab, -1);
		else if (verb == "open") Show(TabNamed(name), 1);
		else if (verb == "close") Show(TabNamed(name), 0);
		else if (verb == "toggle") Show(TabNamed(name), -1);
		else if (verb == "scroll") {
			SummaryClassic.ScrollBy(std::atoll(name.c_str()));
			SummaryClassic.ApplyTexts(PanelName(Tabs[0].id).c_str());
		} else if (verb == "summary") { // the charm tab's summary lines into invtabs.log (tests compare them with tooltips)
			SummaryTask(Context, nullptr); // fresh totals (a level-up changes what counts without a page change)
			const auto& lines = SummaryHd.Lines();
			Log(false, "summary: %s, %zu counted, %zu left out, %zu line(s)", SummaryOn ? "on" : "off", SummaryHd.Counted(), SummaryHd.Skipped(), lines.size());
			for (std::size_t i = 0; i < lines.size(); ++i) Log(false, "summary line %zu: %s", i, lines[i].c_str());
			Context->WriteConsoleMessage("invtabs: summary lines written to the log");
		} else {
			const std::string line = StatusLine();
			Context->WriteConsoleMessage(line.c_str());
			Log(false, "status: %s", line.c_str() + 8); // also in invtabs.log, where tests read it
		}
	} catch (...) {
	}
	return D2RL::ConsoleCommandResult::Handled;
}

auto OnToggleAction(const D2RL::PluginContext*, const D2RL::Input::ActionEvent* event, void*) noexcept -> D2RL::Input::ActionResult {
	if (!D2RL::Input::HasActionEventField(event, D2RL::Input::ActionEventRequiredSize) || event->kind != D2RL::Input::ActionEventKind::Pressed) return D2RL::Input::ActionResult::Ignored;
	if (!Tabs.empty()) Show(&Tabs[0], -1);
	return D2RL::Input::ActionResult::Handled;
}

// Classic graphics have no mouse wheel for plugin widgets: two bindable keys scroll the charm tab's summary.
auto OnScrollAction(const D2RL::PluginContext*, const D2RL::Input::ActionEvent* event, void* user) noexcept -> D2RL::Input::ActionResult {
	if (!D2RL::Input::HasActionEventField(event, D2RL::Input::ActionEventRequiredSize) || event->kind != D2RL::Input::ActionEventKind::Pressed) return D2RL::Input::ActionResult::Ignored;
	if (Tabs.empty() || ShownSlot() != 0 || !DrawnClassic[0].load()) return D2RL::Input::ActionResult::Ignored;
	try {
		SummaryClassic.ScrollBy(user ? 3 : -3);
		SummaryClassic.ApplyTexts(PanelName(Tabs[0].id).c_str());
	} catch (...) {
	}
	return D2RL::Input::ActionResult::Handled;
}

// ---- character load and leave ----

void __cdecl ScanOnGameThread(const D2RL::PluginContext*, void*) noexcept {
	try {
		D2RL::PlayerHandle player {};
		if (!LocalPlayer(player)) return;
		int total = 0, outside = 0;
		for (const auto& [item, size] : ScanPage(player)) {
			++total;
			bool in = false;
			for (const auto& tab : Tabs) in = in || invtabs::Inside(tab.area, item.x, item.y, size.first, size.second);
			if (!in) {
				++outside;
				Log(true, "a page item (%dx%d) at %d,%d lies outside every tab: it stays there (reach it with 'invtabs all')", size.first, size.second, item.x, item.y);
			}
		}
		Log(false, "character ready: %d item(s) on the page, %d outside every tab", total, outside);
		SaveMemory();
	} catch (...) {
	}
}

void __cdecl OnPlayerReady(const D2RL::PluginContext*, const D2RL::Lifecycle::GameplayEvent*, void*) noexcept {
	// A joined TCP/IP client has no game thread of its own (SDK: runOnGameThread returns Unavailable there): that is how
	// this client knows another PC hosts its game.
	const auto queued = ThreadApi ? ThreadApi->runOnGameThread(Context, ScanOnGameThread, nullptr) : D2RL::Threads::Result::Busy;
	try {
		ResetLink(true, queued == D2RL::Threads::Result::Unavailable);
		if (Remote.load()) {
			Log(false, "multiplayer: this game is hosted by another PC; tabs are read-only until its invtabs answers");
			if (!NetApi || Channel == Net::InvalidChannelHandle) RefuseLink();
		}
	} catch (...) {
	}
	if (queued != D2RL::Threads::Result::Success) ScanOnGameThread(Context, nullptr);
}

void __cdecl OnGameLeft(const D2RL::PluginContext*, const D2RL::Lifecycle::GameplayEvent*, void*) noexcept {
	ClientOwner = nullptr;
	try {
		ResetLink(false, false);
		SaveMemory();
	} catch (...) {
	}
}

// ---- type tables ----

constexpr std::uint32_t TypeColumn = 8; // itemType: up to 4 characters and the NUL, padded

std::string TableName(const invtabs::Tab& tab) {
	std::string name = tab.typesFile.substr(0, tab.typesFile.size() - 4); // types_<name>.txt -> types_<name>
	for (auto& c : name) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
	return name;
}

void RegisterTypeTables() {
	if (!TableApi) return;
	static const Tables::ColumnDefinition column {
		.structSize = Tables::ColumnDefinitionSize, .name = "itemType", .type = Tables::ColumnType::Ascii, .offset = 0, .length = TypeColumn };
	for (auto& tab : Tabs) {
		if (!tab.cfg.types.empty() || tab.cfg.typesFile.empty()) continue; // inline item_types
		const std::string                name = TableName(tab.cfg);
		const Tables::TableRegistration  table {
			 .structSize = Tables::TableRegistrationSize, .name = name.c_str(), .banks = Tables::TableBank::Rotw, .rowSize = TypeColumn, .columns = &column,
			 .columnCount = 1, .columnStride = Tables::ColumnDefinitionSize };
		if (const auto r = TableApi->registerTable(Context, &table, &tab.table); r != Tables::Result::Success) {
			tab.table = Tables::InvalidHandle;
			Log(true, "tab %s: could not register its type table %s (result %u)", tab.cfg.name.c_str(), name.c_str(), static_cast<unsigned>(r));
		}
	}
}

std::vector<std::string> ReadTypeTable(const TabState& tab) {
	std::vector<std::string> codes;
	if (!TableApi || tab.table == Tables::InvalidHandle) return codes;
	Tables::TableInfo info { .structSize = Tables::TableInfoSize };
	if (TableApi->getTableInfo(Context, tab.table, Tables::TableBank::Rotw, &info) != Tables::Result::Success || info.state != Tables::TableState::Ready) {
		Log(true, "tab %s: its type table %s is not loaded (state %u)", tab.cfg.name.c_str(), tab.cfg.typesFile.c_str(), static_cast<unsigned>(info.state));
		return codes;
	}
	std::vector<char> rows(static_cast<std::size_t>(info.byteCount));
	if (info.byteCount && TableApi->copyRows(Context, tab.table, Tables::TableBank::Rotw, info.revision, rows.data(), info.byteCount) != Tables::Result::Success) return codes;
	for (std::uint32_t i = 0; i < info.rowCount; ++i) {
		const char* cell = rows.data() + static_cast<std::size_t>(i) * info.rowSize;
		codes.emplace_back(cell, strnlen(cell, TypeColumn));
	}
	return codes;
}

// Each tab's types: inline item_types, else its table; codes the game does not know are left out (logged).
void LoadTypes() {
	for (std::size_t i = 0; i < Tabs.size(); ++i) {
		auto&                    tab   = Tabs[i];
		std::vector<std::string> codes = tab.cfg.types.empty() ? ReadTypeTable(tab) : tab.cfg.types;
		std::vector<invtabs::TypeCode> known;
		for (const auto& code : codes) {
			bool                ok = true;
			Inv::ItemTypeFourCC four {};
			std::memcpy(four.value, code.data(), std::min<std::size_t>(code.size(), 4));
			if (Inventory->isItemTypeCodeKnown && Inventory->isItemTypeCodeKnown(Context, four, &ok) == Inv::Result::Success && !ok) {
				Log(true, "tab %s: item type '%s' is not in the game's itemtypes: left out", tab.cfg.name.c_str(), code.c_str());
				continue;
			}
			known.push_back(code);
		}
		if (known.empty() && i == 0) {
			known = invtabs::CharmFallbackTypes();
			Log(true, "tab %s: no type list, it takes charms (type 'char' and its children)", tab.cfg.name.c_str());
		} else if (known.empty()) Log(true, "tab %s: no type list: it takes nothing (see %s)", tab.cfg.name.c_str(), tab.cfg.typesFile.c_str());
		std::string list;
		for (const auto& k : known) list += (list.empty() ? "" : " ") + k;
		Log(false, "tab %s: takes %s", tab.cfg.name.c_str(), list.empty() ? "nothing" : list.c_str());
		std::lock_guard guard(TypesLock);
		tab.types = std::move(known);
	}
}

void __cdecl OnTablesLoaded(const D2RL::PluginContext*, const D2RL::Lifecycle::DataTablesLoadedEvent*, void*) noexcept {
	static bool done = false;
	if (done) return;
	done = true;
	try {
		LoadTypes();
	} catch (...) {
	}
	// Every plugin has loaded: wrap the grid on top of whatever is there.
	if (NativesOk && !Tabs.empty() && !PatchVtable()) {
		NextDraw = nullptr;
		Log(true, "the grid widget could not be wrapped: tab areas off (each tab shows the whole page)");
	}
}

// ---- load ----

void RegisterPage() {
	const Inv::PlayerPageRegistration page { .structSize = Inv::PlayerPageRegistrationSize, .logicalId = LogicalPageId };
	if (const auto r = Inventory->registerPlayerPage(Context, &page, &Page); r != Inv::Result::Success) {
		Page = Inv::InvalidHandle;
		Log(true, "could not get the custom page (result %u): another plugin registered it first (CharmInv?). invtabs stays off.", static_cast<unsigned>(r));
		return;
	}
	const Inv::PlayerPageConfiguration size { .structSize = Inv::PlayerPageConfigurationSize, .width = invtabs::PageSize, .height = invtabs::PageSize };
	if (const auto r = Inventory->configurePlayerPage(Context, Page, &size); r != Inv::Result::Success) Log(true, "page size 16x16 refused (result %u)", static_cast<unsigned>(r));
	const Inv::PlayerPageCharmPolicyConfiguration charms {
		.structSize = Inv::PlayerPageCharmPolicyConfigurationSize,
		.flags      = static_cast<std::uint32_t>(Inv::PlayerPageInactiveCharmTint::Default),
		.page       = Page,
		.policy     = Settings.inventoryCharms ? Inv::PlayerPageCharmPolicy::StockInventoryAndPlayerPage : Inv::PlayerPageCharmPolicy::PlayerPageOnly,
	};
	if (const auto r = Inventory->configurePlayerPageCharmPolicy(Context, &charms); r != Inv::Result::Success) Log(true, "the charm policy was refused (result %u)", static_cast<unsigned>(r));
	const Inv::PlayerPageItemPolicy policy { .structSize = Inv::PlayerPageItemPolicySize, .page = Page, .callback = OnPagePolicy };
	if (const auto r = Inventory->configurePlayerPageItemPolicy(Context, &policy); r != Inv::Result::Success) Log(true, "could not set the page's item policy (result %u)", static_cast<unsigned>(r));
}

// The tabs from the config and the remembered layout.
void PlanLayout() {
	for (const auto& problem : Settings.problems) Log(true, "invtabs.toml: %s", problem.c_str());
	std::string remembered = ReadFile(MemoryPath());
	if (remembered.size() > 65536) { // a few lines per tab: anything this big is not ours, so it is ignored (worst case: no refusal)
		Log(true, "%s is too big to be this plugin's file: ignored", MemoryFile);
		remembered.clear();
	}
	const auto memory = invtabs::ParseMemory(remembered);
	const auto        plan       = invtabs::PlanTabs(Settings.tabs, memory);
	for (const auto& note : plan.notes) Log(plan.refused, "%s", note.c_str());
	if (plan.refused) Log(true, "the tab config was refused: the %s layout stays (nothing on the page moves)", memory.empty() ? "default" : "remembered");
	for (std::size_t i = 0; i < plan.tabs.size(); ++i) {
		TabState tab;
		tab.cfg  = plan.tabs[i];
		tab.area = plan.areas[i];
		tab.id   = tab.cfg.name;
		tab.id[0] = static_cast<char>(std::toupper(static_cast<unsigned char>(tab.id[0])));
		Tabs.push_back(std::move(tab));
	}
	std::lock_guard guard(MemoryLock);
	Memory      = invtabs::MemoryOf(plan, memory);
	MemoryDirty = invtabs::FormatMemory(Memory) != invtabs::FormatMemory(memory);
}

void RegisterPad() {
	const auto log = [](bool warn, const char* text) noexcept { Log(warn, "%s", text); };
	const auto sprite = [](const char* name, int w, int h, const std::uint8_t* rgba) noexcept {
		try {
			Lay::Picture p { w, h, std::vector<unsigned char>(rgba, rgba + static_cast<std::size_t>(w) * h * 4) };
			return RegisterSprite(name, { p });
		} catch (...) {
			return false;
		}
	};
	// the summary in the panel's summary well (a margin inside the drawn rim)
	const auto        well    = invtabs::pad::Layout(Tabs[0].area.w, Tabs[0].area.h).summary;
	const std::string summary = SummaryOn ? SummaryPad.Fragment(invtabs::summary::LayoutMode::Hd, { well.x + 20, well.y + 16, well.w - 40, well.h - 32 }) : std::string();
	invtabs::pad::Options options { .cols = Tabs[0].area.w, .rows = Tabs[0].area.h, .slot = 0 };
	if (!summary.empty()) options.summary = summary.c_str();
	const invtabs::pad::Hooks   hooks { .log = log, .registerSprite = sprite };
	const auto                  status = invtabs::pad::Register(Context, PanelApi, ResourceApi, Page, options, hooks, &PadHandles);
	Log(status != invtabs::pad::Status::Ok, "controller tab: %s (status %u)", status == invtabs::pad::Status::Ok ? "in the gamepad menu" : "off", static_cast<unsigned>(status));
}

bool Load() {
	Inventory   = Query<D2RL::InventoryService>("inventory");
	PanelApi    = Query<D2RL::PanelService>("panel");
	ResourceApi = Query<D2RL::ResourceService>("resource");
	ItemApi     = Query<D2RL::ItemService>("item");
	ThreadApi   = Query<D2RL::ThreadService>("thread");
	WidgetApi   = Query<D2RL::WidgetService>("widget");
	TableApi    = Query<D2RL::CustomTableService>("custom table");
	if (!Inventory) {
		Log(true, "%s: no inventory service, the page cannot be registered", PluginVersion);
		return true;
	}
	PlanLayout();

	RegisterPage(); // always: D2RCore refuses characters with page items when nobody owns the page
	if (!Settings.enabled) {
		Tabs.clear();
		Log(false, "%s: disabled in config; the page is kept so saved page items still load", PluginVersion);
		return true;
	}
	if (Page == Inv::InvalidHandle) {
		Tabs.clear();
		return true;
	}
	RegisterTypeTables();

	Base      = Context->exeBase;
	NativesOk = Base && Locate();
	SummaryOn = NativesOk && SummaryHd.Init(reinterpret_cast<const void*>(Base), SummaryLog) && SummaryClassic.Init(reinterpret_cast<const void*>(Base), SummaryLog)
	         && SummaryPad.Init(reinterpret_cast<const void*>(Base), SummaryLog);
	if (!SummaryOn) Log(true, "the charm summary is off (see the lines above)");

	if (!PanelApi || !ResourceApi || !D2RL::HasPanelServiceField(PanelApi, D2RL::PanelServiceRegisterChildLayoutFieldEnd)) {
		Log(true, "no panel or resource service: no tab panels (the page and its charms still work)");
	} else {
		if (const std::string stock = ReadModFile("data/hd/global/ui/panel/invtabs/stockgrid.sprite"); !stock.empty()) StockGrid = Lay::ParseSprite(stock);
		Log(!StockGrid, "grid cells: %s", StockGrid ? "D2R's stash cells (stockgrid.sprite)" : "drawn stand-in (the mod has no data/hd/global/ui/panel/invtabs/stockgrid.sprite)");
		for (auto& tab : Tabs) {
			tab.classic = Lay::ClassicFits(tab.area.w, tab.area.h) && ModFileExists("data/global/ui/panel/invtabs_" + tab.cfg.name + ".dc6");
			if (!tab.classic)
				Log(false, "tab %s (%dx%d): no classic layout (%s): HD graphics only", tab.cfg.name.c_str(), tab.area.w, tab.area.h,
				    Lay::ClassicFits(tab.area.w, tab.area.h) ? "the mod has no classic art for it" : "more than 10 columns or too many rows for the classic panel");
		}
		for (std::size_t i = 0; i < Tabs.size(); ++i) Tabs[i].panel = AddPanel(static_cast<int>(i));
		AllTab.id    = "All";
		AllTab.area  = { 0, 0, invtabs::PageSize, invtabs::PageSize };
		AllTab.panel = AddPanel(invtabs::AllSlot);
		if (Settings.openButton) AddButton();
		RegisterPad();
	}

	if (const auto* lifecycle = Query<D2RL::LifecycleService>("lifecycle")) {
		D2RL::Lifecycle::ListenerHandle                 handle {};
		const D2RL::Lifecycle::DataTablesLoadedListener tables { .structSize = D2RL::Lifecycle::DataTablesLoadedListenerSize, .callback = OnTablesLoaded };
		if (lifecycle->registerDataTablesLoadedListener(Context, &tables, &handle) != D2RL::Lifecycle::Result::Success) Log(true, "could not follow data table loads: tab areas off");
		const D2RL::Lifecycle::GameplayEventListener ready {
			.structSize = D2RL::Lifecycle::GameplayEventListenerSize,
			.kind       = D2RL::Lifecycle::GameplayEventKind::LocalPlayerReady,
			.callback   = OnPlayerReady,
		};
		(void)lifecycle->registerGameplayEventListener(Context, &ready, &handle);
		const D2RL::Lifecycle::GameplayEventListener left {
			.structSize = D2RL::Lifecycle::GameplayEventListenerSize,
			.kind       = D2RL::Lifecycle::GameplayEventKind::GameLeft,
			.callback   = OnGameLeft,
		};
		(void)lifecycle->registerGameplayEventListener(Context, &left, &handle);
	}
	if (const auto* clicks = Query<D2RL::ItemInteractionService>("item interaction"); clicks && ItemApi && ThreadApi) {
		const Clicks::ItemInteractionListener listener { .structSize = Clicks::ItemInteractionListenerSize, .priority = -1000, .callback = OnItemClick };
		Clicks::ListenerHandle                handle = Clicks::InvalidHandle;
		if (const auto r = clicks->registerListener(Context, &listener, &handle); r != Clicks::Result::Success)
			Log(true, "Ctrl+click into a tab is off: the item click listener was refused (result %u)", static_cast<unsigned>(r));
	} else Log(true, "Ctrl+click into a tab is off (no item interaction, item or thread service)");
	StartNetwork();
	if (const D2RL::InputService* input = nullptr;
	    Context->QueryService(&input) == D2RL::ServiceQueryResult::Success && input && D2RL::HasInputServiceField(input, D2RL::InputServiceRequiredSize)) {
		struct Action {
			const char* id;
			const char* name;
			D2RL::Input::Key key;
			D2RL::Input::ActionCallback callback;
			void*       user;
		};
		// open_key 73 (I) is the game's own inventory key: binding it would take I from the inventory, so that value (and 0)
		// leaves the action unbound; the player can bind it in the Controls menu.
		const bool bindKey = Settings.openKey > 0 && Settings.openKey < 256 && Settings.openKey != 'I';
		const auto openKey = bindKey ? static_cast<D2RL::Input::Key>(Settings.openKey) : D2RL::Input::Key::None;
		for (const Action& a : { Action { "toggle-charms", "Open/close charms", openKey, OnToggleAction, nullptr },
		                         Action { "summary-up", "Charm summary up (classic graphics)", D2RL::Input::Key::PageUp, OnScrollAction, nullptr },
		                         Action { "summary-down", "Charm summary down (classic graphics)", D2RL::Input::Key::PageDown, OnScrollAction, reinterpret_cast<void*>(1) } }) {
			const D2RL::Input::ActionRegistration action {
				.structSize       = D2RL::Input::ActionRegistrationSize,
				.logicalId        = a.id,
				.displayName      = a.name,
				.category         = "Inventory Tabs",
				.defaultPrimary   = { .key = a.key },
				.defaultSecondary = { .key = D2RL::Input::Key::None },
				.callback         = a.callback,
				.userData         = a.user,
			};
			D2RL::Input::ActionHandle handle = D2RL::Input::InvalidHandle;
			if (const auto r = input->registerAction(Context, &action, &handle); r != D2RL::Input::Result::Success)
				Log(true, "could not add '%s' to the Controls menu (result %u)", a.name, static_cast<unsigned>(r));
		}
	}
	(void)Context->RegisterConsoleCommand("invtabs", Command,
	                                      "Inventory tabs: 'invtabs' status, 'invtabs open|close|toggle [tab]' a tab (the charm tab without a name), 'invtabs all' the whole page, 'invtabs scroll n' the classic summary.");
	const Area a = Tabs[0].area;
	Log(false, "%s: page 16x16 owned, %zu tab(s), charm tab %dx%d at %d,%d, charms count %s, areas %s", PluginVersion, Tabs.size(), a.w, a.h, a.x, a.y,
	    Settings.inventoryCharms ? "in the inventory and the tab" : "in the tab only", NativesOk ? "found (wrapped once tables load)" : "OFF");
	for (std::size_t i = 1; i < Tabs.size(); ++i) Log(false, "tab %s '%s' %dx%d at %d,%d", Tabs[i].cfg.name.c_str(), Tabs[i].cfg.label.c_str(), Tabs[i].area.w, Tabs[i].area.h, Tabs[i].area.x, Tabs[i].area.y);
	SaveMemory();
	return true;
}

} // namespace

// For mxl2012-core (charmdup, stash retirement): the charm tab's rectangle on the page. 1 when the tab exists.
extern "C" __declspec(dllexport) int __cdecl InvTabsCharmTab(int* x, int* y, int* w, int* h) noexcept {
	if (Tabs.empty() || Page == Inv::InvalidHandle) return 0;
	const Area a = Tabs[0].area;
	if (x) *x = a.x;
	if (y) *y = a.y;
	if (w) *w = a.w;
	if (h) *h = a.h;
	return 1;
}

D2RL_PLUGIN_EXPORT auto D2RLoaderGetPluginInfo() noexcept -> const D2RL::PluginInfo* {
	return &Info;
}

D2RL_PLUGIN_EXPORT auto D2RLoaderLoadPlugin(const D2RL::PluginContext* context) noexcept -> bool {
	if (!D2RL::HasContext(context) || !context->GetApi()) return false;
	Context = context;
	try {
		(void)Context->EnsureConfig();
		std::uint32_t required = 0;
		std::string   config(16384, '\0');
		if (Context->ReadConfig(config.data(), static_cast<std::uint32_t>(config.size()), &required)) {
			config.resize(std::strlen(config.c_str()));
			Settings = invtabs::ParseConfig(config);
		} else Log(true, "could not read invtabs.toml: defaults used");
		return Load();
	} catch (...) {
		Log(true, "load failed (out of memory?)");
		return true;
	}
}

D2RL_PLUGIN_EXPORT void D2RLoaderUnloadPlugin() noexcept {
	StopNetwork();
	RestoreVtable();
	try {
		if (PanelApi && ResourceApi) invtabs::pad::Unregister(Context, PanelApi, ResourceApi, &PadHandles);
		SaveMemory();
	} catch (...) {
	}
}

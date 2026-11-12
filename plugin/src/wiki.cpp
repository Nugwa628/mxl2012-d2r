// The wiki panel (docs/wiki-panel.md; off word wiki). The Controls action "Wiki" (mxl_wiki, rebindable) opens the native HD panel
// `mxl2012-core/Wiki` (tools/wiki_layout.py): a search box, a row of categories, a result list with pages on the left and the selected
// entry's text on the right, with links to other entries and a Back button.
//
// Layering: everything runs on the UI thread. The panel's widgets are native; button clicks, D2R's own text setter with change tracking, the
// search box typing fix and the mouse wheel come from panel_shared.cpp, shared with the developer menu. The rules (the content table's
// parser, search, pages, wrapping, scrolling, links, history) are wiki_logic.h, unit tested without the game.
//
// The content (data/mxl2012-wiki/wiki.tsv in the mod, written by the build) is read once at load. The panel reads no game state and changes
// nothing in the game, so it has no single-player gate: it opens the same in a joined or TCP/IP game. HD graphics only: in classic graphics
// the action prints one line in the message log and the panel stays closed.
#include "wiki.h"

#include "d2r.h"
#include "map_reveal_logic.h"
#include "mxl_wiki_layout.h"
#include "panel_logic.h"
#include "panel_shared.h"
#include "wiki_logic.h"

#include <D2RLPlugin/input.h>
#include <D2RLPlugin/panels.h>
#include <D2RLPlugin/threads.h>
#include <D2RLPlugin/widgets.h>

#include <windows.h>

#include <algorithm>
#include <atomic>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>

namespace {

using namespace wiki_logic;
namespace layout = wiki_layout;

// game functions (image 0x6ab3782c; the plugin's image check guards all of them)
constexpr uint64_t RvaLocalId = 0x8b2d0;         // () -> the client's own player id
constexpr uint64_t RvaClientPlayer = 0x9a480;    // (id) -> the client's player unit
constexpr uint64_t RvaClientChat = 0x12c190;     // client handler of packet 0x26 (map_reveal.cpp, docs/d2r-addresses.md 13)
constexpr uint64_t RvaMenuNpcValid = 0x2a48760;  // u32, non-zero while the client talks to an NPC (a chat line would freeze the speech)
constexpr uint8_t ChatEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x10, 0x48, 0x89, 0x74, 0x24, 0x18, 0x57, 0x48, 0x81, 0xec, 0x90};
constexpr size_t MaxTableBytes = 64 * 1024 * 1024;
constexpr int WheelLines = 3;  // detail lines one wheel notch scrolls
constexpr int MatchLead = 2;   // lines shown above the search hit an entry opens at
constexpr size_t RowGapChars = 3, MinSubtitleChars = 8;  // a row: the least room between name and subtitle, the shortest subtitle worth showing
constexpr char MarkText[] = ">";  // left of a detail line that holds the search words
static_assert(layout::ColourCount == ColourCount, "one text box per table colour for every detail line");
constexpr char WelcomeName[] = "Welcome";
constexpr char HintText[] = "An arrow opens an entry or a link. The mouse wheel turns the list's pages and scrolls the text. Esc closes.";
constexpr char NeedsHdText[] = "The wiki is only available in HD graphics.";
constexpr char NoTableText[] = "The wiki text was not found in this installation of the mod.";

using LocalIdFn = uint32_t (*)();
using ClientPlayerFn = void* (*)(uint32_t);
using ChatFn = void (*)(const uint8_t*);

const D2RL::PluginContext* g_context = nullptr;
const D2RL::ThreadService* g_threads = nullptr;
const D2RL::WidgetService* g_widgets = nullptr;
const D2RL::PanelService* g_panels = nullptr;
const D2RL::InputService* g_input = nullptr;
D2RL::Panels::RegistrationHandle g_panel = 0;
D2RL::Input::ActionHandle g_action = D2RL::Input::InvalidHandle;
uint64_t g_base = 0;
bool g_on = false;
bool g_chatOk = false;  // the chat handler's entry bytes matched: the notices can be printed

Table g_table;            // read once at load, read-only afterwards
int g_welcome = NotFound;  // the entry shown when the panel opens
long g_loadMs = 0;
std::string g_layoutJson;  // the layout with the table's category labels

panel_shared::Client g_client;
std::atomic<bool> g_tickQueued{false};
std::atomic<bool> g_toggleQueued{false};
std::atomic<long> g_presses{0}, g_faults{0}, g_notices{0};

// UI-thread-only state
View g_view;
bool g_dirty = true;
bool g_shownValid = false;  // false: resend every line (a new panel)
std::string g_testInput;    // the harness's "input" verb (unset: the search box)
bool g_testInputSet = false;
std::string g_status = HintText;
bool g_justOpened = false;  // the panel opened on this tick: the Welcome page when the search box is empty
// what the text boxes should hold (BuildTexts) and what they hold (ApplyTexts)
std::string g_wantRows[layout::MaxRows], g_wantSubs[layout::MaxRows], g_wantLines[layout::MaxLines], g_wantMarks[layout::MaxLines], g_wantPage, g_wantLinesText;
bool g_wantSelected[layout::MaxRows] = {};
int g_wantColour[layout::MaxLines] = {};
std::string g_shownRows[layout::MaxRows][2], g_shownSubs[layout::MaxRows], g_shownLines[layout::MaxLines][layout::ColourCount], g_shownMarks[layout::MaxLines];
std::string g_shownPage, g_shownLinesText, g_shownStatus;
int g_firstMatch = NotFound;  // the selected entry's first line that holds the search words
int g_lineLink[layout::MaxLines];  // per detail line: the link it is (index into the entry's links), or -1
int g_rowCount = 0;
std::vector<int> g_pressQueue;
std::mutex g_pressMutex;
std::mutex g_uiMutex;  // guards the strings the status line of the harness shows
std::string g_queryShown, g_selectedShown, g_statusShown;

template <class F>
auto Fn(uint64_t rva) noexcept -> F {
	return reinterpret_cast<F>(g_base + rva);
}

void LogLine(const char* text) {
	if (g_context != nullptr) {
		char line[320];
		std::snprintf(line, sizeof(line), "wiki: %s", text);
		g_context->LogInfo(line);
	}
}

auto Fmt(const char* format, ...) -> std::string {
	char buf[400];
	va_list args;
	va_start(args, format);
	std::vsnprintf(buf, sizeof(buf), format, args);
	va_end(args);
	return buf;
}

void SetStatus(const std::string& text) {
	g_status = text;
	const std::lock_guard<std::mutex> lock(g_uiMutex);
	g_statusShown = text;
}

// --- text ---------------------------------------------------------------------------------------------------------------------------
// `text` cut to at most `chars` UTF-8 characters, ending in "..." when cut.
auto Cut(const std::string& text, size_t chars) -> std::string {
	if (Utf8Length(text) <= chars) {
		return text;
	}
	return text.substr(0, Utf8Advance(text, 0, chars > 3 ? chars - 3 : 0)) + "...";
}

auto CategoryLabel(int category) -> std::string {
	return category >= 0 && category < static_cast<int>(g_table.categories.size()) ? g_table.categories[static_cast<size_t>(category)].label : std::string("All");
}

// What every text box should hold now, from the view.
void BuildTexts() {
	const auto& m = layout::Hd;
	const size_t rowChars = static_cast<size_t>(m.rowChars);
	const Page page = CurrentPage(g_view);
	const int selectedRow = SelectedRow(g_view);
	g_rowCount = page.count;
	for (int i = 0; i < layout::MaxRows; ++i) {
		const int index = i < page.count ? RowEntry(g_view, i) : NotFound;
		g_wantRows[i].clear();
		g_wantSubs[i].clear();
		g_wantSelected[i] = i == selectedRow;
		if (index == NotFound) {
			continue;
		}
		// the name, then the subtitle in what the name leaves of the row (the two are one line: the subtitle is right-aligned)
		const Entry& e = g_table.entries[static_cast<size_t>(index)];
		g_wantRows[i] = Cut(e.name, rowChars);
		const size_t used = Utf8Length(g_wantRows[i]) + RowGapChars;
		if (!e.subtitle.empty() && used + MinSubtitleChars <= rowChars) {
			g_wantSubs[i] = Cut(e.subtitle, rowChars - used);
		}
	}
	const int total = static_cast<int>(g_view.results.size());
	const std::string scope = g_view.query.empty() ? CategoryLabel(g_view.category) : CategoryLabel(g_view.category) + ", \"" + g_view.query + "\"";
	g_wantPage = total == 0 ? scope + ": nothing found." : Fmt("%s: %d %s. %s", scope.c_str(), total, total == 1 ? "entry" : "entries", PageText(page).c_str());

	int first = 0, count = 0;
	VisibleDetail(g_view, first, count);
	const Entry* selected = g_view.selected != NotFound ? &g_table.entries[static_cast<size_t>(g_view.selected)] : nullptr;
	const int lines = static_cast<int>(g_view.detail.size());
	const int links = selected != nullptr ? static_cast<int>(selected->links.size()) : 0;
	// the lines that hold the search words are marked: every word when some line has them all, else any word (wiki_logic.h FirstMatchingLine)
	const Query query = ParseQuery(g_view.query);
	bool all = false;
	g_firstMatch = selected != nullptr ? FirstMatchingLine(g_view.detail, query, &all) : NotFound;
	for (int i = 0; i < layout::MaxLines; ++i) {
		const int index = first + i;
		const bool on = selected != nullptr && i < count && index < lines;
		const Line* line = on ? &g_view.detail[static_cast<size_t>(index)] : nullptr;
		g_wantLines[i] = on ? line->text : std::string();
		g_wantColour[i] = on ? static_cast<int>(line->colour) : 0;
		g_lineLink[i] = on && index >= lines - links ? index - (lines - links) : -1;  // the entry's last lines are its links (AddLinkLines)
		bool hit = false;
		if (on && g_firstMatch != NotFound && g_lineLink[i] < 0) {
			const std::string folded = Fold(line->text);
			hit = all ? HasAllWords(folded, query) : HasAnyWord(folded, query);
		}
		g_wantMarks[i] = hit ? MarkText : "";
	}
	g_wantLinesText = lines > g_view.visibleLines ? ViewLinesText(g_view) : std::string();
	{
		const std::lock_guard<std::mutex> lock(g_uiMutex);
		g_queryShown = g_view.query;
		g_selectedShown = selected != nullptr ? selected->name : std::string();
	}
}

// Sends what changed to the text boxes. A detail line is one box per colour at the same place (tools/wiki_layout.py): the box of the line's
// colour gets the text, the others are emptied; a row's name is a white and a gold box (the selected row).
void ApplyTexts() {
	void* panel = panel_shared::NativePanel(g_client);
	if (panel == nullptr) {
		return;
	}
	const bool force = !g_shownValid;
	g_shownValid = true;
	const std::string none;
	char name[32];
	for (int i = 0; i < layout::MaxRows; ++i) {
		for (int c = 0; c < 2; ++c) {
			std::snprintf(name, sizeof(name), "RowText%d_%d", i, c);
			panel_shared::SetLine(g_client, panel, name, g_shownRows[i][c], (c == 1) == g_wantSelected[i] ? g_wantRows[i] : none, force);
		}
		std::snprintf(name, sizeof(name), "RowSub%d", i);
		panel_shared::SetLine(g_client, panel, name, g_shownSubs[i], g_wantSubs[i], force);
	}
	for (int i = 0; i < layout::MaxLines; ++i) {
		for (int c = 0; c < layout::ColourCount; ++c) {
			std::snprintf(name, sizeof(name), "DetailText%d_%d", i, c);
			panel_shared::SetLine(g_client, panel, name, g_shownLines[i][c], c == g_wantColour[i] ? g_wantLines[i] : none, force);
		}
		std::snprintf(name, sizeof(name), "LineMark%d", i);
		panel_shared::SetLine(g_client, panel, name, g_shownMarks[i], g_wantMarks[i], force);
	}
	panel_shared::SetLine(g_client, panel, "PageText", g_shownPage, g_wantPage, force);
	panel_shared::SetLine(g_client, panel, "LinesText", g_shownLinesText, g_wantLinesText, force);
	panel_shared::SetLine(g_client, panel, "StatusText", g_shownStatus, panel_logic::Ellipsize(g_status, static_cast<size_t>(layout::Hd.statusChars)), force);
}

// --- widgets ------------------------------------------------------------------------------------------------------------------------
void Show(D2RL::Widgets::WidgetHandle panel, const char* name, bool visible) noexcept {
	D2RL::Widgets::WidgetHandle w = D2RL::Widgets::InvalidHandle;
	if (g_widgets->findWidget(g_context, panel, name, &w) == D2RL::Widgets::Result::Success) {
		(void)g_widgets->setWidgetVisible(g_context, w, visible);
		(void)g_widgets->setWidgetEnabled(g_context, w, visible);
	}
}

void ApplyWidgets() noexcept {
	D2RL::Widgets::WidgetHandle panel = D2RL::Widgets::InvalidHandle;
	if (g_widgets->findPanel(g_context, layout::PanelName, &panel) != D2RL::Widgets::Result::Success || panel == D2RL::Widgets::InvalidHandle) {
		return;
	}
	char name[32];
	for (int i = 0; i < layout::CategorySlots; ++i) {
		std::snprintf(name, sizeof(name), "Btn_cat%d", i);
		Show(panel, name, i <= static_cast<int>(g_table.categories.size()));
	}
	for (int i = 0; i < layout::MaxRows; ++i) {
		std::snprintf(name, sizeof(name), "Btn_row%d", i);
		Show(panel, name, i < g_rowCount);
	}
	for (int i = 0; i < layout::MaxLines; ++i) {
		std::snprintf(name, sizeof(name), "Btn_line%d", i);
		Show(panel, name, g_lineLink[i] >= 0);
	}
	const Page page = CurrentPage(g_view);
	Show(panel, "Btn_prev", page.pages > 1);
	Show(panel, "Btn_next", page.pages > 1);
	const bool scrolls = static_cast<int>(g_view.detail.size()) > g_view.visibleLines;
	Show(panel, "Btn_up", scrolls);
	Show(panel, "Btn_down", scrolls);
	Show(panel, "Btn_back", !g_view.history.Empty());
}

// --- actions ------------------------------------------------------------------------------------------------------------------------
auto ButtonId(const char* name) noexcept -> int {
	for (int i = 0; i < layout::ButtonCount; ++i) {
		if (std::strcmp(layout::ButtonNames[i], name) == 0) {
			return i;
		}
	}
	return -1;
}

// The entry the panel opens on: the page named "Welcome", or an empty text when the table has none.
void ShowWelcome() {
	g_view.history.Clear();
	if (g_welcome != NotFound) {
		(void)internal::Show(g_view, g_table, g_welcome, 0);
	} else {
		g_view.selected = NotFound;
		g_view.detail.clear();
		g_view.scroll = 0;
	}
	g_dirty = true;
}

void OnPress(int button) {
	g_presses.fetch_add(1);
	const char* name = layout::ButtonNames[button];
	const auto startsWith = [&](const char* prefix) { return std::strncmp(name, prefix, std::strlen(prefix)) == 0; };
	uint32_t change = ChangeNone;
	if (startsWith("cat")) {
		const int slot = std::atoi(name + 3);
		if (slot <= static_cast<int>(g_table.categories.size())) {
			change = SetCategory(g_view, g_table, slot == 0 ? AllCategories : slot - 1);
		}
	} else if (startsWith("row")) {
		change = SelectRow(g_view, g_table, std::atoi(name + 3));
		// opened from a search: the text starts a little above the first line that holds the typed words, when that line is not on the first page
		const int match = FirstMatchingLine(g_view.detail, ParseQuery(g_view.query));
		if (change != ChangeNone && match >= g_view.visibleLines) {
			g_view.scroll = ClampScroll(match - MatchLead, static_cast<int>(g_view.detail.size()), g_view.visibleLines);
		}
	} else if (startsWith("line")) {
		const int line = std::atoi(name + 4);
		if (line >= 0 && line < layout::MaxLines && g_lineLink[line] >= 0) {
			change = FollowLink(g_view, g_table, g_lineLink[line]);
			if ((change & LinkNotFound) != 0) {
				SetStatus("That page is not in the wiki.");
			}
		}
	} else if (std::strcmp(name, "prev") == 0) {
		change = PreviousPage(g_view);
	} else if (std::strcmp(name, "next") == 0) {
		change = NextPage(g_view);
	} else if (std::strcmp(name, "up") == 0) {
		change = ScrollByPages(g_view, -1);
	} else if (std::strcmp(name, "down") == 0) {
		change = ScrollByPages(g_view, 1);
	} else if (std::strcmp(name, "back") == 0) {
		change = Back(g_view, g_table);
	} else if (std::strcmp(name, "close") == 0) {
		(void)g_panels->closePanel(g_context, g_panel);
	}
	if (change != ChangeNone) {
		g_dirty = true;
	}
}

void QueueTick() noexcept;

void QueuePress(int button) noexcept {
	{
		const std::lock_guard<std::mutex> lock(g_pressMutex);
		g_pressQueue.push_back(button);
	}
	QueueTick();
}

// UI listener (panel_shared.cpp): a button of the panel was clicked. Every button sends the same message (D2R allows a plugin 64 registered
// panel names; this panel has more buttons than are left), so the button is the one under the pointer when the mouse button went up. The
// work runs on the next UI tick.
void OnButton(int) noexcept {
	int x = 0, y = 0, w = 0, h = 0;
	double ux = 0.0, uy = 0.0;
	if (!panel_shared::LastClick(&x, &y, &w, &h) || !panel_logic::ToPanelUnits(true, w, h, layout::Hd.panelX, layout::Hd.panelY, x, y, &ux, &uy)) {
		return;
	}
	const int button = panel_logic::RectAt(layout::ButtonRects, layout::ButtonCount, ux, uy);
	if (button >= 0) {
		QueuePress(button);
	}
}

auto InputBox(panel_shared::BoxRect* box) noexcept -> bool {
	const auto& m = layout::Hd;
	*box = panel_shared::BoxRect{true, m.panelX, m.panelY, m.inputX, m.inputY, m.inputW, m.inputH};
	return true;
}

// The game window's thread (the UI thread). The wheel over the list turns its pages, over the text it scrolls; anywhere else on the panel
// it does nothing (and not the game's skill switch either); outside the panel it is the game's.
auto WheelInner(int notches, int x, int y, int clientW, int clientH) -> bool {
	const auto& m = layout::Hd;
	const auto on = [&](int bx, int by, int bw, int bh) { return panel_logic::OnBox(true, clientW, clientH, m.panelX, m.panelY, bx, by, bw, bh, x, y, 0); };
	if (!on(0, 0, m.panelW, m.panelH)) {
		return false;
	}
	uint32_t change = ChangeNone;
	if (on(m.listX, m.listY, m.listW, m.listH)) {
		change = TurnPage(g_view, -notches);
	} else if (on(m.detailX, m.detailY, m.detailW, m.detailH)) {
		change = ScrollBy(g_view, -notches * WheelLines);
	}
	if (change != ChangeNone) {
		g_dirty = true;
		QueueTick();
	}
	return true;
}

auto OnWheel(int notches, int x, int y, int clientW, int clientH) noexcept -> bool {
	__try {
		return WheelInner(notches, x, y, clientW, clientH);
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		g_faults.fetch_add(1);
	}
	return true;
}

// Page Up and Page Down scroll the text while the search box does not have the keyboard.
void KeyInner(unsigned key) {
	if (ScrollByPages(g_view, key == VK_PRIOR ? -1 : 1) != ChangeNone) {
		g_dirty = true;
		QueueTick();
	}
}

auto OnKey(unsigned key) noexcept -> bool {
	if (key != VK_PRIOR && key != VK_NEXT) {
		return false;
	}
	__try {
		KeyInner(key);
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		g_faults.fetch_add(1);
	}
	return true;
}

// One line in the game's message log (client only: nothing goes to the server, so it works in a joined game). Not while an NPC talks.
void Notice(const char* text) noexcept {
	if (!g_chatOk || Fn<ClientPlayerFn>(RvaClientPlayer)(Fn<LocalIdFn>(RvaLocalId)()) == nullptr || *reinterpret_cast<const uint32_t*>(g_base + RvaMenuNpcValid) != 0) {
		return;
	}
	uint8_t packet[map_reveal::ChatPacketMax];
	if (map_reveal::BuildChatPacket(packet, sizeof(packet), map_reveal::ColourYellow, text) == 0) {
		return;
	}
	Fn<ChatFn>(RvaClientChat)(packet);
	g_notices.fetch_add(1);
}

void TickInner() {
	D2RL::Panels::PanelInfo info{};
	info.structSize = D2RL::Panels::PanelInfoSize;
	const auto isOpen = [&] {
		return g_panels->getPanelInfo(g_context, g_panel, &info) == D2RL::Panels::Result::Success && info.presentationState == D2RL::Panels::PresentationState::Open;
	};
	const bool hd = panel_shared::IsHd();
	bool open = isOpen();
	if (g_toggleQueued.exchange(false)) {
		if (open) {
			(void)g_panels->closePanel(g_context, g_panel);
		} else if (!g_table.ok) {
			Notice(NoTableText);
		} else if (!hd) {
			Notice(NeedsHdText);
		} else {
			(void)g_panels->togglePanel(g_context, g_panel);
		}
		open = isOpen();
	}
	if (open && !hd) {  // the graphics mode changed under the open panel: there is no classic layout
		(void)g_panels->closePanel(g_context, g_panel);
		Notice(NeedsHdText);
		open = isOpen();
	}
	if (open && !g_client.open.load()) {
		g_shownValid = false;
		g_justOpened = true;
		g_dirty = true;
		SetStatus(HintText);
	}
	g_client.open.store(open);
	if (!open) {
		g_client.boxFocus.store(false);
		g_client.boxClicked.store(false);
		const std::lock_guard<std::mutex> lock(g_pressMutex);
		g_pressQueue.clear();  // a press never waits for the next opening
		return;
	}
	std::vector<int> presses;
	{
		const std::lock_guard<std::mutex> lock(g_pressMutex);
		presses.swap(g_pressQueue);
	}
	for (int b : presses) {
		OnPress(b);
	}
	panel_shared::HookGameWindow();
	g_client.boxFocus.store(panel_shared::BoxFocused(g_client));
	char input[64] = "";
	if (g_testInputSet) {
		std::snprintf(input, sizeof(input), "%s", g_testInput.c_str());
	} else {
		D2RL::Widgets::WidgetHandle panel = D2RL::Widgets::InvalidHandle, box = D2RL::Widgets::InvalidHandle;
		uint32_t need = 0;
		if (g_widgets->findPanel(g_context, layout::PanelName, &panel) == D2RL::Widgets::Result::Success && panel != D2RL::Widgets::InvalidHandle &&
		    g_widgets->findWidget(g_context, panel, layout::InputName, &box) == D2RL::Widgets::Result::Success) {
			(void)g_widgets->getInputText(g_context, box, input, sizeof(input), &need);
		}
	}
	if (SetQuery(g_view, g_table, input) != ChangeNone) {
		g_dirty = true;
	}
	if (g_justOpened) {  // nothing typed: the Welcome page; a search left in the box: the list and the entry as they were
		g_justOpened = false;
		if (g_view.query.empty()) {
			ShowWelcome();
		}
	}
	if (g_dirty) {
		g_dirty = false;
		BuildTexts();
		ApplyWidgets();
	}
	ApplyTexts();
}

void __cdecl TickOnUi(const D2RL::PluginContext*, void*) noexcept {
	g_tickQueued.store(false);
	__try {
		TickInner();
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		g_faults.fetch_add(1);
	}
}

void QueueTick() noexcept {
	if (!g_tickQueued.exchange(true) && g_threads->runOnUiThread(g_context, &TickOnUi, nullptr) != D2RL::Threads::Result::Success) {
		g_tickQueued.store(false);
	}
}

DWORD WINAPI TimerThread(LPVOID) {
	for (;;) {
		Sleep(g_client.open.load() || g_toggleQueued.load() ? 100 : 400);
		if (g_client.open.load() || g_toggleQueued.load()) {
			QueueTick();
		}
	}
}

auto __cdecl OnAction(const D2RL::PluginContext*, const D2RL::Input::ActionEvent* event, void*) noexcept -> D2RL::Input::ActionResult {
	if (event == nullptr || !D2RL::Input::HasActionEventField(event, D2RL::Input::ActionEventRequiredSize) || event->kind != D2RL::Input::ActionEventKind::Pressed) {
		return D2RL::Input::ActionResult::Ignored;
	}
	g_toggleQueued.store(true);
	QueueTick();
	return D2RL::Input::ActionResult::Handled;
}

// --- load -----------------------------------------------------------------------------------------------------------------------------
// An entry's links become its last lines: an empty line, "See also", then one line per link whose page exists, each cut to one line, so the
// links scroll with the text and the n-th of them is the entry's n-th link (BuildTexts). Links to pages the table does not have are dropped.
auto AddLinkLines(Table& table, size_t chars) -> int {
	int dropped = 0;
	for (Entry& e : table.entries) {
		std::vector<std::string> kept;
		for (std::string& link : e.links) {
			if (FindEntry(table, link) != NotFound) {
				kept.push_back(std::move(link));
			} else {
				++dropped;
			}
		}
		e.links = std::move(kept);
	}
	for (Entry& e : table.entries) {
		if (e.links.empty()) {
			continue;
		}
		e.lines.push_back(Line{Colour::White, std::string()});
		e.lines.push_back(Line{Colour::Gold, "See also"});
		for (const std::string& link : e.links) {
			e.lines.push_back(Line{Colour::White, Cut(link, chars)});
		}
	}
	return dropped;
}

auto LoadTable(const char* selfPath) -> std::string {
	const ULONGLONG start = GetTickCount64();
	std::string text;
	switch (panel_shared::ReadModFile(g_context, selfPath, L"data\\mxl2012-wiki\\wiki.tsv", MaxTableBytes, &text)) {
	case panel_shared::FileResult::Ok:
		break;
	case panel_shared::FileResult::NoPath:
		return "the plugin path could not be read";
	case panel_shared::FileResult::NotFound:
		return "no content table in the mod (data/mxl2012-wiki/wiki.tsv)";
	case panel_shared::FileResult::BadSize:
		return "the content table has a bad size";
	case panel_shared::FileResult::ReadFailed:
		return "the content table could not be read";
	}
	g_table = ParseTable(text);
	if (!g_table.ok) {
		return g_table.error.empty() ? std::string("the content table is not usable") : g_table.error;
	}
	const int dropped = AddLinkLines(g_table, static_cast<size_t>(layout::Hd.lineChars));
	g_welcome = FindEntry(g_table, WelcomeName);
	g_loadMs = static_cast<long>(GetTickCount64() - start);
	if (dropped > 0 || !g_table.problem.empty()) {
		LogLine(Fmt("content table: %d links without a page dropped; first problem: %s", dropped, g_table.problem.empty() ? "none" : g_table.problem.c_str()).c_str());
	}
	return "";
}

auto JsonEscaped(const std::string& text) -> std::string {
	std::string out;
	for (const char ch : text) {
		if (ch == '"' || ch == '\\') {
			out += '\\';
		}
		if (static_cast<unsigned char>(ch) >= 0x20) {
			out += ch;
		}
	}
	return out;
}

// The layout with the table's category labels in the buttons (tools/wiki_layout.py: `@C<n>@`, slot 0 is "All").
auto BuildLayout() -> std::string {
	std::string json;
	for (const char* part : layout::LayoutHdParts) {
		json += part;
	}
	for (int i = 0; i < layout::CategorySlots; ++i) {
		const std::string mark = Fmt("@C%d@", i);
		const size_t at = json.find(mark);
		if (at != std::string::npos) {
			json.replace(at, mark.size(), JsonEscaped(i == 0 ? std::string("All") : i <= static_cast<int>(g_table.categories.size()) ? g_table.categories[static_cast<size_t>(i - 1)].label : std::string()));
		}
	}
	return json;
}

}  // namespace

auto InstallWiki(const D2RL::PluginContext* context, const char* selfPath, char* report, size_t reportSize) noexcept -> bool {
	g_context = context;
	g_base = context->exeBase;
	std::fill(std::begin(g_lineLink), std::end(g_lineLink), -1);
	g_chatOk = std::memcmp(reinterpret_cast<const void*>(g_base + RvaClientChat), ChatEntry, sizeof(ChatEntry)) == 0;
	if (context->QueryService(&g_threads) != D2RL::ServiceQueryResult::Success || !D2RL::HasThreadServiceField(g_threads, D2RL::ThreadServiceRequiredSize) ||
	    context->QueryService(&g_widgets) != D2RL::ServiceQueryResult::Success || !D2RL::HasWidgetServiceField(g_widgets, D2RL::WidgetServiceRequiredSize) ||
	    context->QueryService(&g_panels) != D2RL::ServiceQueryResult::Success || !D2RL::HasPanelServiceField(g_panels, D2RL::PanelServiceRequiredSize) ||
	    context->QueryService(&g_input) != D2RL::ServiceQueryResult::Success || !D2RL::HasInputServiceField(g_input, D2RL::InputServiceRequiredSize) ||
	    !panel_shared::Init(context)) {
		std::snprintf(report, reportSize, "wiki off: a loader service is unavailable");
		return false;
	}
	std::string tableError;
	try {
		tableError = LoadTable(selfPath);
		if (tableError.empty()) {
			(void)Init(g_view, g_table, layout::Hd.rows, layout::Hd.lineChars, layout::Hd.lines);
		}
		g_layoutJson = BuildLayout();
	} catch (...) {
		tableError = "out of memory reading the content table";
		g_table.ok = false;
	}
	(void)panel_shared::RegisterLayout(context, "Wikihd", g_layoutJson.c_str(), g_layoutJson.size());
	D2RL::Panels::PanelRegistration panel{};
	panel.structSize = D2RL::Panels::PanelRegistrationSize;
	panel.flags = D2RL::Panels::PanelFlags::CloseOnEscape;
	panel.localId = layout::PanelLocalId;
	if (g_panels->registerPanel(context, &panel, &g_panel) != D2RL::Panels::Result::Success) {
		std::snprintf(report, reportSize, "wiki off: the panel could not be registered");
		return false;
	}
	if (panel_shared::RegisterButtons(context, "WikiB_", 1) >= 0) {
		std::snprintf(report, reportSize, "wiki off: the buttons' panel name could not be registered");
		return false;
	}
	const D2RL::Input::ActionRegistration reg{
	    .structSize = D2RL::Input::ActionRegistrationSize,
	    .flags = 0,
	    .logicalId = "mxl_wiki",
	    .displayName = "Wiki",
	    .category = "D2R-XL 2012",
	    .defaultPrimary = {.key = D2RL::Input::Key::J, .modifier = D2RL::Input::Modifier::None},
	    .defaultSecondary = {.key = D2RL::Input::Key::None, .modifier = D2RL::Input::Modifier::None},
	    .callback = &OnAction,
	    .userData = nullptr,
	};
	const auto rc = g_input->registerAction(context, &reg, &g_action);
	if (rc != D2RL::Input::Result::Success) {
		std::snprintf(report, reportSize, "wiki off: the Controls action could not be registered (result %u)", static_cast<unsigned>(rc));
		return false;
	}
	g_client.panelName = layout::PanelName;
	g_client.inputName = layout::InputName;
	g_client.buttonPrefix = "mxl2012-core/WikiB_";
	g_client.buttonCount = 1;
	g_client.onPress = &OnButton;
	g_client.inputBox = &InputBox;
	g_client.onWheel = &OnWheel;
	g_client.onKey = &OnKey;
	if (!panel_shared::AddClient(&g_client)) {
		std::snprintf(report, reportSize, "wiki off: the panel list is full");
		return false;
	}
	if (HANDLE t = CreateThread(nullptr, 0, TimerThread, nullptr, 0, nullptr)) {
		CloseHandle(t);
	}
	g_on = true;
	if (!tableError.empty()) {
		std::snprintf(report, reportSize, "wiki on, but the panel stays closed: %s", tableError.c_str());
		return true;
	}
	std::snprintf(report, reportSize, "wiki on: Controls action mxl_wiki (default J), content table ok (%zu entries, %zu categories, read in %ld ms), welcome page %s, notices %s",
	              g_table.entries.size(), g_table.categories.size(), g_loadMs, g_welcome != NotFound ? "found" : "missing", g_chatOk ? "on" : "off (entry bytes differ)");
	return true;
}

void WikiStatus(char* out, size_t size) noexcept {
	std::string status, query, selected;
	{
		const std::lock_guard<std::mutex> lock(g_uiMutex);
		status = g_statusShown;
		query = g_queryShown;
		selected = g_selectedShown;
	}
	const Page page = CurrentPage(g_view);
	int links = 0, firstLink = -1;
	for (int i = 0; i < layout::MaxLines; ++i) {
		if (g_lineLink[i] >= 0) {
			++links;
			firstLink = firstLink < 0 ? i : firstLink;
		}
	}
	std::snprintf(out, size,
	              "on=%d table=%d entries=%zu open=%d hd=%d cat=%d results=%zu page=%d pages=%d rows=%d sel=%d scroll=%d lines=%zu links=%d firstlink=%d match=%d history=%d presses=%ld texts=%ld textfails=%ld "
	              "boxfocus=%d boxclicked=%d keysheld=%ld keystaken=%ld wheels=%ld notices=%ld faults=%ld loadms=%ld query=\"%s\" selected=\"%s\" status=\"%.60s\"",
	              g_on ? 1 : 0, g_table.ok ? 1 : 0, g_table.entries.size(), g_client.open.load() ? 1 : 0, panel_shared::IsHd() ? 1 : 0, g_view.category, g_view.results.size(), page.page,
	              page.pages, g_rowCount, g_view.selected, g_view.scroll, g_view.detail.size(), links, firstLink, g_firstMatch, g_view.history.count, g_presses.load(), g_client.textsSet.load(),
	              g_client.textFails.load(), g_client.boxFocus.load() ? 1 : 0, g_client.boxClicked.load() ? 1 : 0, g_client.keysHeld.load(), g_client.keysTaken.load(),
	              g_client.wheels.load(), g_notices.load(), g_faults.load(), g_loadMs, query.c_str(), selected.c_str(), status.c_str());
}

namespace {

// The harness's `raw`: one text box set as given, for looking at what D2R's text boxes can show. UI thread.
struct RawText {
	char widget[40];
	std::string text;
};
RawText g_raw;

void RawInner() {
	void* panel = panel_shared::NativePanel(g_client);
	if (panel != nullptr) {
		std::string shown;
		panel_shared::SetLine(g_client, panel, g_raw.widget, shown, g_raw.text, true);
	}
}

void __cdecl RawOnUi(const D2RL::PluginContext*, void*) noexcept {
	__try {
		RawInner();
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		g_faults.fetch_add(1);
	}
}

}  // namespace

auto WikiHarness(const char* verb, const char* argument) noexcept -> bool {
	if (!g_on || verb == nullptr) {
		return false;
	}
	if (std::strcmp(verb, "open") == 0 || std::strcmp(verb, "close") == 0) {
		const bool wantOpen = verb[0] == 'o';
		if (wantOpen != g_client.open.load()) {
			g_toggleQueued.store(true);
			QueueTick();
		}
		return true;
	}
	if (std::strcmp(verb, "input") == 0) {
		g_testInput = argument != nullptr ? argument : "";
		g_testInputSet = true;
		QueueTick();
		return true;
	}
	if (std::strcmp(verb, "box") == 0) {  // back to the search box's own text (`input` overrides it)
		g_testInputSet = false;
		QueueTick();
		return true;
	}
	if (std::strcmp(verb, "raw") == 0 && argument != nullptr) {
		const char* space = std::strchr(argument, ' ');
		if (space == nullptr || static_cast<size_t>(space - argument) >= sizeof(g_raw.widget)) {
			return false;
		}
		std::memcpy(g_raw.widget, argument, static_cast<size_t>(space - argument));
		g_raw.widget[space - argument] = '\0';
		g_raw.text.clear();
		for (const char* p = space + 1; *p != '\0'; ++p) {
			if (p[0] == '\\' && p[1] == 'n') {
				g_raw.text += '\n';
				++p;
			} else if (*p == '^') {
				g_raw.text += "\xC3\xBF" "c";
			} else {
				g_raw.text += *p;
			}
		}
		return g_threads->runOnUiThread(g_context, &RawOnUi, nullptr) == D2RL::Threads::Result::Success;
	}
	if (std::strcmp(verb, "press") == 0 && argument != nullptr) {
		const int b = ButtonId(argument);
		if (b < 0) {
			return false;
		}
		QueuePress(b);
		return true;
	}
	return false;
}

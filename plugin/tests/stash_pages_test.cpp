// Standalone test of stashpage2's pure part (stash_pages_logic.h) and its generated layouts (mxl_stash_page.h); not part of the
// plugin DLL.
#include "../src/mxl_stash_page.h"
#include "../src/stash_pages_logic.h"

#include <cstdio>
#include <cstring>

namespace {
int failures = 0;
void Check(bool ok, const char* what) {
	if (!ok) {
		++failures;
		std::printf("FAIL: %s\n", what);
	}
}
}  // namespace

int main() {
	using namespace stash_pages;
	// the tab bar's message (onSwitchTabMessage "BankPanelMessage:SelectTab", the tab index as text)
	Check(SelectedTab("BankPanelMessage", "SelectTab", "0") == 0, "Personal");
	Check(SelectedTab("BankPanelMessage", "SelectTab", "1") == 1, "Shared");
	Check(SelectedTab("BankPanelMessage", "SelectTab", "4") == 4, "Runes");
	Check(SelectedTab("BankPanelMessage", "SelectTab", "") == -1 && SelectedTab("BankPanelMessage", "SelectTab", nullptr) == -1, "no index");
	Check(SelectedTab("BankPanelMessage", "SelectTab", "x1") == -1 && SelectedTab("BankPanelMessage", "SelectTab", "-1") == -1, "not a number");
	Check(SelectedTab("BankPanelMessage", "SharedStashRight", "") == -1, "the shared page arrows are no tab switch");
	Check(SelectedTab("PanelManager", "SelectTab", "0") == -1 && SelectedTab(nullptr, "SelectTab", "0") == -1, "another target");
	Check(SelectedTab("BankPanelMessage", "SelectTab", "99999999999") == -1, "no overflow");

	// the stock stash opening
	Check(StockStashOpens("OpenPanel", "BankExpansionLayout", mxl_stash_page::StockPanel), "OpenPanel");
	Check(StockStashOpens("LoadPanel", "BankExpansionLayout", mxl_stash_page::StockPanel), "LoadPanel");
	Check(!StockStashOpens("ClosePanel", "BankExpansionLayout", mxl_stash_page::StockPanel), "ClosePanel");
	Check(!StockStashOpens("OpenPanel", "mxl2012-core/StashPage2", mxl_stash_page::StockPanel), "our own panel");
	Check(!StockStashOpens(nullptr, nullptr, mxl_stash_page::StockPanel), "no text");

	// the arrows' own message (bug #543)
	const char* const page = mxl_stash_page::PanelName;
	Check(std::strcmp(page, "mxl2012-core/StashPage2") == 0, "the page panel's name");
	Check(ShowRequest("PanelManager", "OpenPanel", page, page) == 2, "stock arrows: page 2");
	Check(ShowRequest("PanelManager", "ClosePanel", page, page) == 1, "page 2 arrows: page 1");
	Check(ShowRequest("PanelManager", "TogglePanel", page, page) == -1 && ShowRequest("PanelManager", "OpenPanel", "BankExpansionLayout", page) == -1,
	      "another panel message");
	Check(ShowRequest("BankPanelMessage", "OpenPanel", page, page) == -1, "another target");
	Check(ShowRequest(nullptr, nullptr, nullptr, page) == -1, "null");

	// what brings page 1 back
	Check(LeavesPage2("BankPanelMessage", "SelectTab", "", mxl_stash_page::StockPanel), "a tab click (empty text)");
	Check(LeavesPage2("BankPanelMessage", "SelectTab", "1", mxl_stash_page::StockPanel), "a tab click (with index)");
	Check(LeavesPage2("BankPanelMessage", "Close", "", mxl_stash_page::StockPanel), "the stock X");
	Check(LeavesPage2("PanelManager", "ClosePanel", "BankExpansionLayout", mxl_stash_page::StockPanel), "the stash closed");
	Check(LeavesPage2("PanelManager", "TogglePanel", "BankExpansionLayout", mxl_stash_page::StockPanel), "the stash toggled");
	Check(!LeavesPage2("BankPanelMessage", "SharedStashRight", "", mxl_stash_page::StockPanel), "shared page arrows");
	Check(!LeavesPage2("BankPanelMessage", "Withdraw", "", mxl_stash_page::StockPanel), "gold");
	Check(!LeavesPage2("PanelManager", "ClosePanel", "PlayerInventoryExpansionLayout", mxl_stash_page::StockPanel), "another panel");
	Check(!LeavesPage2(nullptr, nullptr, nullptr, mxl_stash_page::StockPanel), "null");

	// the strip: Personal tab with the page only
	Check(StripVisible(true, 0), "page and Personal");
	Check(!StripVisible(true, 1) && !StripVisible(true, 2), "other tabs");
	Check(!StripVisible(false, 0), "no page: hidden");

	// cells
	Check(PackCell(-1, 3) == -1 && PackCell(2, -1) == -1, "automatic");
	Check(CellX(PackCell(9, 7)) == 9 && CellY(PackCell(9, 7)) == 7, "round trip");
	Check(CellX(-1) == -1 && CellY(-1) == -1, "automatic unpacked");
	Check(CellX(PackCell(0, 0)) == 0 && CellY(PackCell(0, 0)) == 0, "the corner cell");

	char code[5];
	Check(PaddedCode("r05", code) && std::memcmp(code, "r05 ", 4) == 0, "three letters padded");
	Check(PaddedCode("cm1a", code) && std::memcmp(code, "cm1a", 4) == 0, "four letters");
	Check(!PaddedCode("", code) && !PaddedCode(nullptr, code) && !PaddedCode("toolong", code), "bad codes");

	// the generated layouts: the page is the stock stash's 10 x 10, names as the plugin and the layout tools use them
	Check(mxl_stash_page::Width == 10 && mxl_stash_page::Height == 10, "10 x 10");
	Check(std::strstr(mxl_stash_page::LayoutHd, "\"name\": \"mxl2012-core/StashPage2\"") != nullptr, "HD root name = <plugin id>/<local id>");
	Check(std::strstr(mxl_stash_page::LayoutClassic, "\"name\": \"mxl2012-core/StashPage2\"") != nullptr, "classic root name");
	Check(std::strstr(mxl_stash_page::LayoutHd, mxl_stash_page::GridName) != nullptr && std::strstr(mxl_stash_page::LayoutClassic, mxl_stash_page::GridName) != nullptr,
	      "both layouts have the bound grid");
	Check(std::strstr(mxl_stash_page::LayoutHd, "\"@") == nullptr && std::strstr(mxl_stash_page::LayoutClassic, "\"@") == nullptr, "no string keys (bug #30)");
	// an overlay on the open stock stash: no click catcher, background or X of its own; the arrows close the page panel (bug #543)
	const char* const layouts[] = {mxl_stash_page::LayoutHd, mxl_stash_page::LayoutClassic};
	for (const char* lay : layouts) {
		Check(std::strstr(lay, "PanelManager:ClosePanel:mxl2012-core/StashPage2") != nullptr, "page 2's arrows close the page panel");
		Check(std::strstr(lay, "ClickCatcherWidget") == nullptr && std::strstr(lay, "\"background\"") == nullptr && std::strstr(lay, "\"close\"") == nullptr,
		      "nothing over the stock tabs, gold or X");
		Check(std::strstr(lay, "OpenPanel") == nullptr && std::strstr(lay, "BankExpansionLayout") == nullptr, "no other PanelManager message");
	}
	if (failures == 0) {
		std::printf("stash_pages: all checks passed\n");
	}
	return failures == 0 ? 0 : 1;
}

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
	Check(std::strstr(mxl_stash_page::LayoutHd, "PanelManager:ClosePanel:BankExpansionLayout") != nullptr, "X closes the stock stash");
	if (failures == 0) {
		std::printf("stash_pages: all checks passed\n");
	}
	return failures == 0 ? 0 : 1;
}

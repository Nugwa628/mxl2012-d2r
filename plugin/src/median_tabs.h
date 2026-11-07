// The stash's MEDIAN and ORBS tabs and the Materials tab's Vanilla / Median selector (median_tabs.cpp, tools/median_tabs.py).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Part medtab: tabs 5 and 6 run as the Runes page with their own slot groups shown, the Materials selector shows one of its two
// slot groups. `tabsOn` false (off word medtab): the same hooks, tabs 5 and 6 hidden in every game (a 7-tab layout needs the
// hooks not to crash). On any byte difference nothing is written. The report gets one entry.
auto InstallMedianTabs(const D2RL::PluginContext* context, bool tabsOn, char* report, size_t reportSize) noexcept -> bool;
void MedianTabsStatus(char* out, size_t outSize) noexcept;
// True while the last tab update's panel had the 7-tab layout in a game that shows tabs 6 and 7 (part tabflash).
auto MedianTabsLive() noexcept -> bool;
// The stash panel's real tab (its tab bar +0x16c4, not D2R's getter, which shows tabs 6 and 7 as Runes); -1 without a tab bar.
auto MedianTabsRealTab(void* panel) noexcept -> int;

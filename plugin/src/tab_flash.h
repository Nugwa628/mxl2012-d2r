// The stash tab flash after a Ctrl-click deposit (tab_flash.cpp, bug #550, lane tabhl).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Hooks the page kind lookup 0x15ef70 and the tab flash 0x23bb50, and gives the flash 7 tabs (tab_flash_logic.h). The report
// gets one entry. On any byte difference nothing is written.
auto InstallTabFlash(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
// Flashes run, flashes skipped on the shown tab, the last flashed tab and the deposits given the MEDIAN / ORBS kind.
void TabFlashStatus(char* out, size_t outSize) noexcept;

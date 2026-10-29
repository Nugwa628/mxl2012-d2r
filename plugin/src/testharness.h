// Test harness (testharness.cpp): input for unattended test runs, so the real mouse, keyboard and focus stay free.
// Off unless mxl2012-testharness.txt exists next to the plugin DLL (or env MXL_TESTHARNESS is set). Never active in normal play.
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>
#include <cstdint>

auto InstallTestHarness(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
void StopTestHarness() noexcept;
void HarnessEcho(const char* line) noexcept;  // appends a console line to mxl2012-testharness-console.txt while the harness is on

// Gameplay commands (harness_cmds.cpp): "h <verb> ..." lines of the console mailbox. Server-side verbs run on the game
// thread inside HarnessGameFrame, which goblins.cpp calls after the server frame 0x406550.
void HarnessCmdsInit(uint64_t exeBase) noexcept;
void HarnessCmdsContext(const D2RL::PluginContext* context) noexcept;  // text verb: data table and localization services
auto HarnessCommand(const char* line) noexcept -> int;  // UI thread; 1 ok, 0 failed, -2 crashed, -3 timed out
void HarnessGameFrame(void* game) noexcept;             // game thread; cheap no-op while the harness is off

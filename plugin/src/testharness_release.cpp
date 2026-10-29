// Release builds (cmake -DMXL_RELEASE=ON, tools/package_release.py): the test harness and its gameplay commands are not
// compiled in (testharness.cpp, harness_cmds.cpp). These are the functions the rest of the plugin calls; each does nothing,
// so mxl2012-testharness.txt next to the DLL has no effect.
#include "testharness.h"

auto InstallTestHarness(const D2RL::PluginContext*, char* report, size_t reportSize) noexcept -> bool {
	if (report != nullptr && reportSize > 0) {
		report[0] = '\0';
	}
	return false;
}
void StopTestHarness() noexcept {}
void HarnessEcho(const char*) noexcept {}
void HarnessCmdsInit(uint64_t) noexcept {}
void HarnessCmdsContext(const D2RL::PluginContext*) noexcept {}
auto HarnessCommand(const char*) noexcept -> int {
	return 0;
}
void HarnessGameFrame(void*) noexcept {}

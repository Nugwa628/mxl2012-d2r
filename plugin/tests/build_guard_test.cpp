// Standalone test of the game build decision (build_guard_logic.h; not part of the plugin DLL).
#include "../src/build_guard_logic.h"

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
auto HasDigitRun(const char* s, int run) -> bool {
	int n = 0;
	for (; *s != '\0'; ++s) {
		n = (*s >= '0' && *s <= '9') ? n + 1 : 0;
		if (n >= run) {
			return true;
		}
	}
	return false;
}
}  // namespace

int main() {
	using namespace build_guard;
	static_assert(Matches(ExpectedImage, "93847"), "the dumped image matches at compile time");

	Check(Matches(0x6ab3782cU, "93847"), "build 93847, dumped image: hooks go in");
	Check(Matches(0x6ab3782cU, nullptr), "dumped image, no build name from D2RLoader: hooks go in");
	Check(Matches(0x6ab3782cU, ""), "dumped image, empty build name: hooks go in");
	Check(!Matches(0x6ab3782dU, "93847"), "build name 93847 but another D2R.exe: nothing installed");
	Check(!Matches(0x6b000000U, "94100"), "another build: nothing installed");
	Check(!Matches(0x6ab3782cU, "94100"), "dumped image but D2RLoader names another build: nothing installed");
	Check(!Matches(0x6ab3782cU, "938470"), "longer build name: nothing installed");
	Check(!Matches(0x6ab3782cU, "9384"), "shorter build name: nothing installed");
	Check(!Matches(0, nullptr), "no image (exe base 0): nothing installed");

	// `wrongbuild` (docs/plugin-plan.md 1.2): the player's text names "Diablo II: Resurrected 3.3", never a build number or
	// the image stamp; those are in the log line only.
	char text[256];
	Message(text, sizeof(text), "0.1.0");
	Check(std::strcmp(text, "D2R-XL 2012 0.1.0 needs Diablo II: Resurrected 3.3; this game is a different version. The mod's engine changes are off.") == 0,
	      "screen text");
	Check(std::strstr(text, "3.3") != nullptr, "screen text has 3.3");
	Check(!HasDigitRun(text, 5), "screen text has no build number (no run of 5 digits)");
	Check(std::strstr(text, "0x") == nullptr && std::strstr(text, "6ab3782c") == nullptr, "screen text has no image stamp");
	Check(std::strstr(text, ExpectedBuild) == nullptr, "screen text has no 93847");

	char log[256];
	LogDetail(log, sizeof(log), 0x6b000000U, "94100");
	Check(std::strstr(log, "image 0x6b000000, buildName 94100 (another build)") != nullptr, "log line: found image and build");
	Check(std::strstr(log, "expected image 0x6ab3782c, buildName 93847") != nullptr, "log line: expected image and build");
	LogDetail(log, sizeof(log), 0x6b000000U, nullptr);
	Check(std::strstr(log, "buildName (none) (no build name)") != nullptr, "log line without a build name");
	LogDetail(log, sizeof(log), 0x6ab3782dU, "93847");
	Check(std::strstr(log, "same build name, another D2R.exe") != nullptr, "log line: same number, other exe");

	char small[16];
	Message(small, sizeof(small), "0.1.0");
	Check(std::strlen(small) == sizeof(small) - 1, "message is cut to the buffer");
	Message(nullptr, 0, "0.1.0");  // must not write
	LogDetail(nullptr, 0, 0, "1");  // must not write

	if (failures == 0) {
		std::printf("build guard tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}

// Which D2R the plugin runs on (mxl2012_core.cpp; unit test plugin/tests/build_guard_test.cpp). Every address, hook and patch of
// the plugin belongs to one image: D2R 3.3.0 build 93847, PE timestamp 0x6ab3782c. On any
// other image the plugin installs nothing and says so: in the log, on the screen (D2RLoader's overlay) and in the `mxl2012`
// command. What a player reads names "Diablo II: Resurrected 3.3", never the build number or stamp (docs/plugin-plan.md 1.2).
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace build_guard {

constexpr uint32_t ExpectedImage = 0x6ab3782cU;  // TimeDateStamp of the dumped D2R.exe
constexpr const char* ExpectedBuild = "93847";  // D2RLoader's buildName for that image

// Hooks may go in only on the dumped image. The build name D2RLoader reports (null or "" when it has none) must agree too.
constexpr auto Matches(uint32_t imageStamp, const char* buildName) noexcept -> bool {
	if (imageStamp != ExpectedImage) {
		return false;
	}
	if (buildName == nullptr || buildName[0] == '\0') {
		return true;
	}
	const char* want = ExpectedBuild;
	for (; *buildName != '\0' && *want != '\0'; ++buildName, ++want) {
		if (*buildName != *want) {
			return false;
		}
	}
	return *buildName == '\0' && *want == '\0';
}

// The game version as players know it: the only requirement a player reads (screen notice, `mxl2012`, PluginInfo).
constexpr const char* PlayerVersion = "Diablo II: Resurrected 3.3";

// The screen / console text on another image:
// "D2R-XL 2012 0.1.0 needs Diablo II: Resurrected 3.3; this game is a different version. The mod's engine changes are off."
inline void Message(char* out, size_t outSize, const char* pluginVersion) noexcept {
	if (out == nullptr || outSize == 0) {
		return;
	}
	std::snprintf(out, outSize, "D2R-XL 2012 %s needs %s; this game is a different version. The mod's engine changes are off.",
	              pluginVersion != nullptr ? pluginVersion : "?", PlayerVersion);
}

// The log line for support (players send logs): which image and build name were found, which are expected.
inline void LogDetail(char* out, size_t outSize, uint32_t imageStamp, const char* buildName) noexcept {
	if (out == nullptr || outSize == 0) {
		return;
	}
	const bool named = buildName != nullptr && buildName[0] != '\0';
	const char* kind = !named ? "no build name"
	                   : std::strcmp(buildName, ExpectedBuild) == 0 ? "same build name, another D2R.exe (patched or another region)"
	                                                                : "another build";
	std::snprintf(out, outSize, "mxl2012-core: wrong game: image 0x%08x, buildName %.40s (%s); expected image 0x%08x, buildName %s", imageStamp,
	              named ? buildName : "(none)", kind, ExpectedImage, ExpectedBuild);
}

}  // namespace build_guard

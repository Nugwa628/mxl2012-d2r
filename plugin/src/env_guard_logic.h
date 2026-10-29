// Which mxl2012-core runs, from where, for which mod (docs/bugs.md #53; mxl2012_core.cpp, unit test plugin/tests/env_guard_test.cpp).
// D2RLoader loads the plugins of the mod it starts (<game>\mods\<mod>\d2rloader\plugins) and then the game-wide ones
// (<game>\d2rloader\plugins). An old mxl2012-core.dll in the game-wide folder, or D2RLoader's default_mod naming another mod
// folder, made the game run another build than the one the downloader installed. No Windows headers here.
#pragma once

#include <cstddef>
#include <cstdio>
#include <cstring>

namespace env_guard {

constexpr const char* OurMod = "mxl2012";
constexpr const char* OurPluginId = "mxl2012-core";  // PluginInfo::id of every mxl2012-core build

inline auto Lower(char c) noexcept -> char {
	return (c >= 'A' && c <= 'Z') ? static_cast<char>(c - 'A' + 'a') : (c == '/' ? '\\' : c);
}

inline auto EqualNoCase(const char* a, const char* b) noexcept -> bool {
	if (a == nullptr || b == nullptr) {
		return false;
	}
	for (; *a != '\0' && *b != '\0'; ++a, ++b) {
		if (Lower(*a) != Lower(*b)) {
			return false;
		}
	}
	return *a == '\0' && *b == '\0';
}

// True when `path` lies inside `<gameDir>\mods\<mod>\` (any case, '\' or '/', a trailing separator on gameDir is fine).
inline auto UnderModFolder(const char* path, const char* gameDir, const char* mod) noexcept -> bool {
	if (path == nullptr || gameDir == nullptr || mod == nullptr || gameDir[0] == '\0') {
		return false;
	}
	char want[600];
	size_t g = std::strlen(gameDir);
	while (g > 0 && (gameDir[g - 1] == '\\' || gameDir[g - 1] == '/')) {
		--g;
	}
	const int n = std::snprintf(want, sizeof(want), "%.*s\\mods\\%s\\", static_cast<int>(g), gameDir, mod);
	if (n <= 0 || static_cast<size_t>(n) >= sizeof(want)) {
		return false;
	}
	for (size_t i = 0; want[i] != '\0'; ++i) {
		if (path[i] == '\0' || Lower(path[i]) != Lower(want[i])) {
			return false;
		}
	}
	return std::strstr(path, "..") == nullptr;
}

// Another loaded module that is mxl2012-core too: its file is mxl2012-core*.dll, or its PluginInfo id is "mxl2012-core".
inline auto IsOurModule(const char* fileName, const char* pluginId) noexcept -> bool {
	if (pluginId != nullptr && std::strcmp(pluginId, OurPluginId) == 0) {
		return true;
	}
	if (fileName == nullptr) {
		return false;
	}
	static constexpr char Prefix[] = "mxl2012-core";
	for (size_t i = 0; Prefix[i] != '\0'; ++i) {
		if (Lower(fileName[i]) != Prefix[i]) {
			return false;
		}
	}
	const size_t len = std::strlen(fileName);
	return len > 4 && EqualNoCase(fileName + len - 4, ".dll");
}

struct Verdict {
	bool outsideMod = false;  // this DLL is not under <game>\mods\mxl2012\ (e.g. the game-wide plugins folder)
	bool otherMod = false;    // D2RLoader runs another mod than D2R-XL 2012
	bool duplicate = false;   // a second mxl2012-core is loaded in the process
	[[nodiscard]] auto Ok() const noexcept -> bool { return !outsideMod && !otherMod && !duplicate; }
};

// `selfPath`: this DLL; `gameDir`: the folder of D2R.exe; `activeMod`: D2RLoader's active mod (null or "" when unknown);
// `otherInstances`: other mxl2012-core modules found. An unknown path or mod gives no warning (nothing to compare).
inline auto Check(const char* selfPath, const char* gameDir, const char* activeMod, int otherInstances) noexcept -> Verdict {
	Verdict v;
	v.outsideMod = selfPath != nullptr && selfPath[0] != '\0' && gameDir != nullptr && gameDir[0] != '\0' &&
	               !UnderModFolder(selfPath, gameDir, OurMod);
	v.otherMod = activeMod != nullptr && activeMod[0] != '\0' && !EqualNoCase(activeMod, OurMod);
	v.duplicate = otherInstances > 0;
	return v;
}

// The full line for the log and `mxl` ("" when ok): "WARNING: ... Run the D2R-XL 2012 Downloader ...".
inline void Detail(char* out, size_t n, const Verdict& v, const char* selfPath, const char* activeMod, const char* otherPath) noexcept {
	if (out == nullptr || n == 0) {
		return;
	}
	out[0] = '\0';
	if (v.Ok()) {
		return;
	}
	size_t len = 0;
	auto put = [&](const char* fmt, const char* a) {
		if (len < n) {
			const int w = std::snprintf(out + len, n - len, fmt, a != nullptr ? a : "?");
			len += w > 0 ? static_cast<size_t>(w) : 0;
		}
	};
	put("%s", "WARNING:");
	if (v.outsideMod) {
		put(" this D2R-XL 2012 plugin is not in mods\\mxl2012 but in %s, so it loads with every mod;", selfPath);
	}
	if (v.otherMod) {
		put(" D2RLoader runs the mod %s, not D2R-XL 2012 (its default_mod);", activeMod);
	}
	if (v.duplicate) {
		put(" a second copy of the D2R-XL 2012 plugin is loaded (%s);", otherPath);
	}
	put("%s", " this may be another or an old build. Run the D2R-XL 2012 Downloader: it shows and fixes this.");
}

// The short line for the screen ("" when ok).
inline void Notice(char* out, size_t n, const Verdict& v, const char* pluginVersion, const char* activeMod) noexcept {
	if (out == nullptr || n == 0) {
		return;
	}
	out[0] = '\0';
	if (v.Ok()) {
		return;
	}
	const char* what = v.duplicate    ? "two copies of the D2R-XL 2012 plugin are loaded"
	                   : v.outsideMod ? "the D2R-XL 2012 plugin is loaded from outside mods\\mxl2012"
	                                  : "D2RLoader runs another mod";
	char mod[80] = "";
	if (v.otherMod) {
		std::snprintf(mod, sizeof(mod), " (mod %.40s)", activeMod != nullptr ? activeMod : "?");
	}
	std::snprintf(out, n, "D2R-XL 2012 %s: %s%s. Run the D2R-XL 2012 Downloader to fix it.", pluginVersion != nullptr ? pluginVersion : "?", what, mod);
}

}  // namespace env_guard

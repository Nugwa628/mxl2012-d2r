// Pure part of the `other plugins` line of `mxl2012` and of the plugin guard (mxl2012_core.cpp; no Windows headers, tested in plugin/tests/other_plugins_test.cpp).
// D2RLoader loads the plugins of the running mod (<game>\mods\<mod>\d2rloader\plugins) and then the game-wide ones
// (<game>\d2rloader\plugins). A player crash report then needs to say which other plugins ran next to mxl2012-core (bug #42).
#pragma once

#include <cstddef>
#include <cstdio>
#include <cstring>

namespace other_plugins {

inline auto Lower(char c) noexcept -> char {
	return (c >= 'A' && c <= 'Z') ? static_cast<char>(c - 'A' + 'a') : (c == '/' ? '\\' : c);
}

// Position of "\d2rloader\plugins\" in path (any case, / or \), or -1.
inline auto PluginDirAt(const char* path) noexcept -> long long {
	static constexpr char Needle[] = "\\d2rloader\\plugins\\";
	if (path == nullptr) {
		return -1;
	}
	for (long long i = 0; path[i] != '\0'; ++i) {
		size_t k = 0;
		while (Needle[k] != '\0' && path[i + static_cast<long long>(k)] != '\0' && Lower(path[i + static_cast<long long>(k)]) == Needle[k]) {
			++k;
		}
		if (Needle[k] == '\0') {
			return i;
		}
	}
	return -1;
}

// "<file> (mod <name>)" or "<file> (global)" for a module loaded from a D2RLoader plugin folder; false for any other module.
inline auto Label(const char* path, char* out, size_t n) noexcept -> bool {
	const long long at = PluginDirAt(path);
	if (at < 0 || out == nullptr || n == 0) {
		return false;
	}
	const char* file = path + at + 19;  // past "\d2rloader\plugins\"
	for (const char* p = file; *p != '\0'; ++p) {
		if (*p == '\\' || *p == '/') {
			file = p + 1;
		}
	}
	// The folder holding d2rloader\: <game> (global) or <game>\mods\<mod>.
	long long end = at, start = at;
	while (start > 0 && path[start - 1] != '\\' && path[start - 1] != '/') {
		--start;
	}
	long long pstart = start - 1;
	while (pstart > 0 && path[pstart - 1] != '\\' && path[pstart - 1] != '/') {
		--pstart;
	}
	const bool inMods = start >= 1 && pstart >= 0 && start - 1 - pstart == 4 && Lower(path[pstart]) == 'm' && Lower(path[pstart + 1]) == 'o' &&
	                    Lower(path[pstart + 2]) == 'd' && Lower(path[pstart + 3]) == 's';
	if (inMods) {
		std::snprintf(out, n, "%s (mod %.*s)", file, static_cast<int>(end - start), path + start);
	} else {
		std::snprintf(out, n, "%s (global)", file);
	}
	return true;
}

// --- Plugin guard (docs/plugin-plan.md 1.3, item F) -------------------------------------------------------------------
// Another D2RLoader plugin is known to write the same free table slots as mxl2012-core (client do 113, the empty missile
// slot stubs). Mod-scoped, it stays out of the mxl2012 mod, but a stray copy in the game-wide d2rloader\plugins folder
// loads with every mod. With it in the game, mxl2012-core installs nothing. Kept as name hashes: FNV-1a 32 of the
// ASCII-lowercased PluginInfo id and file name.
inline auto NameHash(const char* s) noexcept -> unsigned {
	unsigned h = 2166136261u;
	for (; *s != '\0'; ++s) {
		const char c = (*s >= 'A' && *s <= 'Z') ? static_cast<char>(*s - 'A' + 'a') : *s;
		h = (h ^ static_cast<unsigned char>(c)) * 16777619u;
	}
	return h;
}

constexpr unsigned ConflictingPluginIds[] = {0xee3aa6a0u};
constexpr unsigned ConflictingFiles[] = {0x27adb37au};

inline auto HashIn(const char* name, const unsigned* hashes, size_t n) noexcept -> bool {
	if (name == nullptr || hashes == nullptr) {
		return false;
	}
	const unsigned h = NameHash(name);
	for (size_t i = 0; i < n; ++i) {
		if (hashes[i] == h) {
			return true;
		}
	}
	return false;
}

// A module conflicts when its PluginInfo id is in `ids` (pluginId null when it is no plugin / has none), or its file name
// is in `files` (any case). mxl2012-core.dll never is.
inline auto IsConflictingPlugin(const char* fileName, const char* pluginId, const unsigned* ids, size_t nIds, const unsigned* files,
                                size_t nFiles) noexcept -> bool {
	return HashIn(pluginId, ids, nIds) || HashIn(fileName, files, nFiles);
}

inline auto IsConflictingPlugin(const char* fileName, const char* pluginId) noexcept -> bool {
	return IsConflictingPlugin(fileName, pluginId, ConflictingPluginIds, sizeof(ConflictingPluginIds) / sizeof(ConflictingPluginIds[0]),
	                           ConflictingFiles, sizeof(ConflictingFiles) / sizeof(ConflictingFiles[0]));
}

// The screen notice. `fileName`: the conflicting module's file; `where` is the folder holding it as the player knows it
// (default: the game-wide d2rloader\plugins).
inline void ConflictNotice(char* out, size_t n, const char* pluginVersion, const char* fileName, const char* where) noexcept {
	if (out == nullptr || n == 0) {
		return;
	}
	std::snprintf(out, n, "D2R-XL 2012 %s: another plugin (%s) writes the same engine slots; remove it from %s. The mod's engine changes are off.",
	              pluginVersion != nullptr ? pluginVersion : "?", fileName != nullptr && fileName[0] != '\0' ? fileName : "unknown",
	              where != nullptr && where[0] != '\0' ? where : "d2rloader\\plugins");
}

// --- Hook clashes with players' own plugins (docs/bugs.md #522) ------------------------------------------------------------
// D2RLoader loads the mod's plugins first, so mxl2012-core's hooks and patches are in when a game-wide plugin asks for the same
// address; D2RLoader then refuses that plugin's hook and logs (d2rloader.log, seen with D2RLoader 1.3.1-beta):
//   "[...] [ERROR] Plugin <id> could not install a Native Hook at RVA 0x36BC50: game bytes did not match what the plugin expected"
// (and a second line "...: MH_ERROR_ALREADY_CREATED" for a plugin that retries). The plugin still loads; only that feature of it
// does nothing. True with `plugin` (the id) and `rva` filled for such a line.
inline auto ParseHookRefusal(const char* line, char* plugin, size_t n, unsigned long long* rva) noexcept -> bool {
	static constexpr char Head[] = "Plugin ";
	static constexpr char Mid[] = " could not install a Native Hook at RVA 0x";
	if (line == nullptr || plugin == nullptr || n == 0 || rva == nullptr) {
		return false;
	}
	const char* mid = std::strstr(line, Mid);
	const char* head = mid != nullptr ? std::strstr(line, Head) : nullptr;
	if (head == nullptr || head > mid) {
		return false;
	}
	const char* id = head + sizeof(Head) - 1;
	const size_t len = static_cast<size_t>(mid - id);
	if (len == 0 || len >= n) {
		return false;
	}
	std::memcpy(plugin, id, len);
	plugin[len] = '\0';
	unsigned long long v = 0;
	int digits = 0;
	for (const char* p = mid + sizeof(Mid) - 1; digits < 16; ++p, ++digits) {
		const char c = Lower(*p);
		const int d = (c >= '0' && c <= '9') ? c - '0' : (c >= 'a' && c <= 'f') ? c - 'a' + 10 : -1;
		if (d < 0) {
			break;
		}
		v = (v << 4) | static_cast<unsigned>(d);
	}
	*rva = v;
	return digits > 0;
}

// The part of mxl2012-core whose `mxl2012` report names `rva` ("0x36bc50 hooked", "at 0x37d744", "0x44b152 -> jmp ..."): the
// off word of reports[i] (words[i]), or null. An address is matched whole: 0x36bc5 does not match 0x36bc50.
inline auto PartOfAddress(unsigned long long rva, const char* const* words, const char* const* reports, size_t count) noexcept -> const char* {
	char needle[24];
	std::snprintf(needle, sizeof(needle), "0x%llx", rva);
	const size_t nl = std::strlen(needle);
	for (size_t i = 0; i < count; ++i) {
		for (const char* p = reports[i] != nullptr ? std::strstr(reports[i], needle) : nullptr; p != nullptr; p = std::strstr(p + 1, needle)) {
			const char next = Lower(p[nl]);
			if (!((next >= '0' && next <= '9') || (next >= 'a' && next <= 'f'))) {
				return words[i];
			}
		}
	}
	return nullptr;
}

}  // namespace other_plugins

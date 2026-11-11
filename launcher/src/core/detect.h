// Finding D2R and reading its version: the parsers (testable without Windows). The registry / file system side is in
// src/win/game.cpp.
#pragma once

#include <string>
#include <vector>

namespace mxl {

// The downloader never refuses to install or to start the game because of D2R's version or build number: the plugins are
// not tied to a game build or version (docs/plugin-plan.md 1.2). Each part of a plugin checks the running code itself and
// turns itself off when it is not what it expects (plugin/src/image_guard_logic.h). The version found is shown as
// information only.

// "major.minor" of a version string: "3.3.93847" -> "3.3", "3.3.0" -> "3.3", "1.0.0.93847" -> "1.0"; "" when none.
std::string GameVersion(const std::string& version);

// .build.info of a Blizzard (CASC) install: '|' separated, first line "Name!TYPE:n|...". Returns the "Version" of
// the active row ("3.3.93847"), or "" when there is none.
std::string BuildInfoVersion(const std::string& text);

// Last number of a version string: "3.3.93847" -> 93847, "1.0.0.93847" -> 93847; 0 when there is none.
int BuildNumber(const std::string& version);

// Every "path" value of Steam's libraryfolders.vdf (KeyValues text), unescaped ("C:\\Steam" -> "C:\Steam").
std::vector<std::string> SteamLibraryPaths(const std::string& vdf);

// Value of a top-level key of an appmanifest_*.acf ("installdir", "name", "appid"), "" when missing.
std::string AcfValue(const std::string& acf, const std::string& key);

// True when an appmanifest names D2R (its name or install folder).
bool AcfIsD2R(const std::string& acf);

// What was read about the D2R version: information for the status line, never a reason to block.
struct GameInfo {
	bool known = false;   // a version could be read
	int build = 0;
	std::string version;  // the game version found ("3.3", "3.4"), "" when unknown
	std::string message;  // one neutral line for the status bar
};
// `infoVersion` from .build.info, `exeVersion` the file version of D2R.exe ("" when unreadable). .build.info is
// preferred, D2R.exe is the fallback.
GameInfo DescribeGame(const std::string& infoVersion, const std::string& exeVersion);

}  // namespace mxl

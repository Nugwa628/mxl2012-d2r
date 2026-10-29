// Finding D2R and checking its build: the parsers (testable without Windows). The registry / file system side is in
// src/win/game.cpp.
#pragma once

#include <string>
#include <vector>

namespace mxl {

// The game version D2R-XL 2012 needs: major.minor of D2R's version ("3.3" of "3.3.93847"). Never the build number: builds of
// one game version differ by platform (Steam 3.3.94995, Battle.net 3.3.93847) and hotfix, and D2RLoader supports the
// game version (D2RLoader's author, 2026-10-27). The plugin itself still checks the game image at run time and stays off
// on one it was not made for (plugin/src/build_guard_logic.h).
constexpr const char* RequiredGameVersion = "3.3";
constexpr int RequiredBuild = 93847;  // the build the plugin's addresses were taken from (docs/d2r-baseline.md); info only

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

enum class BuildVerdict { Ok, Older, Newer, Unknown };
struct BuildCheck {
	BuildVerdict verdict = BuildVerdict::Unknown;
	int build = 0;
	std::string version;  // the game version found ("3.3"), "" when unknown
	std::string message;  // one line for the status bar
};
// `infoVersion` from .build.info, `exeVersion` the file version of D2R.exe ("" when unreadable). The game version
// (major.minor) of .build.info (else of D2R.exe) must equal `required` ("3.3"); the build number is only shown.
BuildCheck CheckBuild(const std::string& infoVersion, const std::string& exeVersion,
                      const std::string& required = RequiredGameVersion);

}  // namespace mxl

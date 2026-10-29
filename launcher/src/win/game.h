// D2R on this PC: finding installs (Battle.net uninstall entry, Steam libraries, default folders), the build check,
// D2RLoader's version, free space, folder removal and the game processes.
#pragma once

#include "../core/detect.h"

#include <cstdint>
#include <string>
#include <vector>

namespace mxl {

struct D2RInstall {
	std::wstring dir;
	std::string source;  // "Battle.net", "Steam", "default folder", "chosen"
	std::string infoVersion, exeVersion;
	BuildCheck build;
};

bool LooksLikeD2R(const std::wstring& dir);
D2RInstall InspectD2R(const std::wstring& dir, const std::string& source);
// Every install found (duplicates removed), best first: a build-93847 Battle.net install, then other matches.
std::vector<D2RInstall> FindD2RInstalls();

std::string ExeFileVersion(const std::wstring& exe);
// ProductName and FileDescription of a file's version resource ("" when it has none).
void FileVersionStrings(const std::wstring& file, std::string& productName, std::string& fileDescription);
// SHA-1 thumbprint (upper-case hex) of the Authenticode signer of a file. `intact` is false when the signature is
// missing or the file was changed after signing; a self-signed certificate (D2RLoader's) counts as intact.
bool SignerThumbprint(const std::wstring& file, std::string& thumbprint, bool& intact);
// Every file under `dir`, relative with '/' separators (no reparse points followed).
std::vector<std::string> ListFilesUnder(const std::wstring& dir);

bool FreeBytes(const std::wstring& path, uint64_t& free);

// Remove a folder tree. Junctions and symlinks inside are unlinked, never followed.
bool RemoveTree(const std::wstring& dir, std::string& error);

struct GameProcess {
	unsigned long pid;
	std::wstring exe;
};
// Processes whose image lies inside `dir` (the D2R folder): D2RLoader.exe and the D2R it starts.
std::vector<GameProcess> ProcessesUnder(const std::wstring& dir);

}  // namespace mxl

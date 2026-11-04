// Install D2RLoader (docs/launcher.md "Install D2RLoader"): the release manifest's d2rloader block names the official
// ZIP (url, version, size, sha256); the downloader fetches it only when the player asks, checks it, and puts its files
// into the D2R folder. Which manifests are usable, where each ZIP entry goes, when to refuse. Portable for the tests.
#pragma once

#include "manifest.h"
#include "zip.h"

#include <string>
#include <vector>

namespace mxl {

// D2RLoader's own site: the only host a package is downloaded from (https only).
constexpr const char* LoaderHost = "d2rloader.net";
constexpr uint64_t LoaderMaxSize = 512ull << 20;

// "D2RLoader-1.3.1-beta.zip" from the url, "" when the url's last segment is not a plain .zip name.
std::string LoaderZipName(const std::string& url);

// The manifest's d2rloader block can be installed: version, an https:// url on LoaderHost (or a subdomain) ending in a
// .zip name, size (1 byte .. LoaderMaxSize) and a 64-digit sha256. `error` names the first missing or bad field.
bool LoaderPackageUsable(const Manifest::Loader& l, std::string& error);

struct LoaderTarget {
	std::string path;   // relative to the D2R folder, '/' separators, no trailing '/'
	size_t entry = 0;   // index into the ZIP's entries
	bool dir = false;
	bool keepExisting = false;  // the player's settings (d2rloader/config/...): written only when missing
};

// Where every entry of the D2RLoader ZIP goes. Accepted: files at the top named D2RLoader* or D2RCore* (the loader, its
// core DLL and MPQ), anything under d2rloader/, and empty folders (mods/). Everything else (D2R's own files, Data/, a
// file inside mods/, an unsafe path, a duplicate) refuses the whole package, so nothing of D2R or of a mod is replaced.
bool PlanLoaderInstall(const std::vector<ZipEntry>& entries, std::vector<LoaderTarget>& out, std::string& error);

// "D2RLoader.exe is running from <dir>. Close D2RLoader and the game first." for the first of `running` (image paths
// under the D2R folder), "" when nothing runs there.
std::string LoaderRunningRefusal(const std::vector<std::string>& running, const std::string& d2rDir);

}  // namespace mxl

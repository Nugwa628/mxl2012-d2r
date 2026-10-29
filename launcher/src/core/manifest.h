// The download host's channel file and release manifest (docs/release.md "Release manifest", "Hosting layout") and the
// install plan: which files of a release to fetch, which to leave alone and which to remove, given what is installed now.
#pragma once

#include "json.h"

#include <cstdint>
#include <functional>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace mxl {

struct ManifestFile {
	std::string path;  // relative to the mod folder (<game>\mods\<modFolder>), '/' separators
	uint64_t size = 0;
	std::string sha256;
};

// The release manifest schema this downloader reads. 2: the release is a 7z (built on the server) plus one object per
// file; the downloader installs from either (docs/launcher.md "7z or objects"); schema 1 (the zip) is gone.
constexpr int ManifestSchema = 2;

// release-manifest.json, schemaVersion 2 (docs/release.md "Release manifest"). Unknown fields are ignored; another
// schemaVersion is refused.
struct Manifest {
	int schemaVersion = 0;
	std::string name;           // "mxl2012"
	std::string version;        // the release, shown to the player
	std::string pluginVersion;
	bool complete = false;      // false: a package without game data (a --no-data build): only from a test channel
	int d2rBuild = 0;           // d2r.build: the build the plugin's addresses were taken from (93847); shown only
	std::string d2rVersion;     // d2r.version ("3.3.0"): its major.minor ("3.3") is what the player's D2R must be
	uint32_t imageTimestamp = 0;  // d2r.imageTimestamp: of the unpacked image in memory, not the file (0 = not given)
	struct Loader {
		std::string version, url, sha256, signerThumbprint;
		uint64_t size = 0;
	} d2rloader;
	std::string launchDefaultMod;  // launch.default_mod, for the copy's d2rloader.toml
	std::string launchArguments;   // launch.launch_arguments ("-txt")
	std::string modFolder;         // the files live in <game>\mods\<modFolder>; the 7z's top folder
	std::string saveFolder;        // modinfo savepath ("mxl2012/"); the downloader never writes there
	std::set<std::string> preserve;  // player-editable: written only when missing
	std::vector<std::string> emptyDirs;  // folders of the release without files (d2rloader/patches): created
	struct Archive {               // archive: the release 7z (a fresh install downloads and unpacks it; also for manual installs)
		std::string name, path, sha256;  // path: relative to the site root (published manifests)
		uint64_t size = 0;
	} archive;
	std::string objectsBase;       // required: files[i] is at <root><objectsBase><sha[0:2]>/<sha> ("objects/")
	struct LauncherRef {           // launcher (published manifests, optional): the downloader published with the release
		std::string version, path, sha256;
		uint64_t size = 0;
	} launcher;
	std::string launcherMin;       // optional (launcher lane extension): oldest launcher that can install it
	std::vector<ManifestFile> files;
};

// channels/<channel>.json on the download host: which release a channel (stable, test) points to.
struct Channel {
	int schemaVersion = 0;
	std::string version;
	std::string manifest;        // relative to the site root: releases/<v>/release-manifest.json
	std::string manifestSha256;  // the manifest's bytes must hash to this
	std::string publishedAt;
};
bool ParseChannel(const std::string& text, Channel& out, std::string& error);

// The player's message when channels/<channel>.json could not be read. `status` is the HTTP status (0: no answer,
// i.e. a network / TLS failure or an unreachable host; a file:// site gives 404 for a missing file), `transportError`
// the WinHTTP error text. 404: nothing published on that channel yet; another status: the site answered it; 0: the
// site cannot be reached.
std::string ChannelReadError(const std::string& channel, const std::string& url, int status, const std::string& transportError);

// The launcher's one setting as a URL ending in '/': http(s):// and file:// stay (a '/' is added), a local folder
// ("D:\site", "\\server\share\mxl") becomes file:///D:/site/.
std::string SiteRoot(const std::string& setting);

// <objectsBase><sha[0:2]>/<sha>
std::string ObjectPath(const std::string& objectsBase, const std::string& sha256);

// The files to fetch grouped by content: several entries with the same sha256 are one download.
struct ObjectFetch {
	std::string sha256;
	uint64_t size = 0;
	std::vector<std::string> paths;
};
std::vector<ObjectFetch> GroupObjects(const std::vector<ManifestFile>& files);

// Parse and check a manifest. Every path must pass SafeRelativePath, sha256 must be 64 hex digits, fileCount /
// totalSize (when given) must match the list, objectsBase must be there. When schemaVersion is not ManifestSchema it
// returns false with out.schemaVersion, out.version and out.launcher set (so the caller can say "too old / too new"
// and still offer the downloader that the release names).
bool ParseManifest(const std::string& text, Manifest& out, std::string& error);

// A release without game data (complete false) is installed only from a channel other than stable: the test channel
// carries such packages to test the downloader (publish_release.py --allow-incomplete); stable never does (dl_ingest.py).
bool InstallableFromChannel(const Manifest& m, const std::string& channel);
Json ManifestToJson(const Manifest& m);

// A relative path that cannot leave its root: no empty / "." / ".." segment, no drive, no backslash, no characters
// Windows refuses (<>:"|?* and control characters), no trailing dot or space in a segment, no device names.
bool SafeRelativePath(const std::string& path);

// Files under the mod folder that an update never deletes although the release does not list them: D2RLoader's own
// output (d2rloader/logs/, d2rloader/crashes/) and the downloader's marker and downloads (mxl2012-install.json,
// mxl2012-download/).
bool RuntimeOutput(const std::string& path);

struct InstallPlan {
	std::vector<ManifestFile> fetch;      // missing or different: download and install
	std::vector<std::string> remove;      // on disk under the mod folder, not in the release (docs/release.md "files")
	std::vector<std::string> preserved;   // preserve entries that exist: left as they are
	uint64_t fetchBytes = 0;
};

// current(path) gives the sha256 of the installed file, or "" when it is missing; `local` lists every file now under
// the mod folder (relative, '/' separators).
InstallPlan PlanInstall(const Manifest& next, const std::vector<std::string>& local,
                        const std::function<std::string(const std::string&)>& current);

// "1.2.10" > "1.2.9"; a "-beta" style suffix sorts before the plain version.
int CompareVersions(const std::string& a, const std::string& b);

// Resolve `ref` against `base` (a manifest URL): absolute http(s):// or file:// stays, "x.zip" replaces the last
// segment, "/x.zip" keeps scheme and host.
std::string ResolveUrl(const std::string& base, const std::string& ref);

}  // namespace mxl

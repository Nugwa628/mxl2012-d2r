// Where the downloader writes (docs/launcher.md "Where it writes"): the mod folder <D2R>\mods\<modFolder> and nothing
// else in the D2R folder, its own data in %LOCALAPPDATA%\mxl2012, never the official Median XL's folders. The marker that
// proves a mod folder is ours, the D2RLoader version check, the TOML edits for D2RLoader's config. Testable without
// Windows (Windows paths as UTF-8 strings).
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

namespace mxl {

constexpr const char* ProductFolder = "mxl2012";
// The marker file at the top of the mod folder: {"made_by": MarkerMadeBy, "id": ..., "version": ...}.
constexpr const char* InstallMarkerName = "mxl2012-install.json";
constexpr const char* MarkerMadeBy = "D2R-XL 2012 Downloader";
// Downloads in progress, inside the mod folder (same volume: a finished object is renamed into place).
constexpr const char* DownloadFolderName = "mxl2012-download";

// <localAppData>\mxl2012: state, log
std::string DefaultDataDir(const std::string& localAppData);

// A mod folder name from a release manifest: one plain path segment ("mxl2012"), nothing that could leave <D2R>\mods.
bool SafeModFolderName(const std::string& name);
// <d2rDir>\mods\mxl2012 ("" for any other modFolder). The only mod folder the downloader writes.
std::string ModTargetDir(const std::string& d2rDir, const std::string& modFolder);
// True when `path` is `dir` itself or inside it (case-insensitive, '\' or '/', no ".." tricks: a path with a ".."
// segment is never inside).
bool PathIsOrUnder(const std::string& path, const std::string& dir);

// What a mod folder's marker says about who made it.
enum class MarkerVerdict {
	None,      // no marker: not made by the downloader (a manual or tools/install_mod.py install): ask before replacing
	Ours,      // made by the downloader, and its id is the one in the state (or the state has none)
	OtherId,   // made by the downloader, another id (e.g. the state was deleted, or another Windows user installed it)
	Unreadable // a marker that is not ours (damaged, or another made_by)
};
// `text`: the marker file ("" when missing), `stateId`: the id the state recorded ("" when none).
MarkerVerdict CheckMarker(const std::string& text, const std::string& stateId);
std::string MakeMarker(const std::string& id, const std::string& version);

// D2RLoader's file version ("1.3.1-beta") against the release's ("1.3.1-beta"; the manifest's d2rloader.version). Equal
// numbers are enough: "1.3.1" matches "1.3.1-beta", "1.3.1.0" too; "1.3.0" or "1.4.0" do not. "" never matches.
bool LoaderVersionMatches(const std::string& found, const std::string& required);

// Set `key = value` in [section] of a TOML text: an uncommented key is replaced in place (its comment kept), a
// commented template line (`# key = ...`) is replaced, otherwise the key is added under the section header (the
// section is appended when missing). `value` is TOML text (`"mxl2012"`, `false`).
std::string SetTomlKey(const std::string& text, const std::string& section, const std::string& key, const std::string& value);

// Value text of `key` in [section] ("" when missing), without a trailing comment.
std::string GetTomlKey(const std::string& text, const std::string& section, const std::string& key);

// ---- D2RLoader's save format (docs/bugs.md #512). D2R-XL 2012 needs `[d2rcore.save_format] mode = "extended"` in the
// mod's own d2rloader.toml: in retail format D2R cannot write Median's stats 511+ and every save is cancelled. The release
// ships the key, but the file is a `preserve` file: the downloader keeps the one a player already has.

// The mod's config, relative to the mod folder (the manifest path). Its backup is <file>.retail-backup (SaveFormatBackupSuffix,
// manifest.h).
constexpr const char* ModLoaderConfigRel = "d2rloader/config/d2rloader.toml";
// The save format the text asks for, unquoted: `mode` of [d2rcore.save_format], or the dotted key
// `d2rcore.save_format.mode` before the first table. "" when missing (commented lines do not count).
std::string SaveFormatMode(const std::string& text);
// The text with the save format set to "extended": an existing `mode` line (or the dotted key) is changed in place (its
// comment kept), else `mode = "extended"` goes right under an existing [d2rcore.save_format] header, else the table is
// appended. Every other line, a UTF-8 BOM and the line endings stay as they were; an extended file comes back unchanged.
std::string SetExtendedSaveFormat(const std::string& text);

// True for a path the official Median XL owns or this downloader must never use: <localAppData>\mxl-launcher (its
// launcher), <roamingAppData>\MedianXL (its saves), <localAppData>\MedianXL, and a classic Diablo II folder (any path
// segment named "Diablo II"). Case-insensitive, '\' or '/'.
bool OfficialMedianXLPath(const std::string& path, const std::string& localAppData, const std::string& roamingAppData);

// True for the game's own processes, which hold the mod's files: D2R.exe and D2RLoader*.exe (case-insensitive, file name
// or full path). Not the downloader, Battle.net's "Diablo II Resurrected Launcher.exe" or BlizzardError.exe.
bool IsGameProcessName(const std::string& exe);

// ---- The player's D2R around the mod folder (docs/bugs.md #53): D2RLoader can start another build than the one the
// downloader installed. Its game-wide config names the mod it starts, and a copy of our plugin in another plugins
// folder loads too.

// The game-wide config D2RLoader reads at start, relative to the D2R folder.
constexpr const char* LoaderConfigRel = R"(d2rloader\config\d2rloader.toml)";
// A TOML string value without its quotes (`"mxl2012"` or `'mxl2012'` -> `mxl2012`); other text as it is.
std::string TomlUnquote(const std::string& value);

struct DefaultModCheck {
	bool ok = false;             // default_mod names our mod folder (case-insensitive, like Windows folder names)
	bool configMissing = false;  // no game-wide d2rloader.toml (D2RLoader never ran, or is not installed)
	std::string mod;             // the mod D2RLoader starts ("" when default_mod is missing or empty)
};
// `text`: the game-wide d2rloader.toml (`exists` false when there is none); `ourMod`: "mxl2012".
DefaultModCheck CheckDefaultMod(const std::string& text, bool exists, const std::string& ourMod);
// The status line ("" when ok): which mod D2RLoader starts instead of ours.
std::string DefaultModWarning(const DefaultModCheck& c, const std::string& ourMod);
// The config with default_mod set to `ourMod`; every other line stays as it is.
std::string SetDefaultMod(const std::string& text, const std::string& ourMod);

// True for a DLL that is (a copy of) our plugin: the file name mxl2012-core*.dll, or its version resource says D2R-XL 2012
// (ProductName "mxl2012", or a FileDescription naming mxl2012-core or "D2R-XL 2012 core"). Empty strings: no version resource.
bool IsOurPluginFile(const std::string& fileName, const std::string& productName, const std::string& fileDescription);

enum class PluginPlace {
	None,      // not in a D2RLoader plugins folder
	GameWide,  // <D2R>\d2rloader\plugins\...: loads with every mod
	OtherMod,  // <D2R>\mods\<other>\d2rloader\plugins\...: loads when D2RLoader starts that mod
	OurMod     // <D2R>\mods\<ourMod>\d2rloader\plugins\...: the installed one
};
// `rel`: a DLL's path relative to the D2R folder ('\' or '/'); `mod` gets the mod folder for OtherMod / OurMod.
PluginPlace PluginPlaceOf(const std::string& rel, const std::string& ourMod, std::string* mod = nullptr);
// The warning for a copy of our plugin outside mods\<ourMod> ("" for OurMod / None). `path`: the file as shown to the
// player (the CLI and the question before moving it); `brief`: the short form of the window's status panel.
std::string StrayPluginWarning(const std::string& path, PluginPlace place, const std::string& mod, bool brief = false);
// A protected mod (IsProtectedModFolder) is another mod for warnings, but its folder must never be changed.
bool CanMoveStrayPlugin(PluginPlace place, const std::string& mod);
// Mod folders no tool of ours changes: kept as FNV-1a 32 hashes of the lowercased folder name (`hashes`/`n`: a test list;
// nullptr: the built-in one).
bool IsProtectedModFolder(const std::string& mod, const uint32_t* hashes = nullptr, size_t n = 0);
uint32_t NameHash(const std::string& s);
// Where a stray plugin is moved (never deleted): <dataDir>\removed\<date>\<rel>; `date` like "2026-10-27".
std::string RemovedPluginPath(const std::string& dataDir, const std::string& date, const std::string& rel);

}  // namespace mxl

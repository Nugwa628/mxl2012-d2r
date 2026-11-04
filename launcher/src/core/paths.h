// Where the downloader writes (docs/launcher.md "Where it writes"): the mod folder <D2R>\mods\<modFolder> and nothing
// else in the D2R folder, its own data in %LOCALAPPDATA%\mxl2012, never the official Median XL's folders. The marker that
// proves a mod folder is ours, the D2RLoader version check, the TOML edits for D2RLoader's config. Testable without
// Windows (Windows paths as UTF-8 strings).
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

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

// ---- D2RLoader's Ctrl stat ranges (docs/bugs.md #528, owner decision 2026-11-03). D2RCore's `[d2rcore.items]
// item_stat_ranges` prints repeated "Possible base rolls" lines for Median's automagic rows, so the mod's d2rloader.toml
// turns it off; the kept (`preserve`) file of an older install gets the key too.
// The value of `item_stat_ranges` in [d2rcore.items] (or the dotted `d2rcore.items.item_stat_ranges` before the first
// table), unquoted; "" when missing.
std::string ItemStatRanges(const std::string& text);
// The text with `item_stat_ranges = false`: an existing key line gets the value in place (indent and comment kept), else a
// commented template line `# item_stat_ranges = ...` of [d2rcore.items] becomes the key, else the key goes under the
// header, else the table is appended. A BOM and the line endings stay; a file already at false comes back unchanged.
std::string SetItemStatRangesOff(const std::string& text);

// `key = value` in [section] unless the player set the key (tools/install_mod.py ensure_toml_key, the same rules): an
// uncommented key in [section], or the dotted `section.key` before the first table, is kept as it is; else a commented
// template line (`# key = ...`, any number of '#' and spaces) becomes the key; else the key goes under the header; else
// the table is appended. A BOM and the line endings stay.
std::string EnsureTomlKey(const std::string& text, const std::string& section, const std::string& key, const std::string& value);
// `key = value` in [section] whatever the file says (tools/install_mod.py ensure_toml_key with force): an existing key line
// (or the dotted key before the first table) gets the value in place (indent and comment kept), else as EnsureTomlKey. A
// file already at that value (quotes ignored) comes back unchanged.
std::string ForceTomlKey(const std::string& text, const std::string& section, const std::string& key, const std::string& value);
// The value of `key` in [section] (or the dotted key before the first table), as written; "" when missing.
std::string TableKeyValue(const std::string& text, const std::string& section, const std::string& key);

// ---- The keys every install leaves in the mod's own d2rloader.toml (docs/launcher.md "Keys in the mod's config"). The
// mod's file overrides D2RLoader's game-wide one, which the downloader never writes. A fresh install ships them
// (tools/install_mod.py TOML_KEYS); a kept (`preserve`) file of an older install gets them after each install, update and
// repair (ApplyModConfigKey).
struct ModConfigKey {
	const char* section;
	const char* key;
	const char* value;  // TOML text
	bool keepHandSet;   // true: a value the player set stays (EnsureTomlKey); false: always this value (ForceTomlKey)
	const char* why;    // for the panel / log line
	bool atLeast = false;  // an integer minimum: a larger integer stays, a smaller one (or not an integer) becomes `value`
};
// [d2rcore.save_format] mode = "extended" (#512, forced, with a backup: Launcher::EnsureExtendedSaves),
// [d2rcore.items] item_stat_ranges = false (#528, forced),
// [d2rcore.player] always_enable_rotw_legacy_graphics_keybind = true (#498, the G toggle in a RotW game; forced, owner
// decision 2026-11-04: a false set by hand or left by D2RLoader's template becomes true),
// [d2rcore.stash] add_shared_tabs at least 2 (#535: 5 shared stash pages in every game, as a RotW game has; a larger value
// stays, lowering it would hide the items on the pages past it).
extern const ModConfigKey ModConfigKeys[4];
// The text with that key applied (unchanged when nothing is to do); `was` (optional) gets the old value ("" missing).
std::string ApplyModConfigKey(const std::string& text, const ModConfigKey& k, std::string* was = nullptr);

// ---- Copies of the player's saves before an install, update or repair (docs/bugs.md #536: a player's shared stash was
// refused with "bad header" after updates). The save folder is only read; the copies go to <data dir>\save-copies\<folder>.
constexpr const char* SaveCopiesFolder = "save-copies";
constexpr size_t SaveCopiesKept = 10;
// A file name of the save folder that is copied: shared stashes (.d2i), characters (.d2s) and D2RLoader's sidecars (.d2rl),
// case-insensitive. Not the key bindings, automap or settings files.
bool IsSaveCopyFile(const std::string& name);
// "<stamp> <from> to <to>" with every character outside [A-Za-z0-9._-] made '_'; `stamp` is "YYYYMMDD-HHMMSS" and `from` is
// "none" for a first install.
std::string SaveCopyFolderName(const std::string& stamp, const std::string& from, const std::string& to);
// The copy folders to remove so that `keep` stay: the oldest by their stamp. Names that do not start with a stamp are not
// the downloader's and are never listed.
std::vector<std::string> SaveCopiesToRemove(const std::vector<std::string>& folders, size_t keep = SaveCopiesKept);

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

// ---- Play (docs/launcher.md "Play"): the downloader starts `<D2R>\D2RLoader.exe -mod mxl2012` in the D2R folder.
// D2RLoader passes its own command line on to D2R after the game-wide launch_arguments, and a -mod there wins over the
// game-wide default_mod, so Play starts D2R-XL 2012 whatever default_mod says and never writes it.

struct PlayInputs {
	bool d2rFound = false;
	bool buildMismatch = false;    // the D2R version is known and is not the one the release needs
	bool loaderOk = false;         // D2RLoader.exe at the required version
	bool loaderFound = false;      // a D2RLoader.exe, of any version
	bool installed = false;        // our install (the marker) of some release
	bool foreignMod = false;       // mods\mxl2012 was not made by the downloader
	bool updateAvailable = false;  // the channel has another release than the installed one
	bool pending = false;          // an install, update or repair stopped before it finished
	bool gameRunning = false;      // D2R or D2RLoader runs from the D2R folder
};
// "" when Play may start the game, else why not: one short line for the window ("Play: <why>").
std::string PlayBlocked(const PlayInputs& in);
// The words after D2RLoader.exe: `-mod <modFolder>`.
std::string PlayArguments(const std::string& modFolder);
// The whole command line for CreateProcess: the exe in quotes, then PlayArguments. `""` when the exe path cannot be quoted
// (a '"' in it).
std::string PlayCommandLine(const std::string& loaderExe, const std::string& modFolder);

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

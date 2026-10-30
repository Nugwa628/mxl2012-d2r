// mxl2012-core: the D2RLoader plugin of D2R-XL 2012 (Median XL 2012 v005 on Diablo II: Resurrected 3.3).
//
// It loads with the mxl2012 mod, logs the game build it runs on and adds the console command "mxl2012". Engine changes are
// tied to one game image (RVAs from the dump of the D2R image D2RLoader runs), so the plugin records which image it expects
// (the PE header timestamp; it changes with D2R patches and D2RLoader releases) and changes nothing on any other
// (build_guard_logic.h). The player is told "needs Diablo II: Resurrected 3.3"; stamp and build name go to the log only.
//
// v0.1 (docs/plugin-plan.md "mxl2012-core v0.1 = E + F + A + D (+ G in dev builds)"):
//   E  build guard and its screen notice;
//   F  plugin guard: with a conflicting plugin in the game nothing is installed (other_plugins_logic.h), plus the
//      environment check (a second or old copy of mxl2012-core, D2RLoader's default_mod naming another mod);
//   A  client do 113 = 1.13c's client do 22 for Rock Shock / ParasiteSkill (client_skills.cpp, off word cltdo22);
//   D  stubs in the empty missile client do / server hit slots (missile_stubs.cpp, off word cltdostub);
//   +  D2R's client curse (cltdofunc 30) and client start 18 skip rows without a client missile instead of asserting
//      (client_skills.cpp, off word cltnomis; plan section 11 watch-list, bug #6), and D2R's area aura applier skips a radius
//      below 1 instead of asserting (Median's monster property auras with a blank aurarangecalc, bug #31);
//   +  D2R's item-event skill resolver answers 0 for a skill without ItemEffect instead of asserting (Median's item properties
//      that fire such a skill keep their tooltip lines; item_effect.cpp, off word itemeffect, bug #40);
//   +  D2R's skill remove returns at once for a unit that owns no skill instead of asserting `ptSkill` (the level-0 sumskills of
//      Median's pets without skills: Batstrike's bats, Rampagor, Lamia; skill_remove.cpp, off word skillremove, bug #15);
//   +  D2R's damage code skips the missing dodge / avoid / evade state list without its `hList` assert (Median gives those
//      chances as plain stats; dodge_list.cpp, off word dodgelist, bug #53);
//   +  D2R's blaze / spider-lay functions (states 13 / 22, where Median keeps shellshock / raptured as 1.13c did) leave a
//      state list without a skill without their range asserts, as 1.14d does (state_lists.cpp, off word statelist, #50 #52);
//   +  a state-22 list without a skill (Median's raptured) gets 1.14d's fixed trail, missile 143 with the level of the unit's
//      skill 173, instead of nothing (melt_trail.cpp, off word melttrail, #52);
//   +  Whirlwind's 1.13c hit rate (srvdofunc 76: Whirlwind, Spin To Win, Danse Macabre, Harvest) instead of D2R 2.4's
//      (whirlwind.cpp, off word whirlwind, #281);
//   +  a second `useitem` cube output (Median's Oil of Duplication) copies output a as 1.13c did, where D2R makes nothing
//      (cube_dupe.cpp, off word cubedupe, #350);
//   +  mercenaries wield only the weapon / shield types of 1.13c's hireling WType1 / WType2 (Rogue bow, Desert polearm / spear,
//      Iron Wolf sword / shield, Barbarian sword); D2R lets every one wield anything (merc_equip.cpp, off word mercequip);
//   +  a worn item's durability loss reaches the client: D2R's wear stores the update's layer argument in 16 bits of an
//      8-byte slot, and the update never took, so the tooltip and Repair All kept the old value until the item was moved
//      (dur_sync.cpp, off word dursync, #433);
//   +  three D2R asserts that 1.14d does not have, skipped on D2R's own path: a monster skill mode without a sequence
//      (Median's `TH` haunts, off word animseq, #74), a monequip row without a body location (flyingscimitar, monequip, #74),
//      a timed buff without an aurastate (Mon Pain Spirit, aurastate, #181) (orig_asserts.cpp);
//   +  D2R's item serializer keeps item levels 100-127 (the 7-bit field's range) instead of writing 99, so drops of Median's
//      level-100+ monsters keep their item level through Save and Exit (item_level.cpp, off word ilvl, #251);
//   +  a runeword tooltip's rune letters without a D2R key (Median's Great Runes Sha .. Shaad, No, On, Xar) read as the gems
//      cell, as 1.14d draws them, instead of "Missing string" / D2R's other texts (rune_letters.cpp, off word runeletter, #334);
//   +  skill tooltip lines that D2R builds from 1.13c's hard-coded labels read in 1.13c's words ("Fire Damage: 12-15") instead
//      of D2R's raw printf labels ("Fire Damage: %d-%d12-15") (skill_text.cpp, off word skilltext, #396);
//   +  D2R's client sound record lookups skip a sound id outside the loaded sounds.txt, and a sounds table short of ours (the
//      start that builds D2RLoader's table cache) gets a "start again" notice (sound_guard.cpp, off word soundguard, crash-audit C17);
//   +  the Barbarian's spirit summons (Guardian / Defender / Protector Spirit, drawn with D2R's HD Ancients) do not play the
//      Ancients' HD death roar each time one dies or is cast again (sound_guard.cpp, off word spiritsound, #502);
//   +  D2R's unit translation event handler skips an event with an unreadable payload (translation_guard.cpp, off word
//      transguard, crash-audit C14);
//   +  a totem (pettype `totemic`) that D2R brings onto its owner's own sub-tile (the owner's move or the pet warp; Median's
//      immobile totems after Bend the Shadows) is moved to a free spot of a ring round the owner instead of staying stacked; other
//      pets keep D2R's placement (pet_spread.cpp, off word petspread, #493);
//   +  misc pSpell 10 items other than the Book of Skill (Median's Apple) cast skill 47 `Apple Healing Spell` on the user as
//      1.13c's item spell 10, where D2R runs its Book of Skill and refuses them (apple_use.cpp, off word appleuse, #499);
//   +  "Baal says: ..." (the voice file baallaugh1, which Median gives to many skills and missiles) goes into the chat at most
//      once every 30 s; the laugh itself still plays (vo_chat.cpp, off word vochat, #508);
//   +  a unit other than the player that the client's unit reassign (server command 0x15) leaves without a client room is left
//      so instead of D2R's "Could not get act!" end of the game (reassign_guard.cpp, off word reassign, #511 / #292);
//   G  the test harness and its gameplay verbs (dev builds only; testharness.cpp, harness_cmds.cpp).
// Other ports' Median / D2Sigma parts are not part of it (docs/plugin-plan.md section 11).
#include <D2RLPlugin/api.h>

#include "apple_use.h"
#include "build_guard.h"
#include "build_guard_logic.h"
#include "client_skills.h"
#include "cube_dupe.h"
#include "dodge_list.h"
#include "dur_sync.h"
#include "env_guard_logic.h"
#include "item_effect.h"
#include "item_level.h"
#include "lvlup_ui.h"
#include "melt_trail.h"
#include "missile_stubs.h"
#include "orig_asserts.h"
#include "reassign_guard.h"
#include "orig_asserts_logic.h"
#include "other_plugins_logic.h"
#include "pet_spread.h"
#include "rune_letters.h"
#include "save_mode.h"
#include "skill_remove.h"
#include "skill_text.h"
#include "sound_guard.h"
#include "state_lists.h"
#include "testharness.h"
#include "whirlwind.h"
#include "merc_equip.h"
#include "translation_guard.h"
#include "vo_chat.h"

#include <windows.h>
#include <tlhelp32.h>

#include <cctype>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

constexpr const char* PluginVersion = "0.1.7";
constexpr uint32_t ExpectedImage = build_guard::ExpectedImage;  // TimeDateStamp of the dumped image (D2R 3.3.0 build 93847, D2RLoader 1.3.1)
#ifdef MXL_RELEASE
constexpr const char* BuildKind = "release";  // cmake -DMXL_RELEASE=ON: no test harness compiled in
#else
constexpr const char* BuildKind = "dev";
#endif
constexpr const char* OffNote = "off: left out by mxl2012-core-off.txt";

const D2RL::PluginContext* g_context = nullptr;

constexpr D2RL::PluginInfo Info {
	.infoSize    = D2RL::PluginInfoSize,
	.abiVersion  = D2RL_PLUGIN_ABI_VERSION,
	.id          = "mxl2012-core",
	.name        = "D2R-XL 2012 core",
	.version     = PluginVersion,
	.author      = "mxl2012-d2r",
	.description = "Engine support for D2R-XL 2012, the Median XL 2012 port (Diablo II: Resurrected 3.3).",
	.flags       = D2RL::PluginFlags::Shared | D2RL::PluginFlags::ModScopedOnly | D2RL::PluginFlags::NativeHooks,
};

auto ImageStamp(const D2RL::PluginContext* context) noexcept -> uint32_t {
	if (context->exeBase == 0) {
		return 0;
	}
	const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(context->exeBase);
	const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(context->exeBase + dos->e_lfanew);
	return nt->FileHeader.TimeDateStamp;
}

// D2RLoader's build name ("93847"), null when its context is too old to carry the field.
auto BuildName(const D2RL::PluginContext* context) noexcept -> const char* {
	return context->contextSize >= offsetof(D2RL::PluginContext, buildName) + sizeof(context->buildName) ? context->buildName : nullptr;
}

// Every hook and patch belongs to the dumped image (build_guard_logic.h); on any other build none goes in.
auto BuildMatches(const D2RL::PluginContext* context) noexcept -> bool {
	return context->exeBase != 0 && build_guard::Matches(ImageStamp(context), BuildName(context));
}

char g_wrongBuild[256] = "";  // the message for a player on another build, empty on build 93847
char g_conflict[256] = "";    // the message when a conflicting plugin is in the game (nothing installed), else empty

// Diagnosis switch: mxl2012-core-off.txt next to the DLL lists parts to leave out (any of: otherplugins envguard
// pluginguard cltdo22 cltdostub cltnomis itemeffect skillremove dodgelist statelist melttrail whirlwind cubedupe animseq monequip aurastate ilvl runeletter skilltext mercequip dursync soundguard spiritsound transguard lvlupui petspread appleuse vochat reassign savemode), separated by spaces, commas or lines. Off words are letters and digits only.
char g_offList[256] = "";

void ReadOffList() noexcept {
	HMODULE self = nullptr;
	char path[MAX_PATH] = "";
	if (!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
	                        reinterpret_cast<LPCSTR>(&ReadOffList), &self) ||
	    GetModuleFileNameA(self, path, MAX_PATH) == 0) {
		return;
	}
	char* slash = std::strrchr(path, '\\');
	if (slash == nullptr || static_cast<size_t>(slash - path) + 24 >= sizeof(path)) {
		return;
	}
	strcpy_s(slash + 1, sizeof(path) - static_cast<size_t>(slash + 1 - path), "mxl2012-core-off.txt");
	FILE* f = nullptr;
	if (fopen_s(&f, path, "rb") != 0 || f == nullptr) {
		return;
	}
	const size_t n = std::fread(g_offList, 1, sizeof(g_offList) - 1, f);
	g_offList[n] = '\0';
	std::fclose(f);
	for (char* c = g_offList; *c != '\0'; ++c) {
		*c = (*c >= 'A' && *c <= 'Z') ? static_cast<char>(*c - 'A' + 'a') : (std::isalnum(static_cast<unsigned char>(*c)) ? *c : ' ');
	}
}

auto Off(const char* part) noexcept -> bool {
	const size_t len = std::strlen(part);
	for (const char* p = std::strstr(g_offList, part); p != nullptr; p = std::strstr(p + 1, part)) {
		if ((p == g_offList || p[-1] == ' ') && (p[len] == ' ' || p[len] == '\0')) {
			return true;
		}
	}
	return false;
}

// Console line; with the test harness on it is also appended to mxl2012-testharness-console.txt (the console panel cannot
// be opened by an unattended run, see testharness.cpp).
void Say(const D2RL::ConsoleCommandContext* command, const char* text) noexcept {
	command->plugin->WriteConsoleMessage(text);
	HarnessEcho(text);
}

// The other D2RLoader plugins loaded into this process (modules under a ...\d2rloader\plugins\ folder, mod or game-wide;
// other_plugins_logic.h). Read when `mxl2012` runs: the game-wide plugins load after the mod's, so at our load they are not there yet.
void OtherPlugins(char* out, size_t n) noexcept {
	std::snprintf(out, n, "other plugins: none");
	HMODULE self = nullptr;
	GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
	                   reinterpret_cast<LPCWSTR>(&OtherPlugins), &self);
	HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, GetCurrentProcessId());
	if (snap == INVALID_HANDLE_VALUE) {
		std::snprintf(out, n, "other plugins: not readable (module snapshot failed, error %lu)", GetLastError());
		return;
	}
	MODULEENTRY32W me{};
	me.dwSize = sizeof(me);
	int found = 0;
	size_t len = std::strlen("other plugins:");
	for (BOOL ok = Module32FirstW(snap, &me); ok; ok = Module32NextW(snap, &me)) {
		char path[MAX_PATH * 3];
		char label[160];
		if (me.hModule == self || WideCharToMultiByte(CP_UTF8, 0, me.szExePath, -1, path, sizeof(path), nullptr, nullptr) <= 0 ||
		    !other_plugins::Label(path, label, sizeof(label))) {
			continue;
		}
		const int w = std::snprintf(out + len, len < n ? n - len : 0, "%s %s", found ? "," : "", label);
		len += w > 0 ? static_cast<size_t>(w) : 0;
		++found;
		if (len >= n) {
			break;
		}
	}
	CloseHandle(snap);
	if (found == 0) {
		std::snprintf(out, n, "other plugins: none");
	}
}

// Which mxl2012-core runs, from where, for which mod (env_guard_logic.h): an old copy in the game-wide plugins folder, or
// D2RLoader's default_mod naming another mod folder, runs another build than the one installed.
char g_selfPath[MAX_PATH * 3] = "";
char g_envReport[1024] = "ok";  // the `environment` line of `mxl2012`

void ModulePathUtf8(HMODULE module, char* out, size_t n) noexcept {
	wchar_t w[MAX_PATH * 2] = L"";
	const DWORD len = GetModuleFileNameW(module, w, static_cast<DWORD>(sizeof(w) / sizeof(w[0])));
	if (len == 0 || WideCharToMultiByte(CP_UTF8, 0, w, -1, out, static_cast<int>(n), nullptr, nullptr) <= 0) {
		out[0] = '\0';
	}
}

// Other modules of this process that are mxl2012-core too (file mxl2012-core*.dll, or D2RLoaderGetPluginInfo with id
// "mxl2012-core"); `first` gets the path of the first one.
auto OtherInstances(char* first, size_t n) noexcept -> int {
	first[0] = '\0';
	HMODULE self = nullptr;
	GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
	                   reinterpret_cast<LPCWSTR>(&OtherInstances), &self);
	HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, GetCurrentProcessId());
	if (snap == INVALID_HANDLE_VALUE) {
		return 0;
	}
	MODULEENTRY32W me{};
	me.dwSize = sizeof(me);
	int found = 0;
	for (BOOL ok = Module32FirstW(snap, &me); ok; ok = Module32NextW(snap, &me)) {
		char path[MAX_PATH * 3];
		if (me.hModule == self || WideCharToMultiByte(CP_UTF8, 0, me.szExePath, -1, path, sizeof(path), nullptr, nullptr) <= 0) {
			continue;
		}
		const char* slash = std::strrchr(path, '\\');
		const char* file = slash != nullptr ? slash + 1 : path;
		const char* id = nullptr;
		if (other_plugins::PluginDirAt(path) >= 0) {  // only D2RLoader plugins are asked for their info
			using GetInfo = const D2RL::PluginInfo* (*)();
			if (auto get = reinterpret_cast<GetInfo>(reinterpret_cast<void*>(GetProcAddress(me.hModule, "D2RLoaderGetPluginInfo")))) {
				const D2RL::PluginInfo* info = get();
				if (info != nullptr && info->infoSize >= offsetof(D2RL::PluginInfo, id) + sizeof(info->id)) {
					id = info->id;
				}
			}
		}
		if (env_guard::IsOurModule(file, id) && found++ == 0) {
			std::snprintf(first, n, "%s", path);
		}
	}
	CloseHandle(snap);
	return found;
}

// The PluginInfo id of a module loaded from a D2RLoader plugin folder, or null.
auto PluginIdOf(HMODULE module, const char* path) noexcept -> const char* {
	if (other_plugins::PluginDirAt(path) < 0) {
		return nullptr;
	}
	using GetInfo = const D2RL::PluginInfo* (*)();
	auto get = reinterpret_cast<GetInfo>(reinterpret_cast<void*>(GetProcAddress(module, "D2RLoaderGetPluginInfo")));
	const D2RL::PluginInfo* info = get != nullptr ? get() : nullptr;
	return info != nullptr && info->infoSize >= offsetof(D2RL::PluginInfo, id) + sizeof(info->id) ? info->id : nullptr;
}

// A conflicting plugin in this game (other_plugins_logic.h IsConflictingPlugin): loaded already (a plugin of the same folder that loaded
// first, or any later check), or waiting on disk in a folder D2RLoader loads plugins from (the game-wide
// <game>\d2rloader\plugins loads after the mod's, so at our load it is only a file). `where` gets the folder as a player
// knows it, `file` its file name. False when there is none.
auto FindConflictingPlugin(char* where, size_t n, char* file, size_t fn) noexcept -> bool {
	where[0] = '\0';
	file[0] = '\0';
	HMODULE self = nullptr;
	GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
	                   reinterpret_cast<LPCWSTR>(&FindConflictingPlugin), &self);
	if (HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, GetCurrentProcessId()); snap != INVALID_HANDLE_VALUE) {
		MODULEENTRY32W me{};
		me.dwSize = sizeof(me);
		bool found = false;
		for (BOOL ok = Module32FirstW(snap, &me); ok && !found; ok = Module32NextW(snap, &me)) {
			char path[MAX_PATH * 3];
			if (me.hModule == self || WideCharToMultiByte(CP_UTF8, 0, me.szExePath, -1, path, sizeof(path), nullptr, nullptr) <= 0) {
				continue;
			}
			const char* slash = std::strrchr(path, '\\');
			if (other_plugins::IsConflictingPlugin(slash != nullptr ? slash + 1 : path, PluginIdOf(me.hModule, path))) {
				std::snprintf(file, fn, "%s", slash != nullptr ? slash + 1 : path);
				char label[160];  // "<file> (global)" or "<file> (mod <name>)"
				const char* mod = other_plugins::Label(path, label, sizeof(label)) ? std::strstr(label, "(mod ") : nullptr;
				if (mod != nullptr) {
					std::snprintf(where, n, "mods\\%.*s\\d2rloader\\plugins", static_cast<int>(std::strlen(mod + 5) - 1), mod + 5);
				} else {
					std::snprintf(where, n, "d2rloader\\plugins");
				}
				found = true;
			}
		}
		CloseHandle(snap);
		if (found) {
			return true;
		}
	}
	// Not loaded (yet): the files D2RLoader would load. The game-wide folder, then the folder of this DLL (the mod's).
	wchar_t dir[MAX_PATH * 2] = L"";
	const struct {
		HMODULE module;
		const wchar_t* rest;
		const char* label;
	} places[] = {{nullptr, L"\\d2rloader\\plugins\\*.dll", "d2rloader\\plugins"}, {self, L"\\*.dll", "the mod's d2rloader\\plugins"}};
	for (const auto& p : places) {
		const DWORD len = GetModuleFileNameW(p.module, dir, MAX_PATH);
		wchar_t* slash = len > 0 ? std::wcsrchr(dir, L'\\') : nullptr;
		if (slash == nullptr || static_cast<size_t>(slash - dir) + std::wcslen(p.rest) + 1 >= sizeof(dir) / sizeof(dir[0])) {
			continue;
		}
		wcscpy_s(slash, sizeof(dir) / sizeof(dir[0]) - static_cast<size_t>(slash - dir), p.rest);
		WIN32_FIND_DATAW fd{};
		HANDLE find = FindFirstFileW(dir, &fd);
		if (find == INVALID_HANDLE_VALUE) {
			continue;
		}
		bool found = false;
		do {
			char name[MAX_PATH * 3];
			if ((fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) == 0 &&
			    WideCharToMultiByte(CP_UTF8, 0, fd.cFileName, -1, name, sizeof(name), nullptr, nullptr) > 0 &&
			    other_plugins::IsConflictingPlugin(name, nullptr)) {
				std::snprintf(where, n, "%s", p.label);
				std::snprintf(file, fn, "%s", name);
				found = true;
			}
		} while (!found && FindNextFileW(find, &fd));
		FindClose(find);
		if (found) {
			return true;
		}
	}
	return false;
}

// Checks and reports: the log, `mxl2012`, and the screen notice unless the build guard already shows one.
void CheckEnvironment(bool atLoad) noexcept {
	if (g_context == nullptr) {
		return;
	}
	char game[MAX_PATH * 3];
	ModulePathUtf8(nullptr, game, sizeof(game));
	if (char* slash = std::strrchr(game, '\\')) {
		*slash = '\0';
	}
	char other[MAX_PATH * 3];
	const int others = OtherInstances(other, sizeof(other));
	const char* mod = g_context->activeMod;
	const env_guard::Verdict v = env_guard::Check(g_selfPath, game, mod, others);
	char detail[sizeof(g_envReport)];
	env_guard::Detail(detail, sizeof(detail), v, g_selfPath, mod, other);
	std::snprintf(g_envReport, sizeof(g_envReport), "%s", v.Ok() ? "ok" : detail);
	if (v.Ok()) {
		if (!atLoad) {
			g_context->LogInfo("mxl2012-core: environment ok (no second mxl2012-core after the game-wide plugins loaded)");
		}
		return;
	}
	char line[sizeof(g_envReport) + 32];
	std::snprintf(line, sizeof(line), "mxl2012-core: environment %s", detail);
	g_context->LogWarn(line);
	if (g_wrongBuild[0] == '\0' && g_conflict[0] == '\0') {
		char notice[256];
		env_guard::Notice(notice, sizeof(notice), v, PluginVersion, mod);
		if (!ShowNotice(g_context, notice)) {
			g_context->LogWarn("mxl2012-core: no overlay service, the environment warning is in this log only");
		}
	}
}

// What the parts installed (the `mxl2012` lines); empty for a part that did not run.
char g_cltDoReport[256] = "";
char g_stubReport[192] = "";
char g_noMissileReport[256] = "";
char g_itemEffectReport[160] = "";
char g_skillRemoveReport[160] = "";
char g_dodgeListReport[160] = "";
char g_stateListReport[160] = "";
char g_meltTrailReport[160] = "";
char g_whirlwindReport[160] = "";
char g_cubeDupeReport[160] = "";
char g_itemLevelReport[160] = "";
char g_runeLetterReport[192] = "";
char g_skillTextReport[160] = "";
char g_mercEquipReport[200] = "";
char g_durSyncReport[160] = "";
char g_origAssertReport[orig_asserts::BlockCount][160] = {};
char g_soundGuardReport[256] = "";
char g_spiritSoundReport[160] = "";
char g_transGuardReport[192] = "";
char g_lvlUpUiReport[192] = "";
char g_petSpreadReport[192] = "";
char g_appleUseReport[192] = "";
char g_voChatReport[160] = "";
char g_reassignReport[192] = "";
char g_harnessReport[192] = "";
char g_saveModeReport[MAX_PATH + 160] = "";
bool g_partsInstalled = false;

// Start-up log line of the other plugins: D2RLoader loads the game-wide plugins after the mod's, so a one-shot thread waits
// until the loader is done (its plugin list is in d2rloader.log too). The environment check runs again then: a stray
// game-wide mxl2012-core loads only after this one; so does the plugin guard, for a conflicting plugin the file check at load missed
// (another file name): the parts are in by then, so it can only say so.
DWORD WINAPI LogOtherPluginsLater(LPVOID) {
	Sleep(15000);
	if (!Off("envguard")) {
		CheckEnvironment(false);
	}
	if (g_partsInstalled && !Off("pluginguard") && g_context != nullptr) {
		char where[160];
		char file[MAX_PATH * 3];
		if (FindConflictingPlugin(where, sizeof(where), file, sizeof(file))) {
			other_plugins::ConflictNotice(g_conflict, sizeof(g_conflict), PluginVersion, file, where);
			char line[640];
			std::snprintf(line, sizeof(line), "mxl2012-core: another plugin (%s) loaded after mxl2012-core's parts went in (%s); both write the same table slots. %s",
			              file, where, g_conflict);
			g_context->LogError(line);
			ShowNotice(g_context, g_conflict);
		}
	}
	if (Off("otherplugins")) {
		return 0;
	}
	char line[384];
	OtherPlugins(line, sizeof(line));
	if (g_context != nullptr) {
		char msg[400];
		std::snprintf(msg, sizeof(msg), "mxl2012-core: %s", line);
		g_context->LogInfo(msg);
	}
	return 0;
}

// A status line for `mxl2012`: "<part> <report>" or "<part> off: left out by mxl2012-core-off.txt".
void SayPart(const D2RL::ConsoleCommandContext* command, const char* part, const char* report) noexcept {
	char line[448];
	std::snprintf(line, sizeof(line), "%s %s", part, Off(part) ? OffNote : (report[0] != '\0' ? report : "not installed"));
	Say(command, line);
}

auto Mxl2012Command(D2R::Game::Client* client, const D2RL::ConsoleCommandContext* command, void* userData) noexcept
	-> D2RL::ConsoleCommandResult {
	(void)client;
	(void)userData;
	if (command == nullptr || command->plugin == nullptr || g_context == nullptr) {
		return D2RL::ConsoleCommandResult::Failed;
	}
	char line[384];
	{
		// What the player reads names the game version only (docs/plugin-plan.md 1.2); stamp and build name go to the log.
		char first[384 + sizeof(g_selfPath)];
		std::snprintf(first, sizeof(first), "mxl2012-core %s (%s) | game: %s | mod %s | file %s", PluginVersion, BuildKind,
		              BuildMatches(g_context) ? "Diablo II: Resurrected 3.3, engine changes on" : "a different version, engine changes off",
		              g_context->activeMod ? g_context->activeMod : "?", g_selfPath[0] ? g_selfPath : "?");
		Say(command, first);
		std::snprintf(line, sizeof(line), "mxl2012-core: D2R %s | image 0x%08x (expects 0x%08x, %s) | buildName %s | exe base 0x%llx",
		              g_context->buildVersion ? g_context->buildVersion : "?", ImageStamp(g_context), ExpectedImage,
		              BuildMatches(g_context) ? "match" : "MISMATCH, hooks off", BuildName(g_context) ? BuildName(g_context) : "(none)",
		              static_cast<unsigned long long>(g_context->exeBase));
		g_context->LogInfo(line);
		char env[sizeof(g_envReport) + 16];
		std::snprintf(env, sizeof(env), "environment %s", Off("envguard") ? OffNote : g_envReport);
		Say(command, env);
		if (std::strcmp(g_envReport, "ok") != 0) {
			g_context->LogWarn(env);
		}
		if (!Off("savemode") && g_saveModeReport[0] != '\0') {
			std::snprintf(line, sizeof(line), "savemode %s; %d cancelled saves since start", g_saveModeReport, SaveModeFailures());
			Say(command, line);
		}
	}
	if (!Off("otherplugins")) {
		OtherPlugins(line, sizeof(line));
		Say(command, line);
		g_context->LogInfo(line);  // also in the log, for crash reports
	}
	if (g_wrongBuild[0] != '\0') {
		Say(command, g_wrongBuild);
		return D2RL::ConsoleCommandResult::Handled;  // nothing below was installed
	}
	std::snprintf(line, sizeof(line), "pluginguard %s", Off("pluginguard") ? OffNote : (g_conflict[0] != '\0' ? g_conflict : "ok: no conflicting plugin in the game"));
	Say(command, line);
	if (!g_partsInstalled) {
		return D2RL::ConsoleCommandResult::Handled;  // refused: nothing below was installed
	}
	SayPart(command, "cltdo22", g_cltDoReport);
	long cltDo = 0, srvHit = 0;
	MissileStubHits(&cltDo, &srvHit);
	std::snprintf(line, sizeof(line), "%s; missile rows that ran into a stub: client do %ld, server hit %ld", g_stubReport, cltDo, srvHit);
	SayPart(command, "cltdostub", line);
	std::snprintf(line, sizeof(line), "%s; calls skipped %ld, area aura calls skipped %ld", g_noMissileReport, ClientNoMissileSkips(), AreaAuraSkips());
	SayPart(command, "cltnomis", line);
	std::snprintf(line, sizeof(line), "%s; calls answered %ld (last skill %ld)", g_itemEffectReport, ItemEffectSkips(), ItemEffectLastSkill());
	SayPart(command, "itemeffect", line);
	std::snprintf(line, sizeof(line), "%s; calls answered %ld (last skill %ld)", g_skillRemoveReport, SkillRemoveSkips(), SkillRemoveLastSkill());
	SayPart(command, "skillremove", line);
	SayPart(command, "dodgelist", g_dodgeListReport);
	SayPart(command, "statelist", g_stateListReport);
	long trailsClient = 0, trailsServer = 0;
	MeltTrailCounts(&trailsClient, &trailsServer);
	std::snprintf(line, sizeof(line), "%s; trails made: client %ld, server %ld", g_meltTrailReport, trailsClient, trailsServer);
	SayPart(command, "melttrail", line);
	long wwCalls = 0, wwD2R = 0, wwDelay = 0;
	WhirlwindStats(&wwCalls, &wwD2R, &wwDelay);
	std::snprintf(line, sizeof(line), "%s; hit delays answered %ld (last: D2R %ld frames -> %ld)", g_whirlwindReport, wwCalls, wwD2R, wwDelay);
	SayPart(command, "whirlwind", line);
	long dupMade = 0, dupNoRoom = 0, dupFailed = 0;
	CubeDupeCounts(&dupMade, &dupNoRoom, &dupFailed);
	std::snprintf(line, sizeof(line), "%s; copies made %ld, no room %ld, refused %ld", g_cubeDupeReport, dupMade, dupNoRoom, dupFailed);
	SayPart(command, "cubedupe", line);
	SayPart(command, "ilvl", g_itemLevelReport);
	long lettersDrawn = 0, lettersKept = 0;
	RuneLetterCounts(&lettersDrawn, &lettersKept);
	std::snprintf(line, sizeof(line), "%s; letters drawn from the cell %ld, D2R keys kept %ld", g_runeLetterReport, lettersDrawn, lettersKept);
	SayPart(command, "runeletter", line);
	std::snprintf(line, sizeof(line), "%s; labels cut %ld", g_skillTextReport, SkillTextCuts());
	SayPart(command, "skilltext", line);
	long mercChecked = 0, mercRefused = 0;
	MercEquipStats(&mercChecked, &mercRefused);
	std::snprintf(line, sizeof(line), "%s; mercenary tests %ld, refused %ld", g_mercEquipReport, mercChecked, mercRefused);
	SayPart(command, "mercequip", line);
	SayPart(command, "dursync", g_durSyncReport);
	for (size_t i = 0; i < orig_asserts::BlockCount; ++i) {
		SayPart(command, orig_asserts::Blocks[i].word, g_origAssertReport[i]);
	}
	{
		char status[192];
		SoundGuardStatus(status, sizeof(status));
		std::snprintf(line, sizeof(line), "%s | %s", g_soundGuardReport, status);
		SayPart(command, "soundguard", line);
	}
	std::snprintf(line, sizeof(line), "%s; plays skipped %ld", g_spiritSoundReport, SpiritSoundSkips());
	SayPart(command, "spiritsound", line);
	unsigned events = 0, skipped = 0;
	TranslationGuardStats(&events, &skipped);
	std::snprintf(line, sizeof(line), "%s; events %u, skipped %u", g_transGuardReport, events, skipped);
	SayPart(command, "transguard", line);
	long lvlUpdates = 0, lvlDraws = 0;
	LevelUpUiCounts(&lvlUpdates, &lvlDraws);
	std::snprintf(line, sizeof(line), "%s; grey legacy buttons updated %ld times, draws %ld", g_lvlUpUiReport, lvlUpdates, lvlDraws);
	SayPart(command, "lvlupui", line);
	long petGathers = 0, petWarps = 0, petStacked = 0, petSpread = 0, petKept = 0, petClass = -1;
	PetSpreadCounts(&petGathers, &petWarps, &petStacked, &petSpread, &petKept, &petClass);
	std::snprintf(line, sizeof(line), "%s; owner moves with pets %ld, pet warps %ld, onto the owner %ld, spread %ld, other pets left %ld (last pet class %ld)",
	              g_petSpreadReport, petGathers, petWarps, petStacked, petSpread, petKept, petClass);
	long petShifted = 0, petSecond = 0, petMissed = 0, triesTaken = 0, triesBlocked = 0, triesStill = 0, triesOff = 0;
	PetSpreadTries(&petShifted, &petSecond, &petMissed, &triesTaken, &triesBlocked, &triesStill, &triesOff);
	const size_t petLen = std::strlen(line);
	std::snprintf(line + petLen, sizeof(line) - petLen, "; shifted %ld, pass 2 %ld, missed %ld (ring tries taken %ld, blocked %ld, not moved %ld, moved off %ld)",
	              petShifted, petSecond, petMissed, triesTaken, triesBlocked, triesStill, triesOff);
	SayPart(command, "petspread", line);
	long appleCasts = 0, appleRefused = 0, appleBooks = 0;
	AppleUseCounts(&appleCasts, &appleRefused, &appleBooks);
	std::snprintf(line, sizeof(line), "%s; casts %ld, refused %ld, Books of Skill left to D2R %ld", g_appleUseReport, appleCasts, appleRefused, appleBooks);
	SayPart(command, "appleuse", line);
	long voPrinted = 0, voDropped = 0;
	VoChatCounts(&voPrinted, &voDropped);
	std::snprintf(line, sizeof(line), "%s; Baal laugh lines printed %ld, left out %ld", g_voChatReport, voPrinted, voDropped);
	SayPart(command, "vochat", line);
	unsigned reSeen = 0, reLeft = 0, reEnded = 0;
	ReassignGuardStats(&reSeen, &reLeft, &reEnded);
	std::snprintf(line, sizeof(line), "%s; commands %u, units left without a room %u, the player without a room %u", g_reassignReport, reSeen, reLeft, reEnded);
	SayPart(command, "reassign", line);
	std::snprintf(line, sizeof(line), "client wall calls %ld", ClientWallCalls());
	Say(command, line);
	std::snprintf(line, sizeof(line), "testharness %s", g_harnessReport[0] != '\0' ? g_harnessReport : "off");
	Say(command, line);
	return D2RL::ConsoleCommandResult::Handled;
}

}  // namespace

D2RL_PLUGIN_EXPORT auto D2RLoaderGetPluginInfo() noexcept -> const D2RL::PluginInfo* {
	return &Info;
}

D2RL_PLUGIN_EXPORT auto D2RLoaderLoadPlugin(const D2RL::PluginContext* context) noexcept -> bool {
	if (context == nullptr) {
		return false;
	}
	g_context = context;
	{
		HMODULE self = nullptr;
		GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
		                   reinterpret_cast<LPCWSTR>(&ModulePathUtf8), &self);
		ModulePathUtf8(self, g_selfPath, sizeof(g_selfPath));
	}
	char line[256 + sizeof(g_selfPath)];
	std::snprintf(line, sizeof(line), "mxl2012-core %s loaded (mod %s, D2R %s, image 0x%08x%s) from %s", PluginVersion,
	              context->activeMod ? context->activeMod : "?", context->buildVersion ? context->buildVersion : "?",
	              ImageStamp(context), BuildMatches(context) ? "" : "; not the expected image, engine hooks stay off",
	              g_selfPath[0] ? g_selfPath : "?");
	context->LogInfo(line);
	if (!BuildMatches(context)) {
		// Another game build: no hook, patch or harness at all (their addresses are build 93847's). Say why, and keep `mxl2012`.
		build_guard::Message(g_wrongBuild, sizeof(g_wrongBuild), PluginVersion);
		CheckEnvironment(true);  // logged and in `mxl2012`; the screen keeps the wrong-build notice
		context->LogError(g_wrongBuild);
		build_guard::LogDetail(line, sizeof(line), ImageStamp(context), BuildName(context));
		context->LogError(line);
		if (!ShowWrongBuildNotice(context, g_wrongBuild)) {
			context->LogWarn("mxl2012-core: no overlay service, the wrong-build notice is in this log only");
		}
		return context->RegisterConsoleCommand("mxl2012", Mxl2012Command, "D2R-XL 2012 core plugin status.");
	}
	ReadOffList();
	if (g_offList[0] != '\0') {
		std::snprintf(line, sizeof(line), "mxl2012-core: mxl2012-core-off.txt leaves out: %s", g_offList);
		context->LogInfo(line);
	}
	// Plugin guard: with a conflicting plugin in the game nothing goes in (both write the same table slots).
	char where[160], file[MAX_PATH * 3];
	if (!Off("pluginguard") && FindConflictingPlugin(where, sizeof(where), file, sizeof(file))) {
		other_plugins::ConflictNotice(g_conflict, sizeof(g_conflict), PluginVersion, file, where);
		context->LogError(g_conflict);
		if (!ShowNotice(context, g_conflict)) {
			context->LogWarn("mxl2012-core: no overlay service, the conflicting-plugin notice is in this log only");
		}
		if (!Off("envguard")) {
			CheckEnvironment(true);  // logged and in `mxl2012`; the screen keeps the plugin guard's notice
		}
		return context->RegisterConsoleCommand("mxl2012", Mxl2012Command, "D2R-XL 2012 core plugin status.");
	}
	if (!Off("envguard")) {
		CheckEnvironment(true);
	}
	if (!RegisterNotice(context)) {
		context->LogWarn("mxl2012-core: no overlay service, later warnings (environment, conflicting plugin) are in this log only");
	}
	// The save format (D2RLoader's extended format, docs/bugs.md #512) and the watch for cancelled saves; its notice goes over
	// the environment one: a save that does not reach the disk loses progress.
	if (!Off("savemode")) {
		char game[MAX_PATH * 3];
		ModulePathUtf8(nullptr, game, sizeof(game));
		if (char* slash = std::strrchr(game, '\\')) {
			*slash = '\0';
		}
		InstallSaveMode(context, g_selfPath, game, g_saveModeReport, sizeof(g_saveModeReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: savemode %s", g_saveModeReport);
		context->LogInfo(line);
	}
	// Parts, each behind its off word. The empty-slot stubs go in last: they take every slot still empty.
	if (!Off("cltdo22")) {
		InstallClientSkills(context, g_cltDoReport, sizeof(g_cltDoReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: %s", g_cltDoReport);
		context->LogInfo(line);
	}
	if (!Off("cltnomis")) {
		InstallClientNoMissile(context, g_noMissileReport, sizeof(g_noMissileReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: %s", g_noMissileReport);
		context->LogInfo(line);
	}
	if (!Off("itemeffect")) {
		InstallItemEffectGuard(context, g_itemEffectReport, sizeof(g_itemEffectReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: %s", g_itemEffectReport);
		context->LogInfo(line);
	}
	if (!Off("skillremove")) {
		InstallSkillRemoveGuard(context, g_skillRemoveReport, sizeof(g_skillRemoveReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: %s", g_skillRemoveReport);
		context->LogInfo(line);
	}
	if (!Off("dodgelist")) {
		InstallDodgeListGuard(context, g_dodgeListReport, sizeof(g_dodgeListReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: %s", g_dodgeListReport);
		context->LogInfo(line);
	}
	if (!Off("statelist")) {
		InstallStateListGuard(context, g_stateListReport, sizeof(g_stateListReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: %s", g_stateListReport);
		context->LogInfo(line);
	}
	if (!Off("melttrail")) {
		InstallMeltTrail(context, g_meltTrailReport, sizeof(g_meltTrailReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: %s", g_meltTrailReport);
		context->LogInfo(line);
	}
	for (size_t i = 0; i < orig_asserts::BlockCount; ++i) {
		if (!Off(orig_asserts::Blocks[i].word)) {
			InstallOrigAssertGuard(context, i, g_origAssertReport[i], sizeof(g_origAssertReport[i]));
			std::snprintf(line, sizeof(line), "mxl2012-core: %s %s", orig_asserts::Blocks[i].word, g_origAssertReport[i]);
			context->LogInfo(line);
		}
	}
	if (!Off("whirlwind")) {
		InstallWhirlwind(context, g_whirlwindReport, sizeof(g_whirlwindReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: %s", g_whirlwindReport);
		context->LogInfo(line);
	}
	if (!Off("cubedupe")) {
		InstallCubeDupe(context, g_cubeDupeReport, sizeof(g_cubeDupeReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: cubedupe %s", g_cubeDupeReport);
		context->LogInfo(line);
	}
	if (!Off("ilvl")) {
		InstallItemLevel(context, g_itemLevelReport, sizeof(g_itemLevelReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: %s", g_itemLevelReport);
		context->LogInfo(line);
	}
	if (!Off("runeletter")) {
		InstallRuneLetters(context, g_runeLetterReport, sizeof(g_runeLetterReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: runeletter %s", g_runeLetterReport);
		context->LogInfo(line);
	}
	if (!Off("skilltext")) {
		InstallSkillText(context, g_skillTextReport, sizeof(g_skillTextReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: %s", g_skillTextReport);
		context->LogInfo(line);
	}
	if (!Off("mercequip")) {
		InstallMercEquip(context, g_mercEquipReport, sizeof(g_mercEquipReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: %s", g_mercEquipReport);
		context->LogInfo(line);
	}
	if (!Off("dursync")) {
		InstallDurSync(context, g_durSyncReport, sizeof(g_durSyncReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: %s", g_durSyncReport);
		context->LogInfo(line);
	}
	if (!Off("soundguard")) {
		InstallSoundGuard(context, g_soundGuardReport, sizeof(g_soundGuardReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: sound guard %s", g_soundGuardReport);
		context->LogInfo(line);
	}
	if (!Off("spiritsound")) {
		InstallSpiritSound(context, g_spiritSoundReport, sizeof(g_spiritSoundReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: %s", g_spiritSoundReport);
		context->LogInfo(line);
	}
	if (!Off("transguard")) {
		InstallTranslationGuard(context, g_transGuardReport, sizeof(g_transGuardReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: translation guard %s", g_transGuardReport);
		context->LogInfo(line);
	}
	if (!Off("lvlupui")) {
		InstallLevelUpUi(context, g_lvlUpUiReport, sizeof(g_lvlUpUiReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: %s", g_lvlUpUiReport);
		context->LogInfo(line);
	}
	if (!Off("petspread")) {
		InstallPetSpread(context, g_petSpreadReport, sizeof(g_petSpreadReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: %s", g_petSpreadReport);
		context->LogInfo(line);
	}
	if (!Off("appleuse")) {
		InstallAppleUse(context, g_appleUseReport, sizeof(g_appleUseReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: %s", g_appleUseReport);
		context->LogInfo(line);
	}
	if (!Off("vochat")) {
		InstallVoChat(context, g_voChatReport, sizeof(g_voChatReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: %s", g_voChatReport);
		context->LogInfo(line);
	}
	if (!Off("reassign")) {
		InstallReassignGuard(context, g_reassignReport, sizeof(g_reassignReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: %s", g_reassignReport);
		context->LogInfo(line);
	}
	if (!Off("cltdostub")) {
		InstallMissileStubs(context, g_stubReport, sizeof(g_stubReport));
		std::snprintf(line, sizeof(line), "mxl2012-core: %s", g_stubReport);
		context->LogInfo(line);
	}
	g_partsInstalled = true;
	if (HANDLE t = CreateThread(nullptr, 0, LogOtherPluginsLater, nullptr, 0, nullptr)) {
		CloseHandle(t);
	}
	// Off unless mxl2012-testharness.txt exists next to the DLL (unattended test input, testharness.cpp; dev builds only).
	if (InstallTestHarness(context, g_harnessReport, sizeof(g_harnessReport))) {
		std::snprintf(line, sizeof(line), "mxl2012-core: test harness %s", g_harnessReport);
		context->LogInfo(line);
	}
	return context->RegisterConsoleCommand("mxl2012", Mxl2012Command, "D2R-XL 2012 core plugin status.");
}

D2RL_PLUGIN_EXPORT void D2RLoaderUnloadPlugin() noexcept {
	StopTestHarness();
	StopSaveMode();
	g_context = nullptr;
}

#include "app.h"

#include "../core/paths.h"
#include "../core/sevenzip.h"
#include "../core/sha256.h"
#include "http.h"
#include "util.h"

#include <windows.h>

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <ctime>
#include <map>
#include <mutex>
#include <set>
#include <thread>

namespace mxl {
namespace {

std::string Mb(uint64_t b) {  // below 1 MB in KB: a small release is not "0 MB of 0 MB"
	return b < (1 << 20) ? std::to_string((b + 1023) >> 10) + " KB" : std::to_string((b + (1 << 19)) >> 20) + " MB";
}

// "1 file", "3 files"
std::string Count(size_t n, const char* noun) { return std::to_string(n) + " " + noun + (n == 1 ? "" : "s"); }

std::string RandomId() {
	LARGE_INTEGER c;
	QueryPerformanceCounter(&c);
	char s[40];
	std::snprintf(s, sizeof(s), "%08lx%016llx", GetCurrentProcessId(), static_cast<unsigned long long>(c.QuadPart));
	return s;
}

std::string Lower(std::string s) {
	for (char& c : s)
		c = char(std::tolower(uint8_t(c)));
	return s;
}

bool DirEmpty(const std::wstring& dir) {
	WIN32_FIND_DATAW fd;
	HANDLE h = FindFirstFileW(LongPath(JoinPath(dir, L"*")).c_str(), &fd);
	if (h == INVALID_HANDLE_VALUE)
		return true;
	bool empty = true;
	do {
		std::wstring n = fd.cFileName;
		empty = n == L"." || n == L"..";
	} while (empty && FindNextFileW(h, &fd));
	FindClose(h);
	return empty;
}

void RecordFile(Json& files, const std::wstring& dst, const std::string& path, const std::string& sha) {
	uint64_t size = 0, mtime = 0;
	FileSize(dst, size, &mtime);
	Json rec = Json::Object();
	rec.Set("size", size).Set("mtime", std::to_string(mtime)).Set("sha256", sha);
	files.Set(path, rec);
}

// Move `from` onto `to` (same volume): the old file stays in place until the new one is complete.
bool MoveInto(const std::wstring& from, const std::wstring& to) {
	MakeDirs(ParentDir(to));
	return MoveFileExW(LongPath(from).c_str(), LongPath(to).c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
}

std::string NotWritable(const std::wstring& dir, DWORD code) {
	std::string s = "Cannot write into " + Utf8(dir) + ": " + Utf8(LastErrorText(code));
	if (code == ERROR_ACCESS_DENIED)
		s += " Run the D2R-XL 2012 Downloader as administrator (right-click it, Run as administrator), or give your Windows "
		     "user write access to the D2R folder.";
	return s;
}

void Pause(int attempt, const std::atomic<bool>& cancel) {
	for (int waited = 0; attempt && waited < (1000 << attempt) && !cancel.load(); waited += 100)
		Sleep(100);  // 2, 4, 8, 16 s between attempts: a dropped line often comes back
}

// Copies of our plugin outside mods\<ourMod> (docs/bugs.md #53): in <D2R>\d2rloader\plugins (loads with every mod) and
// in mods\<other>\d2rloader\plugins (loads with that mod), by file name or version resource.
std::vector<Launcher::View::StrayPlugin> FindStrayPlugins(const std::wstring& d2r, const std::string& ourMod) {
	std::vector<std::wstring> dirs = {LR"(d2rloader\plugins)"};
	WIN32_FIND_DATAW fd;
	HANDLE h = FindFirstFileW(LongPath(JoinPath(d2r, LR"(mods\*)")).c_str(), &fd);
	if (h != INVALID_HANDLE_VALUE) {
		do {
			std::wstring n = fd.cFileName;
			if ((fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) && !(fd.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) && n != L"." &&
			    n != L".." && Lower(Utf8(n)) != Lower(ourMod))
				dirs.push_back(L"mods\\" + n + LR"(\d2rloader\plugins)");
		} while (FindNextFileW(h, &fd));
		FindClose(h);
	}
	std::vector<Launcher::View::StrayPlugin> out;
	for (const auto& rel : dirs) {
		std::wstring dir = JoinPath(d2r, rel);
		if (!DirExists(dir))
			continue;
		for (const std::string& f : ListFilesUnder(dir)) {
			std::string r = Utf8(rel) + "\\" + f;
			std::replace(r.begin(), r.end(), '/', '\\');
			Launcher::View::StrayPlugin sp;
			sp.place = PluginPlaceOf(r, ourMod, &sp.mod);
			if (sp.place != PluginPlace::GameWide && sp.place != PluginPlace::OtherMod)
				continue;
			std::string name = f.substr(f.find_last_of('/') == std::string::npos ? 0 : f.find_last_of('/') + 1), product, description;
			sp.path = JoinPath(dir, Wide(f));
			if (Lower(name).size() > 4 && Lower(name).substr(name.size() - 4) == ".dll")
				FileVersionStrings(sp.path, product, description);
			if (!IsOurPluginFile(name, product, description))
				continue;
			sp.rel = r;
			out.push_back(sp);
		}
	}
	return out;
}

std::string Today() {
	std::time_t t = std::time(nullptr);
	std::tm tm{};
	localtime_s(&tm, &t);
	char d[16];
	std::strftime(d, sizeof(d), "%Y-%m-%d", &tm);
	return d;
}

// "D2R.exe is running from <dir>. Close the game first." or "".
std::string GameRunning(const std::wstring& d2rDir) {
	auto running = ProcessesUnder(d2rDir);
	if (running.empty())
		return "";
	return Utf8(running.front().exe.substr(running.front().exe.find_last_of(LR"(\/)") + 1)) + " is running from " + Utf8(d2rDir) +
	       ". Close the game first.";
}

}  // namespace

bool OfficialMedianXLFolder(const std::wstring& dir) {
	return OfficialMedianXLPath(Utf8(dir), Utf8(KnownFolder(0)), Utf8(KnownFolder(3)));
}

Launcher::Launcher(Options o) : opt_(std::move(o)) {
	if (opt_.dataDir.empty() || OfficialMedianXLFolder(opt_.dataDir))
		opt_.dataDir = Wide(DefaultDataDir(Utf8(KnownFolder(0))));
	statePath_ = JoinPath(opt_.dataDir, L"launcher.json");
	LoadState();
	if (opt_.site.empty())
		opt_.site = state_["site"].Str(DefaultSite);
	if (opt_.channel.empty())
		opt_.channel = state_["channel"].Str(DefaultChannel);
	siteRoot_ = SiteRoot(opt_.site);
}

void Launcher::Report(const std::string& text, double fraction) {
	Log(text);
	if (onProgress)
		onProgress({text, fraction});
}

bool Launcher::LoadState() {
	std::string text, err;
	state_ = Json::Object();
	if (!ReadWholeFile(statePath_, text))
		return false;
	Json j;
	if (!Json::Parse(text, j, err) || !j.IsObject()) {
		Log("state file unreadable (" + err + "), starting over: " + Utf8(statePath_));
		return false;
	}
	state_ = j;
	return true;
}

bool Launcher::SaveState() {
	state_.Set("launcher", LauncherVersion);
	state_.Set("site", opt_.site.empty() ? state_["site"].Str(DefaultSite) : opt_.site);
	state_.Set("channel", opt_.channel.empty() ? state_["channel"].Str(DefaultChannel) : opt_.channel);
	MakeDirs(opt_.dataDir);
	return WriteFileAtomic(statePath_, state_.Dump());
}

std::string Launcher::ModFolder() const {
	return ProductFolder;
}

std::wstring Launcher::ModDir() const {
	return d2rDir_.empty() ? L"" : Wide(ModTargetDir(Utf8(d2rDir_), ModFolder()));
}

bool Launcher::FindD2R(std::string& error) {
	std::wstring dir = !opt_.gameDir.empty() ? opt_.gameDir : Wide(state_["d2r_dir"].Str());
	std::string source = !opt_.gameDir.empty() ? "chosen" : state_["d2r_source"].Str("saved");
	if (dir.empty() || !LooksLikeD2R(dir)) {
		if (!opt_.gameDir.empty()) {
			error = Utf8(opt_.gameDir) + " has no D2R.exe and Data folder. Choose the Diablo II Resurrected folder.";
			return false;
		}
		auto found = FindD2RInstalls();
		if (found.empty()) {
			error = "D2R was not found. Press D2R folder and choose the Diablo II Resurrected folder (the one with D2R.exe).";
			return false;
		}
		dir = found.front().dir;
		source = found.front().source;
	}
	while (dir.size() > 3 && (dir.back() == L'\\' || dir.back() == L'/'))
		dir.pop_back();
	if (OfficialMedianXLFolder(dir)) {
		error = "D2R-XL 2012 never writes into the official Median XL's folders or a Diablo II folder (" + Utf8(dir) + ").";
		return false;
	}
	d2rDir_ = dir;
	d2rSource_ = source;
	return true;
}

bool Launcher::SetD2RDir(const std::wstring& dir, std::string& error) {
	Options o = opt_;
	opt_.gameDir = dir;
	if (!FindD2R(error)) {
		opt_ = o;
		return false;
	}
	state_.Set("d2r_dir", Utf8(d2rDir_));
	state_.Set("d2r_source", "chosen");
	SaveState();
	return true;
}

std::wstring Launcher::SavesDir() {
	std::string savepath = "mxl2012/", text, err;
	Json j;
	std::wstring mod = ModDir();
	if (!mod.empty() && ReadWholeFile(JoinPath(mod, Wide(ModFolder()) + L".mpq\\modinfo.json"), text) && Json::Parse(text, j, err))
		savepath = j["savepath"].Str(savepath);
	std::wstring w = Wide(savepath);
	while (!w.empty() && (w.back() == L'/' || w.back() == L'\\'))
		w.pop_back();
	return JoinPath(KnownFolder(1), L"Diablo II Resurrected\\mods\\" + w);
}

// ---------------------------------------------------------------- what the window shows

Launcher::View Launcher::Inspect() {
	View v;
	std::string e;
	v.feedOk = feedChecked_;
	v.latest = feed_.version;
	v.latestComplete = feed_.complete;
	v.requiredVersion = !GameVersion(feed_.d2rVersion).empty() ? GameVersion(feed_.d2rVersion) : std::string(RequiredGameVersion);
	v.loaderNeeded = !feed_.d2rloader.version.empty() ? feed_.d2rloader.version : LoaderVersionDefault;
	if (!FindD2R(e)) {
		v.d2rError = e;
		return v;
	}
	v.d2rFound = true;
	v.d2rDir = d2rDir_;
	v.d2rSource = d2rSource_;
	D2RInstall d = InspectD2R(d2rDir_, d2rSource_);
	v.build = CheckBuild(d.infoVersion, d.exeVersion, v.requiredVersion);
	std::wstring loader = JoinPath(d2rDir_, L"D2RLoader.exe");
	if (FileExists(loader))
		v.loaderFound = ExeFileVersion(loader);
	if (FileExists(loader) && v.loaderFound.empty())
		v.loaderFound = "unknown version";
	v.loaderOk = LoaderVersionMatches(v.loaderFound, v.loaderNeeded);
	v.loaderConfig = JoinPath(d2rDir_, Wide(LoaderConfigRel));
	std::string config;
	bool configExists = ReadWholeFile(v.loaderConfig, config);
	v.defaultModChecked = configExists || !v.loaderFound.empty();  // no D2RLoader at all: its own line says so
	if (v.defaultModChecked)
		v.defaultMod = CheckDefaultMod(config, configExists, ModFolder());
	v.strayPlugins = FindStrayPlugins(d2rDir_, ModFolder());
	std::wstring mod = ModDir();
	std::string marker;
	ReadWholeFile(JoinPath(mod, Wide(InstallMarkerName)), marker);
	MarkerVerdict mv = CheckMarker(marker, state_["install_id"].Str());
	bool ours = mv == MarkerVerdict::Ours || mv == MarkerVerdict::OtherId;
	if (ours && state_["mod"].IsObject() && SamePath(Wide(state_["mod_dir"].Str()), mod))
		v.installed = state_["mod"]["version"].Str();
	else if (ours) {  // our folder, another state (e.g. the state was deleted): the marker knows the version
		Json m;
		std::string err;
		if (Json::Parse(marker, m, err))
			v.installed = m["version"].Str();
	}
	v.foreignMod = !ours && DirExists(mod) && !DirEmpty(mod);
	v.updateAvailable = v.feedOk && v.latest != v.installed;
	return v;
}

std::string Launcher::StatusText(const View& v) const {
	// "!" at the start of a line: drawn as a warning
	std::string out;
	if (!v.d2rFound)
		return "!" + (!v.d2rError.empty() ? v.d2rError : std::string("D2R not found: press D2R folder and choose the Diablo II Resurrected folder."));
	std::string found = v.build.version.empty() ? "version unknown"
	                                            : v.build.version + (v.build.build ? ", build " + std::to_string(v.build.build) : "");
	if (v.build.verdict == BuildVerdict::Ok)
		out += "D2R: " + Utf8(v.d2rDir) + " (" + found + ")\n";
	else
		out += "!D2R " + found + ": D2R-XL 2012 needs D2R " + v.requiredVersion +
		       (v.build.verdict == BuildVerdict::Newer ? ". Wait for a D2R-XL 2012 update." : ". Update D2R in Battle.net or Steam.") + "\n";
	if (v.loaderOk)
		out += "D2RLoader: " + v.loaderFound + " (OK)\n";
	else if (v.loaderFound.empty())
		out += "!D2RLoader missing: D2R-XL 2012 needs D2RLoader " + v.loaderNeeded + ".\n";
	else
		out += "!D2RLoader " + v.loaderFound + ": D2R-XL 2012 needs D2RLoader " + v.loaderNeeded + ".\n";
	if (v.foreignMod)
		out += "!D2R-XL 2012: mods\\" + ModFolder() + " was not installed by this downloader (Install asks before replacing it)";
	else if (v.installed.empty())
		out += "D2R-XL 2012: not installed" + (v.feedOk ? " (" + v.latest + " available)" : std::string());
	else if (v.updateAvailable)
		out += "D2R-XL 2012: " + v.installed + " installed, update " + v.latest + " available";
	else
		out += "D2R-XL 2012: " + v.installed + " installed" + (v.feedOk ? " (latest)" : std::string());
	if (v.feedOk && !v.latestComplete)
		out += "\n!D2R-XL 2012 " + v.latest + " is a test package without game data (test channel).";
	if (v.defaultModChecked && !v.defaultMod.ok)
		out += "\n!" + DefaultModWarning(v.defaultMod, ModFolder());
	if (!v.strayPlugins.empty()) {
		const auto& sp = v.strayPlugins.front();
		out += "\n!" + StrayPluginWarning(Utf8(sp.path), sp.place, sp.mod, true);
		if (v.strayPlugins.size() > 1)
			out += " (+" + std::to_string(v.strayPlugins.size() - 1) + " more)";
	}
	out += "\nMod folder: " + Utf8(ModDir());
	return out;
}

std::vector<std::string> Launcher::EnvironmentWarnings(const View& v) const {
	std::vector<std::string> out;
	if (v.defaultModChecked && !v.defaultMod.ok)
		out.push_back(DefaultModWarning(v.defaultMod, ModFolder()) + " (default_mod in " + Utf8(v.loaderConfig) +
		              "), so the game may run another or an old build. Make " + ModFolder() + " the default mod.");
	for (const auto& sp : v.strayPlugins)
		out.push_back(StrayPluginWarning(Utf8(sp.path), sp.place, sp.mod));
	return out;
}

// ---------------------------------------------------------------- what D2RLoader starts (docs/bugs.md #53)

bool Launcher::FixDefaultMod(std::string& error) {
	if (!FindD2R(error))
		return false;
	if (error = GameRunning(d2rDir_); !error.empty())
		return false;
	std::wstring path = JoinPath(d2rDir_, Wide(LoaderConfigRel));
	std::string text;
	bool exists = ReadWholeFile(path, text);
	DefaultModCheck c = CheckDefaultMod(text, exists, ModFolder());
	if (c.ok) {
		Report("D2RLoader's default mod is already " + c.mod + ".");
		return true;
	}
	MakeDirs(ParentDir(path));
	if (!WriteFileAtomic(path, SetDefaultMod(text, ModFolder()))) {
		error = NotWritable(ParentDir(path), GetLastError());
		return false;
	}
	Report("D2RLoader's default mod is now " + ModFolder() + " (was " + (c.mod.empty() ? std::string("none") : c.mod) + "): default_mod in " +
	       Utf8(path) + (exists ? "; nothing else in it changed." : ", a new file."));
	return true;
}

bool Launcher::RemoveStrayPlugins(std::string& error) {
	if (!FindD2R(error))
		return false;
	if (error = GameRunning(d2rDir_); !error.empty())
		return false;
	auto strays = FindStrayPlugins(d2rDir_, ModFolder());
	if (strays.empty()) {
		Report("No old copy of the D2R-XL 2012 plugin found outside mods\\" + ModFolder() + ".");
		return true;
	}
	std::string date = Today();
	for (const auto& sp : strays) {
		if (!CanMoveStrayPlugin(sp.place, sp.mod)) {
			Report("Leaving " + Utf8(sp.path) + ": that mod's folder is protected; move this copy manually.");
			continue;
		}
		std::wstring to = Wide(RemovedPluginPath(Utf8(opt_.dataDir), date, sp.rel));
		for (int n = 2; FileExists(to); ++n)  // moved twice the same day: keep both
			to = Wide(RemovedPluginPath(Utf8(opt_.dataDir), date, sp.rel)) + L"." + std::to_wstring(n);
		MakeDirs(ParentDir(to));
		if (!MoveFileExW(LongPath(sp.path).c_str(), LongPath(to).c_str(), MOVEFILE_COPY_ALLOWED | MOVEFILE_WRITE_THROUGH)) {
			DWORD code = GetLastError();
			error = "Cannot move " + Utf8(sp.path) + " to " + Utf8(to) + ": " + Utf8(LastErrorText(code));
			if (code == ERROR_ACCESS_DENIED)
				error += " Run the D2R-XL 2012 Downloader as administrator, or move the file yourself.";
			return false;
		}
		Report("Moved the old D2R-XL 2012 plugin " + Utf8(sp.path) + " to " + Utf8(to));
	}
	return true;
}

// ---------------------------------------------------------------- the release feed

std::string Launcher::NewLauncherUrl() const {
	return feed_.launcher.path.empty() ? siteRoot_ : ResolveUrl(siteRoot_, feed_.launcher.path);
}

// docs/release.md "Hosting layout": channels/<channel>.json names the release manifest and its sha256.
bool Launcher::CheckFeed(std::string& error) {
	for (char c : opt_.channel)
		if (!std::isalnum(uint8_t(c)) && c != '-') {
			error = "Bad channel name \"" + opt_.channel + "\".";
			return false;
		}
	std::string chUrl = siteRoot_ + "channels/" + opt_.channel + ".json";
	Report("Reading the release channel " + chUrl);
	std::string text;
	int status = 0;
	if (!FetchText(chUrl, text, error, 1u << 20, &status)) {
		Log("channel " + chUrl + ": " + (status ? "HTTP " + std::to_string(status) : std::string("no answer")) + ": " + error);
		error = ChannelReadError(opt_.channel, chUrl, status, status ? "" : error);
		return false;
	}
	Log("channel " + chUrl + ": HTTP " + std::to_string(status) + ", " + std::to_string(text.size()) + " bytes");
	Channel ch;
	if (!ParseChannel(text, ch, error)) {
		error = "The download site's channel file " + chUrl + " is not usable: " + error;
		return false;
	}
	std::string manUrl = ResolveUrl(siteRoot_, ch.manifest);
	if (!FetchText(manUrl, text, error)) {
		error = "Cannot read the release manifest " + manUrl + ": " + error;
		return false;
	}
	if (Sha256Hex(text.data(), text.size()) != ch.manifestSha256) {
		error = "The release manifest " + manUrl + " does not match the channel file (sha256). The site may be in the middle of an "
		        "update; try again in a few minutes.";
		return false;
	}
	Manifest m;
	if (!ParseManifest(text, m, error)) {
		if (m.schemaVersion > ManifestSchema) {
			offer_ = m.launcher;  // the release's own downloader can read it: self-update
			feed_.launcher = m.launcher;
			error = "This downloader is too old for D2R-XL 2012 " + m.version + " (its release manifest has format " +
			        std::to_string(m.schemaVersion) + ", this downloader reads " + std::to_string(ManifestSchema) +
			        "). Update the downloader: " + NewLauncherUrl();
		} else if (m.schemaVersion > 0 && m.schemaVersion < ManifestSchema) {
			error = "This downloader is too new for the release on the download site (D2R-XL 2012 " + m.version +
			        ", release manifest format " + std::to_string(m.schemaVersion) + "; this downloader reads " +
			        std::to_string(ManifestSchema) + "). Try again later, or report it: " + IssuesUrl;
		} else {
			error = "The release manifest is damaged: " + error;
		}
		return false;
	}
	if (m.version != ch.version) {
		error = "The channel names D2R-XL 2012 " + ch.version + " but its manifest is " + m.version + ".";
		return false;
	}
	offer_ = m.launcher;  // a downloader update is possible even when this one cannot install the release
	if (m.modFolder != ProductFolder) {
		error = "The release manifest names an unusable mod folder \"" + m.modFolder + "\".";
		return false;
	}
	if (!InstallableFromChannel(m, opt_.channel)) {
		error = "The release manifest names D2R-XL 2012 " + m.version + " as incomplete (a test package without game data); it cannot be "
		        "installed from the " + opt_.channel + " channel.";
		return false;
	}
	if (!m.complete)
		Report("D2R-XL 2012 " + m.version + " on the " + opt_.channel + " channel is a test package without game data (it tests the "
		       "downloader; the game will not start it as D2R-XL 2012).");
	if (!m.launcherMin.empty() && CompareVersions(LauncherVersion, m.launcherMin) < 0) {
		feed_ = m;
		error = "D2R-XL 2012 " + m.version + " needs downloader " + m.launcherMin + " or newer (this is " + LauncherVersion +
		        "). Get it: " + NewLauncherUrl();
		return false;
	}
	feed_ = std::move(m);
	feedChecked_ = true;
	if (LauncherUpdateAvailable())
		Report("A newer downloader (" + offer_.version + ") is available: " + NewLauncherUrl());
	return true;
}

bool Launcher::LauncherUpdateAvailable() const {
	if (offer_.version.empty() || offer_.path.empty() || offer_.size <= 0 || offer_.sha256.size() != 64 ||
	    CompareVersions(offer_.version, LauncherVersion) <= 0)
		return false;
	// The published exe is this one (a release whose launcher entry carries a wrong version): nothing to update, and
	// offering it would loop, since the replacement reports the same version again.
	if (selfSha256_.empty())
		selfSha256_ = FileSha256(ExePath());
	return selfSha256_ != offer_.sha256;
}

std::wstring Launcher::ExePath() {
	std::wstring buf(32768, L'\0');
	buf.resize(GetModuleFileNameW(nullptr, buf.data(), DWORD(buf.size())));
	return buf;
}

void Launcher::RemoveOldExe() {
	std::wstring old = ExePath() + L".old";
	if (!FileExists(old))
		return;
	std::thread([old] {  // the old process may still be ending
		for (int i = 0; i < 20 && !DeleteFileW(LongPath(old).c_str()) && FileExists(old); ++i)
			Sleep(500);
	}).detach();
}

// The sha256 of the published downloader is what makes it trusted: it comes from the release manifest, which is
// checked against the channel file's manifestSha256 and read over HTTPS. A signature is logged, never required, so a
// new signing certificate (or none) does not block an update.
bool Launcher::SelfUpdate(std::string& error) {
	if (!LauncherUpdateAvailable()) {
		error = "No newer downloader is published.";
		return false;
	}
	std::wstring exe = ExePath(), part = exe + L".download", old = exe + L".old";
	std::string url = ResolveUrl(siteRoot_, offer_.path);
	std::string manual = " Get it yourself: " + url;
	DeleteFileW(LongPath(part).c_str());
	HANDLE h = CreateFileW(LongPath(part).c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
	if (h == INVALID_HANDLE_VALUE) {
		error = "Cannot write next to the downloader (" + Utf8(ParentDir(exe)) + "): " + Utf8(LastErrorText(GetLastError())) + "." + manual;
		return false;
	}
	Report("Downloading downloader " + offer_.version + " from " + url);
	uint64_t got = 0;
	bool writeOk = true;
	FetchResult r = Fetch(url, 0, 0, [&](const uint8_t* p, size_t n) {
		DWORD w = 0;
		if (got + n > offer_.size || !WriteFile(h, p, DWORD(n), &w, nullptr) || w != n) {
			writeOk = false;
			return false;
		}
		got += n;
		if (onProgress)
			onProgress({"Downloading downloader " + offer_.version + ": " + Mb(got) + " of " + Mb(offer_.size), double(got) / double(offer_.size)});
		return !cancel.load();
	});
	CloseHandle(h);
	std::string sha = r.ok && writeOk && got == offer_.size ? FileSha256(part) : "";
	if (sha != offer_.sha256) {
		DeleteFileW(LongPath(part).c_str());
		if (!r.ok)
			error = "Downloader download failed: " + r.error + "." + manual;
		else
			error = "The downloaded downloader does not match the release manifest (" + std::to_string(got) + " bytes, sha256 " +
			        (sha.empty() ? std::string("not checked") : sha) + "; expected " + std::to_string(offer_.size) + " bytes, " +
			        offer_.sha256 + "). Nothing was changed.";
		return false;
	}
	std::string thumb;
	bool intact = false;
	if (SignerThumbprint(part, thumb, intact))
		Log("downloader " + offer_.version + ": signed by " + thumb + (intact ? "" : " (signature not intact)"));
	else
		Log("downloader " + offer_.version + ": not signed");
	DeleteFileW(LongPath(old).c_str());
	if (!MoveFileExW(LongPath(exe).c_str(), LongPath(old).c_str(), MOVEFILE_REPLACE_EXISTING)) {  // a running exe can be renamed
		error = "Cannot replace the downloader: " + Utf8(LastErrorText(GetLastError())) + "." + manual;
		DeleteFileW(LongPath(part).c_str());
		return false;
	}
	if (!MoveFileExW(LongPath(part).c_str(), LongPath(exe).c_str(), MOVEFILE_WRITE_THROUGH)) {
		error = "Cannot replace the downloader: " + Utf8(LastErrorText(GetLastError())) + "." + manual;
		MoveFileExW(LongPath(old).c_str(), LongPath(exe).c_str(), 0);
		DeleteFileW(LongPath(part).c_str());
		return false;
	}
	Report("Downloader updated to " + offer_.version + " (sha256 checked against the release manifest)");
	return true;
}

// ---------------------------------------------------------------- the mod folder

// Before anything is written: D2R not running, the mod folder ours (or the player said to replace it), the mods
// folder writable. Then the marker goes in first, so a folder the downloader wrote into always carries it.
bool Launcher::PrepareTarget(std::string& error) {
	foreign_ = false;
	if (auto running = ProcessesUnder(d2rDir_); !running.empty()) {
		error = Utf8(running.front().exe.substr(running.front().exe.find_last_of(LR"(\/)") + 1)) + " is running from " + Utf8(d2rDir_) + ". Close the game first.";
		return false;
	}
	std::wstring mod = ModDir();
	if (mod.empty() || !PathUnder(mod, JoinPath(d2rDir_, L"mods")) || SamePath(mod, JoinPath(d2rDir_, L"mods"))) {
		error = "Internal error: the mod folder " + Utf8(mod) + " is not inside " + Utf8(d2rDir_) + "\\mods.";
		return false;
	}
	std::wstring markerPath = JoinPath(mod, Wide(InstallMarkerName));
	std::string marker;
	ReadWholeFile(markerPath, marker);
	MarkerVerdict mv = CheckMarker(marker, state_["install_id"].Str());
	std::string id;
	if (mv == MarkerVerdict::Ours || mv == MarkerVerdict::OtherId) {
		Json m;
		std::string err;
		Json::Parse(marker, m, err);
		id = m["id"].Str();
		if (mv == MarkerVerdict::OtherId)
			Log("mod folder " + Utf8(mod) + " was made by the downloader under another state (id " + id + "); taking it over");
	} else if (DirExists(mod) && !DirEmpty(mod)) {
		if (!opt_.replace) {
			foreign_ = true;
			error = Utf8(mod) + " already exists but was not installed by the D2R-XL 2012 Downloader (a manual or developer "
			        "install). Replace it with D2R-XL 2012 " + feed_.version + "? Your characters are not in that folder.";
			return false;
		}
		Report("Replacing " + Utf8(mod) + ", which the downloader did not install");
	}
	if (mv != MarkerVerdict::Ours) {  // records of another installation, or of none: every file is hashed
		state_.Set("mod", Json());
		state_.Set("mod_files", Json::Object());
	}
	// writable? (the mods folder belongs to D2R's folder; Battle.net normally gives Users full control)
	std::wstring mods = JoinPath(d2rDir_, L"mods");
	if (!MakeDirs(mod)) {
		error = NotWritable(mods, GetLastError());
		return false;
	}
	if (id.empty())
		id = RandomId();
	std::wstring probe = markerPath + L".mxlpart";
	HANDLE h = CreateFileW(LongPath(probe).c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
	if (h == INVALID_HANDLE_VALUE) {
		error = NotWritable(mod, GetLastError());
		return false;
	}
	CloseHandle(h);
	DeleteFileW(LongPath(probe).c_str());
	std::string version = mv == MarkerVerdict::None || mv == MarkerVerdict::Unreadable ? "" : state_["mod"]["version"].Str();
	if (!WriteFileAtomic(markerPath, MakeMarker(id, version))) {
		error = NotWritable(mod, GetLastError());
		return false;
	}
	state_.Set("install_id", id);
	state_.Set("d2r_dir", Utf8(d2rDir_));
	state_.Set("d2r_source", d2rSource_);
	state_.Set("mod_dir", Utf8(mod));
	SaveState();
	return true;
}

// 7z or objects (docs/launcher.md "7z or objects"): the 7z when the objects to fetch add up to more bytes than the 7z
// itself (a fresh install: about 1.2 GB of objects against a 355 MB 7z; a small update: a few objects).
bool Launcher::UseSevenZip(const std::vector<ManifestFile>& fetch, uint64_t /*localBytes*/) const {
	if (opt_.via == Via::Objects || feed_.archive.path.empty() || feed_.archive.size == 0 || feed_.archive.sha256.size() != 64)
		return false;
	if (opt_.via == Via::SevenZip)
		return true;
	uint64_t objectBytes = 0;
	for (const auto& o : GroupObjects(fetch))
		objectBytes += o.size;
	return objectBytes > feed_.archive.size;
}

// docs/release.md "Hosting layout": every changed file is one object, <objectsBase><sha[0:2]>/<sha>. Downloads run in
// parallel into <mod>\mxl2012-download\<sha>.part, resume with a Range request (ObjectAttempts tries per object, with a
// growing pause; 404/403/410 end it at once), are checked (size, sha256) and then renamed into place. On return `fetch`
// holds what could not be installed; the rest stays installed.
bool Launcher::InstallObjects(const std::wstring& mod, std::vector<ManifestFile>& fetch, Json& files, std::string& error) {
	std::vector<ObjectFetch> objs = GroupObjects(fetch);
	std::wstring tmp = JoinPath(mod, Wide(DownloadFolderName));
	if (!MakeDirs(tmp)) {
		error = NotWritable(tmp, GetLastError());
		return false;
	}
	uint64_t totalBytes = 0;
	for (const auto& o : objs)
		totalBytes += o.size;
	std::atomic<uint64_t> doneBytes{0};
	std::atomic<size_t> next{0}, doneFiles{0}, running{0};
	std::mutex mu;  // guards files, failed, firstError
	std::set<std::string> failed;
	std::string firstError;
	Report(Count(fetch.size(), "file") + " to download (" + Mb(totalBytes) + ", " + Count(objs.size(), "object") + ") from " +
	       ResolveUrl(siteRoot_, feed_.objectsBase));

	auto one = [&](HttpSession& http, const ObjectFetch& o, std::string& err) -> bool {
		std::string url = ResolveUrl(siteRoot_, ObjectPath(feed_.objectsBase, o.sha256));
		std::wstring part = JoinPath(tmp, Wide(o.sha256) + L".part");
		for (int attempt = 0; attempt < ObjectAttempts; ++attempt) {
			Pause(attempt, cancel);
			if (cancel.load()) {
				err = "cancelled";
				return false;
			}
			uint64_t have = 0;
			if (!FileSize(part, have) || have > o.size) {
				DeleteFileW(LongPath(part).c_str());
				have = 0;
			}
			doneBytes += have;  // a resumed part counts as done
			if (have < o.size || !FileExists(part)) {
				HANDLE h = CreateFileW(LongPath(part).c_str(), FILE_APPEND_DATA, 0, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
				if (h == INVALID_HANDLE_VALUE) {
					err = "cannot write " + Utf8(part) + ": " + Utf8(LastErrorText(GetLastError()));
					return false;
				}
				bool writeOk = true;
				FetchResult r;
				r.ok = true;  // nothing to fetch for an empty file
				if (o.size > have)
					r = http.Fetch(url, have, o.size - have, [&](const uint8_t* p, size_t n) {
						DWORD w = 0;
						if (!WriteFile(h, p, DWORD(n), &w, nullptr) || w != n) {
							writeOk = false;
							return false;
						}
						doneBytes += n;
						return !cancel.load();
					});
				CloseHandle(h);
				if (!writeOk) {
					err = "cannot write " + Utf8(part) + " (disk full?)";
					return false;
				}
				if (!r.ok) {
					err = r.error;
					uint64_t now = 0;
					FileSize(part, now);
					doneBytes -= now;  // counted again on the retry
					if (r.status == 404 || r.status == 403 || r.status == 410 || cancel.load())
						return false;
					continue;
				}
			}
			uint64_t size = 0;
			FileSize(part, size);
			if (size != o.size || FileSha256(part) != o.sha256) {
				err = "object " + o.sha256 + " does not match the release manifest (size or sha256)";
				DeleteFileW(LongPath(part).c_str());
				doneBytes -= size;
				continue;
			}
			// one object, several paths: copy to all but the last, then move the part file itself
			for (size_t i = 0; i < o.paths.size(); ++i) {
				std::wstring dst = JoinPath(mod, Wide(o.paths[i]));
				bool ok;
				if (i + 1 < o.paths.size()) {
					std::wstring t = dst + L".mxlpart";
					MakeDirs(ParentDir(dst));
					ok = CopyFileW(LongPath(part).c_str(), LongPath(t).c_str(), FALSE) && MoveInto(t, dst);
				} else {
					ok = MoveInto(part, dst);
				}
				if (!ok) {
					err = "cannot write " + Utf8(dst) + ": " + Utf8(LastErrorText(GetLastError()));
					return false;
				}
				std::lock_guard<std::mutex> lock(mu);
				RecordFile(files, dst, o.paths[i], o.sha256);
			}
			doneFiles += o.paths.size();
			return true;
		}
		return false;
	};

	size_t nWorkers = std::min<size_t>(8, objs.size());
	running = nWorkers;
	std::vector<std::thread> workers;
	for (size_t w = 0; w < nWorkers; ++w)
		workers.emplace_back([&] {
			HttpSession http;
			for (;;) {
				size_t i = next++;
				if (i >= objs.size() || cancel.load())
					break;
				std::string err;
				if (!one(http, objs[i], err)) {
					std::lock_guard<std::mutex> lock(mu);
					failed.insert(objs[i].sha256);
					if (firstError.empty())
						firstError = err;
				}
			}
			--running;
		});
	ULONGLONG lastSave = GetTickCount64(), lastShow = 0;
	while (running.load()) {
		Sleep(100);
		ULONGLONG now = GetTickCount64();
		if (onProgress && now - lastShow >= 500) {
			lastShow = now;
			onProgress({"Downloading D2R-XL 2012 " + feed_.version + ": " + std::to_string(doneFiles.load()) + " of " +
			                Count(fetch.size(), "file") + " (" + Mb(doneBytes.load()) + " of " + Mb(totalBytes) + ")",
			            totalBytes ? double(doneBytes.load()) / double(totalBytes) : -1});
		}
		if (now - lastSave > 5000) {  // resume point: what is installed so far
			lastSave = now;
			std::lock_guard<std::mutex> lock(mu);
			state_.Set("mod_files", files);
			SaveState();
		}
	}
	for (auto& t : workers)
		t.join();
	std::vector<ManifestFile> left;
	for (const auto& f : fetch)
		if (failed.count(f.sha256) || files[f.path]["sha256"].Str() != f.sha256)
			left.push_back(f);
	size_t installed = fetch.size() - left.size();
	fetch.swap(left);
	if (fetch.empty()) {
		Report("Downloaded " + Count(objs.size(), "object") + " (" + Mb(totalBytes) + "), installed " + Count(installed, "file") +
		       " of D2R-XL 2012 " + feed_.version);
		return true;
	}
	error = cancel.load() ? std::string("cancelled") : std::to_string(failed.size()) + " downloads failed, first: " + firstError;
	return false;
}

// The release's 7z into <data>\download\<name>: resumed with Range into <name>.part, its sha256 must be the manifest's
// archive.sha256 (a damaged one is deleted and fetched again), then renamed to <name>.
bool Launcher::Download7z(std::wstring& file, std::string& error) {
	const auto& a = feed_.archive;
	std::string name = a.name;
	bool plain = !name.empty() && name.size() < 100 && name.find_first_of("/\\:") == std::string::npos && name[0] != '.';
	if (!plain || Lower(name).size() < 3 || Lower(name).compare(name.size() - 3, 3, ".7z") != 0)
		name = "D2R-XL-2012-" + feed_.version + ".7z";
	std::wstring dir = JoinPath(opt_.dataDir, L"download");
	file = JoinPath(dir, Wide(name));
	std::wstring part = file + L".part";
	if (!MakeDirs(dir)) {
		error = NotWritable(dir, GetLastError());
		return false;
	}
	uint64_t size = 0;
	if (FileSize(file, size) && size == a.size && FileSha256(file) == a.sha256) {
		Report("The D2R-XL 2012 " + feed_.version + " 7z is already downloaded");
		return true;
	}
	DeleteFileW(LongPath(file).c_str());
	std::string url = ResolveUrl(siteRoot_, a.path);
	for (int attempt = 0; attempt < ObjectAttempts; ++attempt) {
		Pause(attempt, cancel);
		if (cancel.load()) {
			error = "cancelled";
			return false;
		}
		uint64_t have = 0;
		if (!FileSize(part, have) || have > a.size) {
			DeleteFileW(LongPath(part).c_str());
			have = 0;
		}
		uint64_t free = 0;
		if (FreeBytes(dir, free) && free < a.size - have + (64ull << 20)) {
			error = "Not enough disk space for the D2R-XL 2012 download in " + Utf8(dir) + ": it needs " + Mb(a.size - have) + ", " + Mb(free) + " are free.";
			return false;
		}
		if (have < a.size) {
			Report(have ? "Resuming the D2R-XL 2012 " + feed_.version + " 7z at " + Mb(have) + " of " + Mb(a.size)
			            : "Downloading D2R-XL 2012 " + feed_.version + " as one 7z (" + Mb(a.size) + ") from " + url);
			HANDLE h = CreateFileW(LongPath(part).c_str(), FILE_APPEND_DATA, 0, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
			if (h == INVALID_HANDLE_VALUE) {
				error = NotWritable(dir, GetLastError());
				return false;
			}
			bool writeOk = true;
			uint64_t got = have;
			ULONGLONG t0 = GetTickCount64(), lastShow = 0;
			FetchResult r = Fetch(url, have, a.size - have, [&](const uint8_t* p, size_t n) {
				DWORD w = 0;
				if (got + n > a.size || !WriteFile(h, p, DWORD(n), &w, nullptr) || w != n) {
					writeOk = false;
					return false;
				}
				got += n;
				ULONGLONG now = GetTickCount64();
				if (onProgress && now - lastShow >= 300) {
					lastShow = now;
					double secs = double(now - t0) / 1000.0;
					double rate = secs > 1 ? double(got - have) / secs : 0;
					std::string eta = rate > 0 ? ", " + std::to_string(int(double(a.size - got) / rate / 60.0 + 0.5)) + " min left" : "";
					onProgress({"Downloading D2R-XL 2012 " + feed_.version + " (7z): " + Mb(got) + " of " + Mb(a.size) + eta,
					            double(got) / double(a.size)});
				}
				return !cancel.load();
			});
			CloseHandle(h);
			if (!writeOk) {
				error = "Cannot write " + Utf8(part) + " (disk full?)";
				return false;
			}
			if (!r.ok) {
				error = r.error;
				Log("7z download: " + r.error + (r.status ? " (HTTP " + std::to_string(r.status) + ")" : ""));
				if (r.status == 404 || r.status == 403 || r.status == 410 || cancel.load())
					return false;
				continue;
			}
		}
		Report("Checking the 7z (sha256) ...");
		std::string sha = FileSha256(part);
		if (sha != a.sha256) {
			Report("The downloaded 7z does not match the release manifest (sha256 " + sha + ", expected " + a.sha256 +
			       "); downloading it again");
			DeleteFileW(LongPath(part).c_str());
			error = "the 7z download does not match the release manifest (sha256)";
			continue;
		}
		if (!MoveFileExW(LongPath(part).c_str(), LongPath(file).c_str(), MOVEFILE_REPLACE_EXISTING)) {
			error = "Cannot rename " + Utf8(part) + ": " + Utf8(LastErrorText(GetLastError()));
			return false;
		}
		return true;
	}
	return false;
}

// docs/launcher.md "Installing from the 7z": unpack the 7z into <mod>\mxl2012-download\7z (inside the mod folder: same
// volume, and D2RLoader lists every folder of mods\ as a mod), check every file's size and sha256 against the
// manifest, then rename each into place. Only the files in `fetch` are written; the 7z's other bytes are only decoded.
bool Launcher::InstallFrom7z(const std::wstring& mod, std::vector<ManifestFile>& fetch, Json& files, std::string& error) {
	std::wstring archive;
	if (!Download7z(archive, error))
		return false;
	std::wstring staging = JoinPath(JoinPath(mod, Wide(DownloadFolderName)), L"7z");
	std::string ignore;
	RemoveTree(staging, ignore);
	if (!MakeDirs(staging)) {
		error = NotWritable(staging, GetLastError());
		return false;
	}
	uint64_t need = 0;
	std::map<std::string, size_t> wanted;  // lower-case path -> index in fetch
	std::set<std::string> listed;
	for (const auto& mf : feed_.files)
		listed.insert(Lower(mf.path));
	for (size_t i = 0; i < fetch.size(); ++i) {
		wanted[Lower(fetch[i].path)] = i;
		need += fetch[i].size;
	}
	uint64_t free = 0;
	if (FreeBytes(mod, free) && free < need + (64ull << 20)) {
		error = "Not enough disk space in " + Utf8(d2rDir_) + ": D2R-XL 2012 needs " + Mb(need) + ", " + Mb(free) + " are free.";
		return false;
	}
	std::FILE* f = nullptr;
	if (_wfopen_s(&f, LongPath(archive).c_str(), L"rb") != 0 || !f) {
		error = "Cannot open " + Utf8(archive);
		return false;
	}
	StdioSource src(f);
	SevenZipArchive sz;
	std::string err;
	if (!sz.Open(src, err)) {
		std::fclose(f);
		DeleteFileW(LongPath(archive).c_str());  // its sha256 was the manifest's, so this is not a download fault; fetched again next time
		error = "Cannot read the 7z: " + err;
		return false;
	}
	const std::string prefix = Lower(ModFolder()) + "/";
	std::vector<std::string> staged(fetch.size());  // sha256 of each staged file ("" not staged)
	size_t curIndex = SIZE_MAX;
	HANDLE out = INVALID_HANDLE_VALUE;
	Sha256 hash;
	uint64_t written = 0, total = sz.UnpackedSize();
	size_t unknown = 0;
	std::string writeError;
	ULONGLONG lastShow = 0;
	Report("Unpacking D2R-XL 2012 " + feed_.version + " (" + Mb(total) + ") ...");
	SevenZipArchive::Sink sink;
	sink.begin = [&](size_t i) {
		const SevenZipEntry& e = sz.entries()[i];
		curIndex = SIZE_MAX;
		if (e.dir)
			return false;
		std::string p = Lower(e.path);
		if (p.rfind(prefix, 0) != 0) {
			++unknown;
			return false;
		}
		auto it = wanted.find(p.substr(prefix.size()));
		if (it == wanted.end()) {
			if (!listed.count(p.substr(prefix.size())))
				++unknown;
			return false;  // unchanged here, or not part of the release: only decoded
		}
		const ManifestFile& mf = fetch[it->second];
		if (mf.size != e.size || !SafeRelativePath(mf.path))
			return false;
		std::wstring dst = JoinPath(staging, Wide(mf.path));
		MakeDirs(ParentDir(dst));
		out = CreateFileW(LongPath(dst).c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
		if (out == INVALID_HANDLE_VALUE) {
			writeError = NotWritable(ParentDir(dst), GetLastError());
			return false;
		}
		hash = Sha256();
		curIndex = it->second;
		return true;
	};
	sink.data = [&](const uint8_t* p, size_t n) {
		hash.Update(p, n);
		DWORD w = 0;
		if (!WriteFile(out, p, DWORD(n), &w, nullptr) || w != n) {
			writeError = "Cannot write into " + Utf8(staging) + " (disk full?)";
			return false;
		}
		written += n;
		return true;
	};
	sink.end = [&](size_t) {
		if (curIndex != SIZE_MAX) {
			CloseHandle(out);
			out = INVALID_HANDLE_VALUE;
			std::string sha = hash.HexDigest();
			if (sha == fetch[curIndex].sha256)
				staged[curIndex] = sha;
			else
				Log("7z: " + fetch[curIndex].path + " has sha256 " + sha + ", the manifest " + fetch[curIndex].sha256);
			curIndex = SIZE_MAX;
		}
		return writeError.empty() && !cancel.load();
	};
	sink.progress = [&](uint64_t done) {
		ULONGLONG now = GetTickCount64();
		if (onProgress && now - lastShow >= 300) {
			lastShow = now;
			onProgress({"Unpacking D2R-XL 2012 " + feed_.version + ": " + Mb(done) + " of " + Mb(total), total ? double(done) / double(total) : -1});
		}
		return !cancel.load();
	};
	SevenZipStats stats;
	ULONGLONG t0 = GetTickCount64();
	bool ok = sz.Extract(sink, err, &stats);
	if (out != INVALID_HANDLE_VALUE)
		CloseHandle(out);
	std::fclose(f);
	if (!ok) {
		RemoveTree(staging, ignore);
		if (!writeError.empty())
			error = writeError;
		else if (cancel.load())
			error = "cancelled";
		else {
			DeleteFileW(LongPath(archive).c_str());
			error = "Cannot unpack the 7z: " + err;
		}
		return false;
	}
	Log("7z: " + std::to_string(stats.streamedBlocks) + " streamed and " + std::to_string(stats.memoryBlocks) +
	    " in-memory blocks, largest decode buffer " + Mb(stats.peakBuffer) + ", " + std::to_string(GetTickCount64() - t0) + " ms" +
	    (unknown ? ", " + std::to_string(unknown) + " entries the manifest does not list (skipped)" : ""));
	std::vector<ManifestFile> left;
	size_t moved = 0;
	for (size_t i = 0; i < fetch.size(); ++i) {
		std::wstring from = JoinPath(staging, Wide(fetch[i].path)), to = JoinPath(mod, Wide(fetch[i].path));
		if (staged[i].empty() || !MoveInto(from, to)) {
			left.push_back(fetch[i]);
			continue;
		}
		RecordFile(files, to, fetch[i].path, fetch[i].sha256);
		++moved;
	}
	RemoveTree(staging, ignore);
	Report("Unpacked " + Mb(written) + " from the 7z, installed " + Count(moved, "file") + " of D2R-XL 2012 " + feed_.version +
	       (left.empty() ? std::string() : "; " + Count(left.size(), "file") + " come as objects"));
	fetch.swap(left);
	DeleteFileW(LongPath(archive).c_str());  // installed: the 7z is not kept
	RemoveDirectoryW(LongPath(JoinPath(opt_.dataDir, L"download")).c_str());  // only when empty
	return true;
}

bool Launcher::EnsureMod(bool verify, std::string& error) {
	std::wstring mod = ModDir();
	// files records are only good for the folder they were made for
	Json files = state_["mod_files"].IsObject() && SamePath(Wide(state_["mod_dir"].Str()), mod) ? state_["mod_files"] : Json::Object();
	uint64_t hashed = 0;
	Report(verify ? "Checking every installed D2R-XL 2012 file ..." : "Comparing the installed files with release " + feed_.version + " ...");
	auto current = [&](const std::string& path) -> std::string {
		std::wstring p = JoinPath(mod, Wide(path));
		uint64_t size = 0, mtime = 0;
		if (!FileSize(p, size, &mtime))
			return "";
		const Json& r = files[path];
		if (!verify && r["size"].Int(-1) == int64_t(size) && r["mtime"].Str() == std::to_string(mtime) && r["sha256"].IsString())
			return r["sha256"].Str();
		hashed += size;
		std::string sha = FileSha256(p);
		Json rec = Json::Object();
		rec.Set("size", size).Set("mtime", std::to_string(mtime)).Set("sha256", sha);
		files.Set(path, rec);
		return sha;
	};
	InstallPlan plan = PlanInstall(feed_, ListFilesUnder(mod), current);
	for (const auto& k : plan.preserved)
		Report("Kept your " + k);
	for (const auto& r : plan.remove) {  // not part of the release (docs/release.md "files")
		DeleteFileW(LongPath(JoinPath(mod, Wide(r))).c_str());
		files.Set(r, Json());
	}
	if (!plan.remove.empty())
		Report("Removed " + Count(plan.remove.size(), "file") + " that " + (plan.remove.size() == 1 ? "is" : "are") +
		       " not part of D2R-XL 2012 " + feed_.version);
	if (!plan.fetch.empty()) {
		std::vector<ManifestFile> left = plan.fetch;
		if (UseSevenZip(left, 0)) {
			std::string e7;
			if (!InstallFrom7z(mod, left, files, e7)) {
				state_.Set("mod_files", files);
				SaveState();
				if (cancel.load() || opt_.via == Via::SevenZip) {
					error = cancel.load() ? "Stopped. Install again to continue where it stopped (the 7z download resumes)." : "7z install failed: " + e7;
					return false;
				}
				Report("The 7z could not be used (" + e7 + "); downloading the files one by one instead");
			}
		}
		if (!left.empty() && !InstallObjects(mod, left, files, error)) {
			state_.Set("mod_files", files);
			SaveState();
			if (cancel.load())
				error = "Stopped. Update again to continue where it stopped.";
			else
				error = "Download failed: " + std::to_string(left.size()) + " of " + std::to_string(plan.fetch.size()) +
				        " files could not be downloaded (" + error + "). Check your connection and try again: the " +
				        std::to_string(plan.fetch.size() - left.size()) + " files already downloaded are kept.";
			return false;
		}
	} else {
		Report("D2R-XL 2012 " + feed_.version + " is installed and up to date" + (hashed ? " (" + Mb(hashed) + " checked)" : ""));
	}
	std::string ignore;
	RemoveTree(JoinPath(mod, Wide(DownloadFolderName)), ignore);  // leftover parts of objects no longer needed
	for (const auto& d : feed_.emptyDirs)  // folders the release has without files (d2rloader/patches)
		if (!MakeDirs(JoinPath(mod, Wide(d)))) {
			error = "Cannot create " + Utf8(JoinPath(mod, Wide(d)));
			return false;
		}
	Json clean = Json::Object();  // drop records of files that are gone
	for (const auto& [k, v] : files.members())
		if (v.IsObject())
			clean.Set(k, v);
	state_.Set("mod_files", clean);
	state_.Set("mod", ManifestToJson(feed_));
	WriteFileAtomic(JoinPath(mod, Wide(InstallMarkerName)), MakeMarker(state_["install_id"].Str(), feed_.version));
	SaveState();
	Report("D2R-XL 2012 " + feed_.version + " is in " + Utf8(mod) + ". " + HowToPlay);
	return true;
}

// ---------------------------------------------------------------- actions

bool Launcher::InstallOrUpdate(std::string& error) {
	cancel = false;
	if (!FindD2R(error) || !CheckFeed(error) || !PrepareTarget(error))
		return false;
	return EnsureMod(false, error);
}

bool Launcher::Repair(std::string& error) {
	cancel = false;
	if (!FindD2R(error) || !CheckFeed(error) || !PrepareTarget(error))
		return false;
	return EnsureMod(true, error);
}

bool Launcher::Uninstall(std::string& error) {
	cancel = false;
	if (!FindD2R(error))
		return false;
	std::wstring mod = ModDir();
	std::wstring saves = SavesDir();  // from the mod's modinfo.json, before it goes
	if (!DirExists(mod)) {
		error = "D2R-XL 2012 is not installed in " + Utf8(d2rDir_) + " (no " + Utf8(mod) + ").";
		return false;
	}
	std::string marker;
	ReadWholeFile(JoinPath(mod, Wide(InstallMarkerName)), marker);
	if (CheckMarker(marker, state_["install_id"].Str()) != MarkerVerdict::Ours) {
		error = "Not removing " + Utf8(mod) + ": it has no D2R-XL 2012 Downloader marker (" + InstallMarkerName +
		        ") of this installation, so the downloader did not install it.";
		return false;
	}
	if (auto running = ProcessesUnder(d2rDir_); !running.empty()) {
		error = Utf8(running.front().exe.substr(running.front().exe.find_last_of(LR"(\/)") + 1)) + " is running from " + Utf8(d2rDir_) + ". Close the game first.";
		return false;
	}
	if (!PathUnder(mod, JoinPath(d2rDir_, L"mods")) || SamePath(mod, JoinPath(d2rDir_, L"mods"))) {
		error = "Internal error: " + Utf8(mod) + " is not a folder inside " + Utf8(d2rDir_) + "\\mods.";
		return false;
	}
	Report("Removing " + Utf8(mod) + " ...");
	if (!RemoveTree(mod, error))
		return false;
	std::string ignore;
	RemoveTree(JoinPath(opt_.dataDir, L"download"), ignore);
	for (const char* k : {"mod", "mod_files", "install_id", "mod_dir"})
		state_.Set(k, Json());
	Json clean = Json::Object();
	for (const auto& [k, v] : state_.members())
		if (!v.IsNull())
			clean.Set(k, v);
	state_ = clean;
	SaveState();
	Report("D2R-XL 2012 is uninstalled (only " + Utf8(mod) + " was removed). Your characters stay in " + Utf8(saves) + ".");
	return true;
}

}  // namespace mxl

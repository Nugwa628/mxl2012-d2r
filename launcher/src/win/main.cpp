// D2R-XL 2012 Downloader: the window (window.cpp: D2R folder, D2RLoader check, Install / Update / Repair / Uninstall) or,
// with --cli, the same actions from a terminal (used by the tests, docs/launcher.md "Command line").
#include "app.h"
#include "../core/paths.h"
#include "game.h"
#include "http.h"
#include "util.h"
#include "window.h"

#include <windows.h>
#include <shellapi.h>

#include <cstdlib>
#include <exception>


using namespace mxl;

namespace {

const wchar_t* Usage =
	L"D2R-XL-2012-Downloader.exe [--cli status|detect|install|update|repair|uninstall|self-update|fix-default-mod|remove-stray-plugins|install-loader|play] [options]\n"
	L"  --data-dir DIR   state, download and log (default %LOCALAPPDATA%\\mxl2012)\n"
	L"  --site URL|DIR   download site root (default https://files.werdegames.com/mxl2012/; backup https://dl.werdegames.com/mxl2012/; http://, file:// or a folder for tests)\n"
	L"  --channel NAME   release channel: stable (default) or test\n"
	L"  --game-dir DIR   your D2R folder (default: found via Battle.net / Steam); D2R-XL 2012 goes into DIR\\mods\\mxl2012\n"
	L"  --replace        replace a mods\\mxl2012 that the downloader did not install\n"
	L"  --via auto|7z|objects  how files are fetched (default auto: the 7z for a fresh install, objects for an update)\n"
	L"  --snapshot FILE  write the window as a PNG and exit\n";

struct Cli {
	std::wstring command;
	std::wstring snapshot;
	Options opt;
	bool bad = false;
};

// A relative --game-dir / --data-dir would be saved as given and mean another folder from another working directory.
std::wstring FullPath(const std::wstring& p) {
	if (p.empty())
		return p;
	DWORD n = GetFullPathNameW(p.c_str(), 0, nullptr, nullptr);
	std::wstring full(n, L'\0');
	DWORD m = n ? GetFullPathNameW(p.c_str(), n, full.data(), nullptr) : 0;
	return m && m < n ? full.substr(0, m) : p;
}

Cli ParseArgs() {
	Cli c;
	int argc = 0;
	LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &argc);
	for (int i = 1; i < argc; ++i) {
		std::wstring a = argv[i];
		auto next = [&]() -> std::wstring {
			if (i + 1 < argc)
				return argv[++i];
			c.bad = true;
			return L"";
		};
		if (a == L"--cli") c.command = next();
		else if (a == L"--data-dir") c.opt.dataDir = FullPath(next());
		else if (a == L"--site") c.opt.site = Utf8(next());
		else if (a == L"--channel") c.opt.channel = Utf8(next());
		else if (a == L"--game-dir") c.opt.gameDir = FullPath(next());
		else if (a == L"--replace") c.opt.replace = true;
		else if (a == L"--via") {
			std::wstring v = next();
			if (v == L"auto") c.opt.via = Via::Auto;
			else if (v == L"7z") c.opt.via = Via::SevenZip;
			else if (v == L"objects") c.opt.via = Via::Objects;
			else c.bad = true;
		}
		else if (a == L"--snapshot") c.snapshot = next();
		else c.bad = true;
	}
	LocalFree(argv);
	return c;
}

void SetupLog(const Options& o, bool console) {
	std::wstring data = o.dataDir.empty() ? Wide(DefaultDataDir(Utf8(KnownFolder(0)))) : o.dataDir;
	if (OfficialMedianXLFolder(data))  // never write into the official Median XL's folders (the downloader refuses them)
		data = Wide(DefaultDataDir(Utf8(KnownFolder(0))));
	LogInit(JoinPath(data, L"launcher.log"), console);
}

// A crash or an uncaught C++ exception writes one line before the process ends (Windows Error Reporting still sees the
// crash). With WindowCloseLine and the exit line, every way the downloader ends by itself is in the log.
LONG WINAPI OnCrash(EXCEPTION_POINTERS* e) {
	static LONG once = 0;
	if (InterlockedExchange(&once, 1) == 0)
		LogCrash(CrashLine(e->ExceptionRecord->ExceptionCode, reinterpret_cast<uint64_t>(e->ExceptionRecord->ExceptionAddress)));
	return EXCEPTION_CONTINUE_SEARCH;
}

void OnTerminate() {
	LogCrash("crash: an uncaught C++ exception; the downloader ends");
	std::abort();
}

void InstallCrashLog() {
	SetUnhandledExceptionFilter(OnCrash);
	std::set_terminate(OnTerminate);
	// WM_TIMER would swallow an exception silently and run on in an unknown state: let it reach OnCrash instead
	BOOL suppress = FALSE;
	SetUserObjectInformationW(GetCurrentProcess(), UOI_TIMERPROC_EXCEPTION_SUPPRESSION, &suppress, sizeof(suppress));
}

int RunCli(Cli& c) {
	if (!AttachConsole(ATTACH_PARENT_PROCESS))
		AllocConsole();
	SetupLog(c.opt, true);
	Log(std::string("D2R-XL 2012 Downloader ") + LauncherVersion + " --cli " + Utf8(c.command) + " (" + ProcessOrigin() + ")");
	if (c.command == L"detect") {
		auto found = FindD2RInstalls();
		if (found.empty())
			Log("no D2R install found");
		for (const auto& d : found)
			Log(Utf8(d.dir) + " | " + d.source + " | .build.info " + d.infoVersion + " | D2R.exe " + d.exeVersion + " | " + d.build.message);
		return found.empty() ? 1 : 0;
	}
	Launcher l(c.opt);
	std::string last;
	l.onProgress = [&](const Progress& p) {
		if (p.fraction >= 0 && p.text != last) {  // Report() already logged the plain messages
			static ULONGLONG t = 0;
			if (GetTickCount64() - t > 3000) {
				t = GetTickCount64();
				Log(p.text);
			}
		}
		last = p.text;
	};
	std::string err;
	bool ok = true;
	if (c.command == L"status") {
		l.CheckFeed(err);
		Launcher::View v = l.Inspect();
		Log(l.StatusText(v));
		for (const std::string& w : l.EnvironmentWarnings(v))
			Log("WARNING: " + w);
		if (v.defaultModChecked && !v.defaultMod.ok)
			Log("  --cli fix-default-mod sets default_mod = \"mxl2012\" in D2RLoader's config (only that key)");
		if (v.d2rFound && !v.loaderOk && l.LoaderInstallable())
			Log("  --cli install-loader downloads D2RLoader " + l.LoaderPackage().version + " from " + l.LoaderPackage().url + " into the D2R folder");
		if (!v.strayPlugins.empty())
			Log("  --cli remove-stray-plugins moves them to " + Utf8(l.options().dataDir) + R"(\removed\<date>\ (nothing is deleted; protected mod folders are left in place))");
		if (!err.empty())
			Log("feed: " + err);
		return 0;
	}
	if (c.command == L"install" || c.command == L"update") ok = l.InstallOrUpdate(err);
	else if (c.command == L"repair") ok = l.Repair(err);
	else if (c.command == L"uninstall") ok = l.Uninstall(err);
	else if (c.command == L"fix-default-mod") ok = l.FixDefaultMod(err);
	else if (c.command == L"remove-stray-plugins") ok = l.RemoveStrayPlugins(err);
	else if (c.command == L"install-loader") {
		std::string feedErr;
		if (!l.CheckFeed(feedErr))
			Log("feed: " + feedErr);
		ok = l.InstallLoader(err);
	}
	else if (c.command == L"play") {  // as the window's Play: only when the install is up to date with the channel
		std::string feedErr;
		if (!l.CheckFeed(feedErr))
			Log("feed: " + feedErr);
		ok = l.Play(err);
	}
	else if (c.command == L"self-update") {
		std::string feedErr;
		if (!l.CheckFeed(feedErr) && !l.LauncherUpdateAvailable())
			Log("feed: " + feedErr);
		ok = l.SelfUpdate(err);
	}
	else {
		Log(Utf8(Usage));
		return 2;
	}
	Log(ok ? "OK" : "FAILED: " + err);
	return ok ? 0 : 1;
}

}  // namespace

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE, PWSTR, int) {
	SetUserAgent(L"D2R-XL-2012-Downloader/" + Wide(LauncherVersion));
	Launcher::RemoveOldExe();
	Cli c = ParseArgs();
	if (c.bad) {
		MessageBoxW(nullptr, Usage, L"D2R-XL 2012 Downloader", MB_ICONINFORMATION);
		return 2;
	}
	InstallCrashLog();
	if (!c.command.empty())
		return RunCli(c);
	SetupLog(c.opt, false);
	Log(std::string("D2R-XL 2012 Downloader ") + LauncherVersion + " (window, " + ProcessOrigin() + ")");
	int code = RunWindow(inst, c.opt, c.snapshot);
	Log("D2R-XL 2012 Downloader ends (exit code " + std::to_string(code) + ")");
	return code;
}

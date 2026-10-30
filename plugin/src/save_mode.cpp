// Save format check and cancelled-save watch (save_mode_logic.h, docs/bugs.md #512). At load: the mod's own d2rloader.toml
// (next to this DLL's plugins folder) must ask for D2RLoader's extended save format; when it does not, the key is put back
// (the old file is kept as d2rloader.toml.retail-backup) and the screen says to restart, because D2RLoader reads the format once
// at its start. While the game runs: a thread reads what D2RLoader appends to <game>\d2rloader\logs\d2rloader.log and puts a
// red line on the screen for every save it cancelled, so a save is never dropped without the player seeing it.
#include "save_mode.h"

#include "build_guard.h"
#include "save_mode_logic.h"

#include <windows.h>

#include <atomic>
#include <cstdio>
#include <cstring>
#include <string>

namespace {

const D2RL::PluginContext* g_context = nullptr;
std::atomic<bool> g_stop{false};
HANDLE g_thread = nullptr;
bool g_retail = false;  // this start writes retail saves (the file is fixed only for the next start)
char g_logPath[MAX_PATH * 3] = "";
std::atomic<int> g_failures{0};

auto ReadFileText(const char* path, std::string& out) -> bool {
	HANDLE f = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING, 0, nullptr);
	if (f == INVALID_HANDLE_VALUE) {
		return false;
	}
	LARGE_INTEGER size{};
	bool ok = GetFileSizeEx(f, &size) != 0 && size.QuadPart < (1 << 20);
	if (ok) {
		out.resize(static_cast<size_t>(size.QuadPart));
		DWORD got = 0;
		ok = out.empty() || (ReadFile(f, out.data(), static_cast<DWORD>(out.size()), &got, nullptr) != 0 && got == out.size());
	}
	CloseHandle(f);
	return ok;
}

auto WriteFileText(const char* path, const std::string& text) -> bool {
	HANDLE f = CreateFileA(path, GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
	if (f == INVALID_HANDLE_VALUE) {
		return false;
	}
	DWORD put = 0;
	const bool ok = WriteFile(f, text.data(), static_cast<DWORD>(text.size()), &put, nullptr) != 0 && put == text.size();
	CloseHandle(f);
	return ok;
}

// The new bytes of D2RLoader's log every 5 s; the notice stays until 90 s pass without a new failure.
DWORD WINAPI WatchLog(LPVOID) {
	LARGE_INTEGER offset{};
	bool started = false;
	std::string rest;
	ULONGLONG lastFailure = 0;
	bool shown = false;
	int count = 0;
	while (!g_stop.load()) {
		HANDLE f = CreateFileA(g_logPath, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING, 0, nullptr);
		if (f != INVALID_HANDLE_VALUE) {
			LARGE_INTEGER size{};
			if (GetFileSizeEx(f, &size) != 0) {
				if (!started || size.QuadPart < offset.QuadPart) {
					offset = started ? LARGE_INTEGER{} : size;  // the part written before this plugin loaded is not this session's saves
					started = true;
					rest.clear();
				}
				while (size.QuadPart > offset.QuadPart) {
					char buf[16384];
					const LONGLONG left = size.QuadPart - offset.QuadPart;
					const DWORD want = left < static_cast<LONGLONG>(sizeof(buf)) ? static_cast<DWORD>(left) : static_cast<DWORD>(sizeof(buf));
					DWORD got = 0;
					if (SetFilePointerEx(f, offset, nullptr, FILE_BEGIN) == 0 || ReadFile(f, buf, want, &got, nullptr) == 0 || got == 0) {
						break;
					}
					offset.QuadPart += got;
					const int n = save_mode::CountFailures(std::string(buf, got), rest);
					if (n > 0) {
						count += n;
						lastFailure = GetTickCount64();
						g_failures.store(count);
						SYSTEMTIME t{};
						GetLocalTime(&t);
						char notice[256];
						save_mode::FailureNotice(notice, sizeof(notice), count, t.wHour, t.wMinute, g_retail);
						const bool drawn = ShowNotice(g_context, notice);
						shown = true;
						char line[384];
						std::snprintf(line, sizeof(line), "mxl2012-core: savemode %d cancelled save%s seen in d2rloader.log, %s", count,
						              count == 1 ? "" : "s", drawn ? "notice on screen" : "no overlay service, this log only");
						g_context->LogError(line);
					}
				}
			}
			CloseHandle(f);
		}
		if (shown && GetTickCount64() - lastFailure > 90000) {
			ShowNotice(g_context, "");  // saves go through again (or none was tried for 90 s)
			shown = false;
			g_context->LogInfo("mxl2012-core: savemode no cancelled save for 90 s, notice cleared");
		}
		for (int i = 0; i < 50 && !g_stop.load(); ++i) {
			Sleep(100);
		}
	}
	return 0;
}

}  // namespace

auto InstallSaveMode(const D2RL::PluginContext* context, const char* selfPath, const char* gameDir, char* report, size_t reportSize) noexcept
    -> bool {
	g_context = context;
	// <mod>\d2rloader\plugins\mxl2012-core.dll -> <mod>\d2rloader\config\d2rloader.toml
	char toml[MAX_PATH * 3];
	std::snprintf(toml, sizeof(toml), "%s", selfPath != nullptr ? selfPath : "");
	char* slash = std::strrchr(toml, '\\');
	if (slash != nullptr) {
		*slash = '\0';
		slash = std::strrchr(toml, '\\');
	}
	const char* state = "?";
	if (slash != nullptr) {
		std::snprintf(slash, sizeof(toml) - static_cast<size_t>(slash - toml), "\\config\\d2rloader.toml");
		std::string text;
		const bool read = ReadFileText(toml, text);
		std::string value;
		const save_mode::Mode mode = read ? save_mode::ParseMode(text, &value) : save_mode::Mode::Missing;
		if (mode == save_mode::Mode::Extended) {
			state = "extended";
		} else {
			g_retail = true;
			char backup[MAX_PATH * 3 + 32];
			std::snprintf(backup, sizeof(backup), "%s.retail-backup", toml);
			const bool repaired = (!read || CopyFileA(toml, backup, TRUE) != 0 || GetLastError() == ERROR_FILE_EXISTS) &&
			                      WriteFileText(toml, save_mode::Repair(text));
			char notice[256];
			if (repaired) {
				save_mode::RepairedNotice(notice, sizeof(notice));
			} else {
				save_mode::NotRepairedNotice(notice, sizeof(notice));
			}
			const bool drawn = ShowNotice(context, notice);
			char line[MAX_PATH * 3 + 360];
			std::snprintf(line, sizeof(line),
			              "mxl2012-core: savemode the mod's d2rloader.toml %s (%s): this start writes D2R's retail saves, which cannot hold "
			              "Median's stats 511-537; %s; %s (docs/bugs.md #512)",
			              !read ? "is missing" : (mode == save_mode::Mode::Missing ? "has no [d2rcore.save_format] mode" : "asks for another mode"),
			              toml, repaired ? "mode = \"extended\" written, restart the game" : "the file could not be written",
			              drawn ? "notice on screen" : "no overlay service, this log only");
			context->LogError(line);
			state = repaired ? "retail this start, file fixed for the next" : "retail, file not writable";
		}
	}
	std::snprintf(g_logPath, sizeof(g_logPath), "%s\\d2rloader\\logs\\d2rloader.log", gameDir != nullptr ? gameDir : "");
	g_stop.store(false);
	g_thread = CreateThread(nullptr, 0, WatchLog, nullptr, 0, nullptr);
	std::snprintf(report, reportSize, "save format %s; cancelled saves watched in %s%s", state, "d2rloader\\logs\\d2rloader.log",
	              g_thread != nullptr ? "" : " (watch thread failed)");
	return g_thread != nullptr;
}

auto SaveModeFailures() noexcept -> int {
	return g_failures.load();
}

void StopSaveMode() noexcept {
	g_stop.store(true);
	if (g_thread != nullptr) {
		WaitForSingleObject(g_thread, 2000);
		CloseHandle(g_thread);
		g_thread = nullptr;
	}
}

// A stand-in for D2RLoader.exe in the downloader's Play tests (tools/launcher_play_stress.py, bug #539): FileVersion
// 1.3.1-beta like D2RLoader, so the downloader's loader check passes in a fake D2R folder. It appends its command line to
// fake-loader.log next to it, then runs for the seconds in fake-loader.txt (default 8), so Play sees a game that starts,
// runs and ends. It never starts anything.
#include <windows.h>

#include <cstdio>
#include <cstdlib>
#include <string>

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
	wchar_t exe[MAX_PATH];
	DWORD n = GetModuleFileNameW(nullptr, exe, MAX_PATH);
	std::wstring dir(exe, n);
	dir = dir.substr(0, dir.find_last_of(wchar_t(92)) + 1);
	int seconds = 8;
	if (FILE* f = _wfopen((dir + L"fake-loader.txt").c_str(), L"r")) {
		if (std::fscanf(f, "%d", &seconds) != 1)
			seconds = 8;
		std::fclose(f);
	}
	if (FILE* f = _wfopen((dir + L"fake-loader.log").c_str(), L"a, ccs=UTF-8")) {
		std::fwprintf(f, L"%lu %ls\n", GetCurrentProcessId(), GetCommandLineW());
		std::fclose(f);
	}
	Sleep(DWORD(seconds) * 1000);
	return 0;
}

#include "util.h"

#include "../core/sha256.h"

#include <windows.h>
#include <knownfolders.h>
#include <shlobj.h>

#include <cstdio>
#include <ctime>
#include <mutex>
#include <vector>

namespace mxl {

std::wstring Wide(const std::string& s) {
	if (s.empty())
		return {};
	int n = MultiByteToWideChar(CP_UTF8, 0, s.data(), int(s.size()), nullptr, 0);
	std::wstring w(size_t(n), L'\0');
	MultiByteToWideChar(CP_UTF8, 0, s.data(), int(s.size()), w.data(), n);
	return w;
}

std::string Utf8(const std::wstring& w) {
	if (w.empty())
		return {};
	int n = WideCharToMultiByte(CP_UTF8, 0, w.data(), int(w.size()), nullptr, 0, nullptr, nullptr);
	std::string s(size_t(n), '\0');
	WideCharToMultiByte(CP_UTF8, 0, w.data(), int(w.size()), s.data(), n, nullptr, nullptr);
	return s;
}

std::wstring LongPath(const std::wstring& path) {
	if (path.rfind(L"\\\\?\\", 0) == 0 || path.size() < 3)
		return path;
	if (path.rfind(L"\\\\", 0) == 0)
		return L"\\\\?\\UNC\\" + path.substr(2);
	std::wstring p = path;
	for (auto& c : p)
		if (c == L'/')
			c = L'\\';
	// \\?\ turns off Windows' path parsing: a relative path ("--game-dir fake-d2r") or ".." must be made absolute first.
	if (DWORD n = GetFullPathNameW(p.c_str(), 0, nullptr, nullptr)) {
		std::wstring full(n, L'\0');
		if (DWORD m = GetFullPathNameW(p.c_str(), n, full.data(), nullptr); m && m < n) {
			full.resize(m);
			p = full;
			if (p.rfind(L"\\\\", 0) == 0)
				return L"\\\\?\\UNC\\" + p.substr(2);
		}
	}
	return L"\\\\?\\" + p;
}

std::wstring JoinPath(const std::wstring& a, const std::wstring& b) {
	std::wstring r = a;
	if (!r.empty() && r.back() != L'\\' && r.back() != L'/')
		r += L'\\';
	for (wchar_t c : b)
		r += c == L'/' ? L'\\' : c;
	return r;
}

std::wstring ParentDir(const std::wstring& path) {
	size_t p = path.find_last_of(L"\\/");
	return p == std::wstring::npos ? L"" : path.substr(0, p);
}

namespace {
std::wstring NormForCompare(const std::wstring& p) {
	wchar_t full[MAX_PATH * 4];
	DWORD n = GetFullPathNameW(p.c_str(), DWORD(std::size(full)), full, nullptr);
	std::wstring s = n && n < std::size(full) ? std::wstring(full, n) : p;
	for (auto& c : s)
		c = c == L'/' ? L'\\' : wchar_t(towlower(c));
	while (s.size() > 3 && s.back() == L'\\')
		s.pop_back();
	return s;
}
}  // namespace

bool SamePath(const std::wstring& a, const std::wstring& b) { return NormForCompare(a) == NormForCompare(b); }

bool PathUnder(const std::wstring& path, const std::wstring& dir) {
	std::wstring p = NormForCompare(path), d = NormForCompare(dir);
	if (p == d)
		return true;
	if (d.back() != L'\\')
		d += L'\\';
	return p.rfind(d, 0) == 0;
}

bool FileExists(const std::wstring& path) {
	DWORD a = GetFileAttributesW(LongPath(path).c_str());
	return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

bool DirExists(const std::wstring& path) {
	DWORD a = GetFileAttributesW(LongPath(path).c_str());
	return a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY);
}

bool MakeDirs(const std::wstring& dir) {
	if (dir.empty() || DirExists(dir))
		return true;
	std::wstring parent = ParentDir(dir);
	if (!parent.empty() && parent != dir && !(parent.size() == 2 && parent[1] == L':') && !MakeDirs(parent))
		return false;
	return CreateDirectoryW(LongPath(dir).c_str(), nullptr) || GetLastError() == ERROR_ALREADY_EXISTS;
}

bool ReadWholeFile(const std::wstring& path, std::string& out) {
	HANDLE h = CreateFileW(LongPath(path).c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr,
	                       OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
	if (h == INVALID_HANDLE_VALUE)
		return false;
	LARGE_INTEGER sz;
	bool ok = GetFileSizeEx(h, &sz) && sz.QuadPart < (1ll << 31);
	if (ok) {
		out.resize(size_t(sz.QuadPart));
		DWORD got = 0;
		ok = out.empty() || (::ReadFile(h, out.data(), DWORD(out.size()), &got, nullptr) && got == out.size());
	}
	CloseHandle(h);
	return ok;
}

bool WriteFileAtomic(const std::wstring& path, const void* data, size_t size) {
	MakeDirs(ParentDir(path));
	std::wstring tmp = path + L".mxlpart";
	HANDLE h = CreateFileW(LongPath(tmp).c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
	if (h == INVALID_HANDLE_VALUE)
		return false;
	auto p = static_cast<const char*>(data);
	bool ok = true;
	for (size_t done = 0; ok && done < size;) {
		DWORD chunk = DWORD(size - done > (1u << 30) ? (1u << 30) : size - done), wrote = 0;
		ok = ::WriteFile(h, p + done, chunk, &wrote, nullptr) && wrote == chunk;
		done += wrote;
	}
	ok = ok && FlushFileBuffers(h);
	CloseHandle(h);
	if (ok)
		ok = MoveFileExW(LongPath(tmp).c_str(), LongPath(path).c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
	if (!ok)
		DeleteFileW(LongPath(tmp).c_str());
	return ok;
}

bool WriteFileAtomic(const std::wstring& path, const std::string& text) { return WriteFileAtomic(path, text.data(), text.size()); }

bool FileSize(const std::wstring& path, uint64_t& size, uint64_t* mtime) {
	WIN32_FILE_ATTRIBUTE_DATA d;
	if (!GetFileAttributesExW(LongPath(path).c_str(), GetFileExInfoStandard, &d) || (d.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY))
		return false;
	size = (uint64_t(d.nFileSizeHigh) << 32) | d.nFileSizeLow;
	if (mtime)
		*mtime = (uint64_t(d.ftLastWriteTime.dwHighDateTime) << 32) | d.ftLastWriteTime.dwLowDateTime;
	return true;
}

std::string FileSha256(const std::wstring& path, const std::function<void(uint64_t)>& onBytes) {
	HANDLE h = CreateFileW(LongPath(path).c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_FLAG_SEQUENTIAL_SCAN, nullptr);
	if (h == INVALID_HANDLE_VALUE)
		return "";
	Sha256 s;
	std::vector<char> buf(1 << 20);
	DWORD got = 0;
	bool ok = true;
	while ((ok = ::ReadFile(h, buf.data(), DWORD(buf.size()), &got, nullptr)) && got) {
		s.Update(buf.data(), got);
		if (onBytes)
			onBytes(got);
	}
	CloseHandle(h);
	return ok ? s.HexDigest() : "";
}

std::wstring KnownFolder(int which) {
	const KNOWNFOLDERID& id = which == 0 ? FOLDERID_LocalAppData : which == 1 ? FOLDERID_SavedGames : which == 3 ? FOLDERID_RoamingAppData : FOLDERID_ProgramData;
	PWSTR p = nullptr;
	std::wstring out;
	if (SUCCEEDED(SHGetKnownFolderPath(id, KF_FLAG_DEFAULT, nullptr, &p)))
		out = p;
	CoTaskMemFree(p);
	return out;
}

std::wstring LastErrorText(unsigned long code) {
	wchar_t* msg = nullptr;
	FormatMessageW(FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS, nullptr, code, 0,
	               reinterpret_cast<wchar_t*>(&msg), 0, nullptr);
	std::wstring s = msg ? msg : L"";
	LocalFree(msg);
	while (!s.empty() && (s.back() == L'\n' || s.back() == L'\r' || s.back() == L' ' || s.back() == L'.'))
		s.pop_back();
	return s + L" (" + std::to_wstring(code) + L")";
}

namespace {
std::mutex g_logMutex;
std::wstring g_logFile;
bool g_console = false;
}  // namespace

void LogInit(const std::wstring& file, bool console) {
	g_logFile = file;
	g_console = console;
	MakeDirs(ParentDir(file));
	uint64_t size = 0;
	if (FileSize(file, size) && size > (4u << 20))
		MoveFileExW(file.c_str(), (file + L".old").c_str(), MOVEFILE_REPLACE_EXISTING);
}

void Log(const std::string& line) {
	std::lock_guard<std::mutex> lock(g_logMutex);
	SYSTEMTIME t;
	GetLocalTime(&t);
	char stamp[32];
	std::snprintf(stamp, sizeof(stamp), "%04d-%02d-%02d %02d:%02d:%02d ", t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond);
	std::string text = stamp + line + "\r\n";
	if (!g_logFile.empty()) {
		HANDLE h = CreateFileW(g_logFile.c_str(), FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_ALWAYS,
		                       FILE_ATTRIBUTE_NORMAL, nullptr);
		if (h != INVALID_HANDLE_VALUE) {
			DWORD w;
			::WriteFile(h, text.data(), DWORD(text.size()), &w, nullptr);
			CloseHandle(h);
		}
	}
	if (g_console) {
		HANDLE out = GetStdHandle(STD_OUTPUT_HANDLE);
		if (out && out != INVALID_HANDLE_VALUE) {
			std::string l = line + "\n";
			DWORD w;
			::WriteFile(out, l.data(), DWORD(l.size()), &w, nullptr);
		}
	}
}

}  // namespace mxl

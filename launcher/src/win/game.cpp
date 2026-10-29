#include "game.h"

#include "util.h"
#include "../core/paths.h"

#include <windows.h>
#include <softpub.h>
#include <tlhelp32.h>
#include <wincrypt.h>
#include <wintrust.h>

#include <algorithm>
#include <cstring>

namespace mxl {
namespace {

std::wstring RegString(HKEY root, const wchar_t* key, const wchar_t* value, REGSAM view = 0) {
	HKEY h;
	if (RegOpenKeyExW(root, key, 0, KEY_READ | view, &h) != ERROR_SUCCESS)
		return L"";
	wchar_t buf[1024];
	DWORD type = 0, size = sizeof(buf);
	std::wstring out;
	if (RegQueryValueExW(h, value, nullptr, &type, reinterpret_cast<BYTE*>(buf), &size) == ERROR_SUCCESS && (type == REG_SZ || type == REG_EXPAND_SZ)) {
		out.assign(buf, size / sizeof(wchar_t));
		while (!out.empty() && out.back() == L'\0')
			out.pop_back();
	}
	RegCloseKey(h);
	return out;
}

std::wstring Env(const wchar_t* name) {
	wchar_t buf[1024];
	DWORD n = GetEnvironmentVariableW(name, buf, DWORD(std::size(buf)));
	return n && n < std::size(buf) ? std::wstring(buf, n) : L"";
}

std::wstring TrimSlash(std::wstring p) {
	while (p.size() > 3 && (p.back() == L'\\' || p.back() == L'/'))
		p.pop_back();
	return p;
}

}  // namespace

bool LooksLikeD2R(const std::wstring& dir) {
	return !dir.empty() && FileExists(JoinPath(dir, L"D2R.exe")) && DirExists(JoinPath(dir, L"Data"));
}

std::string ExeFileVersion(const std::wstring& exe) {
	DWORD dummy = 0, size = GetFileVersionInfoSizeW(exe.c_str(), &dummy);
	if (!size)
		return "";
	std::vector<uint8_t> buf(size);
	if (!GetFileVersionInfoW(exe.c_str(), 0, size, buf.data()))
		return "";
	// The string FileVersion ("3.3.93847"; D2RLoader's "1.3.1-beta") first, the fixed binary version as a fallback.
	VS_FIXEDFILEINFO* fi = nullptr;
	UINT len = 0;
	if (!VerQueryValueW(buf.data(), L"\\", reinterpret_cast<void**>(&fi), &len) || !fi || fi->dwSignature != 0xfeef04bd)
		fi = nullptr;
	struct Lang {
		WORD lang, cp;
	}* langs = nullptr;
	if (VerQueryValueW(buf.data(), L"\\VarFileInfo\\Translation", reinterpret_cast<void**>(&langs), &len) && len >= sizeof(Lang)) {
		wchar_t key[64];
		swprintf_s(key, L"\\StringFileInfo\\%04x%04x\\FileVersion", langs[0].lang, langs[0].cp);
		wchar_t* v = nullptr;
		if (VerQueryValueW(buf.data(), key, reinterpret_cast<void**>(&v), &len) && v && len)
			return Utf8(v);
	}
	if (fi)
		return std::to_string(HIWORD(fi->dwFileVersionMS)) + "." + std::to_string(LOWORD(fi->dwFileVersionMS)) + "." +
		       std::to_string(HIWORD(fi->dwFileVersionLS)) + "." + std::to_string(LOWORD(fi->dwFileVersionLS));
	return "";
}

void FileVersionStrings(const std::wstring& file, std::string& productName, std::string& fileDescription) {
	productName.clear();
	fileDescription.clear();
	DWORD dummy = 0, size = GetFileVersionInfoSizeW(file.c_str(), &dummy);
	if (!size)
		return;
	std::vector<uint8_t> buf(size);
	struct Lang {
		WORD lang, cp;
	}* langs = nullptr;
	UINT len = 0;
	if (!GetFileVersionInfoW(file.c_str(), 0, size, buf.data()) ||
	    !VerQueryValueW(buf.data(), L"\\VarFileInfo\\Translation", reinterpret_cast<void**>(&langs), &len) || len < sizeof(Lang))
		return;
	auto value = [&](const wchar_t* name) {
		wchar_t key[96];
		swprintf_s(key, L"\\StringFileInfo\\%04x%04x\\%s", langs[0].lang, langs[0].cp, name);
		wchar_t* v = nullptr;
		return VerQueryValueW(buf.data(), key, reinterpret_cast<void**>(&v), &len) && v && len ? Utf8(v) : std::string();
	};
	productName = value(L"ProductName");
	fileDescription = value(L"FileDescription");
}

D2RInstall InspectD2R(const std::wstring& dir, const std::string& source) {
	D2RInstall d;
	d.dir = TrimSlash(dir);
	d.source = source;
	std::string info;
	if (ReadWholeFile(JoinPath(d.dir, L".build.info"), info))
		d.infoVersion = BuildInfoVersion(info);
	d.exeVersion = ExeFileVersion(JoinPath(d.dir, L"D2R.exe"));
	d.build = CheckBuild(d.infoVersion, d.exeVersion);
	return d;
}

std::vector<D2RInstall> FindD2RInstalls() {
	std::vector<std::pair<std::wstring, std::string>> candidates;
	const wchar_t* uninstall[] = {L"SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Diablo II Resurrected",
	                              L"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Diablo II Resurrected"};
	for (const wchar_t* k : uninstall) {
		for (HKEY root : {HKEY_LOCAL_MACHINE, HKEY_CURRENT_USER}) {
			std::wstring loc = RegString(root, k, L"InstallLocation");
			if (!loc.empty())
				candidates.emplace_back(loc, "Battle.net");
		}
	}
	// Steam: every library in libraryfolders.vdf, the app manifest that names D2R
	std::wstring steam = RegString(HKEY_CURRENT_USER, L"Software\\Valve\\Steam", L"SteamPath");
	if (steam.empty())
		steam = RegString(HKEY_LOCAL_MACHINE, L"SOFTWARE\\WOW6432Node\\Valve\\Steam", L"InstallPath");
	if (!steam.empty()) {
		std::string vdf;
		std::vector<std::string> libs;
		if (ReadWholeFile(JoinPath(steam, L"steamapps\\libraryfolders.vdf"), vdf))
			libs = SteamLibraryPaths(vdf);
		libs.push_back(Utf8(steam));
		for (const auto& lib : libs) {
			std::wstring apps = JoinPath(Wide(lib), L"steamapps");
			WIN32_FIND_DATAW fd;
			HANDLE h = FindFirstFileW(JoinPath(apps, L"appmanifest_*.acf").c_str(), &fd);
			if (h == INVALID_HANDLE_VALUE)
				continue;
			do {
				std::string acf;
				if (ReadWholeFile(JoinPath(apps, fd.cFileName), acf) && AcfIsD2R(acf))
					candidates.emplace_back(JoinPath(apps, L"common\\" + Wide(AcfValue(acf, "installdir"))), "Steam");
			} while (FindNextFileW(h, &fd));
			FindClose(h);
		}
	}
	for (const wchar_t* pf : {L"ProgramFiles(x86)", L"ProgramFiles"}) {
		std::wstring p = Env(pf);
		if (!p.empty())
			candidates.emplace_back(JoinPath(p, L"Diablo II Resurrected"), "default folder");
	}
	std::vector<D2RInstall> out;
	for (const auto& [dir, src] : candidates) {
		if (!LooksLikeD2R(dir))
			continue;
		bool dup = false;
		for (const auto& o : out)
			dup = dup || SamePath(o.dir, dir);
		if (!dup)
			out.push_back(InspectD2R(dir, src));
	}
	std::stable_sort(out.begin(), out.end(), [](const D2RInstall& a, const D2RInstall& b) {
		return (a.build.verdict == BuildVerdict::Ok) > (b.build.verdict == BuildVerdict::Ok);
	});
	return out;
}

bool FreeBytes(const std::wstring& path, uint64_t& free) {
	std::wstring probe = path;
	while (!probe.empty() && !DirExists(probe))
		probe = ParentDir(probe);
	ULARGE_INTEGER avail{};
	if (probe.empty() || !GetDiskFreeSpaceExW((probe.size() == 2 ? probe + L"\\" : probe).c_str(), &avail, nullptr, nullptr))
		return false;
	free = avail.QuadPart;
	return true;
}

bool RemoveTree(const std::wstring& dir, std::string& error) {
	WIN32_FIND_DATAW fd;
	HANDLE h = FindFirstFileExW(LongPath(JoinPath(dir, L"*")).c_str(), FindExInfoBasic, &fd, FindExSearchNameMatch, nullptr, 0);
	if (h != INVALID_HANDLE_VALUE) {
		do {
			std::wstring name = fd.cFileName;
			if (name == L"." || name == L"..")
				continue;
			std::wstring p = JoinPath(dir, name);
			if (fd.dwFileAttributes & FILE_ATTRIBUTE_READONLY)
				SetFileAttributesW(LongPath(p).c_str(), fd.dwFileAttributes & ~DWORD(FILE_ATTRIBUTE_READONLY));
			if ((fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) && !(fd.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT)) {
				if (!RemoveTree(p, error)) {
					FindClose(h);
					return false;
				}
			} else if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
				RemoveDirectoryW(LongPath(p).c_str());  // a junction: remove the link only
			} else if (!DeleteFileW(LongPath(p).c_str())) {
				error = "cannot delete " + Utf8(p) + ": " + Utf8(LastErrorText(GetLastError()));
				FindClose(h);
				return false;
			}
		} while (FindNextFileW(h, &fd));
		FindClose(h);
	}
	if (!RemoveDirectoryW(LongPath(dir).c_str()) && GetLastError() != ERROR_FILE_NOT_FOUND && GetLastError() != ERROR_PATH_NOT_FOUND) {
		error = "cannot delete " + Utf8(dir) + ": " + Utf8(LastErrorText(GetLastError()));
		return false;
	}
	return true;
}

std::vector<GameProcess> ProcessesUnder(const std::wstring& dir) {
	std::vector<GameProcess> out;
	HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
	if (snap == INVALID_HANDLE_VALUE)
		return out;
	PROCESSENTRY32W pe{};
	pe.dwSize = sizeof(pe);
	const DWORD self = GetCurrentProcessId();
	for (BOOL ok = Process32FirstW(snap, &pe); ok; ok = Process32NextW(snap, &pe)) {
		// Only the game counts: D2R.exe and D2RLoader*.exe (slots run renamed copies like D2RLoader-s2.exe). The
		// downloader itself (players do save it into the D2R folder), Battle.net's "Diablo II Resurrected Launcher.exe",
		// BlizzardError.exe and the like do not hold the mod's files.
		if (pe.th32ProcessID == self || !IsGameProcessName(Utf8(pe.szExeFile)))
			continue;
		HANDLE p = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pe.th32ProcessID);
		if (!p)
			continue;
		wchar_t img[MAX_PATH * 2];
		DWORD n = DWORD(std::size(img));
		if (QueryFullProcessImageNameW(p, 0, img, &n) && PathUnder(std::wstring(img, n), dir))
			out.push_back({pe.th32ProcessID, std::wstring(img, n)});
		CloseHandle(p);
	}
	CloseHandle(snap);
	return out;
}

}  // namespace mxl

namespace mxl {

bool SignerThumbprint(const std::wstring& file, std::string& thumbprint, bool& intact) {
	thumbprint.clear();
	intact = false;
	WINTRUST_FILE_INFO fi{};
	fi.cbStruct = sizeof(fi);
	fi.pcwszFilePath = file.c_str();
	WINTRUST_DATA wd{};
	wd.cbStruct = sizeof(wd);
	wd.dwUIChoice = WTD_UI_NONE;
	wd.fdwRevocationChecks = WTD_REVOKE_NONE;
	wd.dwUnionChoice = WTD_CHOICE_FILE;
	wd.pFile = &fi;
	wd.dwStateAction = WTD_STATEACTION_VERIFY;
	wd.dwProvFlags = WTD_CACHE_ONLY_URL_RETRIEVAL;
	GUID action = WINTRUST_ACTION_GENERIC_VERIFY_V2;
	LONG st = WinVerifyTrust(static_cast<HWND>(INVALID_HANDLE_VALUE), &action, &wd);
	wd.dwStateAction = WTD_STATEACTION_CLOSE;
	WinVerifyTrust(static_cast<HWND>(INVALID_HANDLE_VALUE), &action, &wd);
	// the digest matched; only the chain is not trusted (D2RLoader signs with its own certificate)
	intact = st == ERROR_SUCCESS || st == LONG(CERT_E_UNTRUSTEDROOT) || st == LONG(CERT_E_CHAINING);
	HCERTSTORE store = nullptr;
	HCRYPTMSG msg = nullptr;
	if (!CryptQueryObject(CERT_QUERY_OBJECT_FILE, file.c_str(), CERT_QUERY_CONTENT_FLAG_PKCS7_SIGNED_EMBED, CERT_QUERY_FORMAT_FLAG_BINARY,
	                      0, nullptr, nullptr, nullptr, &store, &msg, nullptr))
		return false;
	bool ok = false;
	DWORD len = 0;
	if (CryptMsgGetParam(msg, CMSG_SIGNER_CERT_INFO_PARAM, 0, nullptr, &len) && len) {
		std::vector<uint8_t> buf(len);
		if (CryptMsgGetParam(msg, CMSG_SIGNER_CERT_INFO_PARAM, 0, buf.data(), &len)) {
			auto info = reinterpret_cast<PCERT_INFO>(buf.data());
			PCCERT_CONTEXT cert = CertFindCertificateInStore(store, X509_ASN_ENCODING | PKCS_7_ASN_ENCODING, 0, CERT_FIND_SUBJECT_CERT, info, nullptr);
			if (cert) {
				uint8_t sha1[20];
				DWORD sl = sizeof(sha1);
				if (CertGetCertificateContextProperty(cert, CERT_SHA1_HASH_PROP_ID, sha1, &sl)) {
					static const char hex[] = "0123456789ABCDEF";
					for (DWORD i = 0; i < sl; ++i) {
						thumbprint += hex[sha1[i] >> 4];
						thumbprint += hex[sha1[i] & 15];
					}
					ok = true;
				}
				CertFreeCertificateContext(cert);
			}
		}
	}
	CryptMsgClose(msg);
	CertCloseStore(store, 0);
	return ok;
}

namespace {
void ListInto(const std::wstring& root, const std::wstring& rel, std::vector<std::string>& out) {
	WIN32_FIND_DATAW fd;
	HANDLE h = FindFirstFileExW(LongPath(JoinPath(JoinPath(root, rel), L"*")).c_str(), FindExInfoBasic, &fd, FindExSearchNameMatch, nullptr, 0);
	if (h == INVALID_HANDLE_VALUE)
		return;
	do {
		std::wstring name = fd.cFileName;
		if (name == L"." || name == L".." || (fd.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT))
			continue;
		std::wstring r = rel.empty() ? name : rel + L"\\" + name;
		if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
			ListInto(root, r, out);
		} else {
			std::string u = Utf8(r);
			std::replace(u.begin(), u.end(), char(92), '/');  // backslash
			out.push_back(u);
		}
	} while (FindNextFileW(h, &fd));
	FindClose(h);
}
}  // namespace

std::vector<std::string> ListFilesUnder(const std::wstring& dir) {
	std::vector<std::string> out;
	ListInto(dir, L"", out);
	return out;
}

}  // namespace mxl

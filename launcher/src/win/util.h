// Windows helpers: UTF-8 / UTF-16, long paths, whole-file reads and atomic writes, hashing files, known folders, log.
#pragma once

#include <cstdint>
#include <functional>
#include <string>

namespace mxl {

std::wstring Wide(const std::string& utf8);
std::string Utf8(const std::wstring& wide);

// "C:\a\b" -> "\\?\C:\a\b" so paths past MAX_PATH work (game data paths get long under a deep copy folder).
std::wstring LongPath(const std::wstring& path);
std::wstring JoinPath(const std::wstring& a, const std::wstring& b);  // b may use '/'
std::wstring ParentDir(const std::wstring& path);
bool SamePath(const std::wstring& a, const std::wstring& b);
bool PathUnder(const std::wstring& path, const std::wstring& dir);  // path is dir or inside it

bool FileExists(const std::wstring& path);
bool DirExists(const std::wstring& path);
bool MakeDirs(const std::wstring& dir);
bool ReadWholeFile(const std::wstring& path, std::string& out);
// Write to "<path>.mxlpart", flush, then replace `path`: a crash never leaves half a file under the real name.
bool WriteFileAtomic(const std::wstring& path, const void* data, size_t size);
bool WriteFileAtomic(const std::wstring& path, const std::string& text);
bool FileSize(const std::wstring& path, uint64_t& size, uint64_t* mtime = nullptr);
// sha256 of a file ("" when it cannot be read)
std::string FileSha256(const std::wstring& path, const std::function<void(uint64_t)>& onBytes = {});

std::wstring KnownFolder(int which);  // 0 LocalAppData, 1 Saved Games, 2 ProgramData, 3 (roaming) AppData
std::wstring LastErrorText(unsigned long code);

// Log to %data%\launcher.log and to the console when there is one (CLI mode).
void LogInit(const std::wstring& file, bool console);
void Log(const std::string& line);

}  // namespace mxl

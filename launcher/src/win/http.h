// Downloads over WinHTTP (http/https, redirects followed, byte ranges) and the same calls for file:// sites, so a
// local test folder behaves like the download host.
#pragma once

#include <cstdint>
#include <functional>
#include <string>

namespace mxl {

struct FetchResult {
	bool ok = false;
	int status = 0;           // HTTP status (206 for a range), 200 for a file, 404 for a missing file; 0: no answer
	bool rangeHonoured = false;  // false: the server sent the whole file instead of the range
	uint64_t totalSize = 0;   // whole resource size when known (Content-Range, Content-Length of a 200, file size)
	std::string error;
};

// Calls sink(data, size) for each chunk; sink returns false to cancel. length 0 = to the end. A server that ignores
// the Range header is detected (rangeHonoured false) and its body is skipped up to `offset`.
FetchResult Fetch(const std::string& url, uint64_t offset, uint64_t length,
                  const std::function<bool(const uint8_t*, size_t)>& sink);

// One WinHTTP session kept for many requests (a download worker): its keep-alive connections are reused. Use one per
// thread.
class HttpSession {
public:
	HttpSession();
	~HttpSession();
	HttpSession(const HttpSession&) = delete;
	HttpSession& operator=(const HttpSession&) = delete;
	FetchResult Fetch(const std::string& url, uint64_t offset, uint64_t length, const std::function<bool(const uint8_t*, size_t)>& sink);

private:
	void* h_;
};

// Size of a resource (HEAD, or a 1-byte range when HEAD gives none).
bool FetchSize(const std::string& url, uint64_t& size, std::string& error);

// Whole small resource into memory (manifests). status (optional): the HTTP status, 0 when there was no answer.
bool FetchText(const std::string& url, std::string& out, std::string& error, size_t limit = 64u << 20, int* status = nullptr);

void SetUserAgent(const std::wstring& ua);

}  // namespace mxl

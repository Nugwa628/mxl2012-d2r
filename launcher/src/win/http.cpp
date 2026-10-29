#include "http.h"

#include "util.h"

#include <windows.h>
#include <winhttp.h>

#include <vector>

namespace mxl {
namespace {

std::wstring g_ua = L"D2R-XL-2012-Downloader";

struct Handle {
	HINTERNET h = nullptr;
	~Handle() { if (h) WinHttpCloseHandle(h); }
};

bool IsFileUrl(const std::string& url) { return url.rfind("file://", 0) == 0; }

std::wstring FilePathOfUrl(const std::string& url) {
	std::string p = url.substr(7);  // file:///C:/x -> /C:/x
	if (p.size() >= 3 && p[0] == '/' && p[2] == ':')
		p.erase(0, 1);
	std::string out;
	for (size_t i = 0; i < p.size(); ++i) {  // %20 and friends
		if (p[i] == '%' && i + 2 < p.size() && isxdigit(uint8_t(p[i + 1])) && isxdigit(uint8_t(p[i + 2]))) {
			out += char(std::stoi(p.substr(i + 1, 2), nullptr, 16));
			i += 2;
		} else {
			out += p[i] == '/' ? '\\' : p[i];
		}
	}
	return Wide(out);
}

FetchResult FetchFile(const std::string& url, uint64_t offset, uint64_t length, const std::function<bool(const uint8_t*, size_t)>& sink) {
	FetchResult r;
	std::wstring path = FilePathOfUrl(url);
	HANDLE h = CreateFileW(LongPath(path).c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_FLAG_SEQUENTIAL_SCAN, nullptr);
	if (h == INVALID_HANDLE_VALUE) {
		DWORD e = GetLastError();
		if (e == ERROR_FILE_NOT_FOUND || e == ERROR_PATH_NOT_FOUND)
			r.status = 404;  // like an http site, so callers tell "not there" from "cannot read"
		r.error = "cannot open " + Utf8(path) + ": " + Utf8(LastErrorText(e));
		return r;
	}
	LARGE_INTEGER sz, pos;
	GetFileSizeEx(h, &sz);
	r.totalSize = uint64_t(sz.QuadPart);
	pos.QuadPart = LONGLONG(offset);
	SetFilePointerEx(h, pos, nullptr, FILE_BEGIN);
	uint64_t left = length ? length : (r.totalSize > offset ? r.totalSize - offset : 0);
	std::vector<uint8_t> buf(1 << 20);
	r.ok = true;
	while (left) {
		DWORD want = DWORD(left < buf.size() ? left : buf.size()), got = 0;
		if (!ReadFile(h, buf.data(), want, &got, nullptr) || !got) {
			r.ok = false;
			r.error = "short read in " + Utf8(path);
			break;
		}
		if (!sink(buf.data(), got)) {
			r.ok = false;
			r.error = "cancelled";
			break;
		}
		left -= got;
	}
	CloseHandle(h);
	r.status = 200;
	r.rangeHonoured = true;
	return r;
}

bool Crack(const std::string& url, std::wstring& host, std::wstring& path, INTERNET_PORT& port, bool& https) {
	std::wstring w = Wide(url);
	URL_COMPONENTS c{};
	c.dwStructSize = sizeof(c);
	wchar_t hostBuf[256], pathBuf[4096], extra[4096];
	c.lpszHostName = hostBuf;
	c.dwHostNameLength = DWORD(std::size(hostBuf));
	c.lpszUrlPath = pathBuf;
	c.dwUrlPathLength = DWORD(std::size(pathBuf));
	c.lpszExtraInfo = extra;
	c.dwExtraInfoLength = DWORD(std::size(extra));
	if (!WinHttpCrackUrl(w.c_str(), 0, 0, &c))
		return false;
	host.assign(c.lpszHostName, c.dwHostNameLength);
	path.assign(c.lpszUrlPath, c.dwUrlPathLength);
	path.append(c.lpszExtraInfo, c.dwExtraInfoLength);
	port = c.nPort;
	https = c.nScheme == INTERNET_SCHEME_HTTPS;
	return true;
}

std::wstring Header(HINTERNET req, DWORD which) {
	wchar_t buf[512];
	DWORD len = sizeof(buf);
	if (!WinHttpQueryHeaders(req, which, WINHTTP_HEADER_NAME_BY_INDEX, buf, &len, WINHTTP_NO_HEADER_INDEX))
		return L"";
	return std::wstring(buf, len / sizeof(wchar_t));
}

std::string WinHttpError(const char* what) {
	DWORD e = GetLastError();
	std::string s = what;
	s += ": ";
	if (e >= 12000 && e < 12200) {  // WinHTTP errors are in winhttp.dll's message table
		wchar_t* msg = nullptr;
		FormatMessageW(FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_HMODULE | FORMAT_MESSAGE_IGNORE_INSERTS,
		               GetModuleHandleW(L"winhttp.dll"), e, 0, reinterpret_cast<wchar_t*>(&msg), 0, nullptr);
		s += msg ? Utf8(msg) : "WinHTTP error";
		LocalFree(msg);
		while (!s.empty() && (s.back() == '\n' || s.back() == '\r'))
			s.pop_back();
		s += " (" + std::to_string(e) + ")";
	} else {
		s += Utf8(LastErrorText(e));
	}
	return s;
}

HINTERNET OpenSession() {
	HINTERNET s = WinHttpOpen(g_ua.c_str(), WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY, WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
	if (!s)
		return nullptr;
	DWORD protocols = WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_2 | WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_3;
	if (!WinHttpSetOption(s, WINHTTP_OPTION_SECURE_PROTOCOLS, &protocols, sizeof(protocols))) {
		protocols = WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_2;  // TLS 1.3 needs Windows 11 / Server 2022
		WinHttpSetOption(s, WINHTTP_OPTION_SECURE_PROTOCOLS, &protocols, sizeof(protocols));
	}
	WinHttpSetTimeouts(s, 15000, 15000, 30000, 60000);
	return s;
}

// `shared`: a session kept by the caller (its keep-alive connections are reused), or nullptr for a one-off session
FetchResult FetchHttp(HINTERNET shared, const std::string& url, uint64_t offset, uint64_t length, bool head,
                      const std::function<bool(const uint8_t*, size_t)>& sink) {
	FetchResult r;
	std::wstring host, path;
	INTERNET_PORT port;
	bool https;
	if (!Crack(url, host, path, port, https)) {
		r.error = "bad URL " + url;
		return r;
	}
	Handle own, conn, req;
	HINTERNET session = shared;
	if (!session) {
		session = own.h = OpenSession();
		if (!session) {
			r.error = WinHttpError("WinHttpOpen");
			return r;
		}
	}
	conn.h = WinHttpConnect(session, host.c_str(), port, 0);
	if (!conn.h) {
		r.error = WinHttpError("connect");
		return r;
	}
	req.h = WinHttpOpenRequest(conn.h, head ? L"HEAD" : L"GET", path.c_str(), nullptr, WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES,
	                           https ? WINHTTP_FLAG_SECURE : 0);
	if (!req.h) {
		r.error = WinHttpError("request");
		return r;
	}
	DWORD redirect = WINHTTP_OPTION_REDIRECT_POLICY_DISALLOW_HTTPS_TO_HTTP;
	WinHttpSetOption(req.h, WINHTTP_OPTION_REDIRECT_POLICY, &redirect, sizeof(redirect));
	std::wstring headers;
	if (offset || length) {
		headers = L"Range: bytes=" + std::to_wstring(offset) + L"-" + (length ? std::to_wstring(offset + length - 1) : L"") + L"\r\n";
	}
	if (!WinHttpSendRequest(req.h, headers.empty() ? WINHTTP_NO_ADDITIONAL_HEADERS : headers.c_str(), DWORD(-1L), WINHTTP_NO_REQUEST_DATA,
	                        0, 0, 0) ||
	    !WinHttpReceiveResponse(req.h, nullptr)) {
		r.error = WinHttpError(("download " + url).c_str());
		return r;
	}
	DWORD status = 0, len = sizeof(status);
	WinHttpQueryHeaders(req.h, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, WINHTTP_HEADER_NAME_BY_INDEX, &status, &len,
	                    WINHTTP_NO_HEADER_INDEX);
	r.status = int(status);
	if (status != 200 && status != 206) {
		r.error = "HTTP " + std::to_string(status) + " for " + url;
		return r;
	}
	r.rangeHonoured = status == 206 || (!offset && !length);
	std::wstring cr = Header(req.h, WINHTTP_QUERY_CONTENT_RANGE);  // bytes 0-0/12345
	size_t slash = cr.rfind(L'/');
	if (status == 206 && slash != std::wstring::npos && cr.substr(slash + 1) != L"*")
		r.totalSize = std::stoull(cr.substr(slash + 1));
	else if (status == 200) {
		std::wstring cl = Header(req.h, WINHTTP_QUERY_CONTENT_LENGTH);
		if (!cl.empty())
			r.totalSize = std::stoull(cl);
	}
	if (head) {
		r.ok = true;
		return r;
	}
	uint64_t skip = r.rangeHonoured ? 0 : offset;  // a 200 for a range request: throw away the bytes before `offset`
	uint64_t left = length ? length : UINT64_MAX;
	std::vector<uint8_t> buf(1 << 18);
	for (;;) {
		DWORD got = 0;
		if (!WinHttpReadData(req.h, buf.data(), DWORD(buf.size()), &got)) {
			r.error = WinHttpError("read");
			return r;
		}
		if (!got)
			break;
		const uint8_t* p = buf.data();
		size_t n = got;
		if (skip) {
			size_t s = size_t(skip < n ? skip : n);
			skip -= s;
			p += s;
			n -= s;
		}
		if (n > left)
			n = size_t(left);
		if (n && !sink(p, n)) {
			r.error = "cancelled";
			return r;
		}
		left -= n;
		if (!left)
			break;
	}
	if (length && left) {
		r.error = "connection closed early for " + url;
		return r;
	}
	r.ok = true;
	return r;
}

}  // namespace

void SetUserAgent(const std::wstring& ua) { g_ua = ua; }

FetchResult Fetch(const std::string& url, uint64_t offset, uint64_t length, const std::function<bool(const uint8_t*, size_t)>& sink) {
	if (IsFileUrl(url))
		return FetchFile(url, offset, length, sink);
	return FetchHttp(nullptr, url, offset, length, false, sink);
}

HttpSession::HttpSession() : h_(OpenSession()) {}
HttpSession::~HttpSession() {
	if (h_)
		WinHttpCloseHandle(h_);
}
FetchResult HttpSession::Fetch(const std::string& url, uint64_t offset, uint64_t length,
                               const std::function<bool(const uint8_t*, size_t)>& sink) {
	if (IsFileUrl(url))
		return FetchFile(url, offset, length, sink);
	return FetchHttp(h_, url, offset, length, false, sink);
}

bool FetchSize(const std::string& url, uint64_t& size, std::string& error) {
	if (IsFileUrl(url)) {
		if (!FileSize(FilePathOfUrl(url), size)) {
			error = "missing " + url;
			return false;
		}
		return true;
	}
	FetchResult r = FetchHttp(nullptr, url, 0, 0, true, nullptr);
	if (r.ok && r.totalSize) {
		size = r.totalSize;
		return true;
	}
	r = FetchHttp(nullptr, url, 0, 1, false, [](const uint8_t*, size_t) { return true; });
	if (r.ok && r.totalSize) {
		size = r.totalSize;
		return true;
	}
	error = r.error.empty() ? "size of " + url + " unknown" : r.error;
	return false;
}

bool FetchText(const std::string& url, std::string& out, std::string& error, size_t limit, int* status) {
	out.clear();
	FetchResult r = Fetch(url, 0, 0, [&](const uint8_t* p, size_t n) {
		if (out.size() + n > limit)
			return false;
		out.append(reinterpret_cast<const char*>(p), n);
		return true;
	});
	if (status)
		*status = r.status;
	if (!r.ok)
		error = r.error;
	return r.ok;
}

}  // namespace mxl

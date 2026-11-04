#include "loaderpkg.h"

#include <cctype>
#include <set>
#include <utility>

namespace mxl {
namespace {

std::string Lower(std::string s) {
	for (char& c : s)
		c = char(std::tolower(uint8_t(c)));
	return s;
}

bool StartsWith(const std::string& s, const std::string& p) { return s.compare(0, p.size(), p) == 0; }

bool Hex64(const std::string& s) {
	if (s.size() != 64)
		return false;
	for (char c : s)
		if (!std::isxdigit(uint8_t(c)))
			return false;
	return true;
}

}  // namespace

std::string LoaderZipName(const std::string& url) {
	std::string u = url.substr(0, url.find_first_of("?#"));
	size_t slash = u.find_last_of('/');
	std::string name = slash == std::string::npos ? u : u.substr(slash + 1);
	if (name.size() < 5 || name.size() > 100 || Lower(name).compare(name.size() - 4, 4, ".zip") != 0 || name[0] == '.' ||
	    !SafeRelativePath(name))
		return "";
	return name;
}

bool LoaderPackageUsable(const Manifest::Loader& l, std::string& error) {
	if (l.version.empty()) {
		error = "the release manifest names no D2RLoader version (d2rloader.version)";
		return false;
	}
	if (l.url.empty()) {
		error = "the release manifest has no D2RLoader download (d2rloader.url)";
		return false;
	}
	std::string u = Lower(l.url);
	if (!StartsWith(u, "https://")) {
		error = "the D2RLoader download is not https:// (d2rloader.url " + l.url + ")";
		return false;
	}
	std::string host = u.substr(8, u.find_first_of("/?#:", 8) - 8);
	std::string official = LoaderHost;
	if (host != official && !(host.size() > official.size() + 1 && host.compare(host.size() - official.size() - 1, std::string::npos, "." + official) == 0)) {
		error = "the D2RLoader download is not on " + official + " (d2rloader.url " + l.url + ")";
		return false;
	}
	if (LoaderZipName(l.url).empty()) {
		error = "the D2RLoader download is not a .zip (d2rloader.url " + l.url + ")";
		return false;
	}
	if (l.size == 0 || l.size > LoaderMaxSize) {
		error = "the release manifest has no usable D2RLoader size (d2rloader.size)";
		return false;
	}
	if (!Hex64(l.sha256)) {
		error = "the release manifest has no D2RLoader sha256 (d2rloader.sha256)";
		return false;
	}
	return true;
}

bool PlanLoaderInstall(const std::vector<ZipEntry>& entries, std::vector<LoaderTarget>& result, std::string& error) {
	result.clear();
	std::vector<LoaderTarget> out;  // handed out only when every entry is accepted
	std::set<std::string> seen;
	bool hasLoader = false;
	for (size_t i = 0; i < entries.size(); ++i) {
		const ZipEntry& e = entries[i];
		LoaderTarget t;
		t.entry = i;
		t.dir = e.IsDir();
		t.path = t.dir ? e.name.substr(0, e.name.size() - 1) : e.name;
		if (!SafeRelativePath(t.path)) {
			error = "the D2RLoader ZIP has an unsafe path: " + e.name;
			return false;
		}
		std::string low = Lower(t.path);
		if (!seen.insert(low).second) {
			error = "the D2RLoader ZIP lists " + e.name + " twice";
			return false;
		}
		bool top = low.find('/') == std::string::npos;
		bool ok;
		if (t.dir)
			ok = low == "d2rloader" || StartsWith(low, "d2rloader/") || low == "mods";
		else if (top)
			ok = StartsWith(low, "d2rloader") || StartsWith(low, "d2rcore");
		else
			ok = StartsWith(low, "d2rloader/");
		if (!ok) {
			error = "the D2RLoader ZIP has " + e.name + ", which is not a D2RLoader file; nothing was installed";
			return false;
		}
		t.keepExisting = !t.dir && StartsWith(low, "d2rloader/config/");
		hasLoader = hasLoader || low == "d2rloader.exe";
		out.push_back(t);
	}
	if (!hasLoader) {
		error = "the D2RLoader ZIP has no D2RLoader.exe at its top";
		return false;
	}
	result = std::move(out);
	return true;
}

std::string LoaderRunningRefusal(const std::vector<std::string>& running, const std::string& d2rDir) {
	if (running.empty())
		return "";
	const std::string& exe = running.front();
	size_t slash = exe.find_last_of("\\/");
	return (slash == std::string::npos ? exe : exe.substr(slash + 1)) + " is running from " + d2rDir +
	       ". Close D2RLoader and the game first, then install D2RLoader again.";
}

}  // namespace mxl

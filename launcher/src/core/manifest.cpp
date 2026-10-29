#include "manifest.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>

namespace mxl {
namespace {

bool IsHex64(const std::string& s) {
	if (s.size() != 64)
		return false;
	for (char c : s)
		if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')))
			return false;
	return true;
}

std::string Lower(std::string s) {
	for (auto& c : s)
		c = char(std::tolower(uint8_t(c)));
	return s;
}

}  // namespace

bool SafeRelativePath(const std::string& path) {
	if (path.empty() || path.size() > 400 || path.front() == '/' || path.back() == '/')
		return false;
	size_t start = 0;
	while (start <= path.size()) {
		size_t end = path.find('/', start);
		if (end == std::string::npos)
			end = path.size();
		std::string seg = path.substr(start, end - start);
		if (seg.empty() || seg == "." || seg == ".." || seg.back() == '.' || seg.back() == ' ')
			return false;
		for (char c : seg)
			if (uint8_t(c) < 0x20 || c == '\\' || c == ':' || c == '<' || c == '>' || c == '"' || c == '|' || c == '?' || c == '*')
				return false;
		std::string stem = Lower(seg.substr(0, seg.find('.')));
		static const char* devices[] = {"con", "prn", "aux", "nul", "com1", "com2", "com3", "com4", "com5", "com6", "com7",
		                                "com8", "com9", "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9"};
		for (const char* d : devices)
			if (stem == d)
				return false;
		start = end + 1;
	}
	return true;
}

bool ParseManifest(const std::string& text, Manifest& out, std::string& error) {
	Json j;
	if (!Json::Parse(text, j, error))
		return false;
	Manifest m;
	m.schemaVersion = int(j["schemaVersion"].Int());
	m.version = j["version"].Str();
	m.launcher.version = j["launcher"]["version"].Str();
	m.launcher.path = j["launcher"]["path"].Str();
	m.launcher.size = uint64_t(j["launcher"]["size"].Int());
	m.launcher.sha256 = Lower(j["launcher"]["sha256"].Str());
	if (!m.launcher.path.empty() && !SafeRelativePath(m.launcher.path))
		m.launcher = {};
	if (m.schemaVersion != ManifestSchema) {
		error = "release manifest schemaVersion " + std::to_string(m.schemaVersion) + ", this downloader reads " +
		        std::to_string(ManifestSchema);
		out = Manifest{};
		out.schemaVersion = m.schemaVersion;
		out.version = m.version;
		out.launcher = m.launcher;
		return false;
	}
	m.name = j["name"].Str();
	m.pluginVersion = j["pluginVersion"].Str();
	m.complete = j["complete"].Bool();
	const Json& d2r = j["d2r"];
	m.d2rBuild = d2r["build"].IsString() ? std::atoi(d2r["build"].Str().c_str()) : int(d2r["build"].Int());
	m.d2rVersion = d2r["version"].Str();
	std::string ts = d2r["imageTimestamp"].Str();
	if (!ts.empty())
		m.imageTimestamp = uint32_t(std::strtoul(ts.c_str(), nullptr, 0));
	const Json& ld = j["d2rloader"];
	m.d2rloader.version = ld["version"].Str();
	m.d2rloader.url = ld["url"].Str();
	m.d2rloader.size = uint64_t(ld["size"].Int());
	m.d2rloader.sha256 = Lower(ld["sha256"].Str());
	m.d2rloader.signerThumbprint = ld["signerThumbprint"].Str();
	m.launchDefaultMod = j["launch"]["default_mod"].Str();
	m.launchArguments = j["launch"]["launch_arguments"].Str();
	m.modFolder = j["modFolder"].Str(m.name);
	m.saveFolder = j["saveFolder"].Str();
	m.archive.name = j["archive"]["name"].Str();
	m.archive.path = j["archive"]["path"].Str();
	m.archive.size = uint64_t(j["archive"]["size"].Int());
	m.archive.sha256 = Lower(j["archive"]["sha256"].Str());
	m.objectsBase = j["objectsBase"].Str();
	m.launcherMin = j["launcherMin"].Str();
	if (m.modFolder.empty() || !SafeRelativePath(m.modFolder) || m.modFolder.find('/') != std::string::npos) {
		error = "bad modFolder";
		return false;
	}
	if (m.launchDefaultMod.empty())
		m.launchDefaultMod = m.modFolder;
	auto relOk = [](const std::string& p, bool dir) {
		std::string q = dir && !p.empty() && p.back() == '/' ? p.substr(0, p.size() - 1) : p;
		return q.empty() ? false : SafeRelativePath(q);
	};
	if (m.objectsBase.empty() || m.objectsBase.back() != '/' || !relOk(m.objectsBase, true) ||
	    (!m.archive.path.empty() && !relOk(m.archive.path, false))) {
		error = "missing or bad objectsBase, or a bad archive.path";
		return false;
	}
	if (m.version.empty() || (m.d2rBuild <= 0 && m.d2rVersion.empty())) {
		error = "the manifest lacks version or d2r.version";
		return false;
	}
	for (const Json& d : j["emptyDirs"].items()) {
		if (!SafeRelativePath(d.Str())) {
			error = "unsafe path in emptyDirs: \"" + d.Str() + "\"";
			return false;
		}
		m.emptyDirs.push_back(d.Str());
	}
	std::set<std::string> seen;
	uint64_t total = 0;
	for (const Json& f : j["files"].items()) {
		ManifestFile mf;
		mf.path = f["path"].Str();
		mf.size = uint64_t(f["size"].Int(-1));
		mf.sha256 = Lower(f["sha256"].Str());
		if (!SafeRelativePath(mf.path)) {
			error = "unsafe path in manifest: \"" + mf.path + "\"";
			return false;
		}
		if (!IsHex64(mf.sha256) || f["size"].Num(-1) < 0) {
			error = "bad size or sha256 for \"" + mf.path + "\"";
			return false;
		}
		if (!seen.insert(Lower(mf.path)).second) {  // Windows paths are case-insensitive
			error = "duplicate path in manifest: \"" + mf.path + "\"";
			return false;
		}
		total += mf.size;
		m.files.push_back(std::move(mf));
	}
	if (m.files.empty()) {
		error = "manifest lists no files";
		return false;
	}
	if ((j["fileCount"].IsNumber() && uint64_t(j["fileCount"].Int()) != m.files.size()) ||
	    (j["totalSize"].IsNumber() && uint64_t(j["totalSize"].Int()) != total)) {
		error = "fileCount / totalSize do not match the file list";
		return false;
	}
	for (const Json& k : j["preserve"].items())
		if (SafeRelativePath(k.Str()))
			m.preserve.insert(k.Str());
	out = std::move(m);
	return true;
}

Json ManifestToJson(const Manifest& m) {
	Json j = Json::Object();
	j.Set("schemaVersion", m.schemaVersion);
	j.Set("name", m.name);
	j.Set("version", m.version);
	j.Set("pluginVersion", m.pluginVersion);
	j.Set("complete", m.complete);
	Json d2r = Json::Object();
	d2r.Set("build", std::to_string(m.d2rBuild));
	if (m.imageTimestamp) {
		char buf[16];
		std::snprintf(buf, sizeof buf, "0x%08x", unsigned(m.imageTimestamp));
		d2r.Set("imageTimestamp", std::string(buf));
	}
	j.Set("d2r", d2r);
	Json ld = Json::Object();
	ld.Set("version", m.d2rloader.version).Set("url", m.d2rloader.url).Set("size", m.d2rloader.size);
	ld.Set("sha256", m.d2rloader.sha256).Set("signerThumbprint", m.d2rloader.signerThumbprint);
	j.Set("d2rloader", ld);
	Json launch = Json::Object();
	launch.Set("default_mod", m.launchDefaultMod).Set("launch_arguments", m.launchArguments);
	j.Set("launch", launch);
	j.Set("modFolder", m.modFolder);
	j.Set("saveFolder", m.saveFolder);
	Json keep = Json::Array();
	for (const auto& k : m.preserve)
		keep.Push(k);
	j.Set("preserve", keep);
	Json dirs = Json::Array();
	for (const auto& d : m.emptyDirs)
		dirs.Push(d);
	j.Set("emptyDirs", dirs);
	if (!m.archive.name.empty()) {
		Json a = Json::Object();
		a.Set("format", std::string("7z")).Set("name", m.archive.name).Set("size", m.archive.size).Set("sha256", m.archive.sha256);
		if (!m.archive.path.empty())
			a.Set("path", m.archive.path);
		j.Set("archive", a);
	}
	j.Set("objectsBase", m.objectsBase);
	if (!m.launcher.version.empty()) {
		Json l = Json::Object();
		l.Set("version", m.launcher.version).Set("path", m.launcher.path).Set("size", m.launcher.size).Set("sha256", m.launcher.sha256);
		j.Set("launcher", l);
	}
	if (!m.launcherMin.empty())
		j.Set("launcherMin", m.launcherMin);
	Json files = Json::Array();
	for (const auto& f : m.files) {
		Json e = Json::Object();
		e.Set("path", f.path);
		e.Set("size", f.size);
		e.Set("sha256", f.sha256);
		files.Push(e);
	}
	j.Set("files", files);
	return j;
}

bool ParseChannel(const std::string& text, Channel& out, std::string& error) {
	Json j;
	if (!Json::Parse(text, j, error))
		return false;
	Channel c;
	c.schemaVersion = int(j["schemaVersion"].Int());
	if (c.schemaVersion != 1) {
		error = "unsupported channel schemaVersion " + std::to_string(c.schemaVersion);
		return false;
	}
	c.version = j["version"].Str();
	c.manifest = j["manifest"].Str();
	c.manifestSha256 = Lower(j["manifestSha256"].Str());
	c.publishedAt = j["publishedAt"].Str();
	if (c.version.empty() || !SafeRelativePath(c.manifest) || !IsHex64(c.manifestSha256)) {
		error = "the channel file lacks version, manifest or manifestSha256";
		return false;
	}
	out = std::move(c);
	return true;
}

bool InstallableFromChannel(const Manifest& m, const std::string& channel) {
	return m.complete || (!channel.empty() && channel != "stable");
}

std::string ChannelReadError(const std::string& channel, const std::string& url, int status, const std::string& transportError) {
	if (status == 404)
		return "No release has been published on the " + channel + " channel yet.";
	if (status > 0)
		return "The download site answered " + std::to_string(status) + " for " + url;
	return "Cannot reach the download site (" + url + ")" + (transportError.empty() ? "" : ": " + transportError);
}

std::string SiteRoot(const std::string& setting) {
	const char bs = char(92);  // backslash
	std::string s = setting;
	while (!s.empty() && (s.back() == ' ' || s.back() == bs))
		s.pop_back();
	if (s.rfind("http://", 0) == 0 || s.rfind("https://", 0) == 0 || s.rfind("file://", 0) == 0)
		return s.empty() || s.back() == '/' ? s : s + "/";
	std::string u = "file:///";
	if (s.size() > 2 && s[0] == bs && s[1] == bs) {  // UNC share -> file://server/share
		u = "file://";
		s = s.substr(2);
	}
	for (char c : s) {
		if (c == bs)
			u += '/';
		else if (c == '%' || c == ' ' || c == '#' || c == '?') {
			char buf[4];
			std::snprintf(buf, sizeof buf, "%%%02X", unsigned(uint8_t(c)));
			u += buf;
		} else
			u += c;
	}
	return u.back() == '/' ? u : u + "/";
}

std::string ObjectPath(const std::string& objectsBase, const std::string& sha256) {
	return objectsBase + sha256.substr(0, 2) + "/" + sha256;
}

std::vector<ObjectFetch> GroupObjects(const std::vector<ManifestFile>& files) {
	std::vector<ObjectFetch> out;
	std::map<std::string, size_t> at;
	for (const auto& f : files) {
		auto [it, fresh] = at.emplace(f.sha256, out.size());
		if (fresh)
			out.push_back({f.sha256, f.size, {}});
		out[it->second].paths.push_back(f.path);
	}
	return out;
}

bool RuntimeOutput(const std::string& path) {
	std::string p = Lower(path);
	return p.rfind("d2rloader/logs/", 0) == 0 || p.rfind("d2rloader/crashes/", 0) == 0 || p == "mxl2012-install.json" ||
	       p.rfind("mxl2012-download/", 0) == 0;
}

InstallPlan PlanInstall(const Manifest& next, const std::vector<std::string>& local,
                        const std::function<std::string(const std::string&)>& current) {
	InstallPlan plan;
	std::set<std::string> listed, keep;
	for (const auto& k : next.preserve)
		keep.insert(Lower(k));
	for (const auto& f : next.files) {
		listed.insert(Lower(f.path));
		std::string have = current(f.path);
		if (have == f.sha256)
			continue;
		if (!have.empty() && keep.count(Lower(f.path))) {  // the player's file: written only when missing
			plan.preserved.push_back(f.path);
			continue;
		}
		plan.fetch.push_back(f);
		plan.fetchBytes += f.size;
	}
	for (const auto& p : local)
		if (!listed.count(Lower(p)) && !keep.count(Lower(p)) && !RuntimeOutput(p))
			plan.remove.push_back(p);
	return plan;
}

int CompareVersions(const std::string& a, const std::string& b) {
	auto split = [](const std::string& v, std::vector<long>& nums, std::string& suffix) {
		size_t i = 0;
		if (i < v.size() && (v[i] == 'v' || v[i] == 'V'))
			++i;
		while (i < v.size()) {
			if (!std::isdigit(uint8_t(v[i])))
				break;
			long n = 0;
			while (i < v.size() && std::isdigit(uint8_t(v[i])))
				n = n * 10 + (v[i++] - '0');
			nums.push_back(n);
			if (i < v.size() && v[i] == '.')
				++i;
			else
				break;
		}
		suffix = v.substr(i);
	};
	std::vector<long> na, nb;
	std::string sa, sb;
	split(a, na, sa);
	split(b, nb, sb);
	for (size_t i = 0; i < std::max(na.size(), nb.size()); ++i) {
		long x = i < na.size() ? na[i] : 0, y = i < nb.size() ? nb[i] : 0;
		if (x != y)
			return x < y ? -1 : 1;
	}
	if (sa == sb)
		return 0;
	if (sa.empty())
		return 1;  // 1.3.1 > 1.3.1-beta
	if (sb.empty())
		return -1;
	return sa < sb ? -1 : 1;
}

std::string ResolveUrl(const std::string& base, const std::string& ref) {
	auto hasScheme = [](const std::string& u) {
		return u.rfind("http://", 0) == 0 || u.rfind("https://", 0) == 0 || u.rfind("file://", 0) == 0;
	};
	if (hasScheme(ref))
		return ref;
	if (!ref.empty() && ref[0] == '/') {
		size_t p = base.find("://");
		size_t host = p == std::string::npos ? std::string::npos : base.find('/', p + 3);
		return (host == std::string::npos ? base : base.substr(0, host)) + ref;
	}
	size_t q = base.find_first_of("?#");
	std::string b = q == std::string::npos ? base : base.substr(0, q);
	size_t slash = b.rfind('/');
	return (slash == std::string::npos ? b + "/" : b.substr(0, slash + 1)) + ref;
}

}  // namespace mxl

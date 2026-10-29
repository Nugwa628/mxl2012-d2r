#include "detect.h"

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <sstream>

namespace mxl {
namespace {

std::vector<std::string> Split(const std::string& s, char sep) {
	std::vector<std::string> out;
	size_t start = 0;
	for (;;) {
		size_t p = s.find(sep, start);
		out.push_back(s.substr(start, p == std::string::npos ? std::string::npos : p - start));
		if (p == std::string::npos)
			return out;
		start = p + 1;
	}
}

std::string Trim(const std::string& s) {
	size_t a = 0, b = s.size();
	while (a < b && std::isspace(uint8_t(s[a]))) ++a;
	while (b > a && std::isspace(uint8_t(s[b - 1]))) --b;
	return s.substr(a, b - a);
}

std::string Lower(std::string s) {
	for (auto& c : s)
		c = char(std::tolower(uint8_t(c)));
	return s;
}

// KeyValues tokens: quoted strings (with \\ \" \n \t escapes), braces; // comments.
std::vector<std::string> VdfTokens(const std::string& s) {
	std::vector<std::string> out;
	size_t i = 0;
	while (i < s.size()) {
		char c = s[i];
		if (std::isspace(uint8_t(c))) { ++i; continue; }
		if (c == '/' && i + 1 < s.size() && s[i + 1] == '/') {
			while (i < s.size() && s[i] != '\n') ++i;
			continue;
		}
		if (c == '{' || c == '}') { out.emplace_back(1, c); ++i; continue; }
		std::string t;
		if (c == '"') {
			++i;
			while (i < s.size() && s[i] != '"') {
				if (s[i] == '\\' && i + 1 < s.size()) {
					char e = s[i + 1];
					t += e == 'n' ? '\n' : e == 't' ? '\t' : e;
					i += 2;
					continue;
				}
				t += s[i++];
			}
			++i;
		} else {
			while (i < s.size() && !std::isspace(uint8_t(s[i])) && s[i] != '{' && s[i] != '}' && s[i] != '"')
				t += s[i++];
		}
		out.push_back("\x01" + t);  // mark strings so a value "{" is not a brace
	}
	return out;
}

}  // namespace

std::string BuildInfoVersion(const std::string& text) {
	std::istringstream in(text);
	std::string line;
	std::vector<std::string> head;
	int versionCol = -1, activeCol = -1;
	std::string first;
	while (std::getline(in, line)) {
		if (!line.empty() && line.back() == '\r')
			line.pop_back();
		if (line.empty() || line[0] == '#')
			continue;
		auto cols = Split(line, '|');
		if (head.empty()) {
			head = cols;
			for (size_t k = 0; k < cols.size(); ++k) {
				std::string name = cols[k].substr(0, cols[k].find('!'));
				if (name == "Version") versionCol = int(k);
				if (name == "Active") activeCol = int(k);
			}
			if (versionCol < 0)
				return "";
			continue;
		}
		if (int(cols.size()) <= versionCol)
			continue;
		std::string v = Trim(cols[size_t(versionCol)]);
		if (v.empty())
			continue;
		if (activeCol < 0 || (int(cols.size()) > activeCol && Trim(cols[size_t(activeCol)]) == "1"))
			return v;
		if (first.empty())
			first = v;
	}
	return first;
}

int BuildNumber(const std::string& version) {
	int n = 0;
	bool any = false;
	for (size_t i = 0; i < version.size(); ++i) {
		if (std::isdigit(uint8_t(version[i]))) {
			if (!any || (i > 0 && !std::isdigit(uint8_t(version[i - 1])))) {
				n = 0;
			}
			n = n * 10 + (version[i] - '0');
			any = true;
			if (n > 100000000)
				return 0;
		}
	}
	return any ? n : 0;
}

std::vector<std::string> SteamLibraryPaths(const std::string& vdf) {
	std::vector<std::string> out;
	auto t = VdfTokens(vdf);
	for (size_t i = 0; i + 1 < t.size(); ++i) {
		if (t[i][0] == '\x01' && Lower(t[i].substr(1)) == "path" && t[i + 1][0] == '\x01') {
			out.push_back(t[i + 1].substr(1));
			++i;
		}
	}
	return out;
}

std::string AcfValue(const std::string& acf, const std::string& key) {
	auto t = VdfTokens(acf);
	int depth = 0;
	for (size_t i = 0; i < t.size(); ++i) {
		if (t[i] == "{") { ++depth; continue; }
		if (t[i] == "}") { --depth; continue; }
		if (depth == 1 && i + 1 < t.size() && t[i][0] == '\x01' && t[i + 1][0] == '\x01') {
			if (Lower(t[i].substr(1)) == Lower(key))
				return t[i + 1].substr(1);
			++i;  // skip the value
		}
	}
	return "";
}

bool AcfIsD2R(const std::string& acf) {
	std::string name = Lower(AcfValue(acf, "name")), dir = Lower(AcfValue(acf, "installdir"));
	return name.find("diablo ii: resurrected") != std::string::npos || name.find("diablo ii resurrected") != std::string::npos ||
	       dir == "diablo ii resurrected";
}

std::string GameVersion(const std::string& version) {
	int major = 0, minor = 0;
	size_t i = 0, n = version.size();
	auto num = [&](int& out) {
		size_t start = i;
		while (i < n && version[i] >= '0' && version[i] <= '9')
			out = out * 10 + (version[i++] - '0');
		return i > start;
	};
	while (i < n && !(version[i] >= '0' && version[i] <= '9'))
		++i;
	if (!num(major) || i >= n || version[i] != '.')
		return "";
	++i;
	if (!num(minor))
		return "";
	return std::to_string(major) + "." + std::to_string(minor);
}

static int CompareGameVersions(const std::string& a, const std::string& b) {
	int am = 0, an = 0, bm = 0, bn = 0;
	am = std::atoi(a.c_str()); an = a.find('.') == std::string::npos ? 0 : std::atoi(a.c_str() + a.find('.') + 1);
	bm = std::atoi(b.c_str()); bn = b.find('.') == std::string::npos ? 0 : std::atoi(b.c_str() + b.find('.') + 1);
	return am != bm ? (am < bm ? -1 : 1) : (an == bn ? 0 : (an < bn ? -1 : 1));
}

BuildCheck CheckBuild(const std::string& infoVersion, const std::string& exeVersion, const std::string& required) {
	BuildCheck c;
	c.build = BuildNumber(!infoVersion.empty() ? infoVersion : exeVersion);
	c.version = GameVersion(!infoVersion.empty() ? infoVersion : exeVersion);
	if (c.version.empty())
		c.version = GameVersion(exeVersion);
	std::string shown = c.version.empty() ? std::string() : "D2R " + c.version + (c.build ? " (build " + std::to_string(c.build) + ")" : "");
	if (c.version.empty()) {
		c.message = "Cannot read the D2R version (.build.info and D2R.exe)";
		return c;
	}
	int cmp = CompareGameVersions(c.version, required);
	if (cmp == 0) {
		c.verdict = BuildVerdict::Ok;
		c.message = shown;
	} else if (cmp > 0) {
		c.verdict = BuildVerdict::Newer;
		c.message = "D2R-XL 2012 needs D2R " + required + "; this is " + shown + ". Waiting for a D2R-XL 2012 update for the new version.";
	} else {
		c.verdict = BuildVerdict::Older;
		c.message = "D2R-XL 2012 needs D2R " + required + "; this is " + shown + ". Update D2R in Battle.net or Steam first.";
	}
	return c;
}

}  // namespace mxl

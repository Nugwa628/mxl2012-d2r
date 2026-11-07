#include "paths.h"

#include "json.h"
#include "manifest.h"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

namespace mxl {
namespace {

std::string NormPath(const std::string& p) {  // lower case, '/' separators, no trailing '/'
	std::string s;
	for (char c : p)
		s += c == char(92) ? '/' : char(std::tolower(uint8_t(c)));  // char(92): backslash
	while (s.size() > 1 && s.back() == '/')
		s.pop_back();
	return s;
}

std::string Join(const std::string& a, const std::string& b) {
	if (a.empty())
		return b;
	return a.back() == char(92) || a.back() == '/' ? a + b : a + char(92) + b;
}

std::vector<std::string> Lines(const std::string& text) {
	std::vector<std::string> out;
	size_t start = 0;
	while (start < text.size()) {
		size_t p = text.find('\n', start);
		if (p == std::string::npos) {
			out.push_back(text.substr(start));
			break;
		}
		out.push_back(text.substr(start, p - start));
		start = p + 1;
	}
	return out;
}

std::string Strip(const std::string& s) {
	size_t a = 0, b = s.size();
	while (a < b && (s[a] == ' ' || s[a] == '\t' || s[a] == '\r')) ++a;
	while (b > a && (s[b - 1] == ' ' || s[b - 1] == '\t' || s[b - 1] == '\r')) --b;
	return s.substr(a, b - a);
}

bool IsHeader(const std::string& line, std::string* name = nullptr) {
	std::string t = Strip(line);
	if (t.size() < 3 || t[0] != '[')
		return false;
	size_t close = t.find(']');
	if (close == std::string::npos)
		return false;
	if (name)
		*name = Strip(t.substr(1, close - 1));
	return true;
}

// "key = value # c" -> true and the value part (comment cut outside quotes)
bool KeyLine(const std::string& line, const std::string& key, std::string* value, std::string* comment) {
	std::string t = Strip(line);
	if (t.compare(0, key.size(), key) != 0)
		return false;
	std::string rest = Strip(t.substr(key.size()));
	if (rest.empty() || rest[0] != '=')
		return false;
	rest = rest.substr(1);
	char quote = 0;
	size_t cut = std::string::npos;
	for (size_t i = 0; i < rest.size(); ++i) {
		char c = rest[i];
		if (quote) {
			if (c == '\\' && quote == '"') { ++i; continue; }
			if (c == quote) quote = 0;
		} else if (c == '"' || c == '\'') {
			quote = c;
		} else if (c == '#') {
			cut = i;
			break;
		}
	}
	if (value)
		*value = Strip(cut == std::string::npos ? rest : rest.substr(0, cut));
	if (comment)
		*comment = cut == std::string::npos ? "" : " " + Strip(rest.substr(cut));
	return true;
}

}  // namespace

std::string SetTomlKey(const std::string& text, const std::string& section, const std::string& key, const std::string& value) {
	auto lines = Lines(text);
	bool crlf = text.find("\r\n") != std::string::npos;
	std::string eol = crlf ? "\r" : "";
	int start = -1, end = int(lines.size());
	for (int i = 0; i < int(lines.size()); ++i) {
		std::string name;
		if (!IsHeader(lines[size_t(i)], &name))
			continue;
		if (start >= 0) {
			end = i;
			break;
		}
		if (name == section)
			start = i;
	}
	auto join = [&](const std::vector<std::string>& ls) {
		std::string out;
		for (const auto& l : ls)
			out += l + "\n";
		if (!text.empty() && text.back() != '\n' && !out.empty())
			out.pop_back();  // keep a missing final newline missing
		return out;
	};
	if (start < 0) {
		std::string out = text;
		if (!out.empty() && out.back() != '\n')
			out += crlf ? "\r\n" : "\n";
		std::string nl = crlf ? "\r\n" : "\n";
		out += nl + "[" + section + "]" + nl + key + " = " + value + nl;
		return out;
	}
	for (int i = start + 1; i < end; ++i) {
		std::string comment;
		if (KeyLine(lines[size_t(i)], key, nullptr, &comment)) {
			std::string indent = lines[size_t(i)].substr(0, lines[size_t(i)].find_first_not_of(" \t"));
			lines[size_t(i)] = indent + key + " = " + value + comment + eol;
			return join(lines);
		}
	}
	for (int i = start + 1; i < end; ++i) {
		std::string t = Strip(lines[size_t(i)]);
		if (t.size() > 1 && t[0] == '#') {
			std::string bare = Strip(t.substr(t.find_first_not_of('#') == std::string::npos ? t.size() : t.find_first_not_of('#')));  // "##  key = x" too
			if (KeyLine(bare, key, nullptr, nullptr)) {
				lines[size_t(i)] = key + " = " + value + eol;
				return join(lines);
			}
		}
	}
	lines.insert(lines.begin() + start + 1, key + " = " + value + eol);
	return join(lines);
}

std::string GetTomlKey(const std::string& text, const std::string& section, const std::string& key) {
	auto lines = Lines(text);
	bool in = false;
	for (const auto& l : lines) {
		std::string name;
		if (IsHeader(l, &name)) {
			in = name == section;
			continue;
		}
		std::string v;
		if (in && KeyLine(l, key, &v, nullptr))
			return v;
	}
	return "";
}

namespace {
constexpr const char* SaveFormatSection = "d2rcore.save_format";

// The line of `key` in [table] (or the dotted key `<table>.<key>` before the first table) and the line of the [table] header
// (-1 when missing).
void FindTableKey(const std::vector<std::string>& lines, const std::string& table, const std::string& key, int& keyLine, int& headerLine,
                  std::string* value) {
	keyLine = headerLine = -1;
	const std::string dotted = table + "." + key;
	std::string section;
	bool top = true;
	for (int i = 0; i < int(lines.size()); ++i) {
		std::string name;
		if (IsHeader(lines[size_t(i)], &name)) {
			top = false;
			section = name;
			if (name == table && headerLine < 0)
				headerLine = i;
			continue;
		}
		if (keyLine < 0 && ((!top && section == table && KeyLine(lines[size_t(i)], key, value, nullptr)) ||
		                    (top && KeyLine(lines[size_t(i)], dotted, value, nullptr))))
			keyLine = i;
	}
}

void FindSaveFormat(const std::vector<std::string>& lines, int& keyLine, int& headerLine, std::string* value) {
	FindTableKey(lines, SaveFormatSection, "mode", keyLine, headerLine, value);
}

// A `key = ...` line (or the dotted `<table>.<key> = ...`) with the value replaced; indent, comment and a CR kept.
std::string ReplaceKeyValue(const std::string& line, const std::string& table, const std::string& key, const std::string& value) {
	const std::string dottedKey = table + "." + key;
	std::string comment;
	bool dotted = KeyLine(line, dottedKey, nullptr, &comment);
	if (!dotted)
		KeyLine(line, key, nullptr, &comment);
	bool cr = !line.empty() && line.back() == '\r';
	return line.substr(0, line.find_first_not_of(" \t")) + (dotted ? dottedKey : key) + " = " + value + comment + (cr ? "\r" : "");
}

constexpr const char* ItemsSection = "d2rcore.items";
constexpr const char* StatRangesKey = "item_stat_ranges";
}  // namespace

std::string SaveFormatMode(const std::string& text) {
	std::string t = text.rfind("\xEF\xBB\xBF", 0) == 0 ? text.substr(3) : text;
	int keyLine = 0, headerLine = 0;
	std::string value;
	FindSaveFormat(Lines(t), keyLine, headerLine, &value);
	return keyLine < 0 ? "" : TomlUnquote(value);
}

std::string SetExtendedSaveFormat(const std::string& text) {
	if (SaveFormatMode(text) == "extended")
		return text;
	bool bom = text.rfind("\xEF\xBB\xBF", 0) == 0;
	std::string t = bom ? text.substr(3) : text;
	auto lines = Lines(t);
	std::string eol = t.find("\r\n") != std::string::npos ? "\r" : "";
	bool noFinalNewline = !t.empty() && t.back() != '\n';
	int keyLine = 0, headerLine = 0;
	FindSaveFormat(lines, keyLine, headerLine, nullptr);
	if (keyLine >= 0) {
		lines[size_t(keyLine)] = ReplaceKeyValue(lines[size_t(keyLine)], SaveFormatSection, "mode", "\"extended\"");
	} else if (headerLine >= 0) {
		if (noFinalNewline && headerLine == int(lines.size()) - 1) {  // the header is the last line: it gets its newline
			lines[size_t(headerLine)] += eol;
			noFinalNewline = false;
		}
		lines.insert(lines.begin() + headerLine + 1, "mode = \"extended\"" + eol);
	} else {
		std::string out = SetTomlKey(t, SaveFormatSection, "mode", "\"extended\"");
		return bom ? "\xEF\xBB\xBF" + out : out;
	}
	std::string out = bom ? "\xEF\xBB\xBF" : "";
	for (const auto& l : lines)
		out += l + "\n";
	if (noFinalNewline)
		out.pop_back();  // keep a missing final newline missing
	return out;
}

std::string ItemStatRanges(const std::string& text) {
	std::string t = text.rfind("\xEF\xBB\xBF", 0) == 0 ? text.substr(3) : text;
	int keyLine = 0, headerLine = 0;
	std::string value;
	FindTableKey(Lines(t), ItemsSection, StatRangesKey, keyLine, headerLine, &value);
	return keyLine < 0 ? "" : TomlUnquote(value);
}

std::string MigrateItemStatRanges(const std::string& text) {
	const std::string marker = "# mxl2012 migration: ctrl-stat-ranges-on-v1";
	bool bom = text.rfind("\xEF\xBB\xBF", 0) == 0;
	std::string t = bom ? text.substr(3) : text;
	for (auto line : Lines(t)) {
		if (!line.empty() && line.back() == '\r')
			line.pop_back();
		if (line == marker)
			return text;  // already migrated: respect player edits
	}
	return (bom ? "\xEF\xBB\xBF" : "") + marker + (t.find("\r\n") != std::string::npos ? "\r\n" : "\n") +
	       ForceTomlKey(t, ItemsSection, StatRangesKey, "true");
}

std::string TableKeyValue(const std::string& text, const std::string& section, const std::string& key) {
	std::string t = text.rfind("\xEF\xBB\xBF", 0) == 0 ? text.substr(3) : text;
	int keyLine = 0, headerLine = 0;
	std::string value;
	FindTableKey(Lines(t), section, key, keyLine, headerLine, &value);
	return keyLine < 0 ? "" : value;
}

std::string EnsureTomlKey(const std::string& text, const std::string& section, const std::string& key, const std::string& value) {
	bool bom = text.rfind("\xEF\xBB\xBF", 0) == 0;
	std::string t = bom ? text.substr(3) : text;
	int keyLine = 0, headerLine = 0;
	FindTableKey(Lines(t), section, key, keyLine, headerLine, nullptr);
	if (keyLine >= 0)
		return text;  // set by hand: leave it
	std::string out;
	if (headerLine < 0) {  // a new table after one blank line, as install_mod.ensure_toml_key writes it
		std::string nl = t.find("\r\n") != std::string::npos ? "\r\n" : "\n";
		out = t;
		while (!out.empty() && (out.back() == '\n' || out.back() == '\r'))
			out.pop_back();
		out = (out.empty() ? "" : out + nl + nl) + "[" + section + "]" + nl + key + " = " + value + nl;
	} else {
		out = SetTomlKey(t, section, key, value);  // the commented template line, else right under the header
	}
	return bom ? "\xEF\xBB\xBF" + out : out;
}

std::string ForceTomlKey(const std::string& text, const std::string& section, const std::string& key, const std::string& value) {
	bool bom = text.rfind("\xEF\xBB\xBF", 0) == 0;
	std::string t = bom ? text.substr(3) : text;
	auto lines = Lines(t);
	int keyLine = 0, headerLine = 0;
	std::string old;
	FindTableKey(lines, section, key, keyLine, headerLine, &old);
	if (keyLine < 0)
		return EnsureTomlKey(text, section, key, value);  // a commented template line, else under the header, else a new table
	if (TomlUnquote(old) == TomlUnquote(value))
		return text;
	lines[size_t(keyLine)] = ReplaceKeyValue(lines[size_t(keyLine)], section, key, value);
	std::string out = bom ? "\xEF\xBB\xBF" : "";
	for (const auto& l : lines)
		out += l + "\n";
	if (!t.empty() && t.back() != '\n')
		out.pop_back();  // keep a missing final newline missing
	return out;
}

const ModConfigKey ModConfigKeys[4] = {
	{SaveFormatSection, "mode", "\"extended\"", false, "D2R-XL 2012 saves need it"},
	{ItemsSection, StatRangesKey, "true", true, "Ctrl stat ranges restored once; some automagic range lines may repeat"},
	{"d2rcore.player", "always_enable_rotw_legacy_graphics_keybind", "true", false,
	 "G switches to legacy graphics in a RotW game; without it D2RLoader's game-wide false applies"},
	{"d2rcore.stash", "add_shared_tabs", "2", false, "5 shared stash pages in every game, as a RotW game has", true},
};

std::string ApplyModConfigKey(const std::string& text, const ModConfigKey& k, std::string* was) {
	std::string old = TableKeyValue(text, k.section, k.key);
	if (was)
		*was = old;
	if (std::string(k.section) == ItemsSection && std::string(k.key) == StatRangesKey)
		return MigrateItemStatRanges(text);
	if (k.keepHandSet)
		return EnsureTomlKey(text, k.section, k.key, k.value);
	if (k.atLeast) {
		const std::string v = TomlUnquote(old);
		if (!old.empty() && v == old && !v.empty() && v.size() < 10 && v.find_first_not_of("0123456789") == std::string::npos &&
		    std::stoul(v) >= std::stoul(k.value))
			return text;  // tools/install_mod.py ensure_toml_min
	}
	if (std::string(k.section) == SaveFormatSection && std::string(k.key) == "mode")
		return SetExtendedSaveFormat(text);
	return ForceTomlKey(text, k.section, k.key, k.value);
}

bool PathIsOrUnder(const std::string& path, const std::string& dir) {
	std::string p = NormPath(path), d = NormPath(dir);
	if (d.empty() || (p + "/").find("/../") != std::string::npos || p.rfind("../", 0) == 0)
		return false;
	return p == d || p.rfind(d + "/", 0) == 0;
}

std::string DefaultDataDir(const std::string& localAppData) { return Join(localAppData, ProductFolder); }

bool SafeModFolderName(const std::string& name) {
	if (name.empty() || name.size() > 64 || name == "." || name == ".." || name.back() == '.' || name.back() == ' ' || name[0] == ' ')
		return false;
	for (char c : name)
		if (!(std::isalnum(uint8_t(c)) || c == '-' || c == '_' || c == '.' || c == ' '))
			return false;
	return SafeRelativePath(name);  // device names (CON, NUL, ...)
}

std::string ModTargetDir(const std::string& d2rDir, const std::string& modFolder) {
	if (d2rDir.empty() || modFolder != ProductFolder)
		return "";
	std::string d = d2rDir;
	while (d.size() > 3 && (d.back() == char(92) || d.back() == '/'))
		d.pop_back();
	return Join(Join(d, "mods"), modFolder);
}

MarkerVerdict CheckMarker(const std::string& text, const std::string& stateId) {
	if (text.empty())
		return MarkerVerdict::None;
	Json j;
	std::string err;
	if (!Json::Parse(text, j, err) || !j.IsObject() || j["made_by"].Str() != MarkerMadeBy || j["id"].Str().empty())
		return MarkerVerdict::Unreadable;
	return stateId.empty() || j["id"].Str() == stateId ? MarkerVerdict::Ours : MarkerVerdict::OtherId;
}

std::string MakeMarker(const std::string& id, const std::string& version) {
	Json m = Json::Object();
	m.Set("made_by", MarkerMadeBy).Set("id", id).Set("version", version);
	return m.Dump();
}

bool LoaderVersionMatches(const std::string& found, const std::string& required) {
	auto nums = [](const std::string& v) {
		std::vector<long> n;
		size_t i = 0;
		while (i < v.size() && std::isdigit(uint8_t(v[i]))) {
			long x = 0;
			while (i < v.size() && std::isdigit(uint8_t(v[i])))
				x = x * 10 + (v[i++] - '0');
			n.push_back(x);
			if (i < v.size() && v[i] == '.')
				++i;
			else
				break;
		}
		while (n.size() > 3 && n.back() == 0)  // "1.3.1.0" is 1.3.1
			n.pop_back();
		return n;
	};
	std::vector<long> f = nums(found), r = nums(required);
	return !f.empty() && f == r;
}

bool IsSaveCopyFile(const std::string& name) {
	if (name.find_first_of("/\\") != std::string::npos)
		return false;
	std::string n;
	for (char c : name)
		n += char(std::tolower(uint8_t(c)));
	for (const char* ext : {".d2i", ".d2s", ".d2rl"}) {
		size_t e = std::strlen(ext);
		if (n.size() > e && n.compare(n.size() - e, e, ext) == 0)
			return true;
	}
	return false;
}

std::string SaveCopyFolderName(const std::string& stamp, const std::string& from, const std::string& to) {
	std::string name = stamp + " " + (from.empty() ? "none" : from) + " to " + to, out;
	for (char c : name)
		out += std::isalnum(uint8_t(c)) || c == '.' || c == '-' || c == '_' || c == ' ' ? c : '_';
	return out;
}

static bool HasStamp(const std::string& name) {  // "YYYYMMDD-HHMMSS" then the end or a space
	if (name.size() < 15 || (name.size() > 15 && name[15] != ' ') || name[8] != '-')
		return false;
	for (size_t i = 0; i < 15; ++i)
		if (i != 8 && !std::isdigit(uint8_t(name[i])))
			return false;
	return true;
}

std::vector<std::string> SaveCopiesToRemove(const std::vector<std::string>& folders, size_t keep) {
	std::vector<std::string> ours;
	for (const auto& f : folders)
		if (HasStamp(f))
			ours.push_back(f);
	std::sort(ours.begin(), ours.end());
	if (ours.size() <= keep)
		return {};
	ours.resize(ours.size() - keep);
	return ours;
}

bool OfficialMedianXLPath(const std::string& path, const std::string& localAppData, const std::string& roamingAppData) {
	if (PathIsOrUnder(path, Join(localAppData, "mxl-launcher")) || PathIsOrUnder(path, Join(localAppData, "MedianXL")) ||
	    PathIsOrUnder(path, Join(roamingAppData, "MedianXL")))
		return true;
	std::string p = NormPath(path) + "/";
	return p.find("/diablo ii/") != std::string::npos;  // the classic game folder, wherever it is
}

bool IsGameProcessName(const std::string& exe) {
	size_t slash = exe.find_last_of(R"(\/)");
	std::string n = exe.substr(slash == std::string::npos ? 0 : slash + 1);
	for (char& ch : n)
		ch = char(std::tolower(static_cast<unsigned char>(ch)));
	auto ends = [&](const char* tail) { size_t k = std::strlen(tail); return n.size() >= k && n.compare(n.size() - k, k, tail) == 0; };
	return n == "d2r.exe" || (n.rfind("d2rloader", 0) == 0 && ends(".exe"));
}

std::string TomlUnquote(const std::string& value) {
	std::string v = Strip(value);
	if (v.size() >= 2 && (v[0] == '"' || v[0] == '\'') && v.back() == v[0])
		return v.substr(1, v.size() - 2);
	return v;
}

namespace {
std::string LowerStr(std::string s) {
	for (char& c : s)
		c = char(std::tolower(uint8_t(c)));
	return s;
}
}  // namespace

DefaultModCheck CheckDefaultMod(const std::string& text, bool exists, const std::string& ourMod) {
	DefaultModCheck c;
	c.configMissing = !exists;
	std::string t = text.rfind("\xEF\xBB\xBF", 0) == 0 ? text.substr(3) : text;  // a UTF-8 BOM (Notepad)
	if (exists)
		c.mod = TomlUnquote(GetTomlKey(t, "d2rloader", "default_mod"));
	c.ok = !c.mod.empty() && LowerStr(c.mod) == LowerStr(ourMod);
	return c;
}

std::string DefaultModWarning(const DefaultModCheck& c, const std::string& ourMod) {
	if (c.ok)
		return "";
	if (c.configMissing)
		return "D2RLoader has no settings file yet, so starting it by hand does not start " + ourMod + " (Play does)";
	if (c.mod.empty())
		return "D2RLoader has no default mod, so starting it by hand does not start " + ourMod + " (Play does)";
	return "Started by hand, D2RLoader starts the mod " + c.mod + ", not " + ourMod + " (Play starts " + ourMod + ")";
}

std::string SetDefaultMod(const std::string& text, const std::string& ourMod) {
	bool bom = text.rfind("\xEF\xBB\xBF", 0) == 0;
	std::string out = SetTomlKey(bom ? text.substr(3) : text, "d2rloader", "default_mod", "\"" + ourMod + "\"");
	return bom ? "\xEF\xBB\xBF" + out : out;
}

bool IsOurPluginFile(const std::string& fileName, const std::string& productName, const std::string& fileDescription) {
	std::string n = LowerStr(fileName), p = LowerStr(Strip(productName)), d = LowerStr(fileDescription);
	bool dll = n.size() > 4 && n.compare(n.size() - 4, 4, ".dll") == 0;
	if (!dll)
		return false;
	return n.rfind("mxl2012-core", 0) == 0 || p == "mxl2012" || p == "d2r-xl 2012" ||
	       d.find("mxl2012-core") != std::string::npos || d.find("d2r-xl 2012 core") != std::string::npos;
}

PluginPlace PluginPlaceOf(const std::string& rel, const std::string& ourMod, std::string* mod) {
	std::string p = NormPath(rel);
	if ((p + "/").find("/../") != std::string::npos || p.rfind("../", 0) == 0)
		return PluginPlace::None;
	std::vector<std::string> seg;
	size_t start = 0;
	while (start <= p.size()) {
		size_t s = p.find('/', start);
		seg.push_back(p.substr(start, s == std::string::npos ? std::string::npos : s - start));
		if (s == std::string::npos)
			break;
		start = s + 1;
	}
	if (seg.size() >= 3 && seg[0] == "d2rloader" && seg[1] == "plugins")
		return PluginPlace::GameWide;
	if (seg.size() >= 5 && seg[0] == "mods" && seg[2] == "d2rloader" && seg[3] == "plugins" && !seg[1].empty()) {
		if (mod) {  // the folder name as written (NormPath lowered it)
			std::string orig = rel;
			for (char& c : orig)
				if (c == char(92))
					c = '/';
			size_t a = orig.find('/') + 1;
			*mod = orig.substr(a, orig.find('/', a) - a);
		}
		return seg[1] == LowerStr(ourMod) ? PluginPlace::OurMod : PluginPlace::OtherMod;
	}
	return PluginPlace::None;
}

std::string StrayPluginWarning(const std::string& path, PluginPlace place, const std::string& mod, bool brief) {
	if (place == PluginPlace::GameWide)
		return brief ? R"(Old D2R-XL 2012 plugin in d2rloader\plugins: it loads with every mod)"
		             : "An old copy of the D2R-XL 2012 plugin is in " + path + ": it loads with every mod. Move it away.";
	if (place == PluginPlace::OtherMod)
		return brief ? "Old D2R-XL 2012 plugin in mods\\" + mod + ": it loads with that mod"
		             : "An old copy of the D2R-XL 2012 plugin is in " + path + ": it loads whenever D2RLoader starts the mod " + mod +
		                   ". Move it away.";
	return "";
}

uint32_t NameHash(const std::string& s) {
	uint32_t h = 2166136261u;
	for (unsigned char c : LowerStr(s))
		h = (h ^ c) * 16777619u;
	return h;
}

bool IsProtectedModFolder(const std::string& mod, const uint32_t* hashes, size_t n) {
	static constexpr uint32_t Builtin[] = {0xb7fa757eu};
	if (hashes == nullptr) {
		hashes = Builtin;
		n = sizeof(Builtin) / sizeof(Builtin[0]);
	}
	const uint32_t h = NameHash(mod);
	for (size_t i = 0; i < n; ++i)
		if (hashes[i] == h)
			return true;
	return false;
}

bool CanMoveStrayPlugin(PluginPlace place, const std::string& mod) {
	return place == PluginPlace::GameWide || (place == PluginPlace::OtherMod && !IsProtectedModFolder(mod));
}

std::string RemovedPluginPath(const std::string& dataDir, const std::string& date, const std::string& rel) {
	std::string r = rel;
	for (char& c : r)
		if (c == '/')
			c = char(92);
	while (!r.empty() && r[0] == char(92))
		r.erase(0, 1);
	return Join(Join(Join(dataDir, "removed"), date), r);
}

std::string PlayBlocked(const PlayInputs& in) {
	if (!in.d2rFound)
		return "choose the D2R folder first";
	if (in.buildMismatch)
		return "D2R is not the version D2R-XL 2012 needs";
	if (!in.loaderFound)
		return "install D2RLoader first";
	if (!in.loaderOk)
		return "D2RLoader is not the version D2R-XL 2012 needs";
	if (in.foreignMod)
		return "mods\\mxl2012 was not installed by this downloader; press Install";
	if (!in.installed)
		return "press Install first";
	if (in.pending)
		return "the last install did not finish; press Update or Repair";
	if (in.updateAvailable)
		return "press Update first";
	if (in.gameRunning)
		return "the game is already running";
	return "";
}

std::string PlayArguments(const std::string& modFolder) {
	return "-mod " + modFolder;
}

std::string PlayCommandLine(const std::string& loaderExe, const std::string& modFolder) {
	if (loaderExe.empty() || loaderExe.find('"') != std::string::npos)
		return "";
	return "\"" + loaderExe + "\" " + PlayArguments(modFolder);
}

std::string WindowCloseLine(WindowClose why) {
	switch (why) {
	case WindowClose::Closed: return "window: closed (title bar, Alt+F4 or WM_CLOSE)";
	case WindowClose::AfterPlay: return "window: closed after Play (close the downloader when the game starts is on)";
	case WindowClose::SelfUpdate: return "window: closed for the updated downloader";
	case WindowClose::Snapshot: return "window: closed after the snapshot";
	case WindowClose::SessionEnd: return "window: closed, Windows signs out or shuts down";
	}
	return "window: closed";
}

bool CloseAfterAction(bool play, bool ok, bool closeAfterPlay) {
	return play && ok && closeAfterPlay;
}

bool GameStateChanged(bool busy, bool d2rFound, bool runningNow, bool runningShown) {
	return !busy && d2rFound && runningNow != runningShown;
}

std::string CrashLine(uint32_t code, uint64_t address) {
	char text[96];
	std::snprintf(text, sizeof(text), "crash: exception 0x%08X at 0x%llX; the downloader ends", unsigned(code),
	              static_cast<unsigned long long>(address));
	return text;
}

}  // namespace mxl

// Unit tests of the downloader's portable core (no Windows headers): manifest parsing and the install plan, path
// safety, the mod folder and its marker, the D2RLoader version check, D2R detection parsers and the build check, the
// 7z decoder, TOML edits, the SVG path reader for the window's icons.
// Built and run by CI on Linux (g++) and locally with MSVC: cmake -S launcher/tests -B build/launcher-tests.
#include "../src/core/detect.h"
#include "../src/core/json.h"
#include "../src/core/manifest.h"
#include "../src/core/paths.h"
#include "../src/core/sevenzip.h"
#include "../src/core/sha256.h"
#include "../src/core/svgpath.h"

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <map>
#include <string>
#include <vector>

namespace {
int failures = 0, checks = 0;
void Check(bool ok, const char* what) {
	++checks;
	if (!ok) {
		++failures;
		std::printf("FAIL: %s\n", what);
	}
}

const std::string H1(64, 'a'), H2(64, 'b'), H3(64, 'c'), H4(64, 'd');

std::string ManifestText(const std::string& files, const std::string& extra = "") {
	return R"({"schemaVersion": 2, "name": "mxl2012", "version": "0.70.0", "pluginVersion": "0.70.0", "complete": true,
	  "d2r": {"build": "93847", "version": "3.3.0", "imageTimestamp": "0x6ab3782c"},
	  "d2rloader": {"version": "1.3.1-beta", "url": "https://d2rloader.net/download/D2RLoader-1.3.1-beta.zip", "size": 47652455,
	                "sha256": "9286C6B5BFF7F1043658411DBEA305FAA9698B6A455E6441668FC6D02C22AAD7", "signerThumbprint": "8001082E968FADAA58BF2F73EFA1810A11D0C28F"},
	  "launch": {"default_mod": "mxl2012", "launch_arguments": "-txt"}, "modFolder": "mxl2012", "saveFolder": "mxl2012/",
	  "archive": {"format": "7z", "name": "D2R-XL-2012-0.70.0.7z", "size": 100, "sha256": ")" + H1 + R"("}, "someFutureField": {"x": [1]},
	  "objectsBase": "objects/", "emptyDirs": ["d2rloader/patches"],
	  "files": [)" + files + "]" + extra + "}";
}
std::string Without(std::string text, const std::string& part) {
	size_t at = text.find(part);
	return at == std::string::npos ? text : text.erase(at, part.size());
}
std::string F(const std::string& path, const std::string& sha, int size = 10) {
	return R"({"path": ")" + path + R"(", "size": )" + std::to_string(size) + R"(, "sha256": ")" + sha + R"("})";
}

void TestSha256() {
	Check(mxl::Sha256Hex("", 0) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "sha256 of nothing");
	Check(mxl::Sha256Hex("abc", 3) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", "sha256 abc");
	std::string m = "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
	Check(mxl::Sha256Hex(m.data(), m.size()) == "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1", "sha256 two blocks");
	std::string a(1000000, 'a');
	mxl::Sha256 s;
	for (size_t i = 0; i < a.size(); i += 333)  // odd chunk sizes across block borders
		s.Update(a.data() + i, std::min<size_t>(333, a.size() - i));
	Check(s.HexDigest() == "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0", "sha256 million a, chunked");
}

void TestJson() {
	mxl::Json j;
	std::string err;
	Check(mxl::Json::Parse(R"({"a": [1, 2.5, "x\u00e9\n"], "b": {"c": true, "d": null}, "e": -3})", j, err), "json parses");
	Check(j["a"].size() == 3 && j["a"][1].Num() == 2.5 && j["a"][2].Str() == "x\xc3\xa9\n", "json array and \\u escape");
	Check(j["b"]["c"].Bool() && j["b"]["d"].IsNull() && j["e"].Int() == -3, "json nested");
	Check(j["missing"]["deeper"].Str("fb") == "fb", "missing keys give the fallback");
	Check(!mxl::Json::Parse("{\"a\": 1,}", j, err), "trailing comma refused");
	Check(!mxl::Json::Parse("{\"a\": 1} x", j, err), "trailing data refused");
	mxl::Json o = mxl::Json::Object();
	o.Set("path", "a\"b\\c").Set("n", uint64_t(5000000000ull));
	mxl::Json back;
	Check(mxl::Json::Parse(o.Dump(), back, err) && back["path"].Str() == "a\"b\\c" && back["n"].Int() == 5000000000ll,
	      "json round trip with escapes and a large size");
}

void TestSafePath() {
	Check(mxl::SafeRelativePath("mxl2012.mpq/data/global/excel/skills.txt"), "normal path");
	Check(!mxl::SafeRelativePath("../x"), "parent refused");
	Check(!mxl::SafeRelativePath("a/../../x"), "inner parent refused");
	Check(!mxl::SafeRelativePath("/abs"), "absolute refused");
	Check(!mxl::SafeRelativePath("C:/x"), "drive refused");
	Check(!mxl::SafeRelativePath("a\\b"), "backslash refused");
	Check(!mxl::SafeRelativePath("a//b"), "empty segment refused");
	Check(!mxl::SafeRelativePath("a/./b"), "dot segment refused");
	Check(!mxl::SafeRelativePath("a/nul.txt"), "device name refused");
	Check(!mxl::SafeRelativePath("a/b "), "trailing space refused");
	Check(!mxl::SafeRelativePath("a/b?"), "wildcard refused");
	Check(!mxl::SafeRelativePath(""), "empty refused");
}

void TestManifest() {
	mxl::Manifest m;
	std::string err;
	Check(mxl::ParseManifest(ManifestText(F("a.txt", H1) + "," + F("d2rloader/config/d2rloader.toml", H2),
	                                      R"(, "preserve": ["d2rloader/config/d2rloader.toml"], "fileCount": 2, "totalSize": 20)"), m, err),
	      "manifest parses (release.md schemaVersion 2, unknown fields ignored)");
	Check(m.files.size() == 2 && m.d2rBuild == 93847 && m.modFolder == "mxl2012" && m.preserve.count("d2rloader/config/d2rloader.toml") &&
	          m.complete && m.imageTimestamp == 0x6ab3782cu && m.launchArguments == "-txt" && m.saveFolder == "mxl2012/" &&
	          m.archive.name == "D2R-XL-2012-0.70.0.7z" && m.archive.size == 100 && m.d2rloader.size == 47652455 &&
	          m.emptyDirs.size() == 1 && m.emptyDirs[0] == "d2rloader/patches" && m.objectsBase == "objects/" &&
	          m.d2rloader.sha256 == "9286c6b5bff7f1043658411dbea305faa9698b6a455e6441668fc6d02c22aad7",
	      "manifest fields");
	Check(!mxl::ParseManifest(ManifestText(F("a.txt", H1), R"(, "fileCount": 3)"), m, err), "fileCount mismatch refused");
	Check(!mxl::ParseManifest(ManifestText(F("a.txt", H1), R"(, "totalSize": 11)"), m, err), "totalSize mismatch refused");
	Check(!mxl::ParseManifest(ManifestText(F("../evil.dll", H1)), m, err), "manifest with an unsafe path refused");
	Check(!mxl::ParseManifest(ManifestText(F("a.txt", "xyz")), m, err), "manifest with a bad sha refused");
	Check(!mxl::ParseManifest(ManifestText(F("a.txt", H1) + "," + F("A.TXT", H2)), m, err), "case-insensitive duplicate refused");
	Check(!mxl::ParseManifest(ManifestText(""), m, err), "empty file list refused");
	// schema 1 (the zip) is too old, 3 too new; both refused, with what the caller needs for its message
	std::string v1 = ManifestText(F("a.txt", H1));
	v1.replace(v1.find(R"("schemaVersion": 2)"), 18, R"("schemaVersion": 1)");
	Check(!mxl::ParseManifest(v1, m, err) && m.schemaVersion == 1 && m.version == "0.70.0" && m.files.empty(),
	      "schemaVersion 1 (zip releases) refused");
	std::string v3 = ManifestText(F("a.txt", H1), R"(, "launcher": {"version": "0.9.0", "path": "launcher/0.9.0/D2R-XL-2012-Downloader.exe", "size": 5, "sha256": ")" + H3 + R"("})");
	v3.replace(v3.find(R"("schemaVersion": 2)"), 18, R"("schemaVersion": 3)");
	Check(!mxl::ParseManifest(v3, m, err) && m.schemaVersion == 3 && m.launcher.version == "0.9.0" && m.launcher.sha256 == H3,
	      "schemaVersion 3 refused, its launcher still offered");
	Check(!mxl::ParseManifest(R"({"schemaVersion": 3})", m, err) && m.schemaVersion == 3 && m.launcher.path.empty(), "bare future schema refused");
	std::string noObjects = ManifestText(F("a.txt", H1));
	noObjects.replace(noObjects.find(R"("objectsBase": "objects/", )"), 27, "");
	Check(!mxl::ParseManifest(noObjects, m, err), "manifest without objectsBase refused (small updates and Repair use the objects)");
	std::string dirs = ManifestText(F("a.txt", H1));
	dirs.replace(dirs.find("d2rloader/patches"), 17, "../x");
	Check(!mxl::ParseManifest(dirs, m, err) && err.find("emptyDirs") != std::string::npos, "unsafe emptyDirs refused");
	Check(!mxl::ParseManifest(R"({"schema": 1})", m, err), "old draft format refused");
	mxl::Manifest back;
	mxl::ParseManifest(ManifestText(F("a.txt", H1), R"(, "preserve": ["a.txt"])"), m, err);
	Check(mxl::ParseManifest(mxl::ManifestToJson(m).Dump(), back, err) && back.files.size() == 1 && back.files[0].sha256 == H1 &&
	          back.imageTimestamp == m.imageTimestamp && back.preserve.count("a.txt") && back.d2rBuild == 93847 && back.complete &&
	          back.emptyDirs == m.emptyDirs && back.archive.name == m.archive.name && back.archive.sha256 == H1,
	      "manifest round trip (state file)");
	mxl::Manifest noData;
	noData.complete = false;
	Check(!mxl::InstallableFromChannel(noData, "stable") && !mxl::InstallableFromChannel(noData, "") &&
	          mxl::InstallableFromChannel(noData, "test") && mxl::InstallableFromChannel(m, "stable"),
	      "a package without game data installs from the test channel only");
}

void TestHosting() {
	mxl::Manifest m;
	std::string err;
	std::string pub = R"(, "launcher": {"version": "0.2.0", "path": "launcher/0.2.0/D2R-XL-2012-Downloader.exe", "size": 5, "sha256": ")" + H3 + R"("})";
	std::string text = ManifestText(F("a.txt", H1) + "," + F("b/copy.txt", H1) + "," + F("c.txt", H2), pub);
	text.replace(text.find(R"("name": "D2R-XL-2012-0)"), 0, R"("path": "releases/0.70.0/D2R-XL-2012-0.70.0.7z", )");
	Check(mxl::ParseManifest(text, m, err), "published manifest parses");
	Check(m.objectsBase == "objects/" && m.archive.path == "releases/0.70.0/D2R-XL-2012-0.70.0.7z" && m.launcher.version == "0.2.0" &&
	          m.launcher.sha256 == H3 && m.launcher.size == 5,
	      "objectsBase, archive.path, launcher");
	mxl::Manifest back;
	Check(mxl::ParseManifest(mxl::ManifestToJson(m).Dump(), back, err) && back.objectsBase == "objects/" && back.archive.path == m.archive.path &&
	          back.launcher.path == m.launcher.path,
	      "published fields round trip");
	Check(!mxl::ParseManifest(Without(ManifestText(F("a.txt", H1), R"(, "objectsBase": "../x/")"), R"("objectsBase": "objects/", )"), m, err), "unsafe objectsBase refused");
	Check(!mxl::ParseManifest(Without(ManifestText(F("a.txt", H1), R"(, "objectsBase": "objects")"), R"("objectsBase": "objects/", )"), m, err), "objectsBase without '/' refused");
	Check(!mxl::ParseManifest(Without(ManifestText(F("a.txt", H1), R"(, "objectsBase": "https://evil/")"), R"("objectsBase": "objects/", )"), m, err), "absolute objectsBase refused");
	Check(mxl::ObjectPath("objects/", H2) == "objects/bb/" + H2, "object path");
	auto groups = mxl::GroupObjects({{"a.txt", 10, H1}, {"b/copy.txt", 10, H1}, {"c.txt", 7, H2}});
	Check(groups.size() == 2 && groups[0].sha256 == H1 && groups[0].paths.size() == 2 && groups[0].paths[1] == "b/copy.txt" &&
	          groups[1].size == 7 && groups[1].paths.size() == 1,
	      "same content is one download");

	mxl::Channel c;
	Check(mxl::ParseChannel(R"({"schemaVersion": 1, "version": "0.70.0", "manifest": "releases/0.70.0/release-manifest.json",
	    "manifestSha256": ")" + std::string(64, 'E') + R"(", "publishedAt": "2026-10-26T12:00:00Z", "later": 1})", c, err) &&
	          c.version == "0.70.0" && c.manifest == "releases/0.70.0/release-manifest.json" && c.manifestSha256 == std::string(64, 'e'),
	      "channel parses");
	Check(!mxl::ParseChannel(R"({"schemaVersion": 2, "version": "1", "manifest": "m.json", "manifestSha256": ")" + H1 + R"("})", c, err),
	      "unknown channel schemaVersion refused");
	Check(!mxl::ParseChannel(R"({"schemaVersion": 1, "version": "1", "manifest": "../m.json", "manifestSha256": ")" + H1 + R"("})", c, err),
	      "unsafe channel manifest path refused");
	Check(!mxl::ParseChannel(R"({"schemaVersion": 1, "version": "1", "manifest": "m.json"})", c, err), "channel without sha refused");
	Check(!mxl::ParseChannel("<html>sign in</html>", c, err), "a login page is not a channel");
	const std::string chUrl = "https://dl.werdegames.com/mxl2012/channels/stable.json";
	Check(mxl::ChannelReadError("stable", chUrl, 404, "") == "No release has been published on the stable channel yet.",
	      "channel 404: nothing published yet");
	Check(mxl::ChannelReadError("test", "file:///D:/site/channels/test.json", 404, "cannot open") ==
	          "No release has been published on the test channel yet.",
	      "missing channel file on a local site: nothing published yet");
	Check(mxl::ChannelReadError("stable", chUrl, 503, "") == "The download site answered 503 for " + chUrl, "other status: the site answered it");
	Check(mxl::ChannelReadError("stable", chUrl, 403, "") == "The download site answered 403 for " + chUrl, "403 is not 'not published'");
	std::string net = mxl::ChannelReadError("stable", chUrl, 0, "download x: The server name or address could not be resolved (12007)");
	Check(net.rfind("Cannot reach the download site (" + chUrl + "): ", 0) == 0 && net.find("(12007)") != std::string::npos,
	      "no answer: cannot reach, with the WinHTTP error");
	Check(mxl::ChannelReadError("stable", chUrl, 0, "") == "Cannot reach the download site (" + chUrl + ")", "no answer without error text");

	Check(mxl::SiteRoot("https://dl.werdegames.com/mxl2012") == "https://dl.werdegames.com/mxl2012/", "site root gets a '/'");
	Check(mxl::SiteRoot("http://127.0.0.1:8765/") == "http://127.0.0.1:8765/", "site root kept");
	const std::string bs(1, char(92));
	Check(mxl::SiteRoot("D:" + bs + "test site" + bs) == "file:///D:/test%20site/", "local folder becomes a file URL");
	Check(mxl::SiteRoot(bs + bs + "srv" + bs + "mxl2012") == "file://srv/mxl2012/", "UNC share becomes a file URL");
	Check(mxl::ResolveUrl(mxl::SiteRoot("http://h/mxl2012"), "objects/aa/x") == "http://h/mxl2012/objects/aa/x", "object URL under the root");
}

void TestPlan() {
	std::string err;
	mxl::Manifest next;
	mxl::ParseManifest(ManifestText(F("same.txt", H1) + "," + F("changed.txt", H2, 20) + "," + F("new.txt", H3, 30) + "," +
	                                F("d2rloader/config/d2rloader.toml", H2) + "," + F("missing.txt", H1, 5),
	                                R"(, "preserve": ["d2rloader/config/d2rloader.toml"])"),
	                   next, err);
	std::map<std::string, std::string> disk = {{"same.txt", H1}, {"changed.txt", H1}, {"gone.txt", H1},
	                                           {"d2rloader/config/d2rloader.toml", H4}, {"d2rloader/logs/x.log", H1},
	                                           {"d2rloader/crashes/c.dmp", H1}, {"stray/own.txt", H1}};
	auto cur = [&](const std::string& p) { auto it = disk.find(p); return it == disk.end() ? std::string() : it->second; };
	auto local = [&] { std::vector<std::string> v; for (const auto& [k, _] : disk) v.push_back(k); return v; };
	mxl::InstallPlan plan = mxl::PlanInstall(next, local(), cur);
	auto has = [](const std::vector<mxl::ManifestFile>& v, const char* p) {
		for (const auto& f : v) if (f.path == p) return true;
		return false;
	};
	auto hasS = [](const std::vector<std::string>& v, const char* p) {
		for (const auto& f : v) if (f == p) return true;
		return false;
	};
	Check(!has(plan.fetch, "same.txt"), "unchanged file is not fetched");
	Check(has(plan.fetch, "changed.txt") && has(plan.fetch, "new.txt") && has(plan.fetch, "missing.txt"), "changed, new, missing fetched");
	Check(hasS(plan.preserved, "d2rloader/config/d2rloader.toml") && !has(plan.fetch, "d2rloader/config/d2rloader.toml"),
	      "existing preserve file never overwritten");
	Check(hasS(plan.remove, "gone.txt") && hasS(plan.remove, "stray/own.txt") && plan.remove.size() == 2,
	      "unlisted files removed, D2RLoader logs / crashes kept");
	Check(plan.fetchBytes == 20 + 30 + 5, "fetch byte count");
	disk.clear();
	plan = mxl::PlanInstall(next, local(), cur);
	Check(plan.fetch.size() == next.files.size() && plan.remove.empty(), "fresh install fetches all, preserve file included");
	for (const auto& f : next.files) disk[f.path] = f.sha256;
	plan = mxl::PlanInstall(next, local(), cur);
	Check(plan.fetch.empty() && plan.remove.empty() && plan.preserved.empty(), "verified install: nothing to do");
}

void TestVersions() {
	Check(mxl::CompareVersions("1.2.10", "1.2.9") > 0, "1.2.10 > 1.2.9");
	Check(mxl::CompareVersions("v0.70.0", "0.70.0") == 0, "leading v");
	Check(mxl::CompareVersions("1.3.1", "1.3.1-beta") > 0, "release > beta");
	Check(mxl::CompareVersions("1.3", "1.3.0") == 0, "missing parts are 0");
	Check(mxl::ResolveUrl("https://github.com/o/r/releases/latest/download/mxl2012-manifest.json", "D2R-XL-2012-0.70.0.zip") ==
	          "https://github.com/o/r/releases/latest/download/D2R-XL-2012-0.70.0.zip", "relative url");
	Check(mxl::ResolveUrl("file:///C:/feed/manifest.json", "x.zip") == "file:///C:/feed/x.zip", "relative file url");
	Check(mxl::ResolveUrl("http://127.0.0.1:8000/a/m.json", "/b/x.zip") == "http://127.0.0.1:8000/b/x.zip", "host-relative url");
	Check(mxl::ResolveUrl("https://a/m.json", "https://b/x.zip") == "https://b/x.zip", "absolute url");
}

void TestDetect() {
	std::string info =
		"Branch!STRING:0|Active!DEC:1|Build Key!HEX:16|Version!STRING:0|Product!STRING:0\r\n"
		"eu|0|aaaa|3.3.90000|osi\r\n"
		"us|1|623f|3.3.93847|osi\r\n";
	Check(mxl::BuildInfoVersion(info) == "3.3.93847", ".build.info active row");
	Check(mxl::BuildInfoVersion("Version!STRING:0\n") == "", ".build.info without rows");
	Check(mxl::BuildInfoVersion("garbage") == "", "no Version column");
	std::string real =
		"Branch!STRING:0|Active!DEC:1|Build Key!HEX:16|CDN Key!HEX:16|Install Key!HEX:16|IM Size!DEC:4|CDN Path!STRING:0|CDN Hosts!STRING:0|"
		"CDN Servers!STRING:0|Tags!STRING:0|Armadillo!STRING:0|Last Activated!STRING:0|Version!STRING:0|KeyRing!HEX:16|Product!STRING:0\n"
		"us|1|623f7a1f73eabb08ccb2b2046e3f9164|a10f39cd385730caa4ab1909c888a845|||tpr/osi|level3.blizzard.com us.cdn.blizzard.com|"
		"http://level3.blizzard.com/?maxhosts=5|Windows US? acct-USA? geoip-JP? enUS speech?:Windows US? acct-USA? geoip-JP? enUS text?|||3.3.93847||\n";
	Check(mxl::BuildInfoVersion(real) == "3.3.93847", "real .build.info of build 93847");
	Check(mxl::BuildNumber("3.3.93847") == 93847 && mxl::BuildNumber("1.0.0.93847") == 93847 && mxl::BuildNumber("") == 0, "build numbers");

	// The requirement is the game version (major.minor), never the build number (D2RLoader's author, 2026-10-27).
	Check(mxl::GameVersion("3.3.93847") == "3.3" && mxl::GameVersion("3.3.0") == "3.3" && mxl::GameVersion("1.0.0.93847") == "1.0" &&
	          mxl::GameVersion("").empty() && mxl::GameVersion("93847").empty(), "game version is major.minor");
	auto ok = mxl::CheckBuild("3.3.93847", "3.3.93847");
	Check(ok.verdict == mxl::BuildVerdict::Ok && ok.version == "3.3" && ok.build == 93847, "3.3.93847 is ok");
	auto steam = mxl::CheckBuild("", "3.3.94995");  // Steam: no .build.info, another 3.3 build (bugs.md #41)
	Check(steam.verdict == mxl::BuildVerdict::Ok && steam.build == 94995, "any 3.3 build is ok (Steam 94995)");
	Check(mxl::CheckBuild("3.3.99999", "").verdict == mxl::BuildVerdict::Ok, "a later 3.3 hotfix build is ok");
	auto newer = mxl::CheckBuild("3.4.95000", "3.3.93847");
	Check(newer.verdict == mxl::BuildVerdict::Newer && newer.message.find("Waiting for a D2R-XL 2012 update") != std::string::npos,
	      "3.4: waiting message (.build.info decides)");
	Check(mxl::CheckBuild("3.2.91000", "").verdict == mxl::BuildVerdict::Older, "older version");
	Check(mxl::CheckBuild("3.10.1", "").verdict == mxl::BuildVerdict::Newer, "3.10 is newer than 3.3");
	Check(mxl::CheckBuild("", "").verdict == mxl::BuildVerdict::Unknown, "unknown version");
	Check(mxl::CheckBuild("", "3.3.93847").verdict == mxl::BuildVerdict::Ok, "exe version alone");

	std::string vdf = R"("libraryfolders"
{
	"0"
	{
		"path"		"C:\\Program Files (x86)\\Steam"
		"label"		""
		"apps" { "228980" "340606523" }
	}
	"1"
	{
		"path"		"E:\\SteamLibrary"   // a second library
	}
})";
	auto libs = mxl::SteamLibraryPaths(vdf);
	Check(libs.size() == 2 && libs[0] == "C:\\Program Files (x86)\\Steam" && libs[1] == "E:\\SteamLibrary", "steam library paths");
	std::string acf = R"("AppState"
{
	"appid"		"2536520"
	"name"		"Diablo II: Resurrected"
	"installdir"		"Diablo II Resurrected"
	"UserConfig" { "name" "other" }
})";
	Check(mxl::AcfValue(acf, "installdir") == "Diablo II Resurrected" && mxl::AcfValue(acf, "name") == "Diablo II: Resurrected",
	      "acf top-level values (not the nested name)");
	Check(mxl::AcfIsD2R(acf), "acf names D2R");
	Check(!mxl::AcfIsD2R(R"("AppState" { "name" "Diablo IV" "installdir" "Diablo IV" })"), "Diablo IV is not D2R");
}

// docs/launcher.md "Where it writes": only <D2R>\mods\<modFolder>, proven ours by the marker.
void TestPaths() {
	const std::string bs(1, char(92));
	const std::string d2r = "C:" + bs + "Program Files (x86)" + bs + "Diablo II Resurrected";
	Check(mxl::ModTargetDir(d2r, "mxl2012") == d2r + bs + "mods" + bs + "mxl2012", "mod folder <D2R>\\mods\\mxl2012");
	Check(mxl::ModTargetDir(d2r + bs, "mxl2012") == d2r + bs + "mods" + bs + "mxl2012", "trailing separator");
	for (const char* bad : {"", ".", "..", "../x", "a/b", "a\\b", "C:", "CON", "x ", "x.", "mxl2012/.."})
		Check(!mxl::SafeModFolderName(bad) && mxl::ModTargetDir(d2r, bad).empty(), bad);
	Check(mxl::SafeModFolderName("mxl2012") && mxl::SafeModFolderName("mxl2012-lt"), "plain names allowed");
	Check(mxl::ModTargetDir(d2r, "PriorMod").empty() && mxl::ModTargetDir(d2r, "OtherMod").empty(),
	      "never target another mod, even a safe folder name");
	const std::string mod = mxl::ModTargetDir(d2r, "mxl2012");
	Check(mxl::PathIsOrUnder(mod, mod) && mxl::PathIsOrUnder(mod + bs + "mxl2012.mpq" + bs + "x.txt", mod) &&
	          mxl::PathIsOrUnder(mod + "/a/b", mod),
	      "files inside the mod folder");
	Check(!mxl::PathIsOrUnder(mod + "-old", mod) && !mxl::PathIsOrUnder(d2r + bs + "D2R.exe", mod) &&
	          !mxl::PathIsOrUnder(d2r + bs + "mods" + bs + "MedianXL", mod) && !mxl::PathIsOrUnder(d2r, mod),
	      "the rest of the D2R folder is outside");
	Check(!mxl::PathIsOrUnder(mod + bs + ".." + bs + "MedianXL", mod) && !mxl::PathIsOrUnder(mod + "/../../D2R.exe", mod),
	      "a '..' segment never counts as inside");
	Check(mxl::PathIsOrUnder("c:/program files (x86)/diablo ii resurrected/MODS/MXL2012/x", mod), "case and separators");

	// the marker
	std::string m = mxl::MakeMarker("id1", "0.70.0");
	Check(mxl::CheckMarker(m, "id1") == mxl::MarkerVerdict::Ours, "our marker, our id");
	Check(mxl::CheckMarker(m, "") == mxl::MarkerVerdict::Ours, "our marker, no id in the state yet");
	Check(mxl::CheckMarker(m, "id2") == mxl::MarkerVerdict::OtherId, "our marker, another state");
	Check(mxl::CheckMarker("", "id1") == mxl::MarkerVerdict::None, "no marker: not ours");
	Check(mxl::CheckMarker("{nope", "id1") == mxl::MarkerVerdict::Unreadable, "damaged marker");
	Check(mxl::CheckMarker(R"({"made_by": "another installer", "id": "id1"})", "id1") == mxl::MarkerVerdict::Unreadable,
	      "another program's marker is not ours");
	Check(mxl::CheckMarker(R"({"made_by": "D2R-XL 2012 Downloader"})", "id1") == mxl::MarkerVerdict::Unreadable, "marker without id");
	mxl::Json j;
	std::string err;
	Check(mxl::Json::Parse(m, j, err) && j["made_by"].Str() == mxl::MarkerMadeBy && j["version"].Str() == "0.70.0", "marker content");

	// the plan never deletes the marker or the downloads in progress
	mxl::Manifest next;
	mxl::ParseManifest(ManifestText(F("a.txt", H1)), next, err);
	std::vector<std::string> local = {"a.txt", mxl::InstallMarkerName, std::string(mxl::DownloadFolderName) + "/" + H2 + ".part",
	                                  std::string(mxl::DownloadFolderName) + "/7z/a.txt", "old.txt"};
	mxl::InstallPlan plan = mxl::PlanInstall(next, local, [](const std::string& p) { return p == "a.txt" ? H1 : std::string(); });
	Check(plan.remove.size() == 1 && plan.remove[0] == "old.txt" && plan.fetch.empty(), "marker and mxl2012-download/ kept, old.txt removed");

	// D2RLoader's version
	Check(mxl::LoaderVersionMatches("1.3.1-beta", "1.3.1-beta") && mxl::LoaderVersionMatches("1.3.1", "1.3.1-beta") &&
	          mxl::LoaderVersionMatches("1.3.1.0", "1.3.1-beta"),
	      "D2RLoader 1.3.1 matches");
	Check(!mxl::LoaderVersionMatches("1.3.0", "1.3.1-beta") && !mxl::LoaderVersionMatches("1.4.0", "1.3.1-beta") &&
	          !mxl::LoaderVersionMatches("", "1.3.1-beta") && !mxl::LoaderVersionMatches("1.3.1.2", "1.3.1-beta") &&
	          !mxl::LoaderVersionMatches("unknown version", "1.3.1-beta"),
	      "other D2RLoader versions do not");
}

// A ByteSource over memory, for the damaged-archive cases.
class MemSource : public mxl::ByteSource {
public:
	explicit MemSource(std::string d) : d_(std::move(d)) {}
	bool Read(void* buf, size_t& size) override {
		size = std::min(size, d_.size() - size_t(pos_));
		std::memcpy(buf, d_.data() + pos_, size);
		pos_ += int64_t(size);
		return true;
	}
	bool Seek(int64_t& pos, int origin) override {
		int64_t base = origin == 0 ? 0 : origin == 1 ? pos_ : int64_t(d_.size());
		if (base + pos < 0 || base + pos > int64_t(d_.size()))
			return false;
		pos_ = pos = base + pos;
		return true;
	}

private:
	std::string d_;
	int64_t pos_ = 0;
};

std::string ReadAll(const std::string& path) {
	std::ifstream f(path, std::ios::binary);
	std::stringstream ss;
	ss << f.rdbuf();
	return ss.str();
}

// Extract everything; out: path -> sha256 (directories: "dir").
bool Unpack(mxl::ByteSource& src, std::map<std::string, std::string>& out, std::string& err, mxl::SevenZipStats* stats = nullptr,
            size_t skip = SIZE_MAX) {
	mxl::SevenZipArchive a;
	if (!a.Open(src, err))
		return false;
	mxl::Sha256 h;
	std::string cur;
	mxl::SevenZipArchive::Sink s;
	s.begin = [&](size_t i) {
		const auto& e = a.entries()[i];
		if (e.dir) {
			out[e.path] = "dir";
			return false;
		}
		if (i == skip)
			return false;
		h = mxl::Sha256();
		cur = e.path;
		return true;
	};
	s.data = [&](const uint8_t* p, size_t n) {
		h.Update(p, n);
		return true;
	};
	s.end = [&](size_t i) {
		if (i != skip && !a.entries()[i].dir)
			out[cur] = h.HexDigest();
		return true;
	};
	s.progress = [](uint64_t) { return true; };
	return a.Extract(s, err, stats);
}

// tests/data/sample.7z: made by tests/data/make_sample_7z.py with the release's 7-Zip switches (solid LZMA2, and a BCJ
// block for the .dll); sample.json lists its files with their sha256.
void TestSevenZip() {
	const std::string dir = MXL_TEST_DATA;
	std::string archive = ReadAll(dir + "/sample.7z"), listing = ReadAll(dir + "/sample.json"), err;
	mxl::Json want;
	Check(!archive.empty() && mxl::Json::Parse(listing, want, err) && want["files"].size() >= 7, "sample.7z and sample.json present");
	MemSource src(archive);
	std::map<std::string, std::string> got;
	mxl::SevenZipStats stats;
	Check(Unpack(src, got, err, &stats), ("sample.7z extracts: " + err).c_str());
	size_t same = 0;
	for (const auto& f : want["files"].items())
		same += got["mxl2012/" + f["path"].Str()] == f["sha256"].Str();
	Check(same == want["files"].size(), "every file's sha256 matches sample.json");
	Check(got["mxl2012/d2rloader/patches"] == "dir", "the empty folder is listed");
	Check(got.count("mxl2012/mxl2012.mpq/data/empty.txt") && got["mxl2012/mxl2012.mpq/data/empty.txt"] == mxl::Sha256Hex("", 0), "empty file");
	Check(got.count("mxl2012/modinfo.json"), "UTF-8 content, plain name");
	Check(stats.streamedBlocks >= 1 && stats.memoryBlocks >= 1, "a streamed LZMA2 block and an in-memory BCJ block");
	Check(stats.peakBuffer > 0 && stats.peakBuffer <= (64u << 20), "decode buffers stay small for a small dictionary");

	{  // a skipped file's bytes are decoded but not handed out; the rest still checks
		MemSource s2(archive);
		std::map<std::string, std::string> part;
		mxl::SevenZipArchive probe;
		MemSource s3(archive);
		probe.Open(s3, err);
		size_t big = 0;
		for (size_t i = 0; i < probe.entries().size(); ++i)
			if (probe.entries()[i].path.find("big.txt") != std::string::npos)
				big = i;
		Check(Unpack(s2, part, err, nullptr, big) && !part.count("mxl2012/mxl2012.mpq/data/global/excel/big.txt") &&
		          part["mxl2012/modinfo.json"] == got["mxl2012/modinfo.json"],
		      "skipping a file");
	}
	{  // one flipped byte in the packed data: refused (CRC or LZMA error)
		std::string bad = archive;
		bad[64] = char(bad[64] ^ 0x5a);
		MemSource s2(bad);
		std::map<std::string, std::string> x;
		Check(!Unpack(s2, x, err), "a damaged archive is refused");
	}
	{  // cut short: the header at the end is missing
		MemSource s2(archive.substr(0, archive.size() / 2));
		std::map<std::string, std::string> x;
		Check(!Unpack(s2, x, err), "a truncated archive is refused");
	}
	{
		MemSource s2("not a 7z archive at all");
		std::map<std::string, std::string> x;
		Check(!Unpack(s2, x, err), "junk is refused");
	}
}

// docs/launcher.md "Coexisting with the official Median XL": the default folders never land in the official one's.
void TestGameProcessName() {
	Check(mxl::IsGameProcessName("D2R.exe"), "D2R.exe is the game");
	Check(mxl::IsGameProcessName(R"(C:\Program Files (x86)\Diablo II Resurrected\d2r.EXE)"), "full path, any case");
	Check(mxl::IsGameProcessName("D2RLoader.exe"), "D2RLoader.exe is the game");
	Check(mxl::IsGameProcessName("D2RLoader-s2.exe"), "a slot's renamed loader is the game");
	Check(!mxl::IsGameProcessName("D2R-XL-2012-Downloader.exe"), "the downloader is not the game");
	Check(!mxl::IsGameProcessName("Diablo II Resurrected Launcher.exe"), "Battle.net's launcher is not the game");
	Check(!mxl::IsGameProcessName("BlizzardError.exe"), "the crash reporter is not the game");
	Check(!mxl::IsGameProcessName("D2R.exe.bak"), "not an exe name");
	Check(!mxl::IsGameProcessName(""), "empty");
}

void TestCoexist() {
	const std::string bs(1, char(92));
	const std::string local = "C:" + bs + "Users" + bs + "p" + bs + "AppData" + bs + "Local";
	const std::string roaming = "C:" + bs + "Users" + bs + "p" + bs + "AppData" + bs + "Roaming";
	std::string data = mxl::DefaultDataDir(local);
	Check(data == local + bs + "mxl2012", "data folder %LOCALAPPDATA%\\mxl2012");
	const std::string mod = mxl::ModTargetDir("C:" + bs + "Program Files (x86)" + bs + "Diablo II Resurrected", "mxl2012");
	for (const std::string& p : {data, mod, data + bs + "download"})
		Check(!mxl::OfficialMedianXLPath(p, local, roaming), "the downloader's folders are not the official Median XL's");
	Check(mxl::OfficialMedianXLPath(local + bs + "mxl-launcher", local, roaming) &&
	          mxl::OfficialMedianXLPath(local + bs + "MXL-Launcher" + bs + "game", local, roaming),
	      "the official launcher folder is refused");
	Check(mxl::OfficialMedianXLPath(roaming + "/MedianXL/save", local, roaming) && mxl::OfficialMedianXLPath(local + bs + "MedianXL", local, roaming),
	      "%APPDATA%\\MedianXL and %LOCALAPPDATA%\\MedianXL are refused");
	Check(mxl::OfficialMedianXLPath("C:" + bs + "Program Files (x86)" + bs + "Diablo II", local, roaming) &&
	          mxl::OfficialMedianXLPath("E:" + bs + "Games" + bs + "diablo ii" + bs + "mxl2012", local, roaming),
	      "a classic Diablo II folder is refused");
	Check(!mxl::OfficialMedianXLPath("C:" + bs + "Program Files (x86)" + bs + "Diablo II Resurrected", local, roaming) &&
	          !mxl::OfficialMedianXLPath(local + bs + "mxl-launcher-x", local, roaming) && !mxl::OfficialMedianXLPath(local + bs + "MedianXL2", local, roaming),
	      "similar names are not refused");
}

void TestToml() {
	std::string t = "# head\n[d2rloader]\n# Launch this mod automatically.\ndefault_mod = \"\"  # comment\ncheck_for_updates = true\n\n[d2rloader.backups]\nenabled = true\n";
	std::string u = mxl::SetTomlKey(t, "d2rloader", "default_mod", "\"mxl2012\"");
	Check(mxl::GetTomlKey(u, "d2rloader", "default_mod") == "\"mxl2012\"" && u.find("# comment") != std::string::npos, "replace keeps the comment");
	u = mxl::SetTomlKey(u, "d2rloader", "check_for_updates", "false");
	Check(mxl::GetTomlKey(u, "d2rloader", "check_for_updates") == "false", "replace a bool");
	Check(mxl::GetTomlKey(u, "d2rloader.backups", "enabled") == "true", "other section untouched");
	u = mxl::SetTomlKey(u, "d2rloader", "skip_title_screen", "true");
	Check(mxl::GetTomlKey(u, "d2rloader", "skip_title_screen") == "true" && mxl::GetTomlKey(u, "d2rloader.backups", "skip_title_screen").empty(),
	      "a missing key is added in its own section");
	u = mxl::SetTomlKey(u, "d2rcore.stash", "add_shared_tabs", "7");
	Check(mxl::GetTomlKey(u, "d2rcore.stash", "add_shared_tabs") == "7", "a missing section is appended");
	std::string c = "[a]\r\nx = 1\r\n";
	std::string cu = mxl::SetTomlKey(c, "a", "x", "2");
	Check(cu == "[a]\r\nx = 2\r\n", "CRLF kept");
	Check(mxl::SetTomlKey("[a]\nx = 1", "a", "x", "2") == "[a]\nx = 2", "no final newline stays without one");
	Check(mxl::SetTomlKey("[a]\n# x = 1\n", "a", "x", "2") == "[a]\nx = 2\n", "commented template replaced");
	Check(mxl::GetTomlKey("[a]\ns = \"a # b\" # c\n", "a", "s") == "\"a # b\"", "# inside quotes is no comment");
}

// docs/bugs.md #53: D2RLoader's default mod and stray copies of the plugin.
void TestEnvironment() {
	const std::string bs(1, char(92));
	std::string toml = "[d2rloader]\n# Launch this mod automatically.\ndefault_mod = \"MedianXL\"  # set by the gear\nlaunch_arguments = \"-w\"\n\n[d2rcore.stash]\nadd_shared_tabs = 3\n";
	mxl::DefaultModCheck c = mxl::CheckDefaultMod(toml, true, "mxl2012");
	Check(!c.ok && c.mod == "MedianXL" && !c.configMissing, "default_mod MedianXL is not ours");
	Check(mxl::DefaultModWarning(c, "mxl2012") == "D2RLoader starts the mod MedianXL, not mxl2012", "warning names the mod D2RLoader starts");
	std::string fixed = mxl::SetDefaultMod(toml, "mxl2012");
	Check(mxl::CheckDefaultMod(fixed, true, "mxl2012").ok, "fixed config names D2R-XL 2012");
	Check(fixed == "[d2rloader]\n# Launch this mod automatically.\ndefault_mod = \"mxl2012\" # set by the gear\nlaunch_arguments = \"-w\"\n\n[d2rcore.stash]\nadd_shared_tabs = 3\n",
	      "only default_mod changes");
	Check(mxl::CheckDefaultMod("[d2rloader]\ndefault_mod = 'MXL2012'\n", true, "mxl2012").ok, "single quotes, any case");
	Check(mxl::DefaultModWarning(mxl::CheckDefaultMod("[d2rloader]\ndefault_mod = \"mxl2012\"\n", true, "mxl2012"), "mxl2012").empty(), "no warning when ours");
	mxl::DefaultModCheck none = mxl::CheckDefaultMod("[d2rloader]\ndefault_mod = \"\"\n", true, "mxl2012");
	Check(!none.ok && none.mod.empty() && mxl::DefaultModWarning(none, "mxl2012").find("no default mod") != std::string::npos, "empty default_mod");
	Check(!mxl::CheckDefaultMod("[d2rloader]\n# default_mod = \"mxl2012\"\n", true, "mxl2012").ok, "a commented template is no default mod");
	Check(!mxl::CheckDefaultMod("[other]\ndefault_mod = \"mxl2012\"\n", true, "mxl2012").ok, "default_mod of another section does not count");
	mxl::DefaultModCheck missing = mxl::CheckDefaultMod("", false, "mxl2012");
	Check(!missing.ok && missing.configMissing && mxl::DefaultModWarning(missing, "mxl2012").find("no settings file") != std::string::npos, "no config file");
	Check(mxl::CheckDefaultMod(mxl::SetDefaultMod("", "mxl2012"), true, "mxl2012").ok, "a missing config gets the section and key");
	std::string bom = "\xEF\xBB\xBF[d2rloader]\r\ndefault_mod = \"Old\"\r\n";
	Check(!mxl::CheckDefaultMod(bom, true, "mxl2012").ok && mxl::CheckDefaultMod(bom, true, "mxl2012").mod == "Old", "a BOM before the section");
	Check(mxl::SetDefaultMod(bom, "mxl2012") == "\xEF\xBB\xBF[d2rloader]\r\ndefault_mod = \"mxl2012\"\r\n", "BOM and CRLF kept");
	Check(mxl::TomlUnquote(" \"a b\" ") == "a b" && mxl::TomlUnquote("x") == "x" && mxl::TomlUnquote("\"") == "\"", "TomlUnquote");

	Check(mxl::IsOurPluginFile("mxl2012-core.dll", "", "") && mxl::IsOurPluginFile("MXL2012-Core-0.68.dll", "", "") && mxl::IsOurPluginFile("mxl2012-core (1).dll", "", ""),
	      "plugin by file name");
	Check(mxl::IsOurPluginFile("renamed.dll", "D2R-XL 2012", "") && mxl::IsOurPluginFile("x.dll", "", "D2R-XL 2012 core plugin (mxl2012-core)"), "plugin by version resource");
	Check(!mxl::IsOurPluginFile("loot.dll", "Loot Filter", "Loot filter plugin") && !mxl::IsOurPluginFile("mxl2012-core.txt", "", "") &&
	          !mxl::IsOurPluginFile("mxl2012-core-off.txt", "", "") && !mxl::IsOurPluginFile("D2R-XL-2012-Downloader.exe", "mxl2012", ""),
	      "other plugins, text files and exes are not ours");

	mxl::DefaultModCheck prior = mxl::CheckDefaultMod("[d2rloader]\ndefault_mod = \"PriorMod\"\n", true, "mxl2012");
	Check(!prior.ok && mxl::DefaultModWarning(prior, "mxl2012") == "D2RLoader starts the mod PriorMod, not mxl2012",
	      "another mod warns by name");
	Check(mxl::IsOurPluginFile("renamed.dll", "mxl2012", ""), "current plugin ProductName");
	Check(!mxl::IsOurPluginFile("other-core.dll", "PriorMod", "PriorMod core plugin (other-core)"), "another mod's plugin is not ours");
	const uint32_t protectedMods[] = {mxl::NameHash("priormod")};
	Check(mxl::IsProtectedModFolder("PriorMod", protectedMods, 1) && !mxl::IsProtectedModFolder("Other", protectedMods, 1) &&
	          !mxl::IsProtectedModFolder("mxl2012") && !mxl::IsProtectedModFolder("Other"),
	      "protected mod folders by name hash, any case; ours and plain others are not");
	Check(mxl::NameHash("Other-Core.DLL") == 0x5089ea3du, "FNV-1a of the lowercased name");
	Check(mxl::CanMoveStrayPlugin(mxl::PluginPlace::OtherMod, "Other") && mxl::CanMoveStrayPlugin(mxl::PluginPlace::GameWide, ""),
	      "other stray copies can be moved");
	Check(mxl::PluginPlaceOf("mods/PriorMod/d2rloader/plugins/mxl2012-core.dll", "mxl2012") == mxl::PluginPlace::OtherMod,
	      "a copy in another mod still produces the other-mod warning");

	std::string mod;
	Check(mxl::PluginPlaceOf("d2rloader" + bs + "plugins" + bs + "mxl2012-core.dll", "mxl2012") == mxl::PluginPlace::GameWide, "game-wide plugins folder");
	Check(mxl::PluginPlaceOf("mods/MedianXL/d2rloader/plugins/mxl2012-core.dll", "mxl2012", &mod) == mxl::PluginPlace::OtherMod && mod == "MedianXL",
	      "another mod's plugins folder, its name as written");
	Check(mxl::PluginPlaceOf("MODS" + bs + "MXL2012" + bs + "D2RLoader" + bs + "Plugins" + bs + "mxl2012-core.dll", "mxl2012") == mxl::PluginPlace::OurMod,
	      "our own mod folder, any case");
	Check(mxl::PluginPlaceOf("mods/mxl2012/mxl2012-core.dll", "mxl2012") == mxl::PluginPlace::None && mxl::PluginPlaceOf("mxl2012-core.dll", "mxl2012") == mxl::PluginPlace::None &&
	          mxl::PluginPlaceOf("mods/../d2rloader/plugins/x.dll", "mxl2012") == mxl::PluginPlace::None,
	      "not a plugins folder");
	std::string g = mxl::StrayPluginWarning("C:" + bs + "D2R" + bs + "d2rloader" + bs + "plugins" + bs + "mxl2012-core.dll", mxl::PluginPlace::GameWide, "");
	Check(g == "An old copy of the D2R-XL 2012 plugin is in C:" + bs + "D2R" + bs + "d2rloader" + bs + "plugins" + bs + "mxl2012-core.dll: it loads with every mod. Move it away.",
	      "game-wide warning text");
	Check(mxl::StrayPluginWarning("p", mxl::PluginPlace::OtherMod, "MedianXL").find("starts the mod MedianXL") != std::string::npos &&
	          mxl::StrayPluginWarning("p", mxl::PluginPlace::OtherMod, "MedianXL", true) == "Old D2R-XL 2012 plugin in mods" + bs + "MedianXL: it loads with that mod",
	      "other-mod warning, long and brief");
	Check(mxl::StrayPluginWarning("p", mxl::PluginPlace::OurMod, "mxl2012").empty() && mxl::StrayPluginWarning("p", mxl::PluginPlace::None, "").empty(),
	      "no warning for the installed plugin");
	Check(mxl::RemovedPluginPath("C:" + bs + "L" + bs + "mxl2012", "2026-10-27", "d2rloader/plugins/mxl2012-core.dll") ==
	          "C:" + bs + "L" + bs + "mxl2012" + bs + "removed" + bs + "2026-10-27" + bs + "d2rloader" + bs + "plugins" + bs + "mxl2012-core.dll",
	      "moved under removed, date, relative path");
}

bool Near(float a, float b) { return a - b < 0.001f && b - a < 0.001f; }

void TestSvg() {
	std::vector<mxl::PathCmd> p;
	std::string e;
	Check(mxl::ParseSvgPath("M10 20l5-5h3v-2zm1,1", p, e) && p.size() == 6, "path: commands");
	Check(p[1].op == 'L' && Near(p[1].p[0], 15) && Near(p[1].p[1], 15), "relative line");
	Check(Near(p[2].p[0], 18) && Near(p[2].p[1], 15) && Near(p[3].p[1], 13), "h and v");
	Check(p[4].op == 'Z' && p[5].op == 'M' && Near(p[5].p[0], 11) && Near(p[5].p[1], 21), "move after close starts at the subpath start");
	p.clear();
	Check(mxl::ParseSvgPath("M0 0 1.5.5-2-3", p, e) && p.size() == 3 && Near(p[1].p[0], 1.5f) && Near(p[1].p[1], 0.5f) &&
	          Near(p[2].p[0], -2) && Near(p[2].p[1], -3), "numbers run together; pairs after M are lines");
	p.clear();
	Check(mxl::ParseSvgPath("M0 0c1 2 3 4 5 6s7 8 9 10", p, e) && p.size() == 3 && p[2].op == 'C' && Near(p[2].p[0], 7) && Near(p[2].p[1], 8) &&
	          Near(p[2].p[4], 14) && Near(p[2].p[5], 16), "s reflects the last control point");
	p.clear();
	Check(mxl::ParseSvgPath("M0 0Q3 3 6 0", p, e) && p[1].op == 'C' && Near(p[1].p[0], 2) && Near(p[1].p[1], 2) && Near(p[1].p[4], 6),
	      "q becomes a cubic");
	p.clear();
	Check(mxl::ParseSvgPath("M1e1 2E-1L.5 .5", p, e) && Near(p[0].p[0], 10) && Near(p[0].p[1], 0.2f), "exponents");
	Check(!mxl::ParseSvgPath("M0 0A1 1 0 0 1 2 2", p, e), "arcs refused");
	Check(!mxl::ParseSvgPath("M0 0L1", p, e), "missing number refused");
	Check(!mxl::ParseSvgPath("5 5", p, e), "number without a command refused");
	mxl::SvgIcon icon;
	Check(mxl::ParseSvgIcon("<svg xmlns=\"x\" viewBox=\"0 0 448 512\"><!-- c --><path d=\"M0 0h1v1z\"/><path d='M2 2h1z'/></svg>", icon, e) &&
	          Near(icon.viewBox[2], 448) && icon.path.size() == 7, "icon: viewBox and every path");
	Check(!mxl::ParseSvgIcon("<svg><path d=\"M0 0\"/></svg>", icon, e), "icon without viewBox refused");
	for (const char* name : {"comment.svg"}) {  // the icons the window embeds (launcher/res)
		std::ifstream f(std::string(MXL_RES_DIR) + "/" + name, std::ios::binary);
		std::stringstream ss;
		ss << f.rdbuf();
		Check(mxl::ParseSvgIcon(ss.str(), icon, e) && icon.path.size() > 3, name);
	}
}

}  // namespace

int main() {
	TestSha256();
	TestJson();
	TestSafePath();
	TestManifest();
	TestHosting();
	TestPlan();
	TestVersions();
	TestDetect();
	TestPaths();
	TestSevenZip();
	TestCoexist();
	TestGameProcessName();
	TestToml();
	TestEnvironment();
	TestSvg();
	std::printf("%d checks, %d failures\n", checks, failures);
	return failures ? 1 : 0;
}

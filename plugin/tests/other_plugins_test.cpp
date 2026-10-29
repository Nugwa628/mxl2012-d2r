// Standalone test of the `other plugins` labels (other_plugins_logic.h; not part of the plugin DLL).
#include "../src/other_plugins_logic.h"

#include <cstdio>
#include <cstring>

namespace {
int failures = 0;
void Check(bool ok, const char* what) {
	if (!ok) {
		++failures;
		std::printf("FAIL: %s\n", what);
	}
}
auto LabelOf(const char* path) -> const char* {
	static char buf[128];
	return other_plugins::Label(path, buf, sizeof(buf)) ? buf : "-";
}
}  // namespace

int main() {
	Check(std::strcmp(LabelOf("D:\\D2R\\mods\\MedianXL\\d2rloader\\plugins\\mxl2012-core.dll"), "mxl2012-core.dll (mod MedianXL)") == 0, "mod plugin");
	Check(std::strcmp(LabelOf("C:\\Program Files (x86)\\Diablo II Resurrected\\d2rloader\\plugins\\loot.dll"), "loot.dll (global)") == 0, "global plugin");
	Check(std::strcmp(LabelOf("D:/D2R/MODS/Other/D2RLoader/Plugins/x.dll"), "x.dll (mod Other)") == 0, "any case, forward slashes");
	Check(std::strcmp(LabelOf("D:\\D2R\\mods\\A\\d2rloader\\plugins\\sub\\y.dll"), "y.dll (mod A)") == 0, "a sub folder of plugins");
	Check(std::strcmp(LabelOf("C:\\Windows\\System32\\kernel32.dll"), "-") == 0, "a system module is no plugin");
	Check(std::strcmp(LabelOf("D:\\D2R\\D2RCore.dll"), "-") == 0, "D2RLoader's own core is no plugin");
	Check(std::strcmp(LabelOf("D:\\d2rloader\\plugins\\z.dll"), "z.dll (global)") == 0, "game folder at the drive root");
	Check(!other_plugins::Label(nullptr, nullptr, 0), "no path");

	// Plugin guard: a conflicting plugin by its PluginInfo id or its file name (name hashes); never mxl2012-core itself.
	using other_plugins::IsConflictingPlugin;
	using other_plugins::NameHash;
	Check(sizeof(other_plugins::ConflictingPluginIds) > 0 && sizeof(other_plugins::ConflictingFiles) > 0, "built-in list not empty");
	Check(NameHash("other-core") == 0xb754bd07u && NameHash("Other-Core.DLL") == 0x5089ea3du, "FNV-1a of the lowercased name");
	Check(!IsConflictingPlugin("mxl2012-core.dll", "mxl2012-core"), "our own plugin never conflicts");
	Check(!IsConflictingPlugin("loot.dll", "loot"), "another plugin");
	Check(!IsConflictingPlugin(nullptr, nullptr), "nothing");
	const unsigned ids[] = {NameHash("other-core")};
	const unsigned files[] = {NameHash("other-core.dll")};
	const auto test = [&](const char* file, const char* id) { return IsConflictingPlugin(file, id, ids, 1, files, 1); };
	Check(test("other-core.dll", "other-core"), "by file and id");
	Check(test("renamed.dll", "other-core"), "by id under another file name");
	Check(test("OTHER-Core.DLL", nullptr), "by file name, any case, no plugin info");
	Check(!test("mxl2012-core.dll", "mxl2012-core"), "our own plugin is not it");
	Check(!test("other-core-old.dll", nullptr), "another file name without the id");
	Check(!test("other-core.dll.bak", nullptr), "a renamed-away copy is not loaded by D2RLoader");
	Check(!test(nullptr, nullptr), "nothing (test list)");
	char notice[256];
	other_plugins::ConflictNotice(notice, sizeof(notice), "0.1.0", "other-core.dll", "d2rloader\\plugins");
	Check(std::strcmp(notice, "D2R-XL 2012 0.1.0: another plugin (other-core.dll) writes the same engine slots; remove it from d2rloader\\plugins. The mod's engine changes are off.") == 0,
	      "conflict notice");
	other_plugins::ConflictNotice(notice, sizeof(notice), "0.1.0", nullptr, nullptr);
	Check(std::strstr(notice, "(unknown)") != nullptr && std::strstr(notice, "from d2rloader\\plugins.") != nullptr,
	      "conflict notice defaults: unknown file, the game-wide folder");
	other_plugins::ConflictNotice(nullptr, 0, "0.1.0", nullptr, nullptr);  // must not write
	if (failures == 0) {
		std::printf("other plugins: all checks passed\n");
	}
	return failures == 0 ? 0 : 1;
}

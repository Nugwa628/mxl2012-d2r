// Standalone test of the image guard (image_guard_logic.h; not part of the plugin DLL). With env D2R_DUMP set to a
// memory-layout dump of the image (file offset == RVA, tools/dump_image.py) it also checks the probes against the dump.
#include "../src/image_guard_logic.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

namespace {
int failures = 0;
void Check(bool ok, const char* what) {
	if (!ok) {
		++failures;
		std::printf("FAIL: %s\n", what);
	}
}
auto HasDigitRun(const char* s, int run) -> bool {
	int n = 0;
	for (; *s != '\0'; ++s) {
		n = (*s >= '0' && *s <= '9') ? n + 1 : 0;
		if (n >= run) {
			return true;
		}
	}
	return false;
}
// An image with the probes' bytes at their places and zeroes elsewhere.
auto KnownImage() -> std::vector<uint8_t> {
	uint32_t top = 0;
	for (const auto& p : image_guard::Probes) {
		top = p.rva + sizeof(p.bytes) > top ? p.rva + static_cast<uint32_t>(sizeof(p.bytes)) : top;
	}
	std::vector<uint8_t> image(top + 0x1000);
	for (const auto& p : image_guard::Probes) {
		std::memcpy(image.data() + p.rva, p.bytes, sizeof(p.bytes));
	}
	return image;
}
}  // namespace

int main() {
	using namespace image_guard;
	const std::vector<uint8_t> known = KnownImage();
	auto game = [&](uint32_t stamp, const char* version, const char* name) {
		Running g;
		g.stamp = stamp;
		g.image = known.data();
		g.imageSize = known.size();
		g.buildVersion = version;
		g.buildName = name;
		return g;
	};

	// The same image installs whatever the game's version and build name are: nothing compares them.
	Check(Supported(game(0x6ab3782cU, "3.3.0", "93847")), "the image on D2R 3.3 (build name 93847): parts install");
	Check(Supported(game(0x6ab3782cU, "3.4.0", "95032")), "the image on D2R 3.4 (build name 95032): parts install");
	Check(Supported(game(0x6ab3782cU, "3.4.0", "")), "the image, empty build name: parts install");
	Check(Supported(game(0x6ab3782cU, nullptr, nullptr)), "the image, no version and no build name: parts install");
	Check(Supported(game(0x6ab3782cU, "9.9.9", "123456")), "the image, a made-up version and build name: parts install");
	Check(Supported(game(0x6ab3782cU, "", "not a number")), "the image, a build name that is no number: parts install");

	// Another image installs nothing, whatever names come with it.
	Check(Decide(game(0x6ab3782dU, "3.3.0", "93847")) == Verdict::OtherStamp, "another stamp with build name 93847: nothing installed");
	Check(Decide(game(0x6ad81202U, "3.4.0", "95032")) == Verdict::OtherStamp, "another stamp with build name 95032: nothing installed");
	Check(Decide(game(0x6b000000U, nullptr, nullptr)) == Verdict::OtherStamp, "another stamp without names: nothing installed");
	Running none = game(0x6ab3782cU, "3.3.0", "93847");
	none.image = nullptr;
	Check(Decide(none) == Verdict::NoImage && !Supported(none), "no image (exe base 0): nothing installed");
	Running zero;
	Check(Decide(zero) == Verdict::NoImage, "an empty description: nothing installed");

	// The gate is about content too: the known stamp over other code installs nothing.
	for (int i = 0; i < ProbeCount; ++i) {
		std::vector<uint8_t> other = known;
		other[Probes[i].rva + sizeof(Probes[i].bytes) - 1] ^= 0x01;
		Running g = game(0x6ab3782cU, "3.3.0", "93847");
		g.image = other.data();
		Check(Decide(g) == Verdict::OtherContent && FirstBadProbe(other.data(), other.size()) == i, "one changed byte in a probe: nothing installed");
		// the 16 bytes before a probe are the function's entry: another plugin's jump there leaves the gate alone
		other = known;
		std::memset(other.data() + Probes[i].rva - 16, 0xe9, 16);
		Check(FirstBadProbe(other.data(), other.size()) < 0, "a hook at the function's entry does not trip the gate");
	}
	Running cut = game(0x6ab3782cU, "3.3.0", "93847");
	cut.imageSize = Probes[0].rva + 4;
	Check(Decide(cut) == Verdict::OtherContent, "an image too small for a probe: nothing installed, nothing read past it");
	Check(FirstBadProbe(nullptr, 0x10000000) == 0, "no image: the first probe fails");

	// The player's text: no game version, no build number, no stamp; it names D2RLoader.
	char text[256];
	Message(text, sizeof(text), "0.1.0");
	Check(std::strcmp(text, "D2R-XL 2012 0.1.0: this D2RLoader version is not supported by the mod yet. The mod's engine changes are off.") == 0,
	      "screen text");
	Check(std::strstr(text, "needs") == nullptr && std::strstr(text, "3.3") == nullptr && std::strstr(text, "3.4") == nullptr,
	      "screen text names no game version");
	Check(!HasDigitRun(text, 5), "screen text has no build number (no run of 5 digits)");
	Check(std::strstr(text, "0x") == nullptr && std::strstr(text, "6ab3782c") == nullptr, "screen text has no image stamp");

	// The log line: found and expected image; version and build name as information.
	char log[320];
	LogDetail(log, sizeof(log), game(0x6b000000U, "3.5.0", "96000"));
	Check(std::strstr(log, "game image 0x6b000000: another image; the addresses are for image 0x6ab3782c") != nullptr, "log line: found and expected image");
	Check(std::strstr(log, "not compared: D2R 3.5.0, build name 96000") != nullptr, "log line: version and build name as information");
	LogDetail(log, sizeof(log), game(0x6b000000U, nullptr, nullptr));
	Check(std::strstr(log, "D2R ?, build name (none)") != nullptr, "log line without version and build name");
	{
		std::vector<uint8_t> other = known;
		other[Probes[2].rva] ^= 0xff;
		Running g = game(0x6ab3782cU, "3.3.0", "93847");
		g.image = other.data();
		LogDetail(log, sizeof(log), g);
		Check(std::strstr(log, "the known stamp, other code at CreateMissile (0x5371b0)") != nullptr, "log line: which probe differs");
	}
	LogDetail(log, sizeof(log), none);
	Check(std::strstr(log, "no game image") != nullptr, "log line without an image");
	LogDetail(log, sizeof(log), game(0x6ab3782cU, "3.4.0", "95032"));
	Check(std::strstr(log, "game image 0x6ab3782c: supported") != nullptr, "log line on the supported image");

	char small[16];
	Message(small, sizeof(small), "0.1.0");
	Check(std::strlen(small) == sizeof(small) - 1, "message is cut to the buffer");
	Message(nullptr, 0, "0.1.0");      // must not write
	LogDetail(nullptr, 0, Running{});  // must not write

	// The real image, when a dump is at hand: stamp and every probe.
	if (const char* path = std::getenv("D2R_DUMP"); path == nullptr || path[0] == '\0') {
		std::printf("image guard tests: D2R_DUMP not set, the dump check is skipped\n");
	} else if (std::FILE* f = std::fopen(path, "rb"); f == nullptr) {
		Check(false, "D2R_DUMP cannot be opened");
	} else {
		uint32_t top = 0;
		for (const auto& p : Probes) {
			top = p.rva + sizeof(p.bytes) > top ? p.rva + static_cast<uint32_t>(sizeof(p.bytes)) : top;
		}
		std::vector<uint8_t> dump(top);
		const bool read = std::fread(dump.data(), 1, dump.size(), f) == dump.size();
		std::fclose(f);
		Check(read, "D2R_DUMP holds the probed range");
		if (read) {
			uint32_t lfanew = 0;
			uint32_t stamp = 0;
			std::memcpy(&lfanew, dump.data() + 0x3c, 4);
			std::memcpy(&stamp, dump.data() + lfanew + 8, 4);
			Running g;
			g.stamp = stamp;
			g.image = dump.data();
			g.imageSize = dump.size();
			Check(Decide(g) == Verdict::Supported, "the dump is the supported image: stamp and all probes");
			std::printf("image guard tests: dump checked (stamp 0x%08x, %d probes)\n", static_cast<unsigned>(stamp), ProbeCount);
		}
	}

	if (failures == 0) {
		std::printf("image guard tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}

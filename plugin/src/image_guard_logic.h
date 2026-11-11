// Which game image the plugin's fixed addresses belong to (mxl2012_core.cpp; unit test plugin/tests/image_guard_test.cpp).
//
// Rule: the plugin is never tied to a game build or version. A part installs when the code it needs is what it expects, and
// turns itself off with a log line when it is not. Every inline hook and byte patch carries its own expected bytes. The
// addresses that are only called or read have no such bytes, so one check of the running image itself stands in front of
// them: the image the addresses were taken from (the game program D2RLoader 1.3.1 runs, PE time stamp 0x6ab3782c) and a few
// expected bytes inside key functions the plugin calls. The game's version and the build name D2RLoader reports are
// never compared; they are logged for diagnosis only. D2RLoader 1.3.1 runs this one image on D2R 3.3 and on D2R 3.4
// (docs/port-3.4.md section 3.3). On another image the plugin installs nothing and says so: in the log, on the screen
// (D2RLoader's overlay) and in the `mxl2012` command (docs/plugin-plan.md 1.2).
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace image_guard {

constexpr uint32_t ExpectedImage = 0x6ab3782cU;  // TimeDateStamp of the dumped image (the game program in D2RLoader 1.3.1)

// Expected bytes inside functions the plugin calls at fixed addresses (d2r.h). Each probe starts 16 bytes after the
// function's entry, so a jump another plugin writes at the entry does not change it.
struct Probe {
	uint32_t rva;
	uint8_t bytes[12];
	const char* name;
};
constexpr Probe Probes[] = {
	{0x97790 + 0x10, {0x63, 0xf2, 0xe8, 0xe9, 0x92, 0x26, 0x00, 0x48, 0x8b, 0xf8, 0x48, 0x8b}, "GetSkillRecord"},
	{0x3b5160 + 0x10, {0x41, 0x56, 0x41, 0x57, 0x48, 0x81, 0xec, 0xb0, 0x00, 0x00, 0x00, 0x45}, "EvalSkillCalc"},
	{0x5371a0 + 0x10, {0x00, 0x48, 0x8b, 0x05, 0x10, 0x41, 0x49, 0x02, 0x48, 0x33, 0xc4, 0x48}, "CreateMissile"},
	{0x166040 + 0x10, {0x78, 0x4e, 0x48, 0x8b, 0xcb, 0x48, 0x3b, 0x98, 0x28, 0x11, 0x00, 0x00}, "MissileRecord"},
	{0x34a0e0 + 0x10, {0x24, 0x30, 0xe8, 0x49, 0xc7, 0xff, 0xff, 0x84, 0xc0, 0x74, 0x01, 0xcc}, "UnitDataFlag"},
};
constexpr int ProbeCount = static_cast<int>(sizeof(Probes) / sizeof(Probes[0]));

// What the plugin knows about the running game. `image` is the mapped image (null when D2RLoader gave no exe base),
// `imageSize` its SizeOfImage. buildVersion and buildName are D2RLoader's words for the game; nothing compares them.
struct Running {
	uint32_t stamp = 0;
	const uint8_t* image = nullptr;
	uint64_t imageSize = 0;
	const char* buildVersion = nullptr;
	const char* buildName = nullptr;
};

enum class Verdict {
	Supported,     // the image the addresses were taken from
	NoImage,       // no exe base
	OtherStamp,    // another image
	OtherContent,  // the stamp of the known image, other code at a probe
};

// The first probe whose bytes differ (or that lies outside the image), -1 when all agree.
inline auto FirstBadProbe(const uint8_t* image, uint64_t imageSize) noexcept -> int {
	for (int i = 0; i < ProbeCount; ++i) {
		const Probe& p = Probes[i];
		if (image == nullptr || uint64_t{p.rva} + sizeof(p.bytes) > imageSize || std::memcmp(image + p.rva, p.bytes, sizeof(p.bytes)) != 0) {
			return i;
		}
	}
	return -1;
}

// The gate for everything that uses an address without its own expected bytes.
inline auto Decide(const Running& game) noexcept -> Verdict {
	if (game.image == nullptr) {
		return Verdict::NoImage;
	}
	if (game.stamp != ExpectedImage) {
		return Verdict::OtherStamp;
	}
	return FirstBadProbe(game.image, game.imageSize) < 0 ? Verdict::Supported : Verdict::OtherContent;
}

inline auto Supported(const Running& game) noexcept -> bool {
	return Decide(game) == Verdict::Supported;
}

// The screen / console text on another image:
// "D2R-XL 2012 0.1.0: this D2RLoader version is not supported by the mod yet. The mod's engine changes are off."
inline void Message(char* out, size_t outSize, const char* pluginVersion) noexcept {
	if (out == nullptr || outSize == 0) {
		return;
	}
	std::snprintf(out, outSize, "D2R-XL 2012 %s: this D2RLoader version is not supported by the mod yet. The mod's engine changes are off.",
	              pluginVersion != nullptr ? pluginVersion : "?");
}

// The log line for support (players send logs): what was found and what is expected. The game's version and build name
// are in it as information.
inline void LogDetail(char* out, size_t outSize, const Running& game) noexcept {
	if (out == nullptr || outSize == 0) {
		return;
	}
	const Verdict v = Decide(game);
	char why[96];
	if (v == Verdict::NoImage) {
		std::snprintf(why, sizeof(why), "no game image");
	} else if (v == Verdict::OtherStamp) {
		std::snprintf(why, sizeof(why), "another image");
	} else if (v == Verdict::OtherContent) {
		const int bad = FirstBadProbe(game.image, game.imageSize);
		std::snprintf(why, sizeof(why), "the known stamp, other code at %s (0x%x)", Probes[bad].name, static_cast<unsigned>(Probes[bad].rva));
	} else {
		std::snprintf(why, sizeof(why), "supported");
	}
	const bool named = game.buildName != nullptr && game.buildName[0] != '\0';
	const bool versioned = game.buildVersion != nullptr && game.buildVersion[0] != '\0';
	std::snprintf(out, outSize, "mxl2012-core: game image 0x%08x: %s; the addresses are for image 0x%08x. For information, not compared: D2R %.24s, build name %.40s",
	              static_cast<unsigned>(game.stamp), why, static_cast<unsigned>(ExpectedImage), versioned ? game.buildVersion : "?",
	              named ? game.buildName : "(none)");
}

}  // namespace image_guard

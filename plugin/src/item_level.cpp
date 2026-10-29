// Item levels above 99 kept by the item serializer (docs/bugs.md #251, off word ilvl).
//
// D2Common's item serializer clamps the item level to 99 before it writes the 7-bit field, so an item of Median XL 2012's
// level-100+ monsters came back at 99 after Save and Exit. The patch (item_level_logic.h) moves the clamp to 127, the field's
// maximum; the reader already takes 1-127. The whole clamp and the 7-bit write behind it are compared byte for byte first.
#include "item_level.h"

#include "item_level_logic.h"

#include <cstdio>
#include <cstring>

auto InstallItemLevel(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	const auto* base = reinterpret_cast<const uint8_t*>(context->exeBase);
	const bool same = std::memcmp(base + item_level::ExpectedRva, item_level::Expected, item_level::ExpectedSize) == 0 &&
	                  std::memcmp(base + item_level::MaskRva, item_level::Mask, sizeof(item_level::Mask)) == 0;
	const item_level::Bytes patch = item_level::PatchBytes(item_level::FieldMax);
	const bool ok = same && context->PatchBytes(item_level::PatchRva, item_level::Old, item_level::PatchSize, patch.b, sizeof(patch.b));
	std::snprintf(report, reportSize, "item levels 100-127 kept by the item serializer (clamp 99 -> 127 at 0x37d744)%s",
	              ok ? "" : (same ? " FAILED (patch refused)" : " FAILED (bytes differ, left as D2R: 99)"));
	return ok;
}

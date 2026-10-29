// Standalone test of the cube's second `useitem` output, pure part (cube_dupe_logic.h; not part of the plugin DLL).
#include "../src/cube_dupe_logic.h"

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

struct Record {
	uint8_t bytes[cube_dupe::RecordSize];
};

auto Make(uint8_t a, uint8_t b, uint8_t c) -> Record {
	Record r{};
	std::memset(r.bytes, 0, sizeof(r.bytes));
	const uint8_t s[] = {a, b, c};
	for (int i = 0; i < cube_dupe::Slots; ++i) {
		r.bytes[cube_dupe::SlotBase + cube_dupe::SlotSize * i + cube_dupe::SlotSpecial] = s[i];
	}
	return r;
}
}  // namespace

int main() {
	using namespace cube_dupe;
	// D2R's executor reads the special byte at r15 + 0x67 with r15 = record + 0x5b * slot; the record is 0x16c bytes
	Check(SlotBase + SlotSpecial == 0x67 && SlotSize == 0x5b && RecordSize == 0x16c, "slot layout of build 93847");
	Check(SlotBase + SlotSize * 2 + SlotSize <= RecordSize, "three slots fit the record");
	Check(UseItem == 0xfe, "useitem is 0xfe in both games");
	Check(ItemFlagIdentified == 0x10 && ItemFlagDupeSource == 0x8000000, "flags 0x527e52 / 0x43d8a0 set");

	Record dupe = Make(UseItem, UseItem, 0);  // Median's rows 8397-8420
	Check(ExtraCopies(dupe.bytes) == 1, "useitem a + useitem b: one copy");
	Record three = Make(UseItem, UseItem, UseItem);
	Check(ExtraCopies(three.bytes) == 2, "useitem in all three: two copies");
	Record onlyC = Make(UseItem, 0, UseItem);
	Check(ExtraCopies(onlyC.bytes) == 1, "useitem a + useitem c: one copy");
	Record single = Make(UseItem, 0, 0);
	Check(ExtraCopies(single.bytes) == 0, "a lone useitem (socket removal, rerolls): D2R's result");
	Record notA = Make(0xff, UseItem, 0);
	Check(ExtraCopies(notA.bytes) == 0, "output a usetype: the returned item is no copy source");
	Record cow = Make(1, 0, 0);
	Check(ExtraCopies(cow.bytes) == 0, "portal");
	Check(ExtraCopies(nullptr) == 0, "no record");

	Check(Pages[0].page == 3 && Pages[0].kind == 3 && Pages[1].page == 0 && Pages[1].kind == 0, "cube first, then the backpack");

	if (failures == 0) {
		std::printf("cube_dupe: all checks passed\n");
	}
	return failures == 0 ? 0 : 1;
}

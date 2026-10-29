// Standalone test of the pet-warp spread rule (pet_spread_logic.h; not part of the plugin DLL).
#include "../src/pet_spread_logic.h"

#include <cstddef>
#include <cstdio>
#include <cstdlib>

namespace {
int failures = 0;
void Check(bool ok, const char* what) {
	if (!ok) {
		++failures;
		std::printf("FAIL: %s\n", what);
	}
}
}  // namespace

int main() {
	using namespace pet_spread;
	// bug #493: the warp's fallbacks put the pet on the owner's sub-tile (or next to it): spread
	Check(OnOwner(5460, 5743, 5460, 5743), "a pet on the owner's sub-tile is spread");
	Check(OnOwner(5461, 5742, 5460, 5743), "a pet one sub-tile off is spread");
	// the warp's random first try put it elsewhere: left alone
	Check(!OnOwner(5463, 5743, 5460, 5743), "a pet 3 sub-tiles off is left where it is");
	Check(!OnOwner(5460, 5738, 5460, 5743), "a pet 5 sub-tiles off is left where it is");
	Check(Landed(5463, 5743, 5463, 5743) && Landed(5464, 5744, 5463, 5743) && !Landed(5460, 5743, 5463, 5743),
	      "a move counts as landed within one sub-tile of the asked spot");
	// the ring: 40 distinct spots, none within reach of OnOwner (a spread pet is never spread again), the first 8 at 3
	bool distinct = true, offOwner = true;
	for (int i = 0; i < RingSize; ++i) {
		offOwner = offOwner && !OnOwner(Ring[i].dx, Ring[i].dy, 0, 0);
		for (int j = i + 1; j < RingSize; ++j) {
			distinct = distinct && !(Ring[i].dx == Ring[j].dx && Ring[i].dy == Ring[j].dy);
		}
	}
	Check(RingSize == 40, "the ring has 40 spots");
	Check(distinct, "ring spots are distinct");
	Check(offOwner, "no ring spot is on the owner's spot");
	bool firstRing = true;
	for (int i = 0; i < 8; ++i) {
		firstRing = firstRing && std::abs(Ring[i].dx) <= 3 && std::abs(Ring[i].dy) <= 3 && (std::abs(Ring[i].dx) == 3 || std::abs(Ring[i].dy) == 3);
	}
	Check(firstRing, "the first 8 spots are the ring at 3 sub-tiles");
	// the spot test keeps the warp's own walls / objects / doors and adds player, monster and pet
	Check((SpotMask & 0x1c09) == 0x1c09 && (SpotMask & 0x0080) && (SpotMask & 0x0100) && (SpotMask & 0x2000), "spot mask");

	// spots of the same gather: a pet placed 1-2 sub-tiles away takes the spot, 3 away does not; every first-ring neighbour is 3 apart
	const Spot placed[] = {{5424, 4468}, {5421, 4471}};
	Check(Taken(5425, 4469, placed, 2) && Taken(5423, 4473, placed, 2), "a spot within 2 sub-tiles of a placed pet is taken");
	Check(!Taken(5427, 4468, placed, 2) && !Taken(5424, 4471, placed, 2) && !Taken(5424, 4468, placed, 0), "3 sub-tiles away is free");
	bool apart = true;
	for (int i = 0; i < 8; ++i) {
		const Spot here[] = {{Ring[i].dx, Ring[i].dy}};
		for (int j = 0; j < 8; ++j) {
			apart = apart && (i == j || !Taken(Ring[j].dx, Ring[j].dy, here, 1));
		}
	}
	Check(apart, "the 8 first-ring spots do not take each other");

	// only totems: the owner's `totemic` list (pettype row 34) decides; a node has the unit id at +4 and the next node at +0x18
	Check(TotemicPetType == 34, "totemic is pettype row 34");
	struct Node {
		uint32_t flags, id;
		uint8_t pad[0x10];
		const Node* next;
	};
	static_assert(offsetof(Node, id) == PetNodeUnitId && offsetof(Node, next) == PetNodeNext);
	const Node third {0, 77, {}, nullptr}, second {1, 52, {}, &third}, first {0, 40, {}, &second};
	const auto* head = reinterpret_cast<const uint8_t*>(&first);
	Check(Listed(head, 40) && Listed(head, 52) && Listed(head, 77), "every totem of the list is found");
	Check(!Listed(head, 41) && !Listed(nullptr, 40), "a mercenary / golem id or an empty list is no totem");
	Check(!Listed(head, 77, 2), "the walk stops at its limit");

	if (failures == 0) {
		std::printf("pet spread tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}
